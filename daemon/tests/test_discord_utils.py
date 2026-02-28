"""Tests for Discord adapter utilities."""

import sys
import os

# Add adapters to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adapters", "discord"))

from _discord_utils import (
    channel_from_id,
    id_from_channel,
    is_discord_channel,
    split_message,
    get_allowed_channels,
)


class TestChannelDetection:
    def test_is_discord_channel(self):
        assert is_discord_channel("discord:123456789")
        assert not is_discord_channel("slack:C04ABC123")
        assert not is_discord_channel("telegram:987654321")
        assert not is_discord_channel("terminal:abc")

    def test_channel_from_id(self):
        assert channel_from_id(123456789) == "discord:123456789"
        assert channel_from_id("987654321") == "discord:987654321"

    def test_id_from_channel(self):
        assert id_from_channel("discord:123456789") == 123456789

    def test_roundtrip(self):
        original_id = 123456789012345678
        channel = channel_from_id(original_id)
        assert id_from_channel(channel) == original_id


class TestMessageSplitting:
    def test_short_message_unchanged(self):
        text = "Hello world"
        assert split_message(text) == [text]

    def test_exactly_at_limit(self):
        text = "a" * 2000
        assert split_message(text) == [text]

    def test_over_limit_splits_at_newline(self):
        line = "a" * 999 + "\n"  # 1000 chars per line
        text = line * 3  # 3000 chars total
        chunks = split_message(text)
        assert len(chunks) == 2
        for chunk in chunks:
            assert len(chunk) <= 2000

    def test_no_newline_splits_at_max(self):
        text = "a" * 4000
        chunks = split_message(text)
        assert len(chunks) == 2
        assert len(chunks[0]) == 2000
        assert len(chunks[1]) == 2000

    def test_empty_message(self):
        assert split_message("") == [""]

    def test_custom_limit(self):
        text = "Hello world, this is a test"
        chunks = split_message(text, max_length=10)
        assert all(len(c) <= 10 for c in chunks)


class TestAllowedChannels:
    def test_empty_returns_empty_set(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "")
        # Re-import to pick up new env
        from importlib import reload
        import _discord_utils
        reload(_discord_utils)
        assert _discord_utils.get_allowed_channels() == set()

    def test_single_channel(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "123456789")
        from importlib import reload
        import _discord_utils
        reload(_discord_utils)
        assert _discord_utils.get_allowed_channels() == {"123456789"}

    def test_multiple_channels(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", "111,222,333")
        from importlib import reload
        import _discord_utils
        reload(_discord_utils)
        assert _discord_utils.get_allowed_channels() == {"111", "222", "333"}

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_DISCORD_ALLOWED_CHANNELS", " 111 , 222 , 333 ")
        from importlib import reload
        import _discord_utils
        reload(_discord_utils)
        assert _discord_utils.get_allowed_channels() == {"111", "222", "333"}
