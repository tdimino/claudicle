"""
Telegram adapter for the Claudicle unified launcher.

Uses python-telegram-bot v21+ (async Application class) in polling mode.
No webhook server needed. Mirrors the SlackAdapter interface.
"""

import asyncio
import json
import logging
import os
import re
import threading
from typing import Callable, Optional

from telegram import Bot, Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from memory import working_memory
import config

log = logging.getLogger("claudicle.telegram")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


class TelegramAdapter:
    """Receives Telegram messages and routes them to async callbacks."""

    def __init__(
        self,
        on_message: Callable,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        if not TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

        self._on_message = on_message
        self._loop = loop
        self._app: Application | None = None
        self._bot: Bot | None = None
        self._bot_username: str = ""
        self._poll_loop: asyncio.AbstractEventLoop | None = None

        # Allowed chats (empty = all). Read from env.
        allowed_raw = os.environ.get("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "")
        self._allowed_chats: set[str] = {
            ch.strip() for ch in allowed_raw.split(",") if ch.strip()
        } if allowed_raw else set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _strip_mention(self, text: str) -> str:
        """Remove @botname from message text."""
        if self._bot_username:
            return re.sub(rf"@{re.escape(self._bot_username)}\s*", "", text, flags=re.IGNORECASE).strip()
        return text.strip()

    def _dispatch(self, text, chat_id, thread_id, user_id, display_name, channel_name=""):
        """Schedule the async callback from the Telegram thread."""
        channel = f"telegram:{chat_id}"
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._on_message(text, channel, thread_id, user_id, display_name, channel_name),
                self._loop,
            )
        else:
            log.warning("Event loop not running, dropping Telegram message from %s", user_id)

    def _handle_daimon_command(self, text: str, chat_id: str, thread_id: str, user_id: str):
        """Handle in-thread daimon mode commands like !artifex speak."""
        from daimonic import registry as daimon_registry

        channel = f"telegram:{chat_id}"
        parts = text[1:].split()
        if len(parts) < 2:
            self._dispatch_post(chat_id, "Usage: `!<daimon> <mode>` — modes: whisper, speak, both, off", thread_id)
            return

        daimon_name = parts[0].lower()
        mode = parts[1].lower()

        valid_modes = ("whisper", "speak", "both", "off")
        if mode not in valid_modes:
            self._dispatch_post(chat_id, f"Unknown mode: `{mode}`. Use: {', '.join(valid_modes)}", thread_id)
            return

        daimon = daimon_registry.get(daimon_name)
        if not daimon:
            enabled = daimon_registry.get_enabled()
            names = ", ".join(d.name for d in enabled) if enabled else "none"
            self._dispatch_post(chat_id, f"Unknown daimon: `{daimon_name}`. Available: {names}", thread_id)
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

        self._dispatch_post(chat_id, f"{daimon.display_name} set to *{mode}* for this thread.", thread_id)
        log.info("Daimon %s set to %s in telegram:%s/%s by %s", daimon_name, mode, chat_id, thread_id, user_id)

    def _dispatch_post(self, chat_id: str, text: str, reply_to_id: str | None = None):
        """Schedule an async post on the poll loop (where self._bot lives)."""
        if self._poll_loop and self._poll_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_post(int(chat_id), text, reply_to_id),
                self._poll_loop,
            )

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming Telegram message."""
        message = update.effective_message
        if not message or not message.text:
            return

        chat = update.effective_chat
        user = update.effective_user
        if not chat or not user:
            return

        is_private = chat.type == "private"
        is_group = chat.type in ("group", "supergroup")

        text = message.text.strip()

        if is_group:
            respond_to_mentions = os.environ.get("CLAUDICLE_TELEGRAM_RESPOND_TO_MENTIONS", "true").lower() == "true"
            if not respond_to_mentions:
                return
            # In groups, only respond to @mentions
            if not self._bot_username:
                log.warning("Bot username not resolved; dropping group message from %s", user.id)
                return
            if f"@{self._bot_username}" not in text:
                return
            text = self._strip_mention(text)
            # Check allowed chats
            if self._allowed_chats and str(chat.id) not in self._allowed_chats:
                return
        elif is_private:
            respond_to_dms = os.environ.get("CLAUDICLE_TELEGRAM_RESPOND_TO_DMS", "true").lower() == "true"
            if not respond_to_dms:
                return
        else:
            return

        if not text:
            return

        # Thread tracking: use reply_to_message for threading
        thread_id = str(message.message_id)
        if message.reply_to_message:
            thread_id = str(message.reply_to_message.message_id)

        # Daimon command
        if text.startswith("!"):
            self._handle_daimon_command(text, str(chat.id), thread_id, str(user.id))
            return

        display_name = user.full_name or user.username or str(user.id)
        channel_name = chat.title or ("DM" if is_private else str(chat.id))

        log.info("%s from %s in %s: %s",
                 "DM" if is_private else "@mention",
                 display_name, channel_name, text[:80])

        self._dispatch(text, str(chat.id), thread_id, str(user.id), display_name, channel_name)

    # ------------------------------------------------------------------
    # Public API (matches SlackAdapter interface)
    # ------------------------------------------------------------------

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start Telegram polling in a background daemon thread."""
        if loop:
            self._loop = loop

        def _run_polling():
            """Run python-telegram-bot's polling in its own event loop."""
            poll_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(poll_loop)
            self._poll_loop = poll_loop

            app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            app.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )

            self._app = app
            self._bot = app.bot

            # Get bot info
            async def _init():
                me = await app.bot.get_me()
                self._bot_username = me.username or ""
                log.info("Telegram bot: @%s (ID: %s)", self._bot_username, me.id)

            poll_loop.run_until_complete(_init())
            poll_loop.run_until_complete(app.initialize())
            poll_loop.run_until_complete(app.start())
            poll_loop.run_until_complete(
                app.updater.start_polling(drop_pending_updates=True)
            )

            # Keep running until stopped
            poll_loop.run_forever()

        thread = threading.Thread(target=_run_polling, daemon=True, name="telegram-bot")
        thread.start()
        log.info("Telegram bot started in background thread")

    def stop(self):
        """Stop Telegram polling gracefully."""
        if self._app and self._poll_loop and not self._poll_loop.is_closed():
            log.info("Stopping Telegram polling")

            async def _do_stop():
                try:
                    if self._app.updater and self._app.updater.running:
                        await self._app.updater.stop()
                    await self._app.stop()
                    await self._app.shutdown()
                finally:
                    self._poll_loop.stop()

            try:
                fut = asyncio.run_coroutine_threadsafe(_do_stop(), self._poll_loop)
                fut.result(timeout=10)
            except Exception as e:
                log.warning("Error stopping Telegram: %s", e)

    def post(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        username: Optional[str] = None,
        icon_emoji: Optional[str] = None,
        icon_url: Optional[str] = None,
    ):
        """Post a message to Telegram. Channel format: telegram:{chat_id}.

        Telegram bots cannot change display name per-message. When username is
        provided (daimon speaker), we prefix the message with the identity.
        """
        chat_id = int(channel.replace("telegram:", ""))
        # Prefix with daimon identity if username provided
        if username:
            text = f"[{username}]\n{text}"
        if self._poll_loop and self._poll_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_post(chat_id, text, thread_ts),
                self._poll_loop,
            )

    async def _async_post(self, chat_id: int, text: str, reply_to_id: Optional[str] = None):
        """Async post implementation."""
        from adapters.telegram._telegram_utils import split_message

        if not self._bot:
            log.error("Telegram bot not initialized")
            return

        for chunk in split_message(text):
            try:
                kwargs: dict = {"chat_id": chat_id, "text": chunk}
                if reply_to_id:
                    try:
                        kwargs["reply_to_message_id"] = int(reply_to_id)
                    except ValueError:
                        pass
                await self._bot.send_message(**kwargs)
            except Exception as e:
                log.error("Failed to post to Telegram chat %d: %s", chat_id, e)

    def react(self, channel: str, ts: str, emoji: str, remove: bool = False):
        """Telegram bots cannot add reactions — no-op."""
        pass
