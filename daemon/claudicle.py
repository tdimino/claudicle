#!/usr/bin/env python3
"""
Claudicle, Artifex Maximus — Unified launcher.

Starts an interactive Claude Code terminal session alongside a Slack bot.
Each Slack thread gets its own session. All activity visible in one terminal.

Usage:
    cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" && python3 claudicle.py
    python3 claudicle.py --verbose
    python3 claudicle.py --no-slack      # Terminal only, no Slack bot
"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sys

# Local imports (must run from daemon directory)
import claude_handler
import session_store
import soul_memory
from config import (
    CLAUDE_ALLOWED_TOOLS,
    CLAUDE_CWD,
    LOG_DIR,
    SOUL_ENGINE_ENABLED,
    SOUL_NAME,
    TERMINAL_SESSION_TOOLS,
    TERMINAL_SOUL_ENABLED,
)
from slack_adapter import SlackAdapter
from terminal_ui import TerminalUI

log = logging.getLogger("claudicle")

BANNER = """
╔══════════════════════════════════════════════════╗
║         {name}, Artifex Maximus                 ║
║         Unified Launcher                         ║
║                                                  ║
║  Terminal + Slack · Per-channel sessions          ║
║  Soul engine: {soul:<4}  · CWD: {cwd:<18} ║
╚══════════════════════════════════════════════════╝
"""


class Claudicle:
    """Unified launcher: terminal input + Slack bot, shared soul engine."""

    def __init__(self, enable_slack: bool = True):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._enable_slack = enable_slack
        self._slack: SlackAdapter | None = None
        self._ui = TerminalUI(on_input=self._enqueue_terminal)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutting_down = False

    # ------------------------------------------------------------------
    # Enqueueing
    # ------------------------------------------------------------------

    async def _enqueue_slack(
        self, text: str, channel: str, thread_ts: str, user_id: str, display_name: str
    ):
        """Called from Slack adapter when a message arrives."""
        await self._queue.put({
            "origin": "slack",
            "text": text,
            "channel": channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "display_name": display_name,
        })

    async def _enqueue_terminal(self, text: str):
        """Called from terminal UI when user types input."""
        await self._queue.put({
            "origin": "terminal",
            "text": text,
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
        )

        # Post response and remove thinking reaction
        if self._slack:
            self._slack.post(channel, response, thread_ts)
            self._slack.react(channel, thread_ts, "hourglass_flowing_sand", remove=True)

        self._ui.log_slack_out(channel, response)

        # Daimon speakers respond after Claudicle
        await self._handle_daimon_speakers(text, channel, thread_ts, response)

    async def _handle_daimon_speakers(
        self, user_message: str, channel: str, thread_ts: str,
        claudicle_response: str,
    ):
        """Generate and post responses from daimons in speak mode."""
        import daimon_registry
        import daimon_speak
        import daimonic

        speakers = daimon_registry.get_speakers()
        if not speakers:
            return

        thread_modes = _get_thread_daimon_modes(channel, thread_ts)
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

            if response and self._slack:
                self._slack.post(
                    channel, response, thread_ts,
                    username=daimon.display_name,
                    icon_emoji=daimon.slack_emoji or None,
                    icon_url=daimon.slack_icon_url or None,
                )
                log.info("Daimon %s spoke in %s", daimon.name, channel)

                # Store in working_memory for cognitive completeness
                import working_memory
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id=daimon.name,
                    entry_type="daimonSpeech",
                    content=response,
                    metadata={"daimon": daimon.name},
                )

    async def _handle_terminal_message(self, msg: dict):
        """Process a terminal message through Claude (no soul engine by default)."""
        text = msg["text"]

        response = await claude_handler.async_process(
            text,
            channel="terminal",
            thread_ts="terminal",
            user_id=None,
            soul_enabled=TERMINAL_SOUL_ENABLED,
            allowed_tools=TERMINAL_SESSION_TOOLS,
        )

        self._ui.log_terminal_response(response)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self):
        """Start everything and run until interrupted."""
        self._loop = asyncio.get_event_loop()

        # Initialize daimon registry from config
        import daimon_registry
        daimon_registry.load_from_config()

        # Print banner
        print(BANNER.format(
            name=SOUL_NAME,
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


def _get_thread_daimon_modes(channel: str, thread_ts: str) -> dict:
    """Get per-thread daimon mode overrides from working_memory."""
    import working_memory

    entries = working_memory.get_recent(channel, thread_ts, limit=20)
    for entry in reversed(entries):
        if entry.get("entry_type") == "daimonMode":
            try:
                return json.loads(entry.get("content", "{}"))
            except json.JSONDecodeError:
                pass
    return {}


def main():
    parser = argparse.ArgumentParser(description="Claudicle unified launcher")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging to console")
    parser.add_argument("--no-slack", action="store_true", help="Terminal only, no Slack bot")
    args = parser.parse_args()

    setup_logging(args.verbose)

    claudicle = Claudicle(enable_slack=not args.no_slack)

    try:
        asyncio.run(claudicle.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
