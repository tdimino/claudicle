"""Shared utilities for the Telegram adapter."""

import os


# ---------------------------------------------------------------------------
# Channel ID helpers
# ---------------------------------------------------------------------------

def is_telegram_channel(channel: str) -> bool:
    return channel.startswith("telegram:")


def channel_from_id(chat_id: str | int) -> str:
    """Convert a Telegram chat ID to Claudicle channel format."""
    return f"telegram:{chat_id}"


def id_from_channel(channel: str) -> int:
    """Extract the numeric Telegram chat ID from a Claudicle channel string."""
    return int(channel.replace("telegram:", ""))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_CHATS = os.environ.get("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "")
TELEGRAM_RESPOND_TO_MENTIONS = os.environ.get("CLAUDICLE_TELEGRAM_RESPOND_TO_MENTIONS", "true").lower() == "true"
TELEGRAM_RESPOND_TO_DMS = os.environ.get("CLAUDICLE_TELEGRAM_RESPOND_TO_DMS", "true").lower() == "true"


def get_allowed_chats() -> set[str]:
    """Parse CLAUDICLE_TELEGRAM_ALLOWED_CHATS into a set of chat ID strings."""
    if not TELEGRAM_ALLOWED_CHATS:
        return set()  # empty = all chats
    return {ch.strip() for ch in TELEGRAM_ALLOWED_CHATS.split(",") if ch.strip()}


# ---------------------------------------------------------------------------
# Message splitting (Telegram limit: 4096 chars)
# ---------------------------------------------------------------------------

def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split long messages for Telegram's 4096-char limit."""
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
