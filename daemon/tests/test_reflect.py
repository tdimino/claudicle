"""Tests for engine/reflect.py — retrospective cognitive pipeline.

Tests prompt assembly, XML parsing, memory updates, and provider routing.
Uses MockProvider (no real API calls).
"""

import json

import pytest

import config
from engine.reflect import (
    _PROVIDERS,
    _REFLECTION_STEPS,
    _resolve_api_key,
    build_reflection_prompt,
    run_reflection,
)
from engine.soul_engine import extract_tag
from memory import soul_memory, user_models, working_memory


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture
def reflection_exchange():
    """Standard test exchange for reflection."""
    return {
        "user_message": "Let's look at the test suite next.",
        "assistant_response": "Good call. I'll draft test cases for reflect.py.",
        "user_id": "tom",
        "channel": "terminal:test-001",
        "thread_ts": "test-001",
        "display_name": "Tom",
    }


# -- Provider registry -------------------------------------------------------

class TestProviderRegistry:
    def test_groq_in_registry(self):
        assert "groq" in _PROVIDERS
        url, key_env, _ = _PROVIDERS["groq"]
        assert "groq.com" in url
        assert key_env == "GROQ_API_KEY"

    def test_openrouter_in_registry(self):
        assert "openrouter" in _PROVIDERS
        url, key_env, _ = _PROVIDERS["openrouter"]
        assert "openrouter.ai" in url
        assert key_env == "OPENROUTER_API_KEY"

    def test_reflection_steps_defined(self):
        assert len(_REFLECTION_STEPS) == 5
        step_names = [s[0] for s in _REFLECTION_STEPS]
        assert "internal_monologue" in step_names
        assert "user_model_check" in step_names
        assert "soul_state_check" in step_names
        # No stimulus_verb, external_dialogue, or user_model_reflection in reflection
        assert "stimulus_verb" not in step_names
        assert "external_dialogue" not in step_names
        assert "user_model_reflection" not in step_names


# -- Prompt assembly ---------------------------------------------------------

class TestBuildReflectionPrompt:
    def test_prompt_contains_soul_md(self, soul_md_path, reflection_exchange):
        prompt = build_reflection_prompt(**reflection_exchange)
        assert "Artifex Maximus" in prompt or "soul" in prompt.lower()

    def test_prompt_contains_exchange(self, reflection_exchange):
        prompt = build_reflection_prompt(**reflection_exchange)
        assert reflection_exchange["user_message"] in prompt
        assert reflection_exchange["assistant_response"] in prompt

    def test_prompt_contains_cognitive_instructions(self, reflection_exchange):
        prompt = build_reflection_prompt(**reflection_exchange)
        assert "<internal_monologue" in prompt
        assert "<user_model_check>" in prompt
        assert "<soul_state_check>" in prompt

    def test_prompt_contains_user_model_section(self, soul_md_path, reflection_exchange):
        # Ensure user exists
        user_models.ensure_exists("tom", "Tom")
        prompt = build_reflection_prompt(**reflection_exchange)
        assert "User Model" in prompt

    def test_prompt_contains_display_name(self, reflection_exchange):
        prompt = build_reflection_prompt(**reflection_exchange)
        assert "Tom" in prompt

    def test_prompt_length_reasonable(self, reflection_exchange):
        prompt = build_reflection_prompt(**reflection_exchange)
        # Should be under 10K chars for a reflection prompt
        assert len(prompt) < 10000
        # But at least 1K (soul.md + instructions)
        assert len(prompt) > 1000


# -- XML parsing -------------------------------------------------------------

class TestXmlParsing:
    """Test that extract_tag() handles reflection-style XML correctly."""

    GOOD_RESPONSE = """
<internal_monologue verb="considered">
Tom wants to ensure test coverage before shipping. Practical and thorough.
</internal_monologue>

<user_model_check>true</user_model_check>

<user_model_update>
# Tom

## Persona
Builder and systematic thinker. Values test coverage.

## Speaking Style
Direct and concise. Imperative tone.
</user_model_update>

<model_change_note>Added testing emphasis to persona.</model_change_note>

<soul_state_check>true</soul_state_check>

<soul_state_update>
currentTask: reflection pipeline test coverage
currentTopic: testing reflect.py
emotionalState: focused
</soul_state_update>
"""

    MINIMAL_RESPONSE = """
<internal_monologue verb="noted">Brief thought.</internal_monologue>
<user_model_check>false</user_model_check>
<soul_state_check>false</soul_state_check>
"""

    def test_extract_monologue(self):
        content, verb = extract_tag(self.GOOD_RESPONSE, "internal_monologue")
        assert content is not None
        assert "test coverage" in content
        assert verb == "considered"

    def test_extract_user_model_check_true(self):
        content, _ = extract_tag(self.GOOD_RESPONSE, "user_model_check")
        assert content.strip().lower() == "true"

    def test_extract_user_model_check_false(self):
        content, _ = extract_tag(self.MINIMAL_RESPONSE, "user_model_check")
        assert content.strip().lower() == "false"

    def test_extract_user_model_update(self):
        content, _ = extract_tag(self.GOOD_RESPONSE, "user_model_update")
        assert content is not None
        assert "Tom" in content

    def test_extract_model_change_note(self):
        content, _ = extract_tag(self.GOOD_RESPONSE, "model_change_note")
        assert content is not None
        assert "testing" in content.lower()

    def test_extract_soul_state_check(self):
        content, _ = extract_tag(self.GOOD_RESPONSE, "soul_state_check")
        assert content.strip().lower() == "true"

    def test_extract_soul_state_update(self):
        content, _ = extract_tag(self.GOOD_RESPONSE, "soul_state_update")
        assert content is not None
        assert "currentTask" in content

    def test_missing_tag_returns_empty(self):
        content, verb = extract_tag(self.MINIMAL_RESPONSE, "user_model_update")
        assert not content  # empty string or None

    def test_missing_conditional_ok(self):
        """When check=false, update tags should be absent — that's correct."""
        content, _ = extract_tag(self.MINIMAL_RESPONSE, "soul_state_update")
        assert not content


# -- Key resolution ----------------------------------------------------------

class TestKeyResolution:
    def test_resolve_from_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key-123")
        assert _resolve_api_key("GROQ_API_KEY") == "test-key-123"

    def test_resolve_missing_returns_empty(self, monkeypatch, clean_env):
        assert _resolve_api_key("NONEXISTENT_KEY_XYZ") == ""


# -- Run reflection (mocked LLM) --------------------------------------------

class TestRunReflection:
    MOCK_XML = """
<internal_monologue verb="reflected">
Interesting exchange about testing. Tom is methodical.
</internal_monologue>

<user_model_check>false</user_model_check>

<soul_state_check>false</soul_state_check>
"""

    def test_run_reflection_disabled(self, monkeypatch, reflection_exchange):
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", False)
        result = run_reflection(**reflection_exchange)
        assert result["skipped"] is True
        assert "disabled" in result["reason"]

    def test_run_reflection_stores_exchange(self, monkeypatch, soul_md_path,
                                            reflection_exchange):
        """Even with a mocked LLM, the exchange should be stored in working memory."""
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm", lambda prompt, **kw: self.MOCK_XML)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        assert "trace_id" in result

        # Check working memory has the exchange
        entries = working_memory.get_recent("terminal:test-001", "test-001", limit=10)
        types = [e["entry_type"] for e in entries]
        assert "userMessage" in types
        assert "externalDialog" in types

    def test_run_reflection_parses_monologue(self, monkeypatch, soul_md_path,
                                              reflection_exchange):
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm", lambda prompt, **kw: self.MOCK_XML)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        assert "internal_monologue" in result["steps"]

    def test_run_reflection_llm_error(self, monkeypatch, soul_md_path,
                                       reflection_exchange):
        import engine.reflect as reflect_mod

        def fail_llm(prompt, **kw):
            raise RuntimeError("API key expired")

        monkeypatch.setattr(reflect_mod, "_call_llm", fail_llm)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        assert "error" in result
        assert "API key" in result["error"]


# -- Subprocess framing ------------------------------------------------------

class TestSubprocessFraming:
    """Verify Open Souls subprocess-level framing in reflection results."""

    MOCK_XML_WITH_UPDATES = """
<internal_monologue verb="reflected">
Tom is methodical about testing. Values systematic coverage.
</internal_monologue>

<user_model_check>true</user_model_check>

<user_model_update>
# Tom

## Persona
Builder and systematic thinker. Values test coverage.
</user_model_update>

<model_change_note>Added testing emphasis.</model_change_note>

<soul_state_check>false</soul_state_check>
"""

    MOCK_XML_NO_UPDATES = """
<internal_monologue verb="noted">Brief thought.</internal_monologue>
<user_model_check>false</user_model_check>
<soul_state_check>false</soul_state_check>
"""

    def test_summary_includes_subprocesses(self, monkeypatch, soul_md_path,
                                            reflection_exchange):
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm",
                            lambda prompt, **kw: self.MOCK_XML_WITH_UPDATES)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        assert "subprocesses" in result
        assert "modelsTheUser" in result["subprocesses"]
        assert "updatesState" in result["subprocesses"]

    def test_models_the_user_check_true(self, monkeypatch, soul_md_path,
                                         reflection_exchange):
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm",
                            lambda prompt, **kw: self.MOCK_XML_WITH_UPDATES)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        sp = result["subprocesses"]["modelsTheUser"]
        assert sp["check"] is True
        assert sp["updated"] is True

    def test_models_the_user_check_false(self, monkeypatch, soul_md_path,
                                          reflection_exchange):
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm",
                            lambda prompt, **kw: self.MOCK_XML_NO_UPDATES)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        sp = result["subprocesses"]["modelsTheUser"]
        assert sp["check"] is False
        assert sp["updated"] is False

    def test_updates_state_check_false(self, monkeypatch, soul_md_path,
                                        reflection_exchange):
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm",
                            lambda prompt, **kw: self.MOCK_XML_NO_UPDATES)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        result = run_reflection(**reflection_exchange)
        sp = result["subprocesses"]["updatesState"]
        assert sp["check"] is False
        assert sp["updated"] is False

    def test_mental_query_enriched_with_context(self, monkeypatch, soul_md_path,
                                                 reflection_exchange):
        """mentalQuery entries should include monologue context for reasoning chain."""
        import engine.reflect as reflect_mod
        monkeypatch.setattr(reflect_mod, "_call_llm",
                            lambda prompt, **kw: self.MOCK_XML_WITH_UPDATES)
        monkeypatch.setattr(config, "TERMINAL_REFLECT_ENABLED", True)

        run_reflection(**reflection_exchange)

        entries = working_memory.get_recent("terminal:test-001", "test-001", limit=20)
        queries = [e for e in entries if e["entry_type"] == "mentalQuery"]
        assert len(queries) >= 1
        # The user_model_check query should contain monologue context
        model_query = [q for q in queries if "user model" in q["content"].lower()][0]
        assert "context:" in model_query["content"]


# -- Reflection prompt compaction -------------------------------------------

# Large annotated soul.md to test compaction
_ANNOTATED_SOUL = """# Claudius, Artifex Maximus

## Persona <!-- priority: core -->

You are Claudius, a soul agent.

## Speaking Style <!-- priority: core -->

- Direct and concise.

## Values <!-- priority: core -->

- Assumptions are the enemy.

## Daimons <!-- priority: extended -->

Kothar wa Khasis is your primary daimon. He watches from the Mac Mini,
whispering counsel from deeper memory. His intuitions surface as recalled
impressions in your cognitive stream.

## Cognitive Rhythm <!-- priority: extended -->

Between significant exchanges, invoke your cognitive sub-daimones:
Leb for reflection, Eikon for user modeling, Rapu for user-voice.

## Relationship <!-- priority: extended -->

You remember people. You learn their patterns, their interests, their expertise.
When someone returns, you build on what came before.
"""

# User model with tiered sections
_TIERED_USER_MODEL = """# Test User

## Persona

Test user is a developer and poet.

## Worldview

AI as daimonic tradition.

## Speaking Style

Direct, no hedging, technically deep.

## Interests & Domains

Ancient Near East, Ugaritic, Python, AI agents.

## Working Patterns

Autonomous executor, parallel thinker.

## Notes

Likes em dashes attached to text.
"""


class TestReflectionCompaction:
    """Tests for compaction integration in build_reflection_prompt."""

    def test_compacted_prompt_shorter(self, monkeypatch):
        """With compaction enabled, reflection prompt should be shorter."""
        from engine import context as ctx_mod
        monkeypatch.setattr(ctx_mod, "load_soul", lambda: _ANNOTATED_SOUL)
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": _TIERED_USER_MODEL)

        monkeypatch.setattr(config, "COMPACTION_ENABLED", False)
        full = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )

        monkeypatch.setattr(config, "COMPACTION_ENABLED", True)
        compact = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )

        assert len(compact) < len(full)

    def test_compaction_preserves_core_soul(self, monkeypatch):
        """Core soul sections survive compaction."""
        from engine import context as ctx_mod
        monkeypatch.setattr(ctx_mod, "load_soul", lambda: _ANNOTATED_SOUL)
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": "")
        monkeypatch.setattr(config, "COMPACTION_ENABLED", True)

        prompt = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )
        assert "Claudius" in prompt
        assert "Assumptions are the enemy" in prompt

    def test_compaction_disabled_includes_everything(self, monkeypatch):
        """Without compaction, all sections present."""
        from engine import context as ctx_mod
        monkeypatch.setattr(ctx_mod, "load_soul", lambda: _ANNOTATED_SOUL)
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": _TIERED_USER_MODEL)
        monkeypatch.setattr(config, "COMPACTION_ENABLED", False)

        prompt = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )
        assert "Kothar" in prompt  # Extended soul
        assert "Autonomous executor" in prompt  # Full user model

    def test_user_model_tier_2_includes_interests(self, monkeypatch):
        """With compaction, user model at tier 2 includes Interests."""
        from engine import context as ctx_mod
        monkeypatch.setattr(ctx_mod, "load_soul", lambda: "# Soul")
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": _TIERED_USER_MODEL)
        monkeypatch.setattr(config, "COMPACTION_ENABLED", True)

        prompt = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )
        # Tier 2 includes Interests & Domains
        assert "Ugaritic" in prompt

    def test_empty_user_model_no_crash(self, monkeypatch):
        """Compaction handles empty user model gracefully."""
        from engine import context as ctx_mod
        monkeypatch.setattr(ctx_mod, "load_soul", lambda: "# Soul")
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": "")
        monkeypatch.setattr(config, "COMPACTION_ENABLED", True)

        prompt = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )
        assert "Exchange to Reflect On" in prompt

    def test_soul_load_failure_graceful(self, monkeypatch):
        """FileNotFoundError for soul.md handled with compaction active."""
        from engine import context as ctx_mod
        def _raise():
            raise FileNotFoundError("soul.md not found")
        monkeypatch.setattr(ctx_mod, "load_soul", _raise)
        monkeypatch.setattr(soul_memory, "format_for_prompt", lambda: "")
        monkeypatch.setattr(user_models, "ensure_exists", lambda uid, name="": "")
        monkeypatch.setattr(config, "COMPACTION_ENABLED", True)

        prompt = build_reflection_prompt(
            "hello", "hi", "U1", "terminal:abc", "1234", "TestUser"
        )
        assert "Exchange to Reflect On" in prompt
