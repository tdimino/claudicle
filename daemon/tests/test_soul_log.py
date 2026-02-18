"""Tests for daemon/soul_log.py — structured cognitive cycle JSONL stream."""

import json
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

import soul_log


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

TRACE_A = "aaaaaaaaaaaa"
TRACE_B = "bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# TestEmit — core emit functionality
# ---------------------------------------------------------------------------

class TestEmit:
    """Test the emit() function."""

    def test_writes_jsonl_entry(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A, channel="C1", thread_ts="1.0",
                       user_id="U1", text="hello")

        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["phase"] == "stimulus"
        assert entry["trace_id"] == TRACE_A
        assert entry["user_id"] == "U1"
        assert entry["text"] == "hello"

    def test_common_envelope_fields(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("context", TRACE_A, channel="C1", thread_ts="1.0")

        entry = json.loads(open(log_file).readline())
        assert entry["phase"] == "context"
        assert entry["trace_id"] == TRACE_A
        assert entry["channel"] == "C1"
        assert entry["thread_ts"] == "1.0"
        assert "ts" in entry

    def test_timestamp_is_utc_iso(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)

        entry = json.loads(open(log_file).readline())
        dt = datetime.fromisoformat(entry["ts"])
        assert dt.tzinfo == timezone.utc

    def test_appends_multiple_entries(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)
        soul_log.emit("context", TRACE_A)
        soul_log.emit("response", TRACE_A)

        entries = soul_log.read_log(log_file)
        assert len(entries) == 3
        assert [e["phase"] for e in entries] == ["stimulus", "context", "response"]

    def test_kwargs_merged_into_entry(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("cognition", TRACE_A, step="internalMonologue",
                       verb="pondered", content="thinking...")

        entry = json.loads(open(log_file).readline())
        assert entry["step"] == "internalMonologue"
        assert entry["verb"] == "pondered"
        assert entry["content"] == "thinking..."

    def test_handles_non_serializable_kwargs(self, tmp_path, monkeypatch):
        """default=str in json.dumps should handle odd types."""
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("error", TRACE_A, detail={"nested": set([1, 2, 3])})

        entry = json.loads(open(log_file).readline())
        assert entry["phase"] == "error"
        # set is serialized via default=str
        assert "1" in entry["detail"]["nested"] or "{" in entry["detail"]["nested"]

    def test_silent_on_write_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(soul_log, "LOG_PATH", str(tmp_path / "soul.jsonl"))
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        with patch("builtins.open", side_effect=OSError("disk full")):
            # Should not raise
            soul_log.emit("stimulus", TRACE_A)

    def test_silent_on_serialization_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(soul_log, "LOG_PATH", str(tmp_path / "soul.jsonl"))
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        with patch("soul_log.json.dumps", side_effect=TypeError("boom")):
            soul_log.emit("stimulus", TRACE_A)

    def test_disabled_flag_skips_write(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", False)

        soul_log.emit("stimulus", TRACE_A, text="hello")

        import os
        assert not os.path.exists(log_file)

    def test_unicode_roundtrips(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        text = "Hello \u4e16\u754c \U0001f525 \u0645\u0631\u062d\u0628\u0627"
        soul_log.emit("cognition", TRACE_A, content=text)

        entries = soul_log.read_log(log_file)
        assert entries[0]["content"] == text


# ---------------------------------------------------------------------------
# TestReadLog — reader functionality
# ---------------------------------------------------------------------------

class TestReadLog:
    """Test the read_log() function."""

    def test_read_all_entries(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)
        soul_log.emit("response", TRACE_A)

        entries = soul_log.read_log(log_file)
        assert len(entries) == 2
        assert entries[0]["phase"] == "stimulus"
        assert entries[1]["phase"] == "response"

    def test_read_last_n(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        for i in range(5):
            soul_log.emit("cognition", TRACE_A, step_idx=i)

        entries = soul_log.read_log(log_file, last_n=2)
        assert len(entries) == 2
        assert entries[0]["step_idx"] == 3
        assert entries[1]["step_idx"] == 4

    def test_read_missing_file(self):
        entries = soul_log.read_log("/nonexistent/soul.jsonl")
        assert entries == []

    def test_read_empty_file(self, tmp_path):
        log_file = tmp_path / "soul.jsonl"
        log_file.write_text("")
        assert soul_log.read_log(str(log_file)) == []

    def test_skips_malformed_lines(self, tmp_path):
        log_file = tmp_path / "soul.jsonl"
        log_file.write_text(
            '{"phase":"stimulus","trace_id":"aaa"}\n'
            'NOT JSON\n'
            '{"phase":"response","trace_id":"aaa"}\n'
        )
        entries = soul_log.read_log(str(log_file))
        assert len(entries) == 2
        assert entries[0]["phase"] == "stimulus"
        assert entries[1]["phase"] == "response"

    def test_read_defaults_to_log_path(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)

        entries = soul_log.read_log()
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# TestReadTrace — trace filtering
# ---------------------------------------------------------------------------

class TestReadTrace:
    """Test the read_trace() function."""

    def test_filters_by_trace_id(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)
        soul_log.emit("stimulus", TRACE_B)
        soul_log.emit("context", TRACE_A)
        soul_log.emit("response", TRACE_B)

        trace_a = soul_log.read_trace(TRACE_A, log_file)
        assert len(trace_a) == 2
        assert all(e["trace_id"] == TRACE_A for e in trace_a)

        trace_b = soul_log.read_trace(TRACE_B, log_file)
        assert len(trace_b) == 2

    def test_empty_for_unknown_trace(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        soul_log.emit("stimulus", TRACE_A)

        assert soul_log.read_trace("zzzzzzzzzzzz", log_file) == []


# ---------------------------------------------------------------------------
# TestPhaseSchemas — one per phase, verify fields
# ---------------------------------------------------------------------------

class TestPhaseSchemas:
    """Verify each phase produces the expected fields."""

    def _emit_and_read(self, tmp_path, monkeypatch, phase, **kwargs):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)
        soul_log.emit(phase, TRACE_A, channel="C1", thread_ts="1.0", **kwargs)
        return json.loads(open(log_file).readline())

    def test_stimulus_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "stimulus",
                                     origin="slack", user_id="U1",
                                     display_name="Tom", text="hi",
                                     text_length=2)
        assert entry["phase"] == "stimulus"
        assert entry["origin"] == "slack"
        assert entry["user_id"] == "U1"
        assert entry["text_length"] == 2

    def test_context_schema(self, tmp_path, monkeypatch):
        gates = {"skills_injected": True, "user_model_injected": False}
        entry = self._emit_and_read(tmp_path, monkeypatch, "context",
                                     gates=gates, prompt_length=5000,
                                     pipeline_mode="unified",
                                     interaction_count=3)
        assert entry["gates"]["skills_injected"] is True
        assert entry["prompt_length"] == 5000
        assert entry["pipeline_mode"] == "unified"

    def test_cognition_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "cognition",
                                     step="internalMonologue", verb="pondered",
                                     content="deep thought",
                                     content_length=12)
        assert entry["step"] == "internalMonologue"
        assert entry["verb"] == "pondered"
        assert entry["content_length"] == 12

    def test_decision_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "decision",
                                     gate="user_model_check", result=True,
                                     content="Should update?")
        assert entry["gate"] == "user_model_check"
        assert entry["result"] is True

    def test_memory_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "memory",
                                     action="user_model_update", target="U1",
                                     change_note="added interest",
                                     detail={})
        assert entry["action"] == "user_model_update"
        assert entry["target"] == "U1"

    def test_response_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "response",
                                     text="Here's my answer", text_length=17,
                                     truncated=False, elapsed_ms=4200)
        assert entry["text"] == "Here's my answer"
        assert entry["elapsed_ms"] == 4200
        assert entry["truncated"] is False

    def test_error_schema(self, tmp_path, monkeypatch):
        entry = self._emit_and_read(tmp_path, monkeypatch, "error",
                                     source="soul_engine.parse_response",
                                     error="No dialogue found",
                                     error_type="ValueError")
        assert entry["source"] == "soul_engine.parse_response"
        assert entry["error_type"] == "ValueError"


# ---------------------------------------------------------------------------
# TestThreadSafety — concurrent writes
# ---------------------------------------------------------------------------

class TestThreadSafety:
    """Verify concurrent writes don't corrupt the log."""

    def test_concurrent_writes_no_corruption(self, tmp_path, monkeypatch):
        log_file = str(tmp_path / "soul.jsonl")
        monkeypatch.setattr(soul_log, "LOG_PATH", log_file)
        monkeypatch.setattr(soul_log, "SOUL_LOG_ENABLED", True)

        n_threads = 8
        n_per_thread = 20
        barrier = threading.Barrier(n_threads)

        def writer(thread_id):
            barrier.wait()
            for i in range(n_per_thread):
                soul_log.emit("cognition", f"trace_{thread_id:02d}",
                               step_idx=i, thread_id=thread_id)

        threads = [threading.Thread(target=writer, args=(t,))
                   for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = soul_log.read_log(log_file)
        assert len(entries) == n_threads * n_per_thread
        # Every line is valid JSON (no interleaving)
        with open(log_file) as f:
            for line in f:
                json.loads(line.strip())
