"""Tests for Telegram adapter utilities."""

import sys
import os

# Add adapters to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adapters", "telegram"))

from _telegram_utils import (
    channel_from_id,
    id_from_channel,
    is_telegram_channel,
    split_message,
    get_allowed_chats,
)


class TestChannelDetection:
    def test_is_telegram_channel(self):
        assert is_telegram_channel("telegram:987654321")
        assert not is_telegram_channel("discord:123456789")
        assert not is_telegram_channel("slack:C04ABC123")
        assert not is_telegram_channel("terminal:abc")

    def test_channel_from_id(self):
        assert channel_from_id(987654321) == "telegram:987654321"
        assert channel_from_id("123456789") == "telegram:123456789"

    def test_id_from_channel(self):
        assert id_from_channel("telegram:987654321") == 987654321

    def test_negative_chat_id(self):
        """Group chats have negative IDs in Telegram."""
        channel = channel_from_id(-100123456789)
        assert channel == "telegram:-100123456789"
        assert id_from_channel(channel) == -100123456789

    def test_roundtrip(self):
        original_id = 987654321
        channel = channel_from_id(original_id)
        assert id_from_channel(channel) == original_id


class TestMessageSplitting:
    def test_short_message_unchanged(self):
        text = "Hello world"
        assert split_message(text) == [text]

    def test_exactly_at_limit(self):
        text = "a" * 4096
        assert split_message(text) == [text]

    def test_over_limit_splits_at_newline(self):
        line = "a" * 2047 + "\n"  # 2048 chars per line
        text = line * 3  # 6144 chars total
        chunks = split_message(text)
        assert len(chunks) == 2
        for chunk in chunks:
            assert len(chunk) <= 4096

    def test_no_newline_splits_at_max(self):
        text = "a" * 8192
        chunks = split_message(text)
        assert len(chunks) == 2
        assert len(chunks[0]) == 4096
        assert len(chunks[1]) == 4096

    def test_empty_message(self):
        assert split_message("") == [""]

    def test_custom_limit(self):
        text = "Hello world, this is a test"
        chunks = split_message(text, max_length=10)
        assert all(len(c) <= 10 for c in chunks)


class TestAllowedChats:
    def test_empty_returns_empty_set(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "")
        from importlib import reload
        import _telegram_utils
        reload(_telegram_utils)
        assert _telegram_utils.get_allowed_chats() == set()

    def test_single_chat(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "987654321")
        from importlib import reload
        import _telegram_utils
        reload(_telegram_utils)
        assert _telegram_utils.get_allowed_chats() == {"987654321"}

    def test_multiple_chats(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "111,222,333")
        from importlib import reload
        import _telegram_utils
        reload(_telegram_utils)
        assert _telegram_utils.get_allowed_chats() == {"111", "222", "333"}

    def test_negative_group_ids(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TELEGRAM_ALLOWED_CHATS", "-100111,-100222")
        from importlib import reload
        import _telegram_utils
        reload(_telegram_utils)
        assert _telegram_utils.get_allowed_chats() == {"-100111", "-100222"}
