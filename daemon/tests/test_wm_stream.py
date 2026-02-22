"""Tests for monitoring/wm_stream.py — working memory JSONL stream."""

import json
import threading

import pytest

from monitoring import wm_stream


# -- Emit basics -------------------------------------------------------------

class TestEmit:
    def test_writes_jsonl_entry(self, tmp_path, monkeypatch):
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        wm_stream.emit(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="userMessage", content="hello",
        )

        with open(stream_file) as f:
            entry = json.loads(f.readline())
        assert entry["entry_type"] == "userMessage"
        assert entry["content"] == "hello"
        assert entry["user_id"] == "tom"

    def test_common_fields(self, tmp_path, monkeypatch):
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        wm_stream.emit(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="internalMonologue", content="thinking...",
            verb="pondered", trace_id="abc123", display_name="Tom",
        )

        with open(stream_file) as f:
            entry = json.loads(f.readline())
        assert "ts" in entry
        assert entry["channel"] == "C1"
        assert entry["thread_ts"] == "T1"
        assert entry["verb"] == "pondered"
        assert entry["trace_id"] == "abc123"
        assert entry["display_name"] == "Tom"

    def test_metadata_roundtrip(self, tmp_path, monkeypatch):
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        wm_stream.emit(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="mentalQuery", content="gate check",
            metadata={"result": True},
        )

        with open(stream_file) as f:
            entry = json.loads(f.readline())
        assert entry["metadata"] == {"result": True}

    def test_disabled_flag_skips(self, tmp_path, monkeypatch):
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", False)

        wm_stream.emit(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="userMessage", content="hello",
        )

        import os
        assert not os.path.exists(stream_file)

    def test_silent_on_write_failure(self, tmp_path, monkeypatch):
        """Emit should never raise, even on I/O errors."""
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", "/nonexistent/dir/wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        # Should not raise
        wm_stream.emit(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="userMessage", content="hello",
        )


# -- Thread safety -----------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_writes(self, tmp_path, monkeypatch):
        """Multiple threads writing simultaneously should produce valid JSONL."""
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        n_threads = 8
        n_writes = 20
        errors = []

        def writer(thread_id):
            try:
                for i in range(n_writes):
                    wm_stream.emit(
                        channel="C1", thread_ts="T1", user_id=f"user-{thread_id}",
                        entry_type="userMessage", content=f"msg-{thread_id}-{i}",
                        trace_id=f"trace-{thread_id}",
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        # Verify all lines are valid JSON
        with open(stream_file) as f:
            lines = f.readlines()
        assert len(lines) == n_threads * n_writes
        for line in lines:
            entry = json.loads(line)
            assert "entry_type" in entry
            assert "content" in entry


# -- Integration with working_memory.add() ----------------------------------

class TestWorkingMemoryIntegration:
    def test_add_emits_to_stream(self, tmp_path, monkeypatch):
        """working_memory.add() should also write to the WM stream."""
        stream_file = str(tmp_path / "wm.jsonl")
        monkeypatch.setattr(wm_stream, "WM_STREAM_PATH", stream_file)
        monkeypatch.setattr(wm_stream, "WM_STREAM_ENABLED", True)

        from memory import working_memory
        working_memory.add(
            channel="C1", thread_ts="T1", user_id="tom",
            entry_type="userMessage", content="hello from add()",
            trace_id="abc123",
        )

        with open(stream_file) as f:
            entry = json.loads(f.readline())
        assert entry["entry_type"] == "userMessage"
        assert entry["content"] == "hello from add()"
        assert entry["trace_id"] == "abc123"
