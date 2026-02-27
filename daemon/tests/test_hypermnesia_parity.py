"""Tests for Hypermnesia parity polish — Phase 4a.

Covers: replace_region, get_regions, archive_entries, add_monologue,
and verifies compression.py uses public APIs (no _get_conn).
"""

import json

import config
from memory import working_memory, compression


def _seed(channel, thread_ts, idx, entry_type, **kwargs):
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=kwargs.get("user_id", "U1"),
        entry_type=entry_type,
        content=kwargs.get("content", f"entry-{idx}"),
        metadata=kwargs.get("metadata"),
        display_name=kwargs.get("display_name"),
        verb=kwargs.get("verb"),
        region=kwargs.get("region", "default"),
    )


# ---------------------------------------------------------------------------
# replace_region
# ---------------------------------------------------------------------------

class TestReplaceRegion:
    def test_atomic_swap(self):
        """Seed 3 summary entries, replace with 1 — old entries gone."""
        for i in range(3):
            _seed("C1", "T1", i, "memorySummary", content=f"old-{i}", region="summary")

        working_memory.replace_region("C1", "T1", "summary", [
            {"user_id": "claudicle", "entry_type": "memorySummary", "content": "new-summary"},
        ])

        entries = working_memory.get_region("C1", "T1", "summary", limit=10)
        assert len(entries) == 1
        assert entries[0]["content"] == "new-summary"

    def test_empty_clears_region(self):
        """Replace with empty list = clear the region."""
        _seed("C1", "T1", 0, "memorySummary", content="old", region="summary")

        working_memory.replace_region("C1", "T1", "summary", [])

        entries = working_memory.get_region("C1", "T1", "summary", limit=10)
        assert entries == []

    def test_preserves_other_regions(self):
        """Replacing one region doesn't touch other regions."""
        _seed("C1", "T1", 0, "userMessage", content="default-msg", region="default")
        _seed("C1", "T1", 1, "memorySummary", content="old-summary", region="summary")

        working_memory.replace_region("C1", "T1", "summary", [
            {"user_id": "claudicle", "entry_type": "memorySummary", "content": "new-summary"},
        ])

        default = working_memory.get_region("C1", "T1", "default", limit=10)
        assert len(default) == 1
        assert default[0]["content"] == "default-msg"


# ---------------------------------------------------------------------------
# get_regions
# ---------------------------------------------------------------------------

class TestGetRegions:
    def test_multi_region_query(self):
        """Query multiple regions at once."""
        _seed("C1", "T1", 0, "userMessage", content="msg", region="default")
        _seed("C1", "T1", 1, "memorySummary", content="sum", region="summary")
        _seed("C1", "T1", 2, "decision", content="dec", region="core")

        result = working_memory.get_regions("C1", "T1", ["summary", "core"])
        types = [e["entry_type"] for e in result]
        assert "memorySummary" in types
        assert "decision" in types
        assert "userMessage" not in types

    def test_empty_list_returns_empty(self):
        _seed("C1", "T1", 0, "userMessage", content="msg")
        assert working_memory.get_regions("C1", "T1", []) == []

    def test_nonexistent_region(self):
        _seed("C1", "T1", 0, "userMessage", content="msg")
        assert working_memory.get_regions("C1", "T1", ["nonexistent"]) == []


# ---------------------------------------------------------------------------
# archive_entries
# ---------------------------------------------------------------------------

class TestArchiveEntries:
    def test_archive_with_rowid(self, monkeypatch):
        monkeypatch.setattr(config, "COMPRESSION_ARCHIVE", True)

        for i in range(3):
            _seed("C1", "T1", i, "userMessage", content=f"m{i}")

        entries = working_memory.get_region("C1", "T1", "default", limit=10)
        assert len(entries) == 3

        deleted = working_memory.archive_entries(
            entries=entries,
            channel="C1",
            thread_ts="T1",
            compression_trace_id="trace-test",
            archive=True,
        )
        assert deleted == 3

        remaining = working_memory.get_region("C1", "T1", "default", limit=10)
        assert remaining == []

        # Verify archive rows exist
        conn = working_memory._get_conn()
        count = conn.execute(
            "SELECT COUNT(*) as n FROM working_memory_archive WHERE channel = ? AND thread_ts = ?",
            ("C1", "T1"),
        ).fetchone()["n"]
        assert count == 3

    def test_archive_disabled_deletes_only(self, monkeypatch):
        """archive=False deletes entries but doesn't write to archive table."""
        monkeypatch.setattr(config, "COMPRESSION_ARCHIVE", True)

        for i in range(2):
            _seed("C1", "T1", i, "userMessage", content=f"m{i}")

        entries = working_memory.get_region("C1", "T1", "default", limit=10)

        deleted = working_memory.archive_entries(
            entries=entries,
            channel="C1",
            thread_ts="T1",
            compression_trace_id="trace-no-archive",
            archive=False,
        )
        assert deleted == 2

        remaining = working_memory.get_region("C1", "T1", "default", limit=10)
        assert remaining == []

        conn = working_memory._get_conn()
        count = conn.execute(
            "SELECT COUNT(*) as n FROM working_memory_archive WHERE channel = ? AND thread_ts = ?",
            ("C1", "T1"),
        ).fetchone()["n"]
        assert count == 0


# ---------------------------------------------------------------------------
# add_monologue
# ---------------------------------------------------------------------------

class TestAddMonologue:
    def test_defaults(self):
        working_memory.add_monologue("C1", "T1", "I sense a pattern here.")

        entries = working_memory.get_region("C1", "T1", "default", limit=10)
        assert len(entries) == 1
        e = entries[0]
        assert e["entry_type"] == "internalMonologue"
        assert e["verb"] == "thought"
        assert e["content"] == "I sense a pattern here."
        assert e["user_id"] == "claudicle"

    def test_custom_verb(self):
        working_memory.add_monologue("C1", "T1", "Hmm.", verb="mused")

        entries = working_memory.get_region("C1", "T1", "default", limit=10)
        assert entries[0]["verb"] == "mused"


# ---------------------------------------------------------------------------
# Compression uses public API (no _get_conn)
# ---------------------------------------------------------------------------

class TestCompressionUsesPublicAPI:
    def test_no_private_access_in_compression_source(self):
        """Verify compression.py has zero _get_conn() calls."""
        import inspect
        source = inspect.getsource(compression)
        assert "_get_conn" not in source

    def test_store_summary_delegates_to_replace_region(self):
        """store_summary should create a memorySummary in the summary region."""
        compression.store_summary(
            channel="C1",
            thread_ts="T1",
            summary="test summary",
            original_count=5,
            time_range={"start": 1.0, "end": 2.0},
            method="heuristic",
        )

        entries = working_memory.get_region("C1", "T1", "summary", limit=10)
        assert len(entries) == 1
        assert entries[0]["content"] == "test summary"
        meta = json.loads(entries[0]["metadata"])
        assert meta["original_count"] == 5
        assert meta["method"] == "heuristic"

    def test_archive_and_delete_delegates(self, monkeypatch):
        """archive_and_delete should delegate to working_memory.archive_entries."""
        monkeypatch.setattr(config, "COMPRESSION_ARCHIVE", True)

        for i in range(3):
            _seed("C1", "T1", i, "userMessage", content=f"m{i}")

        entries = working_memory.get_region("C1", "T1", "default", limit=10)

        deleted = compression.archive_and_delete(
            entries=entries,
            channel="C1",
            thread_ts="T1",
            time_range={"start": 0.0, "end": 10.0},
            compression_trace_id="trace-delegate",
        )
        assert deleted == 3
