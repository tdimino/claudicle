"""Tests for per-step model selection (Feature 2).

Covers the fallback chain: CognitiveStep.model → config.STEP_MODEL → DEFAULT_MODEL.
"""

import pytest

from engine.pipeline import _resolve_model, _resolve_provider


class TestResolveModel:
    def test_step_model_takes_priority(self, monkeypatch):
        """CognitiveStep.model should override config dicts."""
        import config
        monkeypatch.setattr(config, "STEP_MODEL", {"internal_monologue": "sonnet"})
        monkeypatch.setattr(config, "DEFAULT_MODEL", "opus")
        assert _resolve_model("internal_monologue", step_model="haiku") == "haiku"

    def test_config_dict_fallback(self, monkeypatch):
        """config.STEP_MODEL should be used when CognitiveStep.model is empty."""
        import config
        monkeypatch.setattr(config, "STEP_MODEL", {"user_model_check": "haiku"})
        monkeypatch.setattr(config, "DEFAULT_MODEL", "opus")
        assert _resolve_model("user_model_check") == "haiku"

    def test_default_model_fallback(self, monkeypatch):
        """DEFAULT_MODEL should be used when all else is empty."""
        import config
        monkeypatch.setattr(config, "STEP_MODEL", {"user_model_check": ""})
        monkeypatch.setattr(config, "DEFAULT_MODEL", "opus")
        assert _resolve_model("user_model_check") == "opus"

    def test_unknown_step_uses_default(self, monkeypatch):
        """Unknown step names should fall through to DEFAULT_MODEL."""
        import config
        monkeypatch.setattr(config, "STEP_MODEL", {})
        monkeypatch.setattr(config, "DEFAULT_MODEL", "sonnet")
        assert _resolve_model("nonexistent_step") == "sonnet"

    def test_empty_step_model_falls_through(self, monkeypatch):
        """Empty step_model arg should fall through to config."""
        import config
        monkeypatch.setattr(config, "STEP_MODEL", {"internal_monologue": "flash"})
        monkeypatch.setattr(config, "DEFAULT_MODEL", "opus")
        assert _resolve_model("internal_monologue", step_model="") == "flash"


class TestResolveProvider:
    def test_step_provider_takes_priority(self, monkeypatch):
        """CognitiveStep.provider should override config dicts."""
        import config
        from tests.helpers import MockProvider
        from providers import register

        mock = MockProvider(name="custom_prov")
        register(mock)

        monkeypatch.setattr(config, "STEP_PROVIDER", {"internal_monologue": "claude_cli"})
        result = _resolve_provider("internal_monologue", step_provider="custom_prov")
        assert result.name == "custom_prov"

    def test_config_dict_fallback(self, monkeypatch):
        """config.STEP_PROVIDER should be used when step_provider is empty."""
        import config
        from tests.helpers import MockProvider
        from providers import register

        mock = MockProvider(name="config_prov")
        register(mock)

        monkeypatch.setattr(config, "STEP_PROVIDER", {"soul_state_check": "config_prov"})
        result = _resolve_provider("soul_state_check")
        assert result.name == "config_prov"

    def test_default_provider_fallback(self, monkeypatch):
        """DEFAULT_PROVIDER should be used when all else is empty."""
        import config
        from tests.helpers import MockProvider
        from providers import register

        mock = MockProvider(name="default_prov")
        register(mock)

        monkeypatch.setattr(config, "STEP_PROVIDER", {})
        monkeypatch.setattr(config, "DEFAULT_PROVIDER", "default_prov")
        result = _resolve_provider("nonexistent_step")
        assert result.name == "default_prov"
