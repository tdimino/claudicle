#!/usr/bin/env python3
"""
Claudicle, Artifex Maximus — Unified launcher.

Starts an interactive Claude Code terminal session alongside a Slack bot.
Each Slack thread gets its own session. All activity visible in one terminal.

Usage:
    cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" && python3 claudicle.py
    python3 claudicle.py --verbose
    python3 claudicle.py --no-slack      # Disable Slack bot
    python3 claudicle.py --no-discord    # Disable Discord bot
    python3 claudicle.py --no-telegram   # Disable Telegram bot
"""

import argparse
import asyncio
import logging
import os
import random
import signal
import sys

# Local imports (must run from daemon directory)
import claude_handler
from memory import session_store, soul_memory
import config
from config import (
    CLAUDE_ALLOWED_TOOLS,
    CLAUDE_CWD,
    DEFAULT_SLACK_USER_ID,
    DEFAULT_USER_NAME,
    LOG_DIR,
    SOUL_ENGINE_ENABLED,
    TERMINAL_SESSION_TOOLS,
    TERMINAL_SOUL_ENABLED,
)
from adapters.slack_adapter import SlackAdapter
from adapters.terminal_ui import TerminalUI

# Optional adapters — imported lazily to avoid hard dependencies
DiscordAdapter = None
TelegramAdapter = None

log = logging.getLogger("claudicle")

BANNER = """
╔══════════════════════════════════════════════════╗
║         {name}, Artifex Maximus                 ║
║         Unified Launcher                         ║
║                                                  ║
║  Terminal + Slack + Discord + Telegram            ║
║  Soul engine: {soul:<4}  · CWD: {cwd:<18} ║
╚══════════════════════════════════════════════════╝
"""


class Claudicle:
    """Unified launcher: terminal input + Slack bot, shared soul engine."""

    def __init__(self, enable_slack: bool = True, enable_discord: bool = True, enable_telegram: bool = True):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._enable_slack = enable_slack
        self._enable_discord = enable_discord
        self._enable_telegram = enable_telegram
        self._slack: SlackAdapter | None = None
        self._discord = None  # DiscordAdapter | None
        self._telegram = None  # TelegramAdapter | None
        self._ui = TerminalUI(on_input=self._enqueue_terminal)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutting_down = False

    # ------------------------------------------------------------------
    # Enqueueing
    # ------------------------------------------------------------------

    async def _enqueue_slack(
        self, text: str, channel: str, thread_ts: str, user_id: str,
        display_name: str, channel_name: str = "",
    ):
        """Called from Slack adapter when a message arrives."""
        await self._queue.put({
            "origin": "slack",
            "text": text,
            "channel": channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "display_name": display_name,
            "channel_name": channel_name,
        })

    async def _enqueue_terminal(self, text: str):
        """Called from terminal UI when user types input."""
        await self._queue.put({
            "origin": "terminal",
            "text": text,
            "user_id": DEFAULT_SLACK_USER_ID,
            "display_name": DEFAULT_USER_NAME,
        })

    async def _enqueue_discord(
        self, text: str, channel: str, thread_ts: str, user_id: str,
        display_name: str, channel_name: str = "",
    ):
        """Called from Discord adapter when a message arrives."""
        await self._queue.put({
            "origin": "discord",
            "text": text,
            "channel": channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "display_name": display_name,
            "channel_name": channel_name,
        })

    async def _enqueue_telegram(
        self, text: str, channel: str, thread_ts: str, user_id: str,
        display_name: str, channel_name: str = "",
    ):
        """Called from Telegram adapter when a message arrives."""
        await self._queue.put({
            "origin": "telegram",
            "text": text,
            "channel": channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "display_name": display_name,
            "channel_name": channel_name,
        })

    # ------------------------------------------------------------------
    # Message processing loop
    # ------------------------------------------------------------------

    async def _process_loop(self):
        """Pull messages from queue, process sequentially."""
        while not self._shutting_down:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                if msg["origin"] == "slack":
                    await self._handle_slack_message(msg)
                elif msg["origin"] == "discord":
                    await self._handle_discord_message(msg)
                elif msg["origin"] == "telegram":
                    await self._handle_telegram_message(msg)
                elif msg["origin"] == "terminal":
                    await self._handle_terminal_message(msg)
            except Exception as e:
                log.error("Error processing message: %s", e, exc_info=True)
                self._ui.log_error(str(e))

    async def _handle_slack_message(self, msg: dict):
        """Process a Slack message through Claude with soul engine."""
        user = msg["display_name"]
        channel = msg["channel"]
        thread_ts = msg["thread_ts"]
        text = msg["text"]
        user_id = msg["user_id"]
        channel_name = msg.get("channel_name", "")

        self._ui.log_slack_in(user, channel, text)

        # Add thinking reaction
        if self._slack:
            self._slack.react(channel, thread_ts, "hourglass_flowing_sand")

        response = await claude_handler.async_process(
            text,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            soul_enabled=True,
            allowed_tools=CLAUDE_ALLOWED_TOOLS,
            origin="slack",
            display_name=user,
            channel_name=channel_name,
        )

        # Post response and remove thinking reaction
        if self._slack:
            self._slack.post(channel, response, thread_ts)
            self._slack.react(channel, thread_ts, "hourglass_flowing_sand", remove=True)

        self._ui.log_slack_out(channel, response)

        # Daimon speakers respond after Claudicle
        await self._handle_daimon_speakers(text, channel, thread_ts, response, adapter=self._slack)

    async def _handle_daimon_speakers(
        self, user_message: str, channel: str, thread_ts: str,
        claudicle_response: str, adapter=None,
    ):
        """Generate and post responses from daimons in speak mode."""
        from daimonic import registry as daimon_registry
        from daimonic import speak as daimon_speak
        import daimonic

        speakers = daimon_registry.get_speakers()
        if not speakers:
            return

        from memory import working_memory
        thread_modes = working_memory.get_thread_daimon_modes(channel, thread_ts)
        context = daimonic.read_context(channel, thread_ts)

        for daimon in speakers:
            # Check per-thread mode override
            thread_mode = thread_modes.get(daimon.name, daimon.mode)
            if thread_mode not in ("speak", "both"):
                continue

            # Stagger: natural pause before second soul responds
            await asyncio.sleep(0.8 + random.random() * 0.4)

            response = await daimon_speak.generate_response(
                daimon, user_message, context, claudicle_response,
            )

            if response and adapter:
                adapter.post(
                    channel, response, thread_ts,
                    username=daimon.display_name,
                    icon_emoji=getattr(daimon, "slack_emoji", None),
                    icon_url=getattr(daimon, "slack_icon_url", None),
                )
                log.info("Daimon %s spoke in %s", daimon.name, channel)

                # Store in working_memory for cognitive completeness
                from memory import working_memory
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id=daimon.name,
                    entry_type="daimonSpeech",
                    content=response,
                    metadata={"daimon": daimon.name},
                )

    async def _handle_discord_message(self, msg: dict):
        """Process a Discord message through Claude with soul engine."""
        user = msg["display_name"]
        channel = msg["channel"]
        thread_ts = msg["thread_ts"]
        text = msg["text"]
        user_id = msg["user_id"]
        channel_name = msg.get("channel_name", "")

        self._ui.log_slack_in(user, f"[discord] {channel_name or channel}", text)

        response = await claude_handler.async_process(
            text,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            soul_enabled=True,
            allowed_tools=CLAUDE_ALLOWED_TOOLS,
            origin="discord",
            display_name=user,
            channel_name=channel_name,
        )

        if self._discord:
            self._discord.post(channel, response, thread_ts)

        self._ui.log_slack_out(f"[discord] {channel_name or channel}", response)

        # Daimon speakers respond after Claudicle
        await self._handle_daimon_speakers(text, channel, thread_ts, response, adapter=self._discord)

    async def _handle_telegram_message(self, msg: dict):
        """Process a Telegram message through Claude with soul engine."""
        user = msg["display_name"]
        channel = msg["channel"]
        thread_ts = msg["thread_ts"]
        text = msg["text"]
        user_id = msg["user_id"]
        channel_name = msg.get("channel_name", "")

        self._ui.log_slack_in(user, f"[telegram] {channel_name or channel}", text)

        response = await claude_handler.async_process(
            text,
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            soul_enabled=True,
            allowed_tools=CLAUDE_ALLOWED_TOOLS,
            origin="telegram",
            display_name=user,
            channel_name=channel_name,
        )

        if self._telegram:
            self._telegram.post(channel, response, thread_ts)

        self._ui.log_slack_out(f"[telegram] {channel_name or channel}", response)

        # Daimon speakers respond after Claudicle
        await self._handle_daimon_speakers(text, channel, thread_ts, response, adapter=self._telegram)

    async def _handle_terminal_message(self, msg: dict):
        """Process a terminal message through Claude (no soul engine by default)."""
        text = msg["text"]
        user_id = msg.get("user_id", DEFAULT_SLACK_USER_ID)
        display_name = msg.get("display_name", DEFAULT_USER_NAME)

        response = await claude_handler.async_process(
            text,
            channel="terminal",
            thread_ts="terminal",
            user_id=user_id,
            soul_enabled=TERMINAL_SOUL_ENABLED,
            allowed_tools=TERMINAL_SESSION_TOOLS,
            origin="terminal",
            display_name=display_name,
        )

        self._ui.log_terminal_response(response)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self):
        """Start everything and run until interrupted."""
        self._loop = asyncio.get_event_loop()

        # Initialize daimon registry from config
        from daimonic import registry as daimon_registry
        daimon_registry.load_from_config()

        # Print banner
        print(BANNER.format(
            name=config.SOUL_NAME,
            soul="ON" if SOUL_ENGINE_ENABLED else "OFF",
            cwd=os.path.basename(str(CLAUDE_CWD)),
        ))

        # Start Slack bot
        if self._enable_slack:
            try:
                self._slack = SlackAdapter(
                    on_message=self._enqueue_slack,
                    loop=self._loop,
                )
                self._slack.start(loop=self._loop)
                log.info("Slack bot started")
                print("Slack bot: connected")
            except Exception as e:
                log.error("Failed to start Slack bot: %s", e)
                print(f"Slack bot: FAILED ({e})")
                self._slack = None
        else:
            print("Slack bot: disabled")

        # Start Discord bot
        if self._enable_discord:
            try:
                global DiscordAdapter
                if DiscordAdapter is None:
                    from adapters.discord_adapter import DiscordAdapter
                self._discord = DiscordAdapter(
                    on_message=self._enqueue_discord,
                    loop=self._loop,
                )
                self._discord.start(loop=self._loop)
                log.info("Discord bot started")
                print("Discord bot: connected")
            except ImportError:
                log.info("discord.py not installed — Discord adapter disabled")
                print("Discord bot: not installed (pip install discord.py)")
                self._discord = None
            except RuntimeError as e:
                log.info("Discord bot disabled: %s", e)
                print(f"Discord bot: disabled ({e})")
                self._discord = None
            except Exception as e:
                log.error("Failed to start Discord bot: %s", e)
                print(f"Discord bot: FAILED ({e})")
                self._discord = None
        else:
            print("Discord bot: disabled")

        # Start Telegram bot
        if self._enable_telegram:
            try:
                global TelegramAdapter
                if TelegramAdapter is None:
                    from adapters.telegram_adapter import TelegramAdapter
                self._telegram = TelegramAdapter(
                    on_message=self._enqueue_telegram,
                    loop=self._loop,
                )
                self._telegram.start(loop=self._loop)
                log.info("Telegram bot started")
                print("Telegram bot: connected")
            except ImportError:
                log.info("python-telegram-bot not installed — Telegram adapter disabled")
                print("Telegram bot: not installed (pip install python-telegram-bot)")
                self._telegram = None
            except RuntimeError as e:
                log.info("Telegram bot disabled: %s", e)
                print(f"Telegram bot: disabled ({e})")
                self._telegram = None
            except Exception as e:
                log.error("Failed to start Telegram bot: %s", e)
                print(f"Telegram bot: FAILED ({e})")
                self._telegram = None
        else:
            print("Telegram bot: disabled")

        print(f"Terminal session: ready (tools: {TERMINAL_SESSION_TOOLS})")
        print("Type a message below. Ctrl+C to quit.\n")

        # Run process loop and terminal input concurrently
        try:
            await asyncio.gather(
                self._process_loop(),
                self._ui.input_loop(),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self._shutdown()

    async def _shutdown(self):
        """Graceful shutdown."""
        if self._shutting_down:
            return
        self._shutting_down = True
        print("\nShutting down Claudicle...")

        self._ui.stop()

        if self._slack:
            self._slack.stop()
            log.info("Slack bot stopped")

        if self._discord:
            self._discord.stop()
            log.info("Discord bot stopped")

        if self._telegram:
            self._telegram.stop()
            log.info("Telegram bot stopped")

        session_store.close()
        soul_memory.close()
        log.info("Claudicle shutdown complete")


def setup_logging(verbose: bool):
    """Configure logging to file + optional console."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, "claudicle.log")

    handlers = [logging.FileHandler(log_file)]
    if verbose:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main():
    parser = argparse.ArgumentParser(description="Claudicle unified launcher")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging to console")
    parser.add_argument("--no-slack", action="store_true", help="Disable Slack bot")
    parser.add_argument("--no-discord", action="store_true", help="Disable Discord bot")
    parser.add_argument("--no-telegram", action="store_true", help="Disable Telegram bot")
    args = parser.parse_args()

    setup_logging(args.verbose)

    claudicle = Claudicle(
        enable_slack=not args.no_slack,
        enable_discord=not args.no_discord,
        enable_telegram=not args.no_telegram,
    )

    try:
        asyncio.run(claudicle.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
