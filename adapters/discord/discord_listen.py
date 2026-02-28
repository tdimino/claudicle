#!/usr/bin/env python3
"""
Background Discord listener — writes incoming messages to inbox.jsonl.

Catches @mentions and DMs via discord.py Gateway, appends to inbox.jsonl.
Standalone process for Session Bridge mode (no unified launcher needed).

Usage:
    python3 discord_listen.py           # foreground (for testing)
    python3 discord_listen.py --bg      # daemonize, write PID file
    python3 discord_listen.py --stop    # kill running listener
    python3 discord_listen.py --status  # check if running

Requires:
    DISCORD_BOT_TOKEN — from Discord Developer Portal
    pip install discord.py
"""

import argparse
import json
import os
import re
import signal
import sys
import time

ADAPTER_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON_DIR = os.path.join(ADAPTER_DIR, "..", "..", "daemon")
INBOX = os.path.join(DAEMON_DIR, "inbox.jsonl")
PID_FILE = os.path.join(DAEMON_DIR, "discord_listener.pid")


def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_stop():
    pid = _read_pid()
    if not _is_running(pid):
        print("Discord listener is not running.")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _is_running(pid):
            break
        time.sleep(0.1)
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass
    print(f"Discord listener (PID {pid}) stopped.")


def cmd_status():
    pid = _read_pid()
    if _is_running(pid):
        print(f"Discord listener running (PID {pid})")
    else:
        print("Discord listener is not running.")
        if pid is not None:
            try:
                os.remove(PID_FILE)
            except FileNotFoundError:
                pass


def run_listener(background=False):
    pid = _read_pid()
    if _is_running(pid):
        print(f"Discord listener already running (PID {pid}). Use --stop first.")
        sys.exit(1)

    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("Error: DISCORD_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    if background:
        pid = os.fork()
        if pid > 0:
            with open(PID_FILE, "w") as f:
                f.write(str(pid))
            print(f"Discord listener started in background (PID {pid})")
            print(f"Inbox: {INBOX}")
            return
        os.setsid()
        log_path = os.path.join(DAEMON_DIR, "logs", "discord_listener.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_fd = open(log_path, "a")
        os.dup2(log_fd.fileno(), sys.stdout.fileno())
        os.dup2(log_fd.fileno(), sys.stderr.fileno())
    else:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    # Import discord.py only when actually running
    import discord

    allowed_raw = os.environ.get("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "")
    allowed_channels = {ch.strip() for ch in allowed_raw.split(",") if ch.strip()} if allowed_raw else set()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.dm_messages = True

    client = discord.Client(intents=intents)

    def write_inbox(channel_id, thread_id, user_id, display_name, text):
        entry = {
            "ts": time.time(),
            "channel": f"discord:{channel_id}",
            "thread_ts": thread_id,
            "user_id": user_id,
            "display_name": display_name,
            "text": text,
            "handled": False,
        }
        with open(INBOX, "a") as f:
            f.write(json.dumps(entry) + "\n")

        ts_str = time.strftime("%H:%M:%S")
        print(f"[{ts_str}] Inbox: {display_name} in discord:{channel_id}: {text[:80]}", flush=True)

    @client.event
    async def on_ready():
        print(f"Discord listener connected as {client.user} (ID: {client.user.id})", flush=True)
        print(f"Inbox: {INBOX}", flush=True)

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = client.user in message.mentions if client.user else False

        if is_dm:
            text = message.content.strip()
        elif is_mentioned:
            if allowed_channels and str(message.channel.id) not in allowed_channels:
                return
            bot_id = str(client.user.id) if client.user else ""
            text = re.sub(rf"<@!?{bot_id}>\s*", "", message.content).strip() if bot_id else message.content.strip()
        else:
            return

        if not text:
            return

        thread_id = str(message.id)
        if isinstance(message.channel, discord.Thread):
            thread_id = str(message.channel.id)
        elif message.reference and message.reference.message_id:
            thread_id = str(message.reference.message_id)

        display_name = message.author.display_name or message.author.name
        write_inbox(str(message.channel.id), thread_id, str(message.author.id), display_name, text)

    # Graceful shutdown
    def _cleanup(signum, frame):
        print("\nDiscord listener shutting down...", flush=True)
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print(f"Discord listener started (PID {os.getpid()})", flush=True)
    client.run(bot_token, log_handler=None)


def main():
    parser = argparse.ArgumentParser(description="Discord inbox listener")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bg", action="store_true", help="Run in background")
    group.add_argument("--stop", action="store_true", help="Stop running listener")
    group.add_argument("--status", action="store_true", help="Check if running")
    args = parser.parse_args()

    if args.stop:
        cmd_stop()
    elif args.status:
        cmd_status()
    else:
        run_listener(background=args.bg)


if __name__ == "__main__":
    main()
