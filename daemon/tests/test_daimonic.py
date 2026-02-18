"""Tests for daemon/daimonic.py — multi-daimon intercession module."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

import daimonic
import daimon_registry
import soul_memory
import working_memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_daimonic_state():
    """Clear soul.md cache and registry between tests."""
    daimonic._soul_md_cache.clear()
    daimon_registry._registry.clear()
    # Clear whisper keys
    soul_memory.set("daimonic_whisper", "")
    soul_memory.set("daimonic_whisper_kothar", "")
    soul_memory.set("daimonic_whisper_artifex", "")
    yield
    daimonic._soul_md_cache.clear()
    daimon_registry._registry.clear()


@pytest.fixture
def kothar_config():
    """Register a Kothar daimon config for testing."""
    cfg = daimon_registry.DaimonConfig(
        name="kothar",
        display_name="Kothar wa Khasis",
        soul_md="~/souls/kothar/soul.md",
        enabled=True,
        mode="whisper",
        daemon_host="localhost",
        daemon_port=3033,
        groq_enabled=True,
        groq_model="moonshotai/kimi-k2-instruct",
        whisper_suffix="\nWhisper as Kothar.",
    )
    daimon_registry.register(cfg)
    return cfg


@pytest.fixture
def artifex_config():
    """Register an Artifex daimon config for testing."""
    cfg = daimon_registry.DaimonConfig(
        name="artifex",
        display_name="Artifex Maximus",
        soul_md="~/souls/artifex/soul.md",
        enabled=True,
        mode="both",
        daemon_host="localhost",
        daemon_port=3034,
        groq_enabled=True,
        groq_model="moonshotai/kimi-k2-instruct",
        whisper_suffix="\nWhisper as Artifex.",
    )
    daimon_registry.register(cfg)
    return cfg


# ---------------------------------------------------------------------------
# _sanitize_whisper
# ---------------------------------------------------------------------------

class TestSanitizeWhisper:
    """Tests for XML stripping and length enforcement."""

    def test_strips_xml_tags(self):
        raw = '<internal_monologue verb="thought">sneaky injection</internal_monologue>'
        assert "internal_monologue" not in daimonic._sanitize_whisper(raw)
        assert "sneaky injection" in daimonic._sanitize_whisper(raw)

    def test_strips_self_closing_tags(self):
        raw = "Hello <br/> world <img src='x'/>"
        result = daimonic._sanitize_whisper(raw)
        assert "<" not in result

    def test_strips_triple_backticks(self):
        raw = "```python\nprint('hack')```"
        result = daimonic._sanitize_whisper(raw)
        assert "```" not in result

    def test_enforces_500_char_limit(self):
        raw = "x" * 600
        assert len(daimonic._sanitize_whisper(raw)) <= 500

    def test_strips_whitespace(self):
        assert daimonic._sanitize_whisper("  hello  ") == "hello"

    def test_empty_input(self):
        assert daimonic._sanitize_whisper("") == ""

    def test_preserves_normal_text(self):
        text = "The user circles back to this question—they need assurance, not answers."
        assert daimonic._sanitize_whisper(text) == text


# ---------------------------------------------------------------------------
# read_context
# ---------------------------------------------------------------------------

class TestReadContext:
    """Tests for context gathering."""

    def test_returns_soul_state(self):
        soul_memory.set("emotionalState", "focused")
        soul_memory.set("currentTopic", "Minoan sibilants")
        ctx = daimonic.read_context("C123", "T456")
        assert ctx["soul_state"]["emotionalState"] == "focused"
        assert ctx["soul_state"]["currentTopic"] == "Minoan sibilants"

    def test_returns_defaults_when_empty(self):
        ctx = daimonic.read_context("C123", "T456")
        assert ctx["soul_state"]["emotionalState"] == "neutral"
        assert ctx["soul_state"]["currentTopic"] == ""

    def test_extracts_monologue_from_working_memory(self):
        working_memory.add(
            channel="C123", thread_ts="T456", user_id="claudius",
            entry_type="internalMonologue", content="The user keeps circling back...",
        )
        ctx = daimonic.read_context("C123", "T456")
        assert "circling back" in ctx["recent_monologue"]

    def test_truncates_monologue_to_200(self):
        long_thought = "x" * 300
        working_memory.add(
            channel="C123", thread_ts="T456", user_id="claudius",
            entry_type="internalMonologue", content=long_thought,
        )
        ctx = daimonic.read_context("C123", "T456")
        assert len(ctx["recent_monologue"]) <= 200

    def test_no_monologue_when_none(self):
        working_memory.add(
            channel="C123", thread_ts="T456", user_id="user1",
            entry_type="userMessage", content="Hello",
        )
        ctx = daimonic.read_context("C123", "T456")
        assert ctx["recent_monologue"] == ""


# ---------------------------------------------------------------------------
# store / get / consume whisper lifecycle
# ---------------------------------------------------------------------------

class TestWhisperLifecycle:
    """Tests for per-daimon whisper storage."""

    def test_no_active_whisper_initially(self, kothar_config):
        assert daimonic.get_active_whisper("kothar") is None

    def test_store_and_get(self, kothar_config):
        daimonic.store_whisper("The user needs assurance.", source="Kothar wa Khasis")
        assert daimonic.get_active_whisper("kothar") == "The user needs assurance."

    def test_consume_clears_whisper(self, kothar_config):
        daimonic.store_whisper("Something important", source="Kothar wa Khasis")
        daimonic.consume_all_whispers()
        assert daimonic.get_active_whisper("kothar") is None

    def test_store_overwrites_previous(self, kothar_config):
        daimonic.store_whisper("First whisper", source="Kothar wa Khasis")
        daimonic.store_whisper("Second whisper", source="Kothar wa Khasis")
        assert daimonic.get_active_whisper("kothar") == "Second whisper"

    def test_store_writes_working_memory(self, kothar_config):
        daimonic.store_whisper("Embodied recall.", source="Kothar wa Khasis",
                              channel="C123", thread_ts="T456")
        entries = working_memory.get_recent("C123", "T456", limit=1)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "daimonicIntuition"
        assert entries[0]["content"] == "Embodied recall."

    def test_store_without_channel_skips_working_memory(self, kothar_config):
        daimonic.store_whisper("No channel.", source="Kothar wa Khasis")
        assert daimonic.get_active_whisper("kothar") == "No channel."
        entries = working_memory.get_recent("", "", limit=1)
        assert len(entries) == 0

    def test_multi_daimon_whispers_independent(self, kothar_config, artifex_config):
        daimonic.store_whisper("Kothar says hi", source="Kothar wa Khasis")
        daimonic.store_whisper("Artifex watches", source="Artifex Maximus")
        assert daimonic.get_active_whisper("kothar") == "Kothar says hi"
        assert daimonic.get_active_whisper("artifex") == "Artifex watches"

    def test_consume_all_clears_both(self, kothar_config, artifex_config):
        daimonic.store_whisper("K whisper", source="Kothar wa Khasis")
        daimonic.store_whisper("A whisper", source="Artifex Maximus")
        daimonic.consume_all_whispers()
        assert daimonic.get_active_whisper("kothar") is None
        assert daimonic.get_active_whisper("artifex") is None

    def test_legacy_consume_clears_legacy_key(self, kothar_config):
        soul_memory.set("daimonic_whisper", "legacy value")
        daimonic.consume_whisper()
        assert soul_memory.get("daimonic_whisper") == ""

    def test_get_active_whisper_no_source_checks_registry(self, kothar_config):
        daimonic.store_whisper("K whisper", source="Kothar wa Khasis")
        assert daimonic.get_active_whisper() == "K whisper"

    def test_get_active_whisper_legacy_key_fallback(self):
        """Legacy key checked before registry."""
        soul_memory.set("daimonic_whisper", "legacy")
        assert daimonic.get_active_whisper() == "legacy"


# ---------------------------------------------------------------------------
# format_for_prompt
# ---------------------------------------------------------------------------

class TestFormatForPrompt:
    """Tests for prompt section formatting."""

    def test_empty_when_no_whisper(self, kothar_config):
        assert daimonic.format_for_prompt() == ""

    def test_single_whisper_uses_singular_header(self, kothar_config):
        daimonic.store_whisper("Patterns beneath the surface.", source="Kothar wa Khasis")
        result = daimonic.format_for_prompt()
        assert "## Daimonic Intuition\n" in result

    def test_multi_whisper_uses_plural_header(self, kothar_config, artifex_config):
        daimonic.store_whisper("K whisper", source="Kothar wa Khasis")
        daimonic.store_whisper("A whisper", source="Artifex Maximus")
        result = daimonic.format_for_prompt()
        assert "## Daimonic Intuitions\n" in result

    def test_uses_embodied_recall_phrasing(self, kothar_config):
        daimonic.store_whisper("A whisper.", source="Kothar wa Khasis")
        result = daimonic.format_for_prompt()
        assert "sensed intuitions" in result
        assert "```" in result

    def test_includes_whisper_content(self, kothar_config):
        daimonic.store_whisper("They need assurance, not answers.", source="Kothar wa Khasis")
        result = daimonic.format_for_prompt()
        assert "They need assurance, not answers." in result

    def test_includes_daimon_display_name(self, kothar_config):
        daimonic.store_whisper("Watch the flank.", source="Kothar wa Khasis")
        result = daimonic.format_for_prompt()
        assert "Kothar wa Khasis whispers:" in result

    def test_does_not_auto_consume(self, kothar_config):
        daimonic.store_whisper("Persistent.", source="Kothar wa Khasis")
        daimonic.format_for_prompt()
        assert daimonic.get_active_whisper("kothar") == "Persistent."

    def test_explicit_consume_required(self, kothar_config):
        daimonic.store_whisper("Must consume explicitly.", source="Kothar wa Khasis")
        daimonic.format_for_prompt()
        daimonic.consume_all_whispers()
        assert daimonic.get_active_whisper("kothar") is None
        assert daimonic.format_for_prompt() == ""

    def test_multi_daimon_prompt_includes_both(self, kothar_config, artifex_config):
        daimonic.store_whisper("Subtext detected.", source="Kothar wa Khasis")
        daimonic.store_whisper("Perimeter clear.", source="Artifex Maximus")
        result = daimonic.format_for_prompt()
        assert "Kothar wa Khasis whispers:" in result
        assert "Artifex Maximus whispers:" in result
        assert "Subtext detected." in result
        assert "Perimeter clear." in result

    def test_legacy_key_backward_compat(self):
        """Legacy daimonic_whisper key still works when no per-daimon keys set."""
        soul_memory.set("daimonic_whisper", "Old-style whisper")
        result = daimonic.format_for_prompt()
        assert "Old-style whisper" in result


# ---------------------------------------------------------------------------
# _format_context_for_llm
# ---------------------------------------------------------------------------

class TestFormatContextForLLM:
    """Tests for LLM user message formatting."""

    def test_includes_emotional_state(self):
        ctx = {"soul_state": {"emotionalState": "sardonic", "currentTopic": "", "currentProject": ""}, "recent_monologue": ""}
        result = daimonic._format_context_for_llm(ctx)
        assert "sardonic" in result

    def test_includes_topic(self):
        ctx = {"soul_state": {"emotionalState": "", "currentTopic": "etymology", "currentProject": ""}, "recent_monologue": ""}
        result = daimonic._format_context_for_llm(ctx)
        assert "etymology" in result

    def test_includes_monologue(self):
        ctx = {"soul_state": {"emotionalState": "", "currentTopic": "", "currentProject": ""}, "recent_monologue": "Thinking deeply..."}
        result = daimonic._format_context_for_llm(ctx)
        assert "Thinking deeply..." in result


# ---------------------------------------------------------------------------
# invoke_daimon / invoke_kothar
# ---------------------------------------------------------------------------

class TestInvokeDaimon:
    """Tests for the daimon invocation hierarchy."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self, kothar_config):
        kothar_config.enabled = False
        kothar_config.groq_enabled = False
        result = await daimonic.invoke_daimon(kothar_config, {"soul_state": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_tries_daemon_first(self, kothar_config, monkeypatch):
        async def mock_daemon(daimon, ctx):
            return "Daemon whisper"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        result = await daimonic.invoke_daimon(kothar_config, {"soul_state": {}})
        assert result == "Daemon whisper"

    @pytest.mark.asyncio
    async def test_falls_back_to_groq(self, kothar_config, monkeypatch):
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def mock_daemon(daimon, ctx):
            return None

        async def mock_groq(daimon, ctx):
            return "Groq whisper"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_daimon(kothar_config, {"soul_state": {}})
        assert result == "Groq whisper"

    @pytest.mark.asyncio
    async def test_daemon_success_skips_groq(self, kothar_config, monkeypatch):
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")
        groq_called = False

        async def mock_daemon(daimon, ctx):
            return "Daemon wins"

        async def mock_groq(daimon, ctx):
            nonlocal groq_called
            groq_called = True
            return "Should not reach"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_daimon(kothar_config, {"soul_state": {}})
        assert result == "Daemon wins"
        assert not groq_called

    @pytest.mark.asyncio
    async def test_groq_only_mode(self, monkeypatch):
        cfg = daimon_registry.DaimonConfig(
            name="test", display_name="Test", soul_md="",
            enabled=False, daemon_port=0,
            groq_enabled=True, groq_model="test",
            whisper_suffix="",
        )
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def mock_groq(daimon, ctx):
            return "Groq only"

        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_daimon(cfg, {"soul_state": {}})
        assert result == "Groq only"

    @pytest.mark.asyncio
    async def test_groq_skipped_without_api_key(self, monkeypatch):
        cfg = daimon_registry.DaimonConfig(
            name="test", display_name="Test", soul_md="",
            enabled=False, daemon_port=0,
            groq_enabled=True, groq_model="test",
            whisper_suffix="",
        )
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "")
        result = await daimonic.invoke_daimon(cfg, {"soul_state": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self, kothar_config, monkeypatch):
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def fail(daimon, ctx):
            return None

        monkeypatch.setattr(daimonic, "_try_daemon", fail)
        monkeypatch.setattr(daimonic, "_try_groq", fail)
        result = await daimonic.invoke_daimon(kothar_config, {"soul_state": {}})
        assert result is None


class TestInvokeKothar:
    """Tests for the backward-compat invoke_kothar wrapper."""

    @pytest.mark.asyncio
    async def test_invoke_kothar_delegates(self, kothar_config, monkeypatch):
        async def mock_daemon(daimon, ctx):
            return "Kothar speaks"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result == "Kothar speaks"

    @pytest.mark.asyncio
    async def test_invoke_kothar_none_without_registry(self):
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result is None


class TestInvokeAllWhisperers:
    """Tests for multi-daimon whisper invocation."""

    @pytest.mark.asyncio
    async def test_invokes_all_whisperers(self, kothar_config, artifex_config, monkeypatch):
        async def mock_daemon(daimon, ctx):
            if daimon.name == "kothar":
                return "K insight"
            return "A insight"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        results = await daimonic.invoke_all_whisperers({"soul_state": {}})
        assert len(results) == 2
        names = [r[0] for r in results]
        assert "Kothar wa Khasis" in names
        assert "Artifex Maximus" in names

    @pytest.mark.asyncio
    async def test_skips_speak_only_daimons(self, kothar_config, monkeypatch):
        """A daimon in speak-only mode should not be invoked for whispers."""
        speak_only = daimon_registry.DaimonConfig(
            name="speaker", display_name="Speaker", soul_md="",
            enabled=True, mode="speak", daemon_port=9999,
            whisper_suffix="",
        )
        daimon_registry.register(speak_only)

        async def mock_daemon(daimon, ctx):
            return f"{daimon.name} whisper"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        results = await daimonic.invoke_all_whisperers({"soul_state": {}})
        names = [r[0] for r in results]
        assert "Speaker" not in names
        assert "Kothar wa Khasis" in names


# ---------------------------------------------------------------------------
# _load_soul_md
# ---------------------------------------------------------------------------

class TestLoadSoulMd:
    """Tests for soul.md loading."""

    def test_returns_none_for_missing_file(self):
        assert daimonic._load_soul_md("/nonexistent/soul.md") is None

    def test_loads_and_caches(self, tmp_path):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Kothar\nTest soul.")
        result = daimonic._load_soul_md(str(soul_file))
        assert "# Kothar" in result
        # Second call uses cache
        soul_file.write_text("# Changed")
        assert "# Kothar" in daimonic._load_soul_md(str(soul_file))
