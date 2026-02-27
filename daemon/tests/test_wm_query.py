"""Tests for working_memory query(), stats(), delete_after(), delete_by_filter().

Phase 2 additions: general query interface, statistics, and selective deletion.
DB isolation comes from conftest.py's isolate_databases fixture.
"""

import time

from memory import working_memory


CH = "test:query"
TH = "thread:1"


def _add(entry_type="userMessage", content="hello", user_id="tom",
         region="default", trace_id="", channel=CH, thread_ts=TH):
    """Shorthand for working_memory.add()."""
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=user_id,
        entry_type=entry_type,
        content=content,
        region=region,
        trace_id=trace_id,
    )


class TestQuery:
    def test_empty_returns_empty(self):
        result = working_memory.query(channel=CH)
        assert result == []

    def test_query_by_channel(self):
        _add(content="a", channel="ch1")
        _add(content="b", channel="ch2")
        result = working_memory.query(channel="ch1")
        assert len(result) == 1
        assert result[0]["content"] == "a"

    def test_query_by_entry_type(self):
        _add(entry_type="userMessage", content="msg")
        _add(entry_type="internalMonologue", content="thought")
        result = working_memory.query(channel=CH, entry_type="internalMonologue")
        assert len(result) == 1
        assert result[0]["content"] == "thought"

    def test_query_by_user_id(self):
        _add(user_id="alice", content="from alice")
        _add(user_id="bob", content="from bob")
        result = working_memory.query(channel=CH, user_id="alice")
        assert len(result) == 1
        assert result[0]["content"] == "from alice"

    def test_query_by_region(self):
        _add(region="default", content="d")
        _add(region="summary", content="s")
        result = working_memory.query(channel=CH, region="summary")
        assert len(result) == 1
        assert result[0]["content"] == "s"

    def test_query_by_trace_id(self):
        _add(trace_id="abc123", content="traced")
        _add(trace_id="def456", content="other")
        result = working_memory.query(channel=CH, trace_id="abc123")
        assert len(result) == 1
        assert result[0]["content"] == "traced"

    def test_query_since_until(self):
        now = time.time()
        _add(content="old")
        _add(content="new")
        # query everything since before now
        result = working_memory.query(channel=CH, since=now - 10)
        assert len(result) == 2

    def test_query_combined_filters(self):
        _add(entry_type="userMessage", user_id="alice", content="a")
        _add(entry_type="internalMonologue", user_id="alice", content="b")
        _add(entry_type="userMessage", user_id="bob", content="c")
        result = working_memory.query(
            channel=CH, entry_type="userMessage", user_id="alice"
        )
        assert len(result) == 1
        assert result[0]["content"] == "a"

    def test_query_limit(self):
        for i in range(10):
            _add(content=f"msg-{i}")
        result = working_memory.query(channel=CH, limit=3)
        assert len(result) == 3

    def test_query_chronological_order(self):
        _add(content="first")
        _add(content="second")
        _add(content="third")
        result = working_memory.query(channel=CH)
        contents = [r["content"] for r in result]
        assert contents == ["first", "second", "third"]


class TestStats:
    def test_stats_empty(self):
        s = working_memory.stats(channel=CH)
        assert s["total_entries"] == 0
        assert s["by_channel"] == {}
        assert s["by_entry_type"] == {}

    def test_stats_with_entries(self):
        _add(entry_type="userMessage", content="a")
        _add(entry_type="userMessage", content="b")
        _add(entry_type="internalMonologue", content="c")
        s = working_memory.stats(channel=CH)
        assert s["total_entries"] == 3
        assert s["by_entry_type"]["userMessage"] == 2
        assert s["by_entry_type"]["internalMonologue"] == 1
        assert s["by_channel"][CH] == 3

    def test_stats_global(self):
        _add(content="a", channel="ch1")
        _add(content="b", channel="ch2")
        s = working_memory.stats()
        assert s["total_entries"] == 2
        assert "ch1" in s["by_channel"]
        assert "ch2" in s["by_channel"]


class TestMaxId:
    def test_max_id_empty(self):
        mid = working_memory.max_id(CH, TH)
        assert mid == 0

    def test_max_id_after_adds(self):
        _add(content="a")
        _add(content="b")
        mid = working_memory.max_id(CH, TH)
        assert mid > 0


class TestDeleteAfter:
    def test_delete_after_removes_entries(self):
        _add(content="keep")
        mid = working_memory.max_id(CH, TH)
        _add(content="remove1")
        _add(content="remove2")

        deleted = working_memory.delete_after(CH, TH, mid, archive=False)
        assert deleted == 2

        remaining = working_memory.query(channel=CH)
        assert len(remaining) == 1
        assert remaining[0]["content"] == "keep"

    def test_delete_after_with_archive(self):
        _add(content="keep")
        mid = working_memory.max_id(CH, TH)
        _add(content="archive_me")

        deleted = working_memory.delete_after(CH, TH, mid, archive=True)
        assert deleted >= 1

        remaining = working_memory.query(channel=CH)
        assert len(remaining) == 1
        assert remaining[0]["content"] == "keep"

    def test_delete_after_nothing_to_delete(self):
        _add(content="only")
        mid = working_memory.max_id(CH, TH)
        deleted = working_memory.delete_after(CH, TH, mid, archive=False)
        assert deleted == 0


class TestDeleteByFilter:
    def test_delete_by_entry_type(self):
        _add(entry_type="userMessage", content="keep")
        _add(entry_type="internalMonologue", content="remove")

        deleted = working_memory.delete_by_filter(
            CH, TH, entry_type="internalMonologue", archive=False
        )
        assert deleted == 1

        remaining = working_memory.query(channel=CH)
        assert len(remaining) == 1
        assert remaining[0]["content"] == "keep"

    def test_delete_by_filter_with_time(self):
        _add(content="a")
        cutoff = time.time() + 100
        deleted = working_memory.delete_by_filter(
            CH, TH, since=0, until=cutoff, archive=False
        )
        assert deleted == 1
