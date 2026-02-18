"""Tests for daemon/slack_log.py — Bolt JSONL event logging middleware."""

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import slack_log


# ---------------------------------------------------------------------------
# Sample Slack event bodies
# ---------------------------------------------------------------------------

MENTION_BODY = {
    "type": "event_callback",
    "event": {
        "type": "app_mention",
        "user": "U123",
        "text": "<@BOT> hello",
        "channel": "C456",
        "ts": "1700000000.000001",
    },
    "team_id": "T789",
    "event_id": "Ev001",
}

DM_BODY = {
    "type": "event_callback",
    "event": {
        "type": "message",
        "channel_type": "im",
        "user": "U123",
        "text": "hi there",
        "channel": "D999",
        "ts": "1700000000.000002",
    },
    "team_id": "T789",
    "event_id": "Ev002",
}

UNICODE_BODY = {
    "type": "event_callback",
    "event": {
        "type": "message",
        "user": "U123",
        "text": "Hello \u4e16\u754c \U0001f525 \u0645\u0631\u062d\u0628\u0627",
        "channel": "C456",
        "ts": "1700000000.000003",
    },
    "team_id": "T789",
    "event_id": "Ev003",
}


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------

class TestLogAllEvents:
    """Test the Bolt global middleware function."""

    def test_writes_jsonl_entry(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        called = []
        slack_log.log_all_events(body=MENTION_BODY, next=lambda: called.append(True))

        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["type"] == "event_callback"
        assert entry["event"]["type"] == "app_mention"
        assert entry["team_id"] == "T789"
        assert entry["event_id"] == "Ev001"

    def test_calls_next(self, tmp_path, monkeypatch):
        monkeypatch.setattr(slack_log, "LOG_PATH", str(tmp_path / "events.jsonl"))

        called = []
        slack_log.log_all_events(body=MENTION_BODY, next=lambda: called.append(True))
        assert called == [True]

    def test_appends_multiple_events(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        noop = lambda: None
        slack_log.log_all_events(body=MENTION_BODY, next=noop)
        slack_log.log_all_events(body=DM_BODY, next=noop)

        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) == 2

        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e1["event_id"] == "Ev001"
        assert e2["event_id"] == "Ev002"

    def test_timestamp_is_utc_iso(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        slack_log.log_all_events(body=MENTION_BODY, next=lambda: None)

        entry = json.loads(open(log_file).readline())
        dt = datetime.fromisoformat(entry["ts"])
        assert dt.tzinfo == timezone.utc

    def test_handles_empty_body(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        called = []
        slack_log.log_all_events(body={}, next=lambda: called.append(True))

        entry = json.loads(open(log_file).readline())
        assert entry["type"] is None
        assert entry["event"] == {}
        assert called == [True]

    def test_calls_next_on_write_failure(self, tmp_path, monkeypatch):
        """next() must always be called even when file write fails."""
        monkeypatch.setattr(slack_log, "LOG_PATH", str(tmp_path / "events.jsonl"))

        called = []
        with patch("builtins.open", side_effect=OSError("disk full")):
            slack_log.log_all_events(body=MENTION_BODY, next=lambda: called.append(True))
        assert called == [True]

    def test_calls_next_on_serialization_error(self, tmp_path, monkeypatch):
        """next() must be called even if json.dumps raises TypeError."""
        monkeypatch.setattr(slack_log, "LOG_PATH", str(tmp_path / "events.jsonl"))

        called = []
        with patch("slack_log.json.dumps", side_effect=TypeError("not serializable")):
            slack_log.log_all_events(body=MENTION_BODY, next=lambda: called.append(True))
        assert called == [True]

    def test_unicode_event_roundtrips(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        slack_log.log_all_events(body=UNICODE_BODY, next=lambda: None)

        entries = slack_log.read_log(log_file)
        assert entries[0]["event"]["text"] == UNICODE_BODY["event"]["text"]


# ---------------------------------------------------------------------------
# read_log tests
# ---------------------------------------------------------------------------

class TestReadLog:
    """Test the JSONL log reader utility."""

    def test_read_all_entries(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        noop = lambda: None
        slack_log.log_all_events(body=MENTION_BODY, next=noop)
        slack_log.log_all_events(body=DM_BODY, next=noop)

        entries = slack_log.read_log(log_file)
        assert len(entries) == 2
        assert entries[0]["event_id"] == "Ev001"
        assert entries[1]["event_id"] == "Ev002"

    def test_read_last_n(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        noop = lambda: None
        for i in range(5):
            body = {**MENTION_BODY, "event_id": f"Ev{i:03d}"}
            slack_log.log_all_events(body=body, next=noop)

        entries = slack_log.read_log(log_file, last_n=2)
        assert len(entries) == 2
        assert entries[0]["event_id"] == "Ev003"
        assert entries[1]["event_id"] == "Ev004"

    def test_last_n_exceeds_total(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        noop = lambda: None
        for _ in range(3):
            slack_log.log_all_events(body=MENTION_BODY, next=noop)

        entries = slack_log.read_log(log_file, last_n=100)
        assert len(entries) == 3

    def test_read_missing_file(self):
        entries = slack_log.read_log("/nonexistent/events.jsonl")
        assert entries == []

    def test_read_empty_file(self, tmp_path):
        log_file = tmp_path / "events.jsonl"
        log_file.write_text("")
        assert slack_log.read_log(str(log_file)) == []

    def test_read_whitespace_only_file(self, tmp_path):
        log_file = tmp_path / "events.jsonl"
        log_file.write_text("\n\n  \n")
        assert slack_log.read_log(str(log_file)) == []

    def test_skips_malformed_lines(self, tmp_path):
        """Corrupted lines should be skipped, not crash the reader."""
        log_file = tmp_path / "events.jsonl"
        log_file.write_text(
            '{"event_id":"Ev001","ts":"2024-01-01","type":null,"event":{},"team_id":null}\n'
            'THIS IS NOT JSON\n'
            '{"event_id":"Ev002","ts":"2024-01-01","type":null,"event":{},"team_id":null}\n'
        )
        entries = slack_log.read_log(str(log_file))
        assert len(entries) == 2
        assert entries[0]["event_id"] == "Ev001"
        assert entries[1]["event_id"] == "Ev002"

    def test_read_defaults_to_log_path(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(slack_log, "LOG_PATH", log_file)

        slack_log.log_all_events(body=MENTION_BODY, next=lambda: None)

        entries = slack_log.read_log()
        assert len(entries) == 1
