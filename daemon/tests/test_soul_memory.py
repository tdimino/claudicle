"""Tests for daemon/soul_memory.py — CRUD, defaults, format_for_prompt."""

from memory import soul_memory


class TestGetSet:
    """Tests for get() and set()."""

    def test_default_for_unset(self):
        assert soul_memory.get("emotionalState") == "neutral"
        assert soul_memory.get("currentProject") == ""

    def test_set_and_get(self):
        soul_memory.set("currentProject", "Claudius Test Suite")
        assert soul_memory.get("currentProject") == "Claudius Test Suite"

    def test_update_existing(self):
        soul_memory.set("emotionalState", "focused")
        soul_memory.set("emotionalState", "sardonic")
        assert soul_memory.get("emotionalState") == "sardonic"

    def test_unknown_key_returns_none(self):
        assert soul_memory.get("nonexistent_key") is None


class TestGetAll:
    """Tests for get_all() merging stored + defaults."""

    def test_all_defaults_when_empty(self):
        state = soul_memory.get_all()
        assert state["emotionalState"] == "neutral"
        assert state["currentProject"] == ""

    def test_stored_overrides_defaults(self):
        soul_memory.set("currentProject", "Testing")
        state = soul_memory.get_all()
        assert state["currentProject"] == "Testing"
        assert state["emotionalState"] == "neutral"  # unchanged default

    def test_all_keys_present(self):
        state = soul_memory.get_all()
        for key in soul_memory.SOUL_MEMORY_DEFAULTS:
            assert key in state


class TestFormatForPrompt:
    """Tests for format_for_prompt()."""

    def test_empty_when_all_defaults(self):
        assert soul_memory.format_for_prompt() == ""

    def test_includes_header_when_content(self):
        soul_memory.set("currentProject", "Claudius")
        result = soul_memory.format_for_prompt()
        assert "## Soul State" in result
        assert "Claudius" in result

    def test_neutral_emotion_hidden(self):
        soul_memory.set("currentProject", "X")
        result = soul_memory.format_for_prompt()
        assert "Emotional State" not in result

    def test_non_neutral_emotion_shown(self):
        soul_memory.set("emotionalState", "sardonic")
        result = soul_memory.format_for_prompt()
        assert "sardonic" in result

    def test_multiple_fields(self):
        soul_memory.set("currentProject", "Claudius")
        soul_memory.set("currentTask", "Writing tests")
        soul_memory.set("emotionalState", "focused")
        result = soul_memory.format_for_prompt()
        assert "Current Project" in result
        assert "Current Task" in result
        assert "focused" in result

    def test_conversation_summary(self):
        soul_memory.set("conversationSummary", "Discussing test architecture")
        result = soul_memory.format_for_prompt()
        assert "Recent Context" in result


class TestGetSoulState:
    """Tests for get_soul_state() — filtered view excluding proc/whisper keys."""

    def test_excludes_process_memory_keys(self):
        soul_memory.set("currentProject", "Testing")
        soul_memory.set("proc:leb:invocation_count", "5")
        soul_memory.set("proc:eikon:last_run", "12345")

        state = soul_memory.get_soul_state()
        assert "currentProject" in state
        assert state["currentProject"] == "Testing"
        assert "proc:leb:invocation_count" not in state
        assert "proc:eikon:last_run" not in state

    def test_excludes_whisper_keys(self):
        soul_memory.set("emotionalState", "focused")
        soul_memory.set("daimonic_whisper_kothar", "some whisper")
        soul_memory.set("daimonic_whisper_artifex", "another whisper")

        state = soul_memory.get_soul_state()
        assert state["emotionalState"] == "focused"
        assert "daimonic_whisper_kothar" not in state
        assert "daimonic_whisper_artifex" not in state

    def test_includes_canonical_defaults(self):
        state = soul_memory.get_soul_state()
        for key in soul_memory.SOUL_MEMORY_DEFAULTS:
            assert key in state

    def test_get_all_still_returns_everything(self):
        """get_all() is unchanged — still returns proc/whisper keys."""
        soul_memory.set("proc:leb:counter", "3")
        soul_memory.set("daimonic_whisper_test", "whisper")

        all_state = soul_memory.get_all()
        assert "proc:leb:counter" in all_state
        assert "daimonic_whisper_test" in all_state


class TestDelete:
    """Tests for delete() — proper key removal."""

    def test_delete_existing_key(self):
        soul_memory.set("currentProject", "ToDelete")
        assert soul_memory.get("currentProject") == "ToDelete"

        result = soul_memory.delete("currentProject")
        assert result is True
        # Falls back to default after deletion
        assert soul_memory.get("currentProject") == ""

    def test_delete_nonexistent_key(self):
        result = soul_memory.delete("never_existed_key")
        assert result is False

    def test_delete_removes_from_get_all(self):
        soul_memory.set("proc:test:key", "value")
        assert "proc:test:key" in soul_memory.get_all()

        soul_memory.delete("proc:test:key")
        assert "proc:test:key" not in soul_memory.get_all()
