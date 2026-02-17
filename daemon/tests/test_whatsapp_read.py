"""Tests for adapters/whatsapp/whatsapp_read.py — inbox filtering."""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Import from adapter path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adapters", "whatsapp"))
import whatsapp_read
import _whatsapp_utils as utils


class TestReadInbox:
    """Tests for read_inbox() filtering."""

    @pytest.fixture
    def inbox_with_mixed(self, tmp_path, monkeypatch):
        """Create an inbox with mixed Slack and WhatsApp entries."""
        inbox = str(tmp_path / "inbox.jsonl")
        entries = [
            {"text": "slack msg", "channel": "C123", "handled": False},
            {"text": "wa msg 1", "channel": "whatsapp:+15551111111", "handled": False, "display_name": "Alice"},
            {"text": "wa msg 2", "channel": "whatsapp:+15552222222", "handled": True, "display_name": "Bob"},
            {"text": "wa msg 3", "channel": "whatsapp:+15551111111", "handled": False, "display_name": "Alice"},
        ]
        with open(inbox, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        monkeypatch.setattr(utils, "inbox_path", lambda: inbox)
        return inbox

    def test_filters_whatsapp_only(self, inbox_with_mixed):
        messages = whatsapp_read.read_inbox()
        assert len(messages) == 3  # wa msg 1, 2, 3 (all WhatsApp, including handled)

    def test_from_phone_filter(self, inbox_with_mixed):
        messages = whatsapp_read.read_inbox(from_phone="+15551111111")
        assert len(messages) == 2
        assert all("Alice" in m.get("display_name", "") for m in messages)

    def test_unhandled_filter(self, inbox_with_mixed):
        messages = whatsapp_read.read_inbox(unhandled_only=True)
        assert len(messages) == 2  # wa msg 1 and 3

    def test_combined_filters(self, inbox_with_mixed):
        messages = whatsapp_read.read_inbox(from_phone="+15551111111", unhandled_only=True)
        assert len(messages) == 2

    def test_empty_inbox(self, tmp_path, monkeypatch):
        inbox = str(tmp_path / "inbox.jsonl")
        with open(inbox, "w") as f:
            f.write("")
        monkeypatch.setattr(utils, "inbox_path", lambda: inbox)
        assert whatsapp_read.read_inbox() == []

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "inbox_path", lambda: str(tmp_path / "nonexistent.jsonl"))
        assert whatsapp_read.read_inbox() == []

    def test_limit(self, inbox_with_mixed):
        messages = whatsapp_read.read_inbox(limit=1)
        assert len(messages) == 1
