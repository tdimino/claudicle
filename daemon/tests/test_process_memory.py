"""Tests for process_memory — per-subprocess persistent state (Phase 4b).

Maps to Open Souls' useProcessMemory hook. Backed by soul_memory
with namespaced keys — test isolation comes free from conftest.py's
isolate_databases fixture (which resets soul_memory).
"""

from memory import process_memory


class TestProcessMemory:
    def test_get_default(self):
        assert process_memory.get("compressesMemory", "last_run") is None
        assert process_memory.get("compressesMemory", "last_run", default=42) == 42

    def test_set_and_get_roundtrip(self):
        process_memory.set("compressesMemory", "count", 7)
        assert process_memory.get("compressesMemory", "count") == 7

    def test_set_overwrites(self):
        process_memory.set("modelsTheUser", "flag", True)
        process_memory.set("modelsTheUser", "flag", False)
        assert process_memory.get("modelsTheUser", "flag") is False

    def test_json_types(self):
        """Round-trip dict, list, int, bool, string."""
        process_memory.set("sp", "dict", {"a": 1, "b": [2, 3]})
        process_memory.set("sp", "list", [1, "two", 3.0])
        process_memory.set("sp", "int", 99)
        process_memory.set("sp", "bool", True)
        process_memory.set("sp", "str", "hello")

        assert process_memory.get("sp", "dict") == {"a": 1, "b": [2, 3]}
        assert process_memory.get("sp", "list") == [1, "two", 3.0]
        assert process_memory.get("sp", "int") == 99
        assert process_memory.get("sp", "bool") is True
        assert process_memory.get("sp", "str") == "hello"

    def test_scoped_by_subprocess(self):
        """Two subprocesses with the same key get different values."""
        process_memory.set("alpha", "count", 10)
        process_memory.set("beta", "count", 20)

        assert process_memory.get("alpha", "count") == 10
        assert process_memory.get("beta", "count") == 20

    def test_scoped_by_thread(self):
        """Same subprocess, different channel/thread, different values."""
        process_memory.set("sp", "x", 1, channel="C1", thread_ts="T1")
        process_memory.set("sp", "x", 2, channel="C1", thread_ts="T2")
        process_memory.set("sp", "x", 3)  # global (no channel/thread)

        assert process_memory.get("sp", "x", channel="C1", thread_ts="T1") == 1
        assert process_memory.get("sp", "x", channel="C1", thread_ts="T2") == 2
        assert process_memory.get("sp", "x") == 3

    def test_clear(self):
        process_memory.set("sp", "a", 1)
        process_memory.set("sp", "b", 2)
        process_memory.set("other", "a", 99)

        cleared = process_memory.clear("sp")
        assert cleared == 2
        assert process_memory.get("sp", "a") is None
        assert process_memory.get("sp", "b") is None
        # Other subprocess untouched
        assert process_memory.get("other", "a") == 99

    def test_clear_scoped_to_thread(self):
        process_memory.set("sp", "x", 1, channel="C1", thread_ts="T1")
        process_memory.set("sp", "y", 2, channel="C1", thread_ts="T1")
        process_memory.set("sp", "x", 3, channel="C1", thread_ts="T2")

        cleared = process_memory.clear("sp", channel="C1", thread_ts="T1")
        assert cleared == 2
        # T2 untouched
        assert process_memory.get("sp", "x", channel="C1", thread_ts="T2") == 3
