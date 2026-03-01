#!/usr/bin/env python3
"""
Post a response to a Telegram chat.

Usage:
    python3 telegram_post.py CHAT_ID TEXT [--reply-to MSG_ID]

Requires:
    TELEGRAM_BOT_TOKEN
    pip install python-telegram-bot
"""

import argparse
import asyncio
import os
import sys

# Add adapter dir to path for shared utilities
sys.path.insert(0, os.path.dirname(__file__))
from _telegram_utils import split_message


async def send_message(chat_id: int, text: str, reply_to: int | None = None):
    """Send a message via Telegram Bot API."""
    from telegram import Bot

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    bot = Bot(token=token)

    chunks = split_message(text)

    for chunk in chunks:
        try:
            kwargs: dict = {"chat_id": chat_id, "text": chunk}
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
            await bot.send_message(**kwargs)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Post a message to Telegram")
    parser.add_argument("chat_id", type=int, help="Telegram chat ID")
    parser.add_argument("text", help="Message text to send")
    parser.add_argument("--reply-to", type=int, default=None, help="Message ID to reply to")
    args = parser.parse_args()

    asyncio.run(send_message(args.chat_id, args.text, args.reply_to))


if __name__ == "__main__":
    main()
