"""Tests for daemon/pipeline.py — split-mode routing, per-step provider calls."""

import importlib
from unittest.mock import patch

import pytest

from engine import context, pipeline, soul_engine
from memory import soul_memory, user_models, working_memory
from tests.helpers import MockProvider, SAMPLE_SOUL_MD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cognitive_response(step_name, content, verb=None):
    """Build a raw XML response for a cognitive step."""
    if verb:
        return f'<{step_name} verb="{verb}">{content}</{step_name}>'
    return f"<{step_name}>{content}</{step_name}>"


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestIsSplitMode:
    """Tests for is_split_mode()."""

    def test_unified_by_default(self):
        assert pipeline.is_split_mode() is False

    def test_split_when_configured(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "PIPELINE_MODE", "split")
        assert pipeline.is_split_mode() is True


class TestBuildContext:
    """Tests for context.build_context() shared context assembly."""

    def test_includes_soul(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        ctx = context.build_context("hi", "U1", "C1", "T1")
        assert "Test Soul" in ctx

    def test_includes_user_message(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        ctx = context.build_context("hi", "U1", "C1", "T1", display_name="Alice")
        assert "Alice: hi" in ctx

    def test_user_model_on_first_turn(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        ctx = context.build_context("hi", "U1", "C1", "T1")
        assert "User Model" in ctx


class TestBuildStepPrompt:
    """Tests for _build_step_prompt()."""

    def test_includes_context(self):
        prompt = pipeline._build_step_prompt("CONTEXT", "monologue", "INSTRUCTION")
        assert "CONTEXT" in prompt
        assert "INSTRUCTION" in prompt

    def test_includes_prior_outputs(self):
        prompt = pipeline._build_step_prompt("CTX", "dialogue", "INSTR", prior_outputs="<monologue>thinking</monologue>")
        assert "Prior Cognitive Steps" in prompt
        assert "thinking" in prompt

    def test_no_prior_section_when_empty(self):
        prompt = pipeline._build_step_prompt("CTX", "monologue", "INSTR")
        assert "Prior Cognitive Steps" not in prompt


# ---------------------------------------------------------------------------
# run_pipeline() tests
# ---------------------------------------------------------------------------

class TestRunPipeline:
    """Tests for run_pipeline() full execution."""

    @pytest.fixture
    def setup_pipeline(self, monkeypatch, soul_md_path):
        """Set up mocks for pipeline execution."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)

        responses = {
            "internal_monologue": _make_cognitive_response("internal_monologue", "thinking hard", verb="pondered"),
            "external_dialogue": _make_cognitive_response("external_dialogue", "Here is my answer", verb="explained"),
            "user_model_check": _make_cognitive_response("user_model_check", "false"),
        }

        providers = {}
        for step, response in responses.items():
            p = MockProvider(name=f"mock_{step}", response=response)
            providers[step] = p

        def mock_resolve_provider(step_name, step_provider=""):
            return providers.get(step_name, MockProvider(name="fallback", response="<user_model_check>false</user_model_check>"))

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve_provider)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")
        return providers

    @pytest.mark.asyncio
    async def test_full_success(self, setup_pipeline):
        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1", display_name="Test")
        assert result.dialogue == "Here is my answer"
        assert result.monologue == "thinking hard"
        assert result.monologue_verb == "pondered"
        assert result.dialogue_verb == "explained"

    @pytest.mark.asyncio
    async def test_stores_working_memory(self, setup_pipeline):
        await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        entries = working_memory.get_recent("C1", "T1")
        types = [e["entry_type"] for e in entries]
        assert "internalMonologue" in types
        assert "externalDialog" in types

    @pytest.mark.asyncio
    async def test_model_check_false_skips_update(self, setup_pipeline):
        user_models.ensure_exists("U1", "Test")
        original = user_models.get("U1")
        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert result.model_check is False
        assert user_models.get("U1") == original

    @pytest.mark.asyncio
    async def test_model_check_true_triggers_update(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)

        step_responses = {
            "internal_monologue": _make_cognitive_response("internal_monologue", "thinking", verb="thought"),
            "external_dialogue": _make_cognitive_response("external_dialogue", "response", verb="said"),
            "user_model_check": _make_cognitive_response("user_model_check", "true"),
            "user_model_update": _make_cognitive_response("user_model_update", "# Updated User Profile"),
        }

        def mock_resolve(step_name, step_provider=""):
            return MockProvider(name=f"mock_{step_name}", response=step_responses.get(step_name, ""))

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        user_models.ensure_exists("U1", "Test")
        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert result.model_check is True
        assert "Updated User Profile" in user_models.get("U1")

    @pytest.mark.asyncio
    async def test_monologue_failure_doesnt_block_dialogue(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)

        class FailOnMonologue:
            name = "fail_mono"
            def generate(self, prompt, model=""): raise RuntimeError("mono fail")
            async def agenerate(self, prompt, model=""): raise RuntimeError("mono fail")

        call_count = 0
        def mock_resolve(step_name, step_provider=""):
            if step_name == "internal_monologue":
                return FailOnMonologue()
            return MockProvider(
                name=f"mock_{step_name}",
                response=_make_cognitive_response("external_dialogue", "still works", verb="said")
                if step_name == "external_dialogue"
                else _make_cognitive_response("user_model_check", "false"),
            )

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert result.dialogue == "still works"
        assert result.monologue == ""

    @pytest.mark.asyncio
    async def test_soul_state_check_periodic(self, monkeypatch, soul_md_path):
        """Soul state check only runs at SOUL_STATE_UPDATE_INTERVAL."""
        import config
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        interval = config.SOUL_STATE_UPDATE_INTERVAL

        state_check_provider = MockProvider(
            name="state_check",
            response=_make_cognitive_response("soul_state_check", "true"),
        )
        state_update_provider = MockProvider(
            name="state_update",
            response=_make_cognitive_response("soul_state_update", "currentProject: TestProject"),
        )

        def mock_resolve(step_name, step_provider=""):
            if step_name == "soul_state_check":
                return state_check_provider
            if step_name == "soul_state_update":
                return state_update_provider
            return MockProvider(
                name=f"mock_{step_name}",
                response=_make_cognitive_response(step_name, "test", verb="said")
                if step_name in ("internal_monologue", "external_dialogue")
                else _make_cognitive_response("user_model_check", "false"),
            )

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        # Run up to interval - state check should trigger on the interval'th call
        context._interaction_count = interval - 1
        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert len(state_check_provider.calls) == 1
        assert len(state_update_provider.calls) == 1
        assert soul_memory.get("currentProject") == "TestProject"

    @pytest.mark.asyncio
    async def test_fallback_dialogue_on_extraction_failure(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)

        def mock_resolve(step_name, step_provider=""):
            return MockProvider(name=f"mock_{step_name}", response="no xml here")

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert "couldn't form a response" in result.dialogue

    @pytest.mark.asyncio
    async def test_increments_user_interaction(self, setup_pipeline):
        user_models.ensure_exists("U1", "Test")
        initial = user_models.get_interaction_count("U1")
        await pipeline.run_pipeline("hi", "U1", "C1", "T1")
        assert user_models.get_interaction_count("U1") == initial + 1


# ---------------------------------------------------------------------------
# Gate context stripping (Tier 2d)
# ---------------------------------------------------------------------------

class TestBuildGateContext:
    """Tests for _build_gate_context() — minimal context for boolean gates."""

    def test_user_model_check_includes_user_model(self):
        user_models.save("U123", "# TestUser\n\nLikes Python.")
        ctx = pipeline._build_gate_context("Hello", "TestUser", "", "user_model_check", "U123")
        assert "Likes Python" in ctx

    def test_user_model_check_includes_exchange(self):
        ctx = pipeline._build_gate_context("What time is it?", "Bob", "", "user_model_check", "U123")
        assert "What time is it?" in ctx
        assert "Bob" in ctx

    def test_soul_state_check_includes_soul_state(self):
        soul_memory.set("currentTopic", "testing pipelines")
        ctx = pipeline._build_gate_context("Hello", "Bob", "", "soul_state_check")
        assert "testing pipelines" in ctx

    def test_soul_state_check_excludes_user_model(self):
        user_models.save("U123", "# TestUser\n\nLikes Rust.")
        ctx = pipeline._build_gate_context("Hello", "Bob", "", "soul_state_check", "U123")
        assert "Likes Rust" not in ctx

    def test_dossier_check_excludes_both(self):
        user_models.save("U123", "# TestUser\n\nLikes Go.")
        soul_memory.set("currentTopic", "dossier testing")
        ctx = pipeline._build_gate_context("Hello", "Bob", "", "dossier_check", "U123")
        assert "Likes Go" not in ctx
        assert "dossier testing" not in ctx

    def test_gate_context_includes_prior_outputs(self):
        prior = '<internal_monologue verb="thought">Interesting.</internal_monologue>'
        ctx = pipeline._build_gate_context("Hello", "Bob", prior, "user_model_check", "U123")
        assert "Interesting" in ctx
        assert "Cognitive Outputs" in ctx

    def test_gate_context_shorter_than_full_context(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        full_ctx = context.build_context("Hello", "U123", "C456", "ts", "Bob")
        gate_ctx = pipeline._build_gate_context("Hello", "Bob", "", "user_model_check", "U123")
        assert len(gate_ctx) < len(full_ctx)

    def test_gate_context_uses_display_name(self):
        ctx = pipeline._build_gate_context("Hi", "Alice", "", "user_model_check", "U789")
        assert "Alice" in ctx

    def test_gate_context_falls_back_to_user_id(self):
        ctx = pipeline._build_gate_context("Hi", "", "", "user_model_check", "U789")
        assert "U789" in ctx


# ---------------------------------------------------------------------------
# Memory discard (Tier 2d — Open Souls pattern)
# ---------------------------------------------------------------------------

class TestMemoryDiscard:
    """When gates return false, raw LLM output is discarded from step_outputs."""

    @pytest.mark.asyncio
    async def test_false_gate_discards_raw(self, monkeypatch, soul_md_path):
        """user_model_check=false → raw NOT in step_outputs."""
        import config
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(config, "SOUL_STATE_UPDATE_INTERVAL", 1)

        def mock_resolve(step_name, step_provider=""):
            responses = {
                "internal_monologue": _make_cognitive_response("internal_monologue", "thinking", verb="thought"),
                "external_dialogue": _make_cognitive_response("external_dialogue", "reply", verb="said"),
                "user_model_check": _make_cognitive_response("user_model_check", "false"),
                "soul_state_check": _make_cognitive_response("soul_state_check", "false"),
            }
            return MockProvider(name=f"mock_{step_name}", response=responses.get(step_name, ""))

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1", "Test")
        assert result.model_check is False
        assert "user_model_check" not in result.step_outputs
        assert result.state_check is False
        assert "soul_state_check" not in result.step_outputs

    @pytest.mark.asyncio
    async def test_true_gate_retains_raw(self, monkeypatch, soul_md_path):
        """user_model_check=true → raw IS in step_outputs."""
        import config
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(config, "SOUL_STATE_UPDATE_INTERVAL", 1)

        def mock_resolve(step_name, step_provider=""):
            responses = {
                "internal_monologue": _make_cognitive_response("internal_monologue", "thinking", verb="thought"),
                "external_dialogue": _make_cognitive_response("external_dialogue", "reply", verb="said"),
                "user_model_check": _make_cognitive_response("user_model_check", "true"),
                "user_model_reflection": _make_cognitive_response("user_model_reflection", "learned something"),
                "user_model_update": _make_cognitive_response("user_model_update", "# Updated"),
                "user_whispers": _make_cognitive_response("user_whispers", "whisper"),
                "soul_state_check": _make_cognitive_response("soul_state_check", "true"),
                "soul_state_update": _make_cognitive_response("soul_state_update", "currentTopic: test"),
            }
            return MockProvider(name=f"mock_{step_name}", response=responses.get(step_name, ""))

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1", "Test")
        assert result.model_check is True
        assert "user_model_check" in result.step_outputs
        assert result.state_check is True
        assert "soul_state_check" in result.step_outputs

    @pytest.mark.asyncio
    async def test_core_steps_always_retained(self, monkeypatch, soul_md_path):
        """Monologue and dialogue raw outputs are always stored."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)

        def mock_resolve(step_name, step_provider=""):
            responses = {
                "internal_monologue": _make_cognitive_response("internal_monologue", "deep thought", verb="pondered"),
                "external_dialogue": _make_cognitive_response("external_dialogue", "hello", verb="said"),
                "user_model_check": _make_cognitive_response("user_model_check", "false"),
            }
            return MockProvider(name=f"mock_{step_name}", response=responses.get(step_name, ""))

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s, step_model="": "")

        result = await pipeline.run_pipeline("hi", "U1", "C1", "T1", "Test")
        assert "internal_monologue" in result.step_outputs
        assert "external_dialogue" in result.step_outputs


# ---------------------------------------------------------------------------
# Config dict completeness (dossier_check / dossier_update)
# ---------------------------------------------------------------------------

class TestConfigStepDicts:
    """Verify STEP_PROVIDER / STEP_MODEL dicts include all gate + update steps."""

    def test_default_step_provider_has_dossier_keys(self):
        from config import _default_step_provider
        d = _default_step_provider()
        assert "dossier_check" in d
        assert "dossier_update" in d

    def test_default_step_model_has_dossier_keys(self):
        from config import _default_step_model
        d = _default_step_model()
        assert "dossier_check" in d
        assert "dossier_update" in d

    def test_build_step_provider_has_dossier_keys(self):
        from config import _build_step_provider
        d = _build_step_provider()
        assert "dossier_check" in d
        assert "dossier_update" in d

    def test_build_step_model_has_dossier_keys(self):
        from config import _build_step_model
        d = _build_step_model()
        assert "dossier_check" in d
        assert "dossier_update" in d

    def test_step_dicts_have_all_gate_steps(self):
        from config import _default_step_provider, _default_step_model
        gates = {"user_model_check", "soul_state_check", "dossier_check"}
        assert gates.issubset(_default_step_provider().keys())
        assert gates.issubset(_default_step_model().keys())

    def test_step_dicts_have_all_update_steps(self):
        from config import _default_step_provider, _default_step_model
        updates = {"user_model_update", "soul_state_update", "dossier_update"}
        assert updates.issubset(_default_step_provider().keys())
        assert updates.issubset(_default_step_model().keys())
