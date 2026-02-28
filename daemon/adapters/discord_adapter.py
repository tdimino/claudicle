"""
Discord adapter for the Claudicle unified launcher.

Receives @mentions and DMs via discord.py Gateway, routes them to an async
callback. Mirrors the SlackAdapter interface for unified launcher compatibility.

Requires discord.py >= 2.6.4 and the Message Content privileged intent enabled
in the Discord Developer Portal.
"""

import asyncio
import collections
import json
import logging
import os
import re
import threading
from typing import Callable, Optional

import discord

from memory import working_memory
import config

log = logging.getLogger("claudicle.discord")

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")


class DiscordAdapter:
    """Receives Discord events and routes them to async callbacks."""

    def __init__(
        self,
        on_message: Callable,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        if not DISCORD_BOT_TOKEN:
            raise RuntimeError("DISCORD_BOT_TOKEN not set")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.dm_messages = True

        self._client = discord.Client(intents=intents)
        self._on_message = on_message
        self._loop = loop

        # Allowed channels (empty = all). Read from env.
        allowed_raw = os.environ.get("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "")
        self._allowed_channels: set[str] = {
            ch.strip() for ch in allowed_raw.split(",") if ch.strip()
        } if allowed_raw else set()

        # Message deduplication — bounded deque + set (from Iconoclast Demo pattern)
        self._dedup_queue: collections.deque[str] = collections.deque(maxlen=1000)
        self._dedup_set: set[str] = set()

        # Webhook cache for daimon identity posting
        self._webhooks: dict[int, discord.Webhook] = {}

        self._setup_handlers()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_duplicate(self, message_id: str) -> bool:
        """Check and register message ID for deduplication."""
        if message_id in self._dedup_set:
            return True
        # Evict oldest if at capacity
        if len(self._dedup_queue) >= self._dedup_queue.maxlen:
            evicted = self._dedup_queue[0]
            self._dedup_set.discard(evicted)
        self._dedup_queue.append(message_id)
        self._dedup_set.add(message_id)
        return False

    def _is_allowed_channel(self, channel_id: str) -> bool:
        """Check if channel is in allowed list (empty = all allowed)."""
        if not self._allowed_channels:
            return True
        return str(channel_id) in self._allowed_channels

    def _strip_mention(self, text: str) -> str:
        """Remove bot @mention from message text."""
        bot_id = str(self._client.user.id) if self._client.user else ""
        if bot_id:
            return re.sub(rf"<@!?{bot_id}>\s*", "", text).strip()
        return text.strip()

    def _dispatch(self, text, channel_id, thread_id, user_id, display_name, channel_name=""):
        """Schedule the async callback from the discord.py thread."""
        channel = f"discord:{channel_id}"
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._on_message(text, channel, thread_id, user_id, display_name, channel_name),
                self._loop,
            )
        else:
            log.warning("Event loop not running, dropping Discord message from %s", user_id)

    def _handle_daimon_command(self, text: str, channel_id: str, thread_id: str, user_id: str):
        """Handle in-thread daimon mode commands like !artifex speak."""
        from daimonic import registry as daimon_registry

        channel = f"discord:{channel_id}"
        parts = text[1:].split()
        if len(parts) < 2:
            self._dispatch_post(channel_id, "Usage: `!<daimon> <mode>` — modes: whisper, speak, both, off", thread_id)
            return

        daimon_name = parts[0].lower()
        mode = parts[1].lower()

        valid_modes = ("whisper", "speak", "both", "off")
        if mode not in valid_modes:
            self._dispatch_post(channel_id, f"Unknown mode: `{mode}`. Use: {', '.join(valid_modes)}", thread_id)
            return

        daimon = daimon_registry.get(daimon_name)
        if not daimon:
            enabled = daimon_registry.get_enabled()
            names = ", ".join(d.name for d in enabled) if enabled else "none"
            self._dispatch_post(channel_id, f"Unknown daimon: `{daimon_name}`. Available: {names}", thread_id)
            return

        current_modes = working_memory.get_thread_daimon_modes(channel, thread_id)
        current_modes[daimon_name] = mode
        working_memory.add(
            channel=channel,
            thread_ts=thread_id,
            user_id=user_id,
            entry_type="daimonMode",
            content=json.dumps(current_modes),
        )

        self._dispatch_post(channel_id, f"{daimon.display_name} set to **{mode}** for this thread.", thread_id)
        log.info("Daimon %s set to %s in discord:%s/%s by %s", daimon_name, mode, channel_id, thread_id, user_id)

    def _dispatch_post(self, channel_id: str, text: str, reply_to_id: str | None = None):
        """Schedule an async post from the discord.py thread (for daimon commands)."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_post(int(channel_id), text, reply_to_id),
                self._loop,
            )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _setup_handlers(self):
        @self._client.event
        async def on_ready():
            log.info("Discord connected as %s (ID: %s)", self._client.user, self._client.user.id)

        @self._client.event
        async def on_message(message: discord.Message):
            # Skip own messages and bots
            if message.author == self._client.user:
                return
            if message.author.bot:
                return

            # Deduplication
            if self._is_duplicate(str(message.id)):
                return

            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self._client.user in message.mentions if self._client.user else False

            # Determine if we should respond
            if is_dm:
                respond_to_dms = os.environ.get("CLAUDICLE_DISCORD_RESPOND_TO_DMS", "true").lower() == "true"
                if not respond_to_dms:
                    return
                text = message.content.strip()
            elif is_mentioned:
                respond_to_mentions = os.environ.get("CLAUDICLE_DISCORD_RESPOND_TO_MENTIONS", "true").lower() == "true"
                if not respond_to_mentions:
                    return
                if not self._is_allowed_channel(str(message.channel.id)):
                    return
                text = self._strip_mention(message.content)
            else:
                return

            if not text:
                return

            # Thread tracking: use thread ID if in a thread, else reply ref, else message ID
            thread_id = str(message.id)
            if hasattr(message.channel, "id") and isinstance(message.channel, discord.Thread):
                thread_id = str(message.channel.id)
            elif message.reference and message.reference.message_id:
                thread_id = str(message.reference.message_id)

            # Daimon command
            if text.startswith("!"):
                self._handle_daimon_command(text, str(message.channel.id), thread_id, str(message.author.id))
                return

            display_name = message.author.display_name or message.author.name
            channel_name = getattr(message.channel, "name", "DM")

            log.info("%s from %s in %s: %s", "DM" if is_dm else "@mention", display_name, channel_name, text[:80])
            self._dispatch(text, str(message.channel.id), thread_id, str(message.author.id), display_name, channel_name)

    # ------------------------------------------------------------------
    # Public API (matches SlackAdapter interface)
    # ------------------------------------------------------------------

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start Discord client in a background daemon thread."""
        if loop:
            self._loop = loop

        def _run():
            self._client.run(DISCORD_BOT_TOKEN, log_handler=None)

        thread = threading.Thread(target=_run, daemon=True, name="discord-bot")
        thread.start()
        log.info("Discord bot started in background thread")

    def stop(self):
        """Stop Discord client."""
        if self._client and not self._client.is_closed():
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)

    def post(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        icon_url: Optional[str] = None,
    ):
        """Post a message to Discord. Channel format: discord:{channel_id}.

        When username/icon_url are provided and the channel supports webhooks,
        the message appears as a distinct identity (for daimon speakers).
        """
        channel_id = int(channel.replace("discord:", ""))
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_post(channel_id, text, thread_ts, username, icon_url),
                self._loop,
            )

    async def _async_post(
        self,
        channel_id: int,
        text: str,
        reply_to_id: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ):
        """Async implementation of post."""
        from adapters.discord._discord_utils import split_message

        ch = self._client.get_channel(channel_id)
        if not ch:
            log.error("Discord channel %d not found", channel_id)
            return

        # Use webhook for daimon identity (guild text channels only)
        if username and isinstance(ch, discord.TextChannel):
            webhook = await self._get_or_create_webhook(ch)
            if webhook:
                for chunk in split_message(text):
                    try:
                        await webhook.send(content=chunk, username=username, avatar_url=avatar_url)
                    except Exception as e:
                        log.error("Webhook send failed: %s", e)
                return

        # Standard message posting
        for chunk in split_message(text):
            try:
                if reply_to_id:
                    try:
                        ref_msg = await ch.fetch_message(int(reply_to_id))
                        await ref_msg.reply(chunk)
                    except (discord.NotFound, ValueError):
                        await ch.send(chunk)
                else:
                    await ch.send(chunk)
            except Exception as e:
                log.error("Failed to post to Discord channel %d: %s", channel_id, e)

    async def _get_or_create_webhook(self, channel: discord.TextChannel) -> Optional[discord.Webhook]:
        """Get or create a webhook for daimon identity posting."""
        if channel.id in self._webhooks:
            return self._webhooks[channel.id]
        try:
            webhooks = await channel.webhooks()
            for wh in webhooks:
                if wh.name == "claudicle-daimon" and wh.user == self._client.user:
                    self._webhooks[channel.id] = wh
                    return wh
            wh = await channel.create_webhook(name="claudicle-daimon")
            self._webhooks[channel.id] = wh
            return wh
        except discord.Forbidden:
            log.debug("No webhook permission in %s — falling back to standard post", channel.name)
            return None
        except Exception as e:
            log.warning("Failed to get/create webhook in %s: %s", channel.name, e)
            return None

    def react(self, channel: str, ts: str, emoji: str, remove: bool = False):
        """Add or remove a reaction on Discord."""
        channel_id = int(channel.replace("discord:", ""))
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_react(channel_id, ts, emoji, remove),
                self._loop,
            )

    async def _async_react(self, channel_id: int, message_id: str, emoji: str, remove: bool):
        ch = self._client.get_channel(channel_id)
        if not ch:
            return
        try:
            msg = await ch.fetch_message(int(message_id))
            emoji_char = self._map_emoji(emoji)
            if remove:
                await msg.remove_reaction(emoji_char, self._client.user)
            else:
                await msg.add_reaction(emoji_char)
        except Exception as e:
            log.debug("Failed to %s reaction on Discord: %s", "remove" if remove else "add", e)

    @staticmethod
    def _map_emoji(slack_name: str) -> str:
        """Map Slack-style emoji names to Unicode for Discord."""
        mapping = {
            "hourglass_flowing_sand": "\u23f3",
            "white_check_mark": "\u2705",
            "thinking_face": "\U0001f914",
        }
        return mapping.get(slack_name, "\u2705")
