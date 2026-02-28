#!/usr/bin/env python3
"""
Background Telegram listener — writes incoming messages to inbox.jsonl.

Catches @mentions in groups and all DMs via polling, appends to inbox.jsonl.
Standalone process for Session Bridge mode (no unified launcher needed).

Usage:
    python3 telegram_listen.py           # foreground (for testing)
    python3 telegram_listen.py --bg      # daemonize, write PID file
    python3 telegram_listen.py --stop    # kill running listener
    python3 telegram_listen.py --status  # check if running

Requires:
    TELEGRAM_BOT_TOKEN — from @BotFather
    pip install python-telegram-bot
"""

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import time

ADAPTER_DIR = os.path.dirname(os.path.abspath(__file__))
DAEMON_DIR = os.path.join(ADAPTER_DIR, "..", "..", "daemon")
INBOX = os.path.join(DAEMON_DIR, "inbox.jsonl")
PID_FILE = os.path.join(DAEMON_DIR, "telegram_listener.pid")


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
        print("Telegram listener is not running.")
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
    print(f"Telegram listener (PID {pid}) stopped.")


def cmd_status():
    pid = _read_pid()
    if _is_running(pid):
        print(f"Telegram listener running (PID {pid})")
    else:
        print("Telegram listener is not running.")
        if pid is not None:
            try:
                os.remove(PID_FILE)
            except FileNotFoundError:
                pass


def run_listener(background=False):
    pid = _read_pid()
    if _is_running(pid):
        print(f"Telegram listener already running (PID {pid}). Use --stop first.")
        sys.exit(1)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    if background:
        pid = os.fork()
        if pid > 0:
            with open(PID_FILE, "w") as f:
                f.write(str(pid))
            print(f"Telegram listener started in background (PID {pid})")
            print(f"Inbox: {INBOX}")
            return
        os.setsid()
        log_path = os.path.join(DAEMON_DIR, "logs", "telegram_listener.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_fd = open(log_path, "a")
        os.dup2(log_fd.fileno(), sys.stdout.fileno())
        os.dup2(log_fd.fileno(), sys.stderr.fileno())
    else:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    # Import only when actually running
    from telegram import Update
    from telegram.ext import Application, ContextTypes, MessageHandler, filters

    allowed_raw = os.environ.get("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "")
    allowed_chats = {ch.strip() for ch in allowed_raw.split(",") if ch.strip()} if allowed_raw else set()

    bot_username = ""

    def write_inbox(chat_id, thread_id, user_id, display_name, text):
        entry = {
            "ts": time.time(),
            "channel": f"telegram:{chat_id}",
            "thread_ts": thread_id,
            "user_id": user_id,
            "display_name": display_name,
            "text": text,
            "handled": False,
        }
        with open(INBOX, "a") as f:
            f.write(json.dumps(entry) + "\n")

        ts_str = time.strftime("%H:%M:%S")
        print(f"[{ts_str}] Inbox: {display_name} in telegram:{chat_id}: {text[:80]}", flush=True)

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        nonlocal bot_username
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
            if not bot_username or f"@{bot_username}" not in text:
                return
            text = re.sub(rf"@{re.escape(bot_username)}\s*", "", text, flags=re.IGNORECASE).strip()
            if allowed_chats and str(chat.id) not in allowed_chats:
                return
        elif not is_private:
            return

        if not text:
            return

        thread_id = str(message.message_id)
        if message.reply_to_message:
            thread_id = str(message.reply_to_message.message_id)

        display_name = user.full_name or user.username or str(user.id)
        write_inbox(str(chat.id), thread_id, str(user.id), display_name, text)

    # Graceful shutdown
    def _cleanup(signum, frame):
        print("\nTelegram listener shutting down...", flush=True)
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print(f"Telegram listener started (PID {os.getpid()})", flush=True)

    # Build and run application
    app = Application.builder().token(bot_token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def _start():
        nonlocal bot_username
        me = await app.bot.get_me()
        bot_username = me.username or ""
        print(f"Telegram bot: @{bot_username} (ID: {me.id})", flush=True)
        print(f"Inbox: {INBOX}", flush=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_start())

    # Run polling (blocks until stopped)
    app.run_polling(drop_pending_updates=True)


def main():
    parser = argparse.ArgumentParser(description="Telegram inbox listener")
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
