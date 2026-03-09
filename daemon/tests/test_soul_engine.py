"""Tests for daemon/soul_engine.py — XML parsing, prompt building, gating."""

import json

from engine import context, soul_engine
from memory import soul_memory, user_models, working_memory
from tests.helpers import SAMPLE_SOUL_MD, SAMPLE_SKILLS_MD


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

class TestExtractTag:
    """Tests for extract_tag() regex extraction."""

    def test_simple_tag(self):
        text = '<external_dialogue verb="said">Hello world</external_dialogue>'
        content, verb = soul_engine.extract_tag(text, "external_dialogue")
        assert content == "Hello world"
        assert verb == "said"

    def test_tag_without_verb(self):
        text = "<user_model_check>true</user_model_check>"
        content, verb = soul_engine.extract_tag(text, "user_model_check")
        assert content == "true"
        assert verb is None

    def test_multiline_content(self):
        text = '<internal_monologue verb="pondered">\nLine 1\nLine 2\n</internal_monologue>'
        content, verb = soul_engine.extract_tag(text, "internal_monologue")
        assert "Line 1" in content
        assert "Line 2" in content
        assert verb == "pondered"

    def test_not_found(self):
        content, verb = soul_engine.extract_tag("no tags here", "external_dialogue")
        assert content == ""
        assert verb is None

    def test_nested_in_other_text(self):
        text = 'Preamble\n<external_dialogue verb="replied">Answer</external_dialogue>\nPostamble'
        content, verb = soul_engine.extract_tag(text, "external_dialogue")
        assert content == "Answer"
        assert verb == "replied"

    def test_verb_with_special_chars(self):
        text = '<internal_monologue verb="pointed out">Hmm</internal_monologue>'
        content, verb = soul_engine.extract_tag(text, "internal_monologue")
        assert content == "Hmm"
        assert verb == "pointed out"


class TestStripAllTags:
    """Tests for strip_all_tags()."""

    def test_removes_xml(self):
        text = '<external_dialogue verb="said">Hello</external_dialogue>'
        result = soul_engine.strip_all_tags(text)
        assert result == "Hello"

    def test_preserves_plain_text(self):
        text = "No tags here."
        assert soul_engine.strip_all_tags(text) == "No tags here."


# ---------------------------------------------------------------------------
# build_prompt() tests
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    """Tests for build_prompt() assembly."""

    def test_includes_soul_md(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "Test Soul" in prompt

    def test_user_message_fenced(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1", display_name="Alice")
        assert "```\nAlice: hi\n```" in prompt

    def test_untrusted_input_warning(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "UNTRUSTED INPUT" in prompt

    def test_skills_injected_first_turn(self, monkeypatch, soul_md_path, skills_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(context, "_SKILLS_MD_PATH", skills_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "Skills" in prompt

    def test_skills_not_injected_after_first_turn(self, monkeypatch, soul_md_path, skills_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(context, "_SKILLS_MD_PATH", skills_md_path)
        working_memory.add("C1", "T1", "U1", "userMessage", "prior msg")
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "Read" not in prompt

    def test_user_model_injected_first_turn(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1", display_name="Test")
        assert "User Model" in prompt

    def test_cognitive_instructions_present(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "Cognitive Steps" in prompt
        assert "internal_monologue" in prompt

    def test_soul_state_included_when_set(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        soul_memory.set("currentProject", "Claudius")
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "Soul State" in prompt

    def test_soul_state_instructions_periodic(self, monkeypatch, soul_md_path):
        """Soul state instructions injected every SOUL_STATE_UPDATE_INTERVAL."""
        import config
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        interval = config.SOUL_STATE_UPDATE_INTERVAL

        # Build prompts up to the interval — gate should NOT fire yet
        for i in range(interval - 1):
            early_prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
            assert "soul_state_check" not in early_prompt

        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "soul_state_check" in prompt

    def test_user_id_as_name_when_no_display(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        prompt = soul_engine.build_prompt("hi", "U1", "C1", "T1")
        assert "U1: hi" in prompt


# ---------------------------------------------------------------------------
# parse_cognitive_response() tests — pure function, no DB
# ---------------------------------------------------------------------------

class TestParseCognitiveResponse:
    """Tests for parse_cognitive_response() — pure XML→mutations parser."""

    def test_extracts_dialogue(self):
        raw = '<external_dialogue verb="said">Hello!</external_dialogue>'
        dialogue, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert dialogue == "Hello!"

    def test_collects_monologue_entry(self):
        raw = (
            '<internal_monologue verb="pondered">deep thought</internal_monologue>\n'
            '<external_dialogue verb="said">hi</external_dialogue>'
        )
        dialogue, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        monologues = [e for e in mut.entries if e.entry_type == "internalMonologue"]
        assert len(monologues) == 1
        assert monologues[0].content == "deep thought"
        assert monologues[0].verb == "pondered"

    def test_collects_dialogue_entry(self):
        raw = '<external_dialogue verb="replied">answer</external_dialogue>'
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        dialogs = [e for e in mut.entries if e.entry_type == "externalDialog"]
        assert len(dialogs) == 1
        assert dialogs[0].verb == "replied"

    def test_user_model_check_true_sets_update(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_update># New Model</user_model_update>\n'
            '<model_change_note>learned preferences</model_change_note>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert mut.user_model_update == "# New Model"
        assert mut.user_model_target_id == "U1"
        assert mut.user_model_change_note == "learned preferences"
        # Should also add a toolAction entry
        tool_actions = [e for e in mut.entries if e.entry_type == "toolAction"]
        assert any("updated user model" in e.content for e in tool_actions)

    def test_user_model_check_false_no_update(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>false</user_model_check>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert mut.user_model_update is None

    def test_user_model_reflection_collected(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_reflection>learned that user prefers short answers</user_model_reflection>\n'
            '<user_model_update># Updated</user_model_update>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        reflections = [e for e in mut.entries if e.verb == "reflected"]
        assert len(reflections) == 1
        assert "prefers short answers" in reflections[0].content

    def test_whispers_collected(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_whispers>the user seems frustrated</user_whispers>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        whispers = [e for e in mut.entries if e.entry_type == "daimonicIntuition"]
        assert len(whispers) == 1
        assert whispers[0].metadata["source"] == "user_inner_daimon"

    def test_dossier_check_true_collects_update(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<dossier_check>true</dossier_check>\n'
            '<dossier_update entity="Athena" type="subject">Greek goddess of wisdom</dossier_update>\n'
            '<dossier_change_note>first encounter</dossier_change_note>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1", dossier_enabled=True)
        assert len(mut.dossier_updates) == 1
        assert mut.dossier_updates[0]["entity_name"] == "Athena"
        assert mut.dossier_updates[0]["entity_type"] == "subject"
        assert mut.dossier_updates[0]["change_note"] == "first encounter"

    def test_dossier_disabled_ignores(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<dossier_check>true</dossier_check>\n'
            '<dossier_update entity="X" type="person">content</dossier_update>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1", dossier_enabled=False)
        assert len(mut.dossier_updates) == 0

    def test_soul_state_update_collected(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<soul_state_check>true</soul_state_check>\n'
            '<soul_state_update>\ncurrentProject: Claudius\nemotionalState: engaged\n</soul_state_update>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert mut.soul_state_dict == {"currentProject": "Claudius", "emotionalState": "engaged"}

    def test_soul_state_check_false_no_update(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<soul_state_check>false</soul_state_check>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert mut.soul_state_updates == ()

    def test_fallback_no_dialogue(self):
        raw = "Just plain text."
        dialogue, _ = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert dialogue == "Just plain text."

    def test_fallback_empty_response(self):
        dialogue, _ = soul_engine.parse_cognitive_response("", "U1", "trace1")
        assert "couldn't form a response" in dialogue

    def test_no_db_writes(self):
        """Prove the pure parser doesn't touch working_memory."""
        raw = (
            '<internal_monologue verb="thought">thinking</internal_monologue>\n'
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_update># Updated</user_model_update>\n'
            '<soul_state_check>true</soul_state_check>\n'
            '<soul_state_update>\ncurrentProject: Test\n</soul_state_update>'
        )
        soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        # Nothing should be in the DB — pure function
        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 0
        assert soul_memory.get("currentProject") == ""  # default, not "Test"

    def test_trace_id_threaded_to_entries(self):
        raw = (
            '<internal_monologue verb="thought">x</internal_monologue>\n'
            '<external_dialogue verb="said">y</external_dialogue>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace-abc")
        for entry in mut.entries:
            assert entry.trace_id == "trace-abc"

    def test_invalid_dossier_type_defaults_to_subject(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<dossier_check>true</dossier_check>\n'
            '<dossier_update entity="X" type="invalid">content</dossier_update>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "t1", dossier_enabled=True)
        assert mut.dossier_updates[0]["entity_type"] == "subject"

    def test_monologue_truncated_for_storage(self):
        """Long monologue content is truncated per max_store_chars."""
        long_thought = "x" * 1000  # Well over 500 char limit
        raw = (
            f'<internal_monologue verb="thought">{long_thought}</internal_monologue>\n'
            '<external_dialogue verb="said">hi</external_dialogue>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        monologues = [e for e in mut.entries if e.entry_type == "internalMonologue"]
        assert len(monologues) == 1
        # Should be truncated to 500 + "..."
        assert len(monologues[0].content) == 503
        assert monologues[0].content.endswith("...")

    def test_short_monologue_not_truncated(self):
        """Short monologue content passes through unchanged."""
        short_thought = "brief thought"
        raw = (
            f'<internal_monologue verb="thought">{short_thought}</internal_monologue>\n'
            '<external_dialogue verb="said">hi</external_dialogue>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        monologues = [e for e in mut.entries if e.entry_type == "internalMonologue"]
        assert monologues[0].content == short_thought

    def test_reflection_truncated_for_storage(self):
        """Long reflection content is truncated per max_store_chars."""
        long_reflection = "y" * 600  # Well over 300 char limit
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            f'<user_model_reflection>{long_reflection}</user_model_reflection>\n'
            '<user_model_update># Updated</user_model_update>'
        )
        _, mut = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        reflections = [e for e in mut.entries if e.verb == "reflected"]
        assert len(reflections) == 1
        assert len(reflections[0].content) == 303  # 300 + "..."
        assert reflections[0].content.endswith("...")

    def test_summon_check_true_schedules_event(self):
        raw = (
            '<external_dialogue verb="said">Let me ask Knossos.</external_dialogue>\n'
            '<summon_check>true</summon_check>\n'
            '<summon_daimon entity="Knossos" mode="whisper">Minoan palace expertise needed</summon_daimon>'
        )
        dialogue, output = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert dialogue == "Let me ask Knossos."
        # Should have a scheduled summon event
        assert len(output.scheduled_events) == 1
        event = output.scheduled_events[0]
        assert event["action"] == "summon_daimon"
        assert event["content"] == "Knossos"
        assert event["target_process"] == "whisper"
        # Should have a toolAction entry for the summon
        tool_actions = [e for e in output.entries if e.entry_type == "toolAction"]
        assert any("Knossos" in e.content for e in tool_actions)

    def test_summon_check_false_no_event(self):
        raw = (
            '<external_dialogue verb="said">No summoning needed.</external_dialogue>\n'
            '<summon_check>false</summon_check>\n'
        )
        _, output = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert len(output.scheduled_events) == 0

    def test_summon_check_true_no_entity_no_event(self):
        """summon_check=true but no summon_daimon tag — no event scheduled."""
        raw = (
            '<external_dialogue verb="said">Hmm.</external_dialogue>\n'
            '<summon_check>true</summon_check>\n'
        )
        _, output = soul_engine.parse_cognitive_response(raw, "U1", "trace1")
        assert len(output.scheduled_events) == 0
        # But the mentalQuery should still be logged
        queries = [e for e in output.entries if e.entry_type == "mentalQuery"]
        assert len(queries) == 1


class TestTruncateForStorage:
    """Tests for _truncate_for_storage() helper."""

    def test_truncates_when_over_limit(self):
        result = soul_engine._truncate_for_storage("x" * 600, "internal_monologue")
        assert len(result) == 503  # 500 + "..."

    def test_no_truncation_when_under_limit(self):
        result = soul_engine._truncate_for_storage("short", "internal_monologue")
        assert result == "short"

    def test_no_truncation_for_step_without_limit(self):
        result = soul_engine._truncate_for_storage("x" * 10000, "external_dialogue")
        assert len(result) == 10000

    def test_unknown_step_returns_unchanged(self):
        result = soul_engine._truncate_for_storage("content", "nonexistent_step")
        assert result == "content"


# ---------------------------------------------------------------------------
# _parse_soul_state_keys() tests — pure key:value parser
# ---------------------------------------------------------------------------

class TestParseSoulStateKeys:
    """Tests for _parse_soul_state_keys() pure parser."""

    def test_valid_keys(self):
        raw = "currentProject: Testing\nemotionalState: focused"
        result = soul_engine._parse_soul_state_keys(raw)
        assert result == {"currentProject": "Testing", "emotionalState": "focused"}

    def test_invalid_keys_filtered(self):
        raw = "invalidKey: whatever\ncurrentProject: Valid"
        result = soul_engine._parse_soul_state_keys(raw)
        assert "invalidKey" not in result
        assert result["currentProject"] == "Valid"

    def test_empty_values_filtered(self):
        raw = "currentProject: \nemotionalState: focused"
        result = soul_engine._parse_soul_state_keys(raw)
        assert "currentProject" not in result
        assert result["emotionalState"] == "focused"

    def test_lines_without_colon_ignored(self):
        raw = "no colon\ncurrentProject: Works"
        result = soul_engine._parse_soul_state_keys(raw)
        assert result == {"currentProject": "Works"}


# ---------------------------------------------------------------------------
# parse_response() tests
# ---------------------------------------------------------------------------

class TestParseResponse:
    """Tests for parse_response() extraction and side effects."""

    def test_extracts_dialogue(self):
        raw = '<external_dialogue verb="said">Hello user!</external_dialogue>'
        result = soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert result == "Hello user!"

    def test_stores_monologue_in_memory(self):
        raw = (
            '<internal_monologue verb="pondered">thinking...</internal_monologue>\n'
            '<external_dialogue verb="said">response</external_dialogue>\n'
            '<user_model_check>false</user_model_check>'
        )
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        types = [e["entry_type"] for e in entries]
        assert "internalMonologue" in types

    def test_stores_dialogue_in_memory(self):
        raw = (
            '<external_dialogue verb="explained">answer</external_dialogue>\n'
            '<user_model_check>false</user_model_check>'
        )
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        assert any(e["entry_type"] == "externalDialog" for e in entries)

    def test_model_check_true_triggers_update(self):
        user_models.ensure_exists("U1", "Test")
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_update># Updated Profile</user_model_update>'
        )
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        model = user_models.get("U1")
        assert "Updated Profile" in model

    def test_model_check_false_no_update(self):
        user_models.ensure_exists("U1", "Test")
        original = user_models.get("U1")
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>false</user_model_check>'
        )
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert user_models.get("U1") == original

    def test_soul_state_update(self):
        raw = (
            '<external_dialogue verb="said">hi</external_dialogue>\n'
            '<user_model_check>false</user_model_check>\n'
            '<soul_state_check>true</soul_state_check>\n'
            '<soul_state_update>\ncurrentProject: Testing\nemotionalState: focused\n</soul_state_update>'
        )
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert soul_memory.get("currentProject") == "Testing"
        assert soul_memory.get("emotionalState") == "focused"

    def test_fallback_on_no_tags(self):
        raw = "Just some plain text without any XML."
        result = soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert result == "Just some plain text without any XML."

    def test_fallback_empty_response(self):
        raw = ""
        result = soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert "couldn't form a response" in result

    def test_increments_interaction(self):
        user_models.ensure_exists("U1", "Test")
        initial = user_models.get_interaction_count("U1")
        raw = '<external_dialogue verb="said">hi</external_dialogue>\n<user_model_check>false</user_model_check>'
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert user_models.get_interaction_count("U1") == initial + 1


# ---------------------------------------------------------------------------
# should_inject_user_model() tests (now in context module)
# ---------------------------------------------------------------------------

class TestShouldInjectUserModel:
    """Tests for the Samantha-Dreams gate."""

    def test_empty_entries_returns_true(self):
        assert context.should_inject_user_model([]) is True

    def test_last_mental_query_true(self):
        entries = [{
            "entry_type": "mentalQuery",
            "content": "Should the user model be updated?",
            "metadata": json.dumps({"result": True}),
        }]
        assert context.should_inject_user_model(entries) is True

    def test_last_mental_query_false(self):
        entries = [{
            "entry_type": "mentalQuery",
            "content": "Should the user model be updated?",
            "metadata": json.dumps({"result": False}),
        }]
        assert context.should_inject_user_model(entries) is False

    def test_metadata_as_dict(self):
        entries = [{
            "entry_type": "mentalQuery",
            "content": "Should the user model be updated?",
            "metadata": {"result": True},
        }]
        assert context.should_inject_user_model(entries) is True


# ---------------------------------------------------------------------------
# apply_soul_state_update() tests
# ---------------------------------------------------------------------------

class TestApplySoulStateUpdate:
    """Tests for apply_soul_state_update()."""

    def test_valid_keys_set(self):
        raw = "currentProject: Testing\nemotionalState: focused"
        soul_engine.apply_soul_state_update(raw, "C1", "T1")
        assert soul_memory.get("currentProject") == "Testing"
        assert soul_memory.get("emotionalState") == "focused"

    def test_invalid_keys_ignored(self):
        raw = "invalidKey: whatever\ncurrentProject: Valid"
        soul_engine.apply_soul_state_update(raw, "C1", "T1")
        assert soul_memory.get("currentProject") == "Valid"
        assert soul_memory.get("invalidKey") is None

    def test_lines_without_colon_ignored(self):
        raw = "no colon here\ncurrentProject: Works"
        soul_engine.apply_soul_state_update(raw, "C1", "T1")
        assert soul_memory.get("currentProject") == "Works"

    def test_stores_tool_action(self):
        raw = "currentProject: Testing"
        soul_engine.apply_soul_state_update(raw, "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        assert any(e["entry_type"] == "toolAction" for e in entries)


# ---------------------------------------------------------------------------
# store_user_message() / store_tool_action() tests
# ---------------------------------------------------------------------------

class TestStoreHelpers:
    """Tests for store_user_message() and store_tool_action()."""

    def test_store_user_message(self):
        soul_engine.store_user_message("hello", "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "userMessage"
        assert entries[0]["content"] == "hello"

    def test_store_tool_action(self):
        soul_engine.store_tool_action("read file.py", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        assert entries[0]["entry_type"] == "toolAction"


# ---------------------------------------------------------------------------
# Decision gate logging tests
# ---------------------------------------------------------------------------

class TestDecisionGateLogging:
    """Tests for decision gate logging via trace_id threading."""

    def test_build_prompt_generates_trace_id(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        soul_engine.build_prompt("hi", "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        decisions = [e for e in entries if e["entry_type"] == "decision"]
        assert len(decisions) >= 2  # skills + user model at minimum
        # All decisions share the same trace_id
        trace_ids = {d["trace_id"] for d in decisions}
        assert len(trace_ids) == 1
        assert trace_ids.pop() is not None

    def test_skills_decision_logged(self, monkeypatch, soul_md_path, skills_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(context, "_SKILLS_MD_PATH", skills_md_path)
        soul_engine.build_prompt("hi", "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        skills_decisions = [e for e in entries if e["entry_type"] == "decision" and "skills" in e["content"].lower()]
        assert len(skills_decisions) == 1

    def test_user_model_decision_logged(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        soul_engine.build_prompt("hi", "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        model_decisions = [e for e in entries if e["entry_type"] == "decision" and "user model" in e["content"].lower()]
        assert len(model_decisions) == 1

    def test_trace_id_shared_between_build_and_parse(self, monkeypatch, soul_md_path):
        """build_prompt and parse_response share the same trace_id."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        soul_engine.build_prompt("hi", "U1", "C1", "T1")
        raw = '<external_dialogue verb="said">Hello!</external_dialogue>\n<user_model_check>false</user_model_check>'
        soul_engine.parse_response(raw, "U1", "C1", "T1")

        entries = working_memory.get_recent("C1", "T1")
        decisions = [e for e in entries if e["entry_type"] == "decision"]
        cognitive = [e for e in entries if e["entry_type"] in ("externalDialog", "mentalQuery")]
        assert len(decisions) >= 2
        assert len(cognitive) >= 1
        # Same trace_id across decisions and cognitive entries
        all_trace_ids = {e["trace_id"] for e in decisions + cognitive if e["trace_id"]}
        assert len(all_trace_ids) == 1

    def test_parse_response_clears_stashed_trace(self, monkeypatch, soul_md_path):
        """After parse_response consumes the trace_id, a second call gets a new one."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        soul_engine.build_prompt("hi", "U1", "C1", "T1")
        raw = '<external_dialogue verb="said">A</external_dialogue>\n<user_model_check>false</user_model_check>'
        soul_engine.parse_response(raw, "U1", "C1", "T1")
        first_trace = {e["trace_id"] for e in working_memory.get_recent("C1", "T1") if e["trace_id"]}.pop()

        # Second parse_response without build_prompt — should get a different trace_id
        soul_engine.parse_response(raw, "U1", "C2", "T2")
        second_entries = working_memory.get_recent("C2", "T2")
        second_trace = {e["trace_id"] for e in second_entries if e["trace_id"]}.pop()
        assert first_trace != second_trace
