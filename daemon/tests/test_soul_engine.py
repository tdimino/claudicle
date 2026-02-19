"""Tests for daemon/soul_engine.py — XML parsing, prompt building, gating."""

import json

import context
import soul_engine
import soul_memory
import user_models
import working_memory
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
        soul_memory.set("currentProject", "Claudicle")
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
