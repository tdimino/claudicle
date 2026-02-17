"""Tests for daemon/providers/__init__.py — registry, fallback, protocol."""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

from tests.helpers import MockProvider


class TestRegistry:
    """Tests for provider registration and lookup."""

    def test_register_and_get(self):
        from providers import register, get_provider, _registry
        _registry.clear()

        p = MockProvider(name="test_provider", response="ok")
        register(p)
        assert get_provider("test_provider") is p

    def test_list_providers(self):
        from providers import register, list_providers, _registry
        _registry.clear()

        register(MockProvider(name="a"))
        register(MockProvider(name="b"))
        assert sorted(list_providers()) == ["a", "b"]

    def test_unknown_provider_raises(self):
        from providers import get_provider, _registry
        _registry.clear()

        with pytest.raises(KeyError, match="not registered"):
            get_provider("nonexistent")

    def test_empty_name_defaults_to_claude_cli(self):
        """Empty string falls back to claude_cli with lazy registration."""
        from providers import get_provider, _registry
        _registry.clear()

        # Mock the claude_cli import to avoid needing actual CLI
        mock_cli = MockProvider(name="claude_cli")
        with patch.dict("providers._registry", {"claude_cli": mock_cli}):
            result = get_provider("")
            assert result.name == "claude_cli"


class TestGenerateWithFallback:
    """Tests for generate_with_fallback() chain."""

    @pytest.mark.asyncio
    async def test_first_succeeds(self):
        from providers import register, generate_with_fallback, _registry
        _registry.clear()

        p1 = MockProvider(name="p1", response="from_p1")
        p2 = MockProvider(name="p2", response="from_p2")
        register(p1)
        register(p2)

        result = await generate_with_fallback("prompt", ["p1", "p2"])
        assert result == "from_p1"
        assert len(p1.calls) == 1
        assert len(p2.calls) == 0

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        from providers import register, generate_with_fallback, _registry
        _registry.clear()

        class FailProvider:
            name = "fail"
            def generate(self, prompt, model=""): raise RuntimeError("boom")
            async def agenerate(self, prompt, model=""): raise RuntimeError("boom")

        p2 = MockProvider(name="backup", response="from_backup")
        register(FailProvider())
        register(p2)

        result = await generate_with_fallback("prompt", ["fail", "backup"])
        assert result == "from_backup"

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        from providers import register, generate_with_fallback, _registry
        _registry.clear()

        class FailProvider:
            name = "fail1"
            def generate(self, prompt, model=""): raise RuntimeError("boom1")
            async def agenerate(self, prompt, model=""): raise RuntimeError("boom1")

        class FailProvider2:
            name = "fail2"
            def generate(self, prompt, model=""): raise RuntimeError("boom2")
            async def agenerate(self, prompt, model=""): raise RuntimeError("boom2")

        register(FailProvider())
        register(FailProvider2())

        with pytest.raises(RuntimeError, match="All providers failed"):
            await generate_with_fallback("prompt", ["fail1", "fail2"])


class TestMockProviderProtocol:
    """Verify MockProvider implements the Provider protocol."""

    def test_has_name(self):
        p = MockProvider(name="test")
        assert p.name == "test"

    def test_generate(self):
        p = MockProvider(response="hello")
        assert p.generate("prompt") == "hello"
        assert len(p.calls) == 1

    @pytest.mark.asyncio
    async def test_agenerate(self):
        p = MockProvider(response="async_hello")
        result = await p.agenerate("prompt", model="test-model")
        assert result == "async_hello"
        assert p.calls[0]["model"] == "test-model"

    def test_records_calls(self):
        p = MockProvider(response="x")
        p.generate("p1", "m1")
        p.generate("p2", "m2")
        assert len(p.calls) == 2
        assert p.calls[0] == {"prompt": "p1", "model": "m1"}
