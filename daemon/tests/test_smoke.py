"""Smoke tests — E2E import validation and round-trip tests."""

import json

import pytest

import soul_engine
import soul_memory
import user_models
import working_memory
import session_store
from tests.helpers import MockProvider, SAMPLE_SOUL_MD


class TestImports:
    """Verify all daemon modules import without error."""

    def test_core_modules(self):
        import config
        import soul_engine
        import working_memory
        import user_models
        import soul_memory
        import session_store
        import pipeline
        import claude_handler
        import inbox_watcher

    def test_providers(self):
        from providers import Provider, register, get_provider, list_providers


class TestSoulEngineRoundTrip:
    """End-to-end: build_prompt → craft XML → parse_response → verify."""

    def test_full_cognitive_cycle(self, monkeypatch, soul_md_path):
        monkeypatch.setattr(soul_engine, "_SOUL_MD_PATH", soul_md_path)

        # Build prompt
        prompt = soul_engine.build_prompt("What is Claudius?", "U1", "C1", "T1", display_name="Tom")
        assert "Test Soul" in prompt
        assert "What is Claudius?" in prompt

        # Simulate LLM XML response
        raw = (
            '<internal_monologue verb="pondered">An interesting question about my identity.</internal_monologue>\n'
            '<external_dialogue verb="explained">I am Claudius, a soul agent framework.</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_update># Tom\n\n## Interests\nAI soul frameworks</user_model_update>'
        )

        # Store user message first (as inbox_watcher does)
        soul_engine.store_user_message("What is Claudius?", "U1", "C1", "T1")

        # Parse response
        dialogue = soul_engine.parse_response(raw, "U1", "C1", "T1")
        assert dialogue == "I am Claudius, a soul agent framework."

        # Verify working memory entries
        entries = working_memory.get_recent("C1", "T1")
        types = [e["entry_type"] for e in entries]
        assert "userMessage" in types
        assert "internalMonologue" in types
        assert "externalDialog" in types
        assert "mentalQuery" in types
        assert "toolAction" in types  # from user model update

        # Verify user model updated
        model = user_models.get("U1")
        assert "AI soul frameworks" in model


class TestPipelineRoundTrip:
    """Pipeline round-trip with mock providers."""

    @pytest.mark.asyncio
    async def test_split_pipeline(self, monkeypatch, soul_md_path):
        import pipeline

        monkeypatch.setattr(soul_engine, "_SOUL_MD_PATH", soul_md_path)

        step_responses = {
            "internal_monologue": '<internal_monologue verb="thought">Pipeline thinking</internal_monologue>',
            "external_dialogue": '<external_dialogue verb="said">Pipeline response</external_dialogue>',
            "user_model_check": '<user_model_check>false</user_model_check>',
        }

        def mock_resolve(step_name):
            resp = step_responses.get(step_name, "<user_model_check>false</user_model_check>")
            return MockProvider(name=f"mock_{step_name}", response=resp)

        monkeypatch.setattr(pipeline, "_resolve_provider", mock_resolve)
        monkeypatch.setattr(pipeline, "_resolve_model", lambda s: "")

        result = await pipeline.run_pipeline("hello", "U1", "C1", "T1")
        assert result.dialogue == "Pipeline response"
        assert result.monologue == "Pipeline thinking"


class TestMultiTurnCognitiveCycle:
    """Full 3-turn cycle: first turn, gated turn, soul state update turn."""

    def test_three_turn_cycle(self, monkeypatch, soul_md_path):
        """Verify the Samantha-Dreams gate across 3 turns of conversation."""
        monkeypatch.setattr(soul_engine, "_SOUL_MD_PATH", soul_md_path)

        # Turn 1: First turn — empty working memory → gate returns True
        entries_t1 = working_memory.get_recent("C1", "T1", limit=5)
        assert soul_engine._should_inject_user_model(entries_t1) is True

        prompt1 = soul_engine.build_prompt("Hello", "U1", "C1", "T1", display_name="Tom")
        assert "User Model" in prompt1
        soul_engine.store_user_message("Hello", "U1", "C1", "T1")

        raw1 = (
            '<internal_monologue verb="thought">First impression</internal_monologue>\n'
            '<external_dialogue verb="said">Welcome!</external_dialogue>\n'
            '<user_model_check>false</user_model_check>'
        )
        soul_engine.parse_response(raw1, "U1", "C1", "T1")

        # Turn 2: model_check was false → gate should return False
        entries_t2 = working_memory.get_recent("C1", "T1", limit=5)
        assert soul_engine._should_inject_user_model(entries_t2) is False
        soul_engine.store_user_message("Tell me more", "U1", "C1", "T1")

        raw2 = (
            '<internal_monologue verb="considered">User wants depth</internal_monologue>\n'
            '<external_dialogue verb="detailed">Here is more detail.</external_dialogue>\n'
            '<user_model_check>true</user_model_check>\n'
            '<user_model_update># Tom\n\n## Interests\nLikes depth and detail</user_model_update>'
        )
        soul_engine.parse_response(raw2, "U1", "C1", "T1")

        # Turn 3: model_check was true → gate returns True, updated model injected
        entries_t3 = working_memory.get_recent("C1", "T1", limit=5)
        assert soul_engine._should_inject_user_model(entries_t3) is True

        prompt3 = soul_engine.build_prompt("And soul state?", "U1", "C1", "T1")
        assert "Likes depth" in prompt3


class TestSessionContinuity:
    """Session store preserves thread→session mapping across turns."""

    def test_two_turn_session(self):
        # Turn 1: new session
        session_store.save("C1", "T1", "session-001")
        assert session_store.get("C1", "T1") == "session-001"

        # Turn 2: resume
        session_store.touch("C1", "T1")
        assert session_store.get("C1", "T1") == "session-001"

        # Different thread: new session
        assert session_store.get("C1", "T2") is None
        session_store.save("C1", "T2", "session-002")
        assert session_store.get("C1", "T2") == "session-002"


class TestProviderRegistryMock:
    """Provider registry with mock flow."""

    def test_mock_provider_flow(self):
        from providers import register, get_provider, _registry
        _registry.clear()

        p = MockProvider(name="test", response="mocked output")
        register(p)

        provider = get_provider("test")
        result = provider.generate("some prompt")
        assert result == "mocked output"
        assert len(p.calls) == 1
        assert p.calls[0]["prompt"] == "some prompt"
