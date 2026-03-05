"""Tests for daemon/memory/snapshot.py — immutable working memory snapshot."""

import dataclasses
import json

import pytest

from memory.snapshot import (
    CognitiveOutput,
    MemoryEntry,
    WorkingMemorySnapshot,
    apply_output,
    load_snapshot,
)
from memory import working_memory, soul_memory


class TestMemoryEntry:
    """Tests for the frozen MemoryEntry dataclass."""

    def test_frozen(self):
        entry = MemoryEntry(entry_type="test", content="hello")
        assert dataclasses.is_dataclass(entry)
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry.content = "modified"  # type: ignore

    def test_from_row_basic(self):
        row = {
            "entry_type": "userMessage",
            "content": "hello",
            "verb": "said",
            "user_id": "U123",
            "display_name": "Tom",
            "metadata": None,
            "trace_id": "abc123",
            "region": "default",
            "created_at": 1000.0,
        }
        entry = MemoryEntry.from_row(row)
        assert entry.entry_type == "userMessage"
        assert entry.content == "hello"
        assert entry.verb == "said"
        assert entry.metadata == {}

    def test_from_row_parses_json_metadata(self):
        row = {
            "entry_type": "mentalQuery",
            "content": "Should update?",
            "metadata": json.dumps({"result": True}),
            "created_at": 1000.0,
        }
        entry = MemoryEntry.from_row(row)
        assert entry.metadata == {"result": True}

    def test_from_row_handles_bad_json(self):
        row = {
            "entry_type": "test",
            "content": "x",
            "metadata": "not-json{",
            "created_at": 1000.0,
        }
        entry = MemoryEntry.from_row(row)
        assert entry.metadata == {}

    def test_from_row_handles_dict_metadata(self):
        row = {
            "entry_type": "test",
            "content": "x",
            "metadata": {"key": "value"},
            "created_at": 1000.0,
        }
        entry = MemoryEntry.from_row(row)
        assert entry.metadata == {"key": "value"}

    def test_defaults(self):
        entry = MemoryEntry(entry_type="test", content="hello")
        assert entry.verb == ""
        assert entry.user_id == ""
        assert entry.region == "default"
        assert entry.metadata == {}
        assert entry.rowid is None


class TestWorkingMemorySnapshot:
    """Tests for the frozen WorkingMemorySnapshot."""

    def test_frozen(self):
        snap = WorkingMemorySnapshot()
        assert dataclasses.is_dataclass(snap)
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.trace_id = "modified"  # type: ignore

    def test_empty_snapshot(self):
        snap = WorkingMemorySnapshot()
        assert snap.entries == ()
        assert snap.soul_state == {}
        assert snap.user_model == ""
        assert snap.trace_id == ""

    def test_with_entry_returns_new_instance(self):
        snap = WorkingMemorySnapshot()
        entry = MemoryEntry(entry_type="test", content="hello")
        new_snap = snap.with_entry(entry)

        assert len(snap.entries) == 0  # original unchanged
        assert len(new_snap.entries) == 1
        assert new_snap.entries[0].content == "hello"
        assert new_snap is not snap

    def test_with_entries_appends(self):
        entry1 = MemoryEntry(entry_type="a", content="1")
        entry2 = MemoryEntry(entry_type="b", content="2")
        snap = WorkingMemorySnapshot(entries=(entry1,))
        new_snap = snap.with_entries((entry2,))

        assert len(new_snap.entries) == 2
        assert new_snap.entries[0].content == "1"
        assert new_snap.entries[1].content == "2"

    def test_with_soul_state_merges(self):
        snap = WorkingMemorySnapshot(soul_state={"emotion": "neutral"})
        new_snap = snap.with_soul_state(emotion="engaged", topic="testing")

        assert snap.soul_state == {"emotion": "neutral"}  # original unchanged
        assert new_snap.soul_state == {"emotion": "engaged", "topic": "testing"}

    def test_with_user_model(self):
        snap = WorkingMemorySnapshot()
        new_snap = snap.with_user_model("# Tom\nBuilder.")
        assert snap.user_model == ""
        assert new_snap.user_model == "# Tom\nBuilder."

    def test_with_trace_id(self):
        snap = WorkingMemorySnapshot()
        new_snap = snap.with_trace_id("abc123")
        assert snap.trace_id == ""
        assert new_snap.trace_id == "abc123"

    def test_get_region(self):
        e1 = MemoryEntry(entry_type="a", content="1", region="default")
        e2 = MemoryEntry(entry_type="b", content="2", region="summary")
        e3 = MemoryEntry(entry_type="c", content="3", region="default")
        snap = WorkingMemorySnapshot(entries=(e1, e2, e3))

        default = snap.get_region("default")
        assert len(default) == 2
        assert default[0].content == "1"
        assert default[1].content == "3"

        summary = snap.get_region("summary")
        assert len(summary) == 1
        assert summary[0].content == "2"

    def test_get_regions(self):
        e1 = MemoryEntry(entry_type="a", content="1", region="default")
        e2 = MemoryEntry(entry_type="b", content="2", region="summary")
        snap = WorkingMemorySnapshot(entries=(e1, e2))
        assert snap.get_regions() == {"default", "summary"}

    def test_get_regions_empty(self):
        snap = WorkingMemorySnapshot()
        assert snap.get_regions() == set()


class TestCognitiveOutput:
    """Tests for the frozen CognitiveOutput — copy-on-write pattern."""

    def test_frozen(self):
        output = CognitiveOutput()
        assert dataclasses.is_dataclass(output)
        with pytest.raises(dataclasses.FrozenInstanceError):
            output.user_model_update = "modified"  # type: ignore

    def test_with_entry_returns_new_instance(self):
        output = CognitiveOutput()
        new = output.with_entry("internalMonologue", "thinking...", verb="thought")
        assert len(output.entries) == 0  # original unchanged
        assert len(new.entries) == 1
        assert new.entries[0].entry_type == "internalMonologue"
        assert new.entries[0].verb == "thought"

    def test_is_empty(self):
        output = CognitiveOutput()
        assert output.is_empty is True
        new = output.with_entry("test", "x")
        assert new.is_empty is False

    def test_soul_state_not_empty(self):
        output = CognitiveOutput()
        new = output.with_soul_state("emotion", "engaged")
        assert new.is_empty is False

    def test_with_soul_state(self):
        output = CognitiveOutput()
        new = output.with_soul_state("emotion", "engaged")
        assert output.soul_state_updates == ()  # original unchanged
        assert new.soul_state_updates == (("emotion", "engaged"),)
        assert new.soul_state_dict == {"emotion": "engaged"}

    def test_with_soul_state_updates(self):
        output = CognitiveOutput()
        new = output.with_soul_state_updates({"emotion": "engaged", "topic": "testing"})
        assert len(new.soul_state_updates) == 2
        assert new.soul_state_dict == {"emotion": "engaged", "topic": "testing"}

    def test_with_user_model(self):
        output = CognitiveOutput()
        new = output.with_user_model("# Updated", "U123", "learned preferences")
        assert output.user_model_update is None  # original unchanged
        assert new.user_model_update == "# Updated"
        assert new.user_model_target_id == "U123"
        assert new.user_model_change_note == "learned preferences"

    def test_with_dossier(self):
        output = CognitiveOutput()
        new = output.with_dossier("Athena", "goddess of wisdom", "subject", "first encounter")
        assert len(output.dossier_updates) == 0  # original unchanged
        assert len(new.dossier_updates) == 1
        assert new.dossier_updates[0]["entity_name"] == "Athena"

    def test_merge(self):
        m1 = (CognitiveOutput()
            .with_entry("a", "1")
            .with_soul_state("emotion", "focused"))

        m2 = (CognitiveOutput()
            .with_entry("b", "2")
            .with_user_model("# Updated", "U123")
            .with_dossier("X", "Y"))

        merged = m1.merge(m2)
        assert len(m1.entries) == 1  # original unchanged
        assert len(merged.entries) == 2
        assert merged.soul_state_dict == {"emotion": "focused"}
        assert merged.user_model_update == "# Updated"
        assert len(merged.dossier_updates) == 1

    def test_chaining(self):
        """Verify fluent copy-on-write chaining — the core pattern."""
        output = (CognitiveOutput()
            .with_entry("internalMonologue", "thinking", verb="thought")
            .with_entry("externalDialog", "hello", verb="said")
            .with_soul_state("emotion", "engaged")
            .with_user_model("# Tom", "U1"))
        assert len(output.entries) == 2
        assert output.soul_state_dict == {"emotion": "engaged"}
        assert output.user_model_update == "# Tom"


class TestLoadSnapshot:
    """Tests for load_snapshot() reading from SQLite."""

    def test_loads_recent_entries(self):
        working_memory.add("C1", "T1", "U1", "userMessage", "hello", verb="said")
        working_memory.add("C1", "T1", "claudicle", "externalDialog", "hi back", verb="said")

        snap = load_snapshot("C1", "T1", trace_id="test123")
        assert len(snap.entries) == 2
        assert snap.entries[0].entry_type == "userMessage"
        assert snap.entries[1].entry_type == "externalDialog"
        assert snap.channel == "C1"
        assert snap.thread_ts == "T1"
        assert snap.trace_id == "test123"

    def test_loads_soul_state(self):
        soul_memory.set("emotionalState", "engaged")
        soul_memory.set("currentTopic", "testing")

        snap = load_snapshot("C1", "T1")
        assert snap.soul_state["emotionalState"] == "engaged"
        assert snap.soul_state["currentTopic"] == "testing"

    def test_empty_thread(self):
        snap = load_snapshot("C1", "T1")
        assert len(snap.entries) == 0
        assert snap.soul_state  # has defaults from SOUL_MEMORY_DEFAULTS


class TestApplyOutput:
    """Tests for apply_output() committing frozen CognitiveOutput to SQLite."""

    def test_applies_entries(self):
        output = CognitiveOutput().with_entry(
            "internalMonologue", "thinking...", verb="thought", trace_id="t1")

        apply_output(output, "C1", "T1")

        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "internalMonologue"
        assert entries[0]["content"] == "thinking..."

    def test_applies_soul_state(self):
        output = (CognitiveOutput()
            .with_soul_state("emotionalState", "focused")
            .with_soul_state("currentTopic", "refactoring"))

        apply_output(output, "C1", "T1")

        assert soul_memory.get("emotionalState") == "focused"
        assert soul_memory.get("currentTopic") == "refactoring"

    def test_applies_user_model(self):
        from memory import user_models
        user_models.ensure_exists("U123", "Tom")

        output = CognitiveOutput().with_user_model(
            "# Tom\nUpdated model.", "U123", "learned preferences")

        apply_output(output, "C1", "T1")

        model = user_models.get("U123")
        assert "Updated model" in model

    def test_empty_output_noop(self):
        output = CognitiveOutput()
        apply_output(output, "C1", "T1")

        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 0

    def test_applies_entry_with_target_overrides(self):
        """Entries with target_channel/target_thread_ts route to those targets."""
        entry = MemoryEntry(
            entry_type="daimonicIntuition",
            content="A lesson",
            verb="learned",
            user_id="leb",
            region="lessons",
            target_channel="daimon:leb",
            target_thread_ts="default::global",
        )
        output = CognitiveOutput().with_raw_entry(entry)

        # Apply with default channel/thread — entry should go to override targets
        apply_output(output, "C_DEFAULT", "T_DEFAULT")

        # Entry should NOT be in default channel
        default_entries = working_memory.get_recent("C_DEFAULT", "T_DEFAULT")
        assert len(default_entries) == 0

        # Entry SHOULD be in override channel
        override_entries = working_memory.get_recent("daimon:leb", "default::global")
        assert len(override_entries) == 1
        assert override_entries[0]["content"] == "A lesson"

    def test_mixed_default_and_override_entries(self):
        """Some entries use defaults, others use target overrides."""
        output = (CognitiveOutput()
            .with_entry("internalMonologue", "thinking", verb="thought")
            .with_raw_entry(MemoryEntry(
                entry_type="daimonicIntuition",
                content="lesson",
                user_id="leb",
                region="lessons",
                target_channel="daimon:leb",
                target_thread_ts="default::global",
            )))

        apply_output(output, "C1", "T1")

        # Default entry in C1/T1
        c1_entries = working_memory.get_recent("C1", "T1")
        assert len(c1_entries) == 1
        assert c1_entries[0]["entry_type"] == "internalMonologue"

        # Override entry in daimon:leb/default::global
        leb_entries = working_memory.get_recent("daimon:leb", "default::global")
        assert len(leb_entries) == 1
        assert leb_entries[0]["entry_type"] == "daimonicIntuition"


class TestWithRawEntry:
    """Tests for CognitiveOutput.with_raw_entry()."""

    def test_appends_prebuilt_entry(self):
        entry = MemoryEntry(
            entry_type="test", content="prebuilt", verb="tested",
            target_channel="ch", target_thread_ts="ts",
        )
        output = CognitiveOutput().with_raw_entry(entry)
        assert len(output.entries) == 1
        assert output.entries[0].target_channel == "ch"
        assert output.entries[0].target_thread_ts == "ts"

    def test_preserves_existing_entries(self):
        output = (CognitiveOutput()
            .with_entry("a", "1")
            .with_raw_entry(MemoryEntry(entry_type="b", content="2")))
        assert len(output.entries) == 2
        assert output.entries[0].entry_type == "a"
        assert output.entries[1].entry_type == "b"


class TestSnapshotSoulStatePurity:
    """load_snapshot() soul_state should NOT contain proc/whisper keys."""

    def test_load_snapshot_excludes_proc_keys(self):
        soul_memory.set("currentProject", "Testing")
        soul_memory.set("proc:leb:counter", "5")
        soul_memory.set("daimonic_whisper_kothar", "whisper")

        snap = load_snapshot("C1", "T1")
        assert "currentProject" in snap.soul_state
        assert snap.soul_state["currentProject"] == "Testing"
        assert "proc:leb:counter" not in snap.soul_state
        assert "daimonic_whisper_kothar" not in snap.soul_state
