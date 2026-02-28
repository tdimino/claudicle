"""Shared utilities for the Discord adapter."""

import os


# ---------------------------------------------------------------------------
# Channel ID helpers
# ---------------------------------------------------------------------------

def is_discord_channel(channel: str) -> bool:
    return channel.startswith("discord:")


def channel_from_id(channel_id: str | int) -> str:
    """Convert a Discord channel ID to Claudicle channel format."""
    return f"discord:{channel_id}"


def id_from_channel(channel: str) -> int:
    """Extract the numeric Discord channel ID from a Claudicle channel string."""
    return int(channel.replace("discord:", ""))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_ALLOWED_CHANNELS = os.environ.get("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "")
DISCORD_RESPOND_TO_MENTIONS = os.environ.get("CLAUDICLE_DISCORD_RESPOND_TO_MENTIONS", "true").lower() == "true"
DISCORD_RESPOND_TO_DMS = os.environ.get("CLAUDICLE_DISCORD_RESPOND_TO_DMS", "true").lower() == "true"


def get_allowed_channels() -> set[str]:
    """Parse CLAUDICLE_DISCORD_ALLOWED_CHANNELS into a set of channel ID strings."""
    if not DISCORD_ALLOWED_CHANNELS:
        return set()  # empty = all channels
    return {ch.strip() for ch in DISCORD_ALLOWED_CHANNELS.split(",") if ch.strip()}


# ---------------------------------------------------------------------------
# Message splitting (Discord limit: 2000 chars)
# ---------------------------------------------------------------------------

def split_message(text: str, max_length: int = 2000) -> list[str]:
    """Split long messages for Discord's 2000-char limit."""
    if len(text) <= max_length:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_point = text.rfind("\n", 0, max_length)
        if split_point == -1:
            split_point = max_length
        chunks.append(text[:split_point])
        text = text[split_point:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def adapter_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def daemon_dir() -> str:
    return os.path.join(adapter_dir(), "..", "..", "daemon")


def inbox_path() -> str:
    return os.path.join(daemon_dir(), "inbox.jsonl")
