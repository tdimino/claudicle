"""Tests for daemon/working_memory.py — CRUD, TTL cleanup, format_for_prompt."""

import json
import time
from unittest.mock import patch

import working_memory


class TestAdd:
    """Tests for working_memory.add()."""

    def test_add_and_get_recent(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "hello")
        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["content"] == "hello"
        assert entries[0]["entry_type"] == "userMessage"

    def test_thread_scoping(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "thread1")
        working_memory.add("C1", "T2", "U1", "userMessage", "thread2")
        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["content"] == "thread1"

    def test_verb_stored(self):
        working_memory.add("C1", "T1", "U1", "internalMonologue", "deep thought", verb="pondered")
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["verb"] == "pondered"

    def test_metadata_roundtrip(self):
        meta = {"result": True, "confidence": 0.9}
        working_memory.add("C1", "T1", "U1", "mentalQuery", "check", metadata=meta)
        entries = working_memory.get_recent("C1", "T1")
        loaded = json.loads(entries[0]["metadata"])
        assert loaded["result"] is True
        assert loaded["confidence"] == 0.9

    def test_none_metadata(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "hi")
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["metadata"] is None


class TestGetRecent:
    """Tests for get_recent() ordering and limit."""

    def test_limit(self):
        for i in range(10):
            working_memory.add("C1", "T1", "U1", "userMessage", f"msg{i}")
        entries = working_memory.get_recent("C1", "T1", limit=3)
        assert len(entries) == 3
        contents = {e["content"] for e in entries}
        assert contents == {"msg7", "msg8", "msg9"}

    def test_chronological_order(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "first")
        working_memory.add("C1", "T1", "U1", "userMessage", "second")
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["content"] == "first"
        assert entries[1]["content"] == "second"


class TestGetUserHistory:
    """Tests for get_user_history() across threads."""

    def test_cross_thread(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "thread1")
        working_memory.add("C2", "T2", "U1", "userMessage", "thread2")
        working_memory.add("C1", "T1", "U2", "userMessage", "other_user")
        entries = working_memory.get_user_history("U1")
        assert len(entries) == 2


class TestFormatForPrompt:
    """Tests for format_for_prompt()."""

    def test_empty(self):
        assert working_memory.format_for_prompt([]) == ""

    def test_user_message(self):
        entries = [{"entry_type": "userMessage", "content": "hi", "verb": None, "metadata": None}]
        assert working_memory.format_for_prompt(entries) == 'User said: "hi"'

    def test_internal_monologue(self):
        entries = [{"entry_type": "internalMonologue", "content": "hmm", "verb": "pondered", "metadata": None}]
        assert working_memory.format_for_prompt(entries) == 'Claudius pondered: "hmm"'

    def test_external_dialog(self):
        entries = [{"entry_type": "externalDialog", "content": "yes", "verb": "explained", "metadata": None}]
        assert working_memory.format_for_prompt(entries) == 'Claudius explained: "yes"'

    def test_mental_query_with_result(self):
        entries = [{
            "entry_type": "mentalQuery",
            "content": "update model?",
            "verb": "evaluated",
            "metadata": json.dumps({"result": True}),
        }]
        result = working_memory.format_for_prompt(entries)
        assert "evaluated" in result
        assert "True" in result

    def test_tool_action(self):
        entries = [{"entry_type": "toolAction", "content": "read file.py", "verb": None, "metadata": None}]
        assert working_memory.format_for_prompt(entries) == "Claudius read file.py"

    def test_custom_soul_name(self):
        entries = [{"entry_type": "internalMonologue", "content": "x", "verb": None, "metadata": None}]
        result = working_memory.format_for_prompt(entries, soul_name="Oracle")
        assert result.startswith("Oracle")


class TestTraceId:
    """Tests for trace_id generation and query functions."""

    def test_new_trace_id_format(self):
        tid = working_memory.new_trace_id()
        assert len(tid) == 12
        assert tid.isalnum()

    def test_new_trace_id_unique(self):
        ids = {working_memory.new_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_add_with_trace_id(self):
        tid = working_memory.new_trace_id()
        working_memory.add("C1", "T1", "U1", "userMessage", "hi", trace_id=tid)
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["trace_id"] == tid

    def test_add_without_trace_id(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "hi")
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["trace_id"] is None

    def test_get_trace(self):
        tid = working_memory.new_trace_id()
        working_memory.add("C1", "T1", "claudicle", "internalMonologue", "thinking", trace_id=tid)
        working_memory.add("C1", "T1", "claudicle", "externalDialog", "response", trace_id=tid)
        working_memory.add("C1", "T1", "claudicle", "mentalQuery", "model check?", trace_id=tid)
        # Different trace — should not appear
        working_memory.add("C1", "T1", "claudicle", "userMessage", "other", trace_id="other123")

        trace = working_memory.get_trace(tid)
        assert len(trace) == 3
        types = [e["entry_type"] for e in trace]
        assert types == ["internalMonologue", "externalDialog", "mentalQuery"]

    def test_get_trace_chronological_order(self):
        tid = working_memory.new_trace_id()
        working_memory.add("C1", "T1", "claudicle", "internalMonologue", "first", trace_id=tid)
        working_memory.add("C1", "T1", "claudicle", "externalDialog", "second", trace_id=tid)
        trace = working_memory.get_trace(tid)
        assert trace[0]["content"] == "first"
        assert trace[1]["content"] == "second"

    def test_recent_traces(self):
        tid1 = working_memory.new_trace_id()
        tid2 = working_memory.new_trace_id()
        working_memory.add("C1", "T1", "claudicle", "internalMonologue", "a", trace_id=tid1)
        working_memory.add("C1", "T1", "claudicle", "externalDialog", "b", trace_id=tid1)
        working_memory.add("C1", "T1", "claudicle", "internalMonologue", "c", trace_id=tid2)

        traces = working_memory.recent_traces("C1", "T1")
        assert len(traces) == 2
        # Most recent first
        assert traces[0]["trace_id"] == tid2
        assert traces[0]["step_count"] == 1
        assert traces[1]["trace_id"] == tid1
        assert traces[1]["step_count"] == 2

    def test_recent_decisions(self):
        tid = working_memory.new_trace_id()
        working_memory.add("C1", "T1", "claudicle", "mentalQuery", "model check?",
                          metadata={"result": True}, trace_id=tid)
        working_memory.add("C1", "T1", "claudicle", "internalMonologue", "thinking", trace_id=tid)
        working_memory.add("C1", "T1", "claudicle", "mentalQuery", "state changed?",
                          metadata={"result": False}, trace_id=tid)

        decisions = working_memory.recent_decisions("C1", "T1")
        assert len(decisions) == 2
        assert decisions[0]["content"] == "model check?"
        assert decisions[1]["content"] == "state changed?"


class TestCleanup:
    """Tests for cleanup() TTL behavior."""

    def test_cleanup_removes_old(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "old")
        # Manually backdate the entry
        conn = working_memory._get_conn()
        conn.execute("UPDATE working_memory SET created_at = ?", (time.time() - 999999,))
        conn.commit()

        working_memory.add("C1", "T1", "U1", "userMessage", "new")
        deleted = working_memory.cleanup(max_age_hours=1)
        assert deleted == 1
        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["content"] == "new"

    def test_cleanup_preserves_recent(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "recent")
        deleted = working_memory.cleanup(max_age_hours=1)
        assert deleted == 0
