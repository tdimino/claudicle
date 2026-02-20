"""Tests for daemon/inbox_watcher.py — inbox I/O and process_entry integration."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from engine import context, soul_engine
from adapters import inbox_watcher
from memory import working_memory
from tests.helpers import MockProvider, make_inbox_entry, write_inbox_entry


# ---------------------------------------------------------------------------
# Inbox I/O tests
# ---------------------------------------------------------------------------

class TestReadUnhandled:
    """Tests for read_unhandled()."""

    def test_empty_inbox(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        assert inbox_watcher.read_unhandled() == []

    def test_missing_inbox_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(inbox_watcher, "INBOX", str(tmp_path / "nonexistent.jsonl"))
        assert inbox_watcher.read_unhandled() == []

    def test_reads_unhandled(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        write_inbox_entry(inbox_file, make_inbox_entry(text="msg1"))
        write_inbox_entry(inbox_file, make_inbox_entry(text="msg2", handled=True))
        write_inbox_entry(inbox_file, make_inbox_entry(text="msg3"))

        entries = inbox_watcher.read_unhandled()
        assert len(entries) == 2
        assert entries[0]["text"] == "msg1"
        assert entries[1]["text"] == "msg3"

    def test_line_index_set(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        write_inbox_entry(inbox_file, make_inbox_entry(text="first"))
        entries = inbox_watcher.read_unhandled()
        assert entries[0]["_line_index"] == 0

    def test_skips_malformed_json(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        with open(inbox_file, "w") as f:
            f.write("not json\n")
            f.write(json.dumps(make_inbox_entry(text="valid")) + "\n")
        entries = inbox_watcher.read_unhandled()
        assert len(entries) == 1
        assert entries[0]["text"] == "valid"


class TestMarkHandled:
    """Tests for mark_handled()."""

    def test_marks_entry(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        write_inbox_entry(inbox_file, make_inbox_entry(text="msg"))
        inbox_watcher.mark_handled(0)

        with open(inbox_file) as f:
            entry = json.loads(f.readline())
        assert entry["handled"] is True

    def test_invalid_index_no_crash(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        write_inbox_entry(inbox_file, make_inbox_entry(text="msg"))
        inbox_watcher.mark_handled(99)  # out of bounds
        # Original entry unchanged
        with open(inbox_file) as f:
            entry = json.loads(f.readline())
        assert entry["handled"] is False

    def test_negative_index_skipped(self, inbox_file, monkeypatch):
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        inbox_watcher.mark_handled(-1)  # should not crash


# ---------------------------------------------------------------------------
# process_entry() integration tests
# ---------------------------------------------------------------------------

class TestProcessEntry:
    """Tests for process_entry() — unified and split mode routing."""

    @pytest.fixture
    def mock_slack_post(self, monkeypatch):
        mock = MagicMock()
        monkeypatch.setattr(inbox_watcher, "slack_post", mock)
        monkeypatch.setattr(inbox_watcher, "slack_react", MagicMock())
        return mock

    @pytest.fixture
    def mock_subprocess(self, monkeypatch):
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stderr = b""
        monkeypatch.setattr("subprocess.run", mock)
        return mock

    @pytest.mark.asyncio
    async def test_unified_mode(self, monkeypatch, soul_md_path, inbox_file, mock_slack_post):
        """Unified mode: build_prompt → agenerate → parse_response → slack_post."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        monkeypatch.setattr("engine.pipeline.is_split_mode", lambda: False)

        mock_p = MockProvider(
            name="mock",
            response='<external_dialogue verb="said">Unified response</external_dialogue>\n<user_model_check>false</user_model_check>',
        )
        monkeypatch.setattr("providers.get_provider", lambda name: mock_p)

        entry = make_inbox_entry(text="test msg", _line_index=0)
        write_inbox_entry(inbox_file, make_inbox_entry(text="test msg"))

        await inbox_watcher.process_entry(entry)
        mock_slack_post.assert_called_once()
        args = mock_slack_post.call_args
        assert "Unified response" in args[0][1]

    @pytest.mark.asyncio
    async def test_split_mode(self, monkeypatch, soul_md_path, inbox_file, mock_slack_post):
        """Split mode: pipeline.run_pipeline path."""
        from engine import pipeline
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        monkeypatch.setattr("engine.pipeline.is_split_mode", lambda: True)

        # Mock the pipeline to return a result
        async def fake_pipeline(text, user_id, channel, thread_ts, display_name=None):
            result = pipeline.PipelineResult()
            result.dialogue = "Split response"
            return result

        monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline)

        entry = make_inbox_entry(text="test", _line_index=0)
        write_inbox_entry(inbox_file, make_inbox_entry(text="test"))

        await inbox_watcher.process_entry(entry)
        mock_slack_post.assert_called_once()
        assert "Split response" in mock_slack_post.call_args[0][1]

    @pytest.mark.asyncio
    async def test_whatsapp_routing(self, monkeypatch, soul_md_path, inbox_file, mock_subprocess):
        """WhatsApp channel routes to whatsapp_send subprocess."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        monkeypatch.setattr("engine.pipeline.is_split_mode", lambda: False)

        mock_p = MockProvider(
            name="mock",
            response='<external_dialogue verb="said">WA response</external_dialogue>\n<user_model_check>false</user_model_check>',
        )
        monkeypatch.setattr("providers.get_provider", lambda name: mock_p)

        entry = make_inbox_entry(
            text="hello", channel="whatsapp:+15551234567",
            _line_index=0,
        )
        write_inbox_entry(inbox_file, make_inbox_entry(text="hello", channel="whatsapp:+15551234567"))

        await inbox_watcher.process_entry(entry)
        # Should call subprocess.run with whatsapp_send.py
        assert mock_subprocess.called
        cmd = mock_subprocess.call_args[0][0]
        assert "whatsapp_send.py" in cmd[1]

    @pytest.mark.asyncio
    async def test_whatsapp_failure_not_marked_handled(self, monkeypatch, soul_md_path, inbox_file):
        """Failed WhatsApp send → entry NOT marked handled for retry."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        monkeypatch.setattr("engine.pipeline.is_split_mode", lambda: False)

        mock_p = MockProvider(
            name="mock",
            response='<external_dialogue verb="said">msg</external_dialogue>\n<user_model_check>false</user_model_check>',
        )
        monkeypatch.setattr("providers.get_provider", lambda name: mock_p)

        mock_sub = MagicMock()
        mock_sub.return_value.returncode = 1
        mock_sub.return_value.stderr = b"gateway error"
        monkeypatch.setattr("subprocess.run", mock_sub)

        entry = make_inbox_entry(
            text="hello", channel="whatsapp:+15551234567",
            _line_index=0,
        )
        write_inbox_entry(inbox_file, make_inbox_entry(text="hello", channel="whatsapp:+15551234567"))

        await inbox_watcher.process_entry(entry)
        # Entry should NOT be marked handled
        with open(inbox_file) as f:
            line = json.loads(f.readline())
        assert line["handled"] is False

    @pytest.mark.asyncio
    async def test_response_truncation(self, monkeypatch, soul_md_path, inbox_file, mock_slack_post):
        """Long responses get truncated at MAX_RESPONSE_LENGTH."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
        monkeypatch.setattr("engine.pipeline.is_split_mode", lambda: False)
        monkeypatch.setattr(inbox_watcher, "MAX_RESPONSE_LENGTH", 50)

        long_text = "x" * 200
        mock_p = MockProvider(
            name="mock",
            response=f'<external_dialogue verb="said">{long_text}</external_dialogue>\n<user_model_check>false</user_model_check>',
        )
        monkeypatch.setattr("providers.get_provider", lambda name: mock_p)

        entry = make_inbox_entry(text="test", _line_index=0)
        write_inbox_entry(inbox_file, make_inbox_entry(text="test"))

        await inbox_watcher.process_entry(entry)
        posted_text = mock_slack_post.call_args[0][1]
        assert "_(truncated)_" in posted_text
