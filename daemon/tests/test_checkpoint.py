"""Tests for memory.checkpoint — point-in-time bookmarks for rollback.

DB isolation comes from conftest.py's isolate_databases fixture.
"""

from memory import working_memory, soul_memory
from memory.checkpoint import create, create_at_last_post, get, list_checkpoints, rollback, delete


CH = "test:checkpoint"
TH = "thread:cp"


def _add(entry_type="userMessage", content="hello", user_id="tom",
         channel=CH, thread_ts=TH, **kwargs):
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=user_id,
        entry_type=entry_type,
        content=content,
        **kwargs,
    )


class TestCheckpointCreate:
    def test_create_basic(self):
        _add(content="before checkpoint")
        cp = create("test-cp", CH, TH)

        assert cp.name == "test-cp"
        assert cp.channel == CH
        assert cp.thread_ts == TH
        assert cp.max_entry_id > 0
        assert cp.created_at > 0

    def test_create_captures_max_id(self):
        _add(content="a")
        _add(content="b")
        cp = create("cp1", CH, TH)
        mid = working_memory.max_id(CH, TH)
        assert cp.max_entry_id == mid

    def test_create_captures_soul_state(self):
        soul_memory.set("mood", "curious")
        _add(content="entry")
        cp = create("cp-soul", CH, TH)
        assert cp.soul_state.get("mood") == "curious"

    def test_create_replaces_same_name(self):
        _add(content="first")
        cp1 = create("dup", CH, TH)
        _add(content="second")
        cp2 = create("dup", CH, TH)

        assert cp2.max_entry_id > cp1.max_entry_id
        # Only one checkpoint with that name exists
        cps = list_checkpoints(channel=CH)
        dup_cps = [c for c in cps if c.name == "dup"]
        assert len(dup_cps) == 1

    def test_create_with_metadata(self):
        _add(content="x")
        cp = create("meta-cp", CH, TH, metadata={"reason": "test"})
        assert cp.metadata.get("reason") == "test"


class TestCheckpointGet:
    def test_get_existing(self):
        _add(content="entry")
        create("findme", CH, TH)
        cp = get("findme", CH, TH)
        assert cp is not None
        assert cp.name == "findme"

    def test_get_nonexistent(self):
        cp = get("nope", CH, TH)
        assert cp is None


class TestCheckpointList:
    def test_list_empty(self):
        cps = list_checkpoints()
        assert cps == []

    def test_list_all(self):
        _add(content="a")
        create("cp-a", CH, TH)
        _add(content="b", channel="other:ch", thread_ts="th2")
        create("cp-b", "other:ch", "th2")

        cps = list_checkpoints()
        assert len(cps) == 2

    def test_list_by_channel(self):
        _add(content="a")
        create("cp-a", CH, TH)
        _add(content="b", channel="other:ch", thread_ts="th2")
        create("cp-b", "other:ch", "th2")

        cps = list_checkpoints(channel=CH)
        assert len(cps) == 1
        assert cps[0].name == "cp-a"


class TestRollback:
    def test_rollback_removes_entries_after_checkpoint(self):
        _add(content="keep1")
        _add(content="keep2")
        create("rb-test", CH, TH)
        _add(content="remove1")
        _add(content="remove2")

        result = rollback("rb-test", CH, TH, archive=False)
        assert result["deleted_count"] == 2
        assert result["checkpoint"] is not None
        assert result["checkpoint"].name == "rb-test"

        remaining = working_memory.query(channel=CH)
        contents = [r["content"] for r in remaining]
        assert "keep1" in contents
        assert "keep2" in contents
        assert "remove1" not in contents
        assert "remove2" not in contents

    def test_rollback_nonexistent_checkpoint(self):
        result = rollback("nope", CH, TH)
        assert result["deleted_count"] == 0
        assert result["checkpoint"] is None

    def test_rollback_restores_soul_state(self):
        soul_memory.set("mood", "focused")
        _add(content="entry")
        create("soul-rb", CH, TH)

        soul_memory.set("mood", "distracted")
        _add(content="later")

        result = rollback("soul-rb", CH, TH, restore_soul_state=True, archive=False)
        assert result["soul_state_restored"] is True
        assert soul_memory.get("mood") == "focused"

    def test_rollback_without_restoring_soul_state(self):
        soul_memory.set("mood", "focused")
        _add(content="entry")
        create("no-soul-rb", CH, TH)

        soul_memory.set("mood", "distracted")
        _add(content="later")

        result = rollback("no-soul-rb", CH, TH, restore_soul_state=False, archive=False)
        assert result["soul_state_restored"] is False
        assert soul_memory.get("mood") == "distracted"


class TestCheckpointDelete:
    def test_delete_existing(self):
        _add(content="entry")
        create("del-cp", CH, TH)
        assert delete("del-cp", CH, TH) is True
        assert get("del-cp", CH, TH) is None

    def test_delete_nonexistent(self):
        assert delete("nope", CH, TH) is False


class TestCheckpointImmutability:
    def test_checkpoint_is_frozen(self):
        _add(content="entry")
        cp = create("frozen-cp", CH, TH)
        try:
            cp.name = "mutated"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass


class TestCreateAtLastPost:
    def test_creates_at_last_external_dialog(self):
        _add(content="early", entry_type="userMessage", user_id="tom")
        _add(content="post to channel", entry_type="externalDialog",
             user_id="claudicle", channel="C_ENG_ALDEA")
        _add(content="after post", entry_type="userMessage", user_id="tom")

        cp = create_at_last_post(CH, TH, target_channel="C_ENG_ALDEA")
        assert cp is not None
        assert "C_ENG_ALDEA" in cp.name

    def test_returns_none_when_no_post(self):
        _add(content="msg", entry_type="userMessage")
        cp = create_at_last_post(CH, TH, target_channel="C_NONEXISTENT")
        assert cp is None
