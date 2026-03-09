"""Tests for daemon/memory/model_journal.py — model/dossier shedding archaeology."""

import time

import pytest

from memory import model_journal, user_models, working_memory


# ---------------------------------------------------------------------------
# generate_diff (pure function)
# ---------------------------------------------------------------------------

class TestGenerateDiff:
    def test_basic_diff(self):
        old = "# Alice\n\nOriginal persona.\n"
        new = "# Alice\n\nUpdated persona with new interests.\n"
        diff = model_journal.generate_diff(old, new)
        assert "-Original persona." in diff
        assert "+Updated persona with new interests." in diff

    def test_no_changes(self):
        same = "# Alice\n\nSame content.\n"
        assert model_journal.generate_diff(same, same) == "(no changes)"

    def test_empty_to_content(self):
        diff = model_journal.generate_diff("", "# New\n")
        assert "+# New" in diff

    def test_content_to_empty(self):
        diff = model_journal.generate_diff("# Old\n", "")
        assert "-# Old" in diff

    def test_multiline_diff(self):
        old = "# Entity\n\n## Section A\nContent A\n\n## Section B\nContent B\n"
        new = "# Entity\n\n## Section A\nContent A revised\n\n## Section B\nContent B\n"
        diff = model_journal.generate_diff(old, new)
        assert "-Content A" in diff
        assert "+Content A revised" in diff
        # Section B unchanged — should not appear in diff hunks
        assert "-Content B" not in diff


class TestSummarizeDiff:
    def test_basic_summary(self):
        diff = "--- before\n+++ after\n@@ -1,2 +1,3 @@\n-old\n+new\n+added\n"
        result = model_journal._summarize_diff(diff)
        assert "+2 lines" in result
        assert "-1 lines" in result

    def test_no_changes(self):
        assert model_journal._summarize_diff("(no changes)") == "no changes"


# ---------------------------------------------------------------------------
# ShedRecord
# ---------------------------------------------------------------------------

class TestShedRecord:
    def test_from_row(self):
        row = {
            "id": 42,
            "entity_id": "U123",
            "entity_name": "Alice",
            "entity_type": "user",
            "old_content": "old",
            "new_content": "new",
            "diff": "diff text",
            "monologue": "reflection",
            "change_note": "updated persona",
            "meta_commentary": None,
            "trace_id": "abc123",
            "channel": "terminal:test",
            "thread_ts": "",
            "created_at": 1234567890.0,
        }
        record = model_journal.ShedRecord.from_row(row)
        assert record.id == 42
        assert record.entity_name == "Alice"
        assert record.meta_commentary == ""  # None → ""

    def test_frozen(self):
        record = model_journal.ShedRecord(entity_name="Test")
        with pytest.raises(AttributeError):
            record.entity_name = "Changed"


# ---------------------------------------------------------------------------
# shed_model
# ---------------------------------------------------------------------------

class TestShedModel:
    def test_creates_record(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        record = model_journal.shed_model(
            user_id="U1", old_md="# v1\nold", new_md="# v2\nnew",
            monologue="learned something", change_note="updated persona",
            channel="terminal:test", thread_ts="t1", trace_id="abc123",
            display_name="Alice",
        )
        assert record.id > 0
        assert record.entity_id == "U1"
        assert record.entity_name == "Alice"
        assert record.entity_type == "user"
        assert record.diff != "(no changes)"
        assert record.monologue == "learned something"
        assert record.change_note == "updated persona"

    def test_queryable_by_entity(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        model_journal.shed_model("U1", "v1", "v2", display_name="Alice")
        model_journal.shed_model("U1", "v2", "v3", display_name="Alice")
        sheds = model_journal.get_entity_archaeology("U1")
        assert len(sheds) == 2

    def test_shed_creates_working_memory_entry(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        model_journal.shed_model(
            "U1", "old", "new", change_note="test change",
            channel="ch", thread_ts="ts",
        )
        entries = working_memory.query(entry_type="modelShed")
        assert len(entries) >= 1
        content = entries[0]["content"]
        assert "shed" in content
        assert "test change" in content

    def test_no_working_memory_without_channel(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        model_journal.shed_model(
            "U1", "old", "new", change_note="test",
            channel="", thread_ts="",
        )
        entries = working_memory.query(entry_type="modelShed")
        assert len(entries) == 0

    def test_disabled_returns_empty_record(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_ENABLED", False, raising=False)
        record = model_journal.shed_model("U1", "old", "new")
        assert record.id == 0


# ---------------------------------------------------------------------------
# shed_dossier
# ---------------------------------------------------------------------------

class TestShedDossier:
    def test_dossier_shed(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        record = model_journal.shed_dossier(
            entity_name="Knossos", old_md="old", new_md="new",
            change_note="added archaeology section",
        )
        assert record.entity_id == "dossier:knossos"
        assert record.entity_type == "subject"
        assert record.entity_name == "Knossos"

    def test_person_dossier(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        record = model_journal.shed_dossier(
            entity_name="Michael Astour", old_md="old", new_md="new",
            entity_type="person",
        )
        assert record.entity_id == "dossier:michael astour"
        assert record.entity_type == "person"


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------

class TestQuerySheds:
    def test_filter_by_type(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        model_journal.shed_model("U1", "a", "b", entity_type="user", display_name="A")
        model_journal.shed_dossier("X", "c", "d", entity_type="subject")
        user_sheds = model_journal.get_sheds(entity_type="user")
        assert len(user_sheds) == 1
        assert user_sheds[0].entity_type == "user"

    def test_get_shed_by_id(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        record = model_journal.shed_model("U1", "a", "b", display_name="Test")
        fetched = model_journal.get_shed(record.id)
        assert fetched is not None
        assert fetched.entity_id == "U1"

    def test_get_shed_nonexistent(self):
        assert model_journal.get_shed(99999) is None

    def test_filter_by_time(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        now = time.time()
        model_journal.shed_model("U1", "a", "b", display_name="A")
        sheds = model_journal.get_sheds(since=now - 1, until=now + 60)
        assert len(sheds) == 1
        # Future window should return nothing
        sheds = model_journal.get_sheds(since=now + 100)
        assert len(sheds) == 0

    def test_limit(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        for i in range(5):
            model_journal.shed_model("U1", f"v{i}", f"v{i + 1}", display_name="A")
        sheds = model_journal.get_sheds(entity_id="U1", limit=3)
        assert len(sheds) == 3

    def test_order_newest_first(self, monkeypatch):
        monkeypatch.setattr("config.MODEL_SHED_META_COMMENTARY", False, raising=False)
        model_journal.shed_model("U1", "v1", "v2", change_note="first", display_name="A")
        model_journal.shed_model("U1", "v2", "v3", change_note="second", display_name="A")
        sheds = model_journal.get_entity_archaeology("U1")
        assert sheds[0].change_note == "second"
        assert sheds[1].change_note == "first"


# ---------------------------------------------------------------------------
# Meta commentary prompt
# ---------------------------------------------------------------------------

class TestMetaCommentary:
    def test_prompt_construction(self):
        record = model_journal.ShedRecord(
            entity_name="Tom", entity_type="user",
            change_note="added expertise section",
            diff="+## Expertise\n+Python, SQL",
            monologue="Tom mentioned Python skills",
        )
        prompt = model_journal._build_meta_commentary_prompt(record)
        assert "Tom" in prompt
        assert "user" in prompt
        assert "added expertise section" in prompt
        assert "Python" in prompt
        assert "epistemic observer" in prompt
