#!/usr/bin/env python3
"""
Post a response to a Discord channel.

Usage:
    python3 discord_post.py CHANNEL_ID TEXT [--reply-to MSG_ID]

Requires:
    DISCORD_BOT_TOKEN
    pip install discord.py
"""

import argparse
import asyncio
import os
import sys

# Add adapter dir to path for shared utilities
sys.path.insert(0, os.path.dirname(__file__))
from _discord_utils import split_message


async def send_message(channel_id: int, text: str, reply_to: int | None = None):
    """Send a message via Discord REST API (no gateway connection needed)."""
    import discord

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            channel = client.get_channel(channel_id)
            if not channel:
                channel = await client.fetch_channel(channel_id)

            chunks = split_message(text)

            for chunk in chunks:
                if reply_to:
                    try:
                        msg = await channel.fetch_message(reply_to)
                        await msg.reply(chunk)
                    except (discord.NotFound, discord.HTTPException):
                        await channel.send(chunk)
                else:
                    await channel.send(chunk)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            await client.close()
            sys.exit(1)

        await client.close()

    await client.start(token)


def main():
    parser = argparse.ArgumentParser(description="Post a message to Discord")
    parser.add_argument("channel_id", type=int, help="Discord channel ID")
    parser.add_argument("text", help="Message text to send")
    parser.add_argument("--reply-to", type=int, default=None, help="Message ID to reply to")
    args = parser.parse_args()

    asyncio.run(send_message(args.channel_id, args.text, args.reply_to))


if __name__ == "__main__":
    main()
