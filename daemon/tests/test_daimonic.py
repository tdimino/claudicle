"""Tests for daemon/daimonic.py — daimonic intercession module."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

import daimonic
import soul_memory
import working_memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_daimonic_cache():
    """Clear Kothar soul.md cache between tests."""
    daimonic._kothar_soul_cache = None
    yield
    daimonic._kothar_soul_cache = None


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
    """Tests for soul_memory-based whisper storage."""

    def test_no_active_whisper_initially(self):
        assert daimonic.get_active_whisper() is None

    def test_store_and_get(self):
        daimonic.store_whisper("The user needs assurance.")
        assert daimonic.get_active_whisper() == "The user needs assurance."

    def test_consume_clears_whisper(self):
        daimonic.store_whisper("Something important")
        daimonic.consume_whisper()
        assert daimonic.get_active_whisper() is None

    def test_store_overwrites_previous(self):
        daimonic.store_whisper("First whisper")
        daimonic.store_whisper("Second whisper")
        assert daimonic.get_active_whisper() == "Second whisper"

    def test_store_writes_working_memory(self):
        daimonic.store_whisper("Embodied recall.", channel="C123", thread_ts="T456")
        entries = working_memory.get_recent("C123", "T456", limit=1)
        assert len(entries) == 1
        assert entries[0]["entry_type"] == "daimonicIntuition"
        assert entries[0]["content"] == "Embodied recall."

    def test_store_without_channel_skips_working_memory(self):
        daimonic.store_whisper("No channel.")
        # soul_memory still set
        assert daimonic.get_active_whisper() == "No channel."
        # working_memory has no entries for empty channel
        entries = working_memory.get_recent("", "", limit=1)
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# format_for_prompt
# ---------------------------------------------------------------------------

class TestFormatForPrompt:
    """Tests for prompt section formatting."""

    def test_empty_when_no_whisper(self):
        assert daimonic.format_for_prompt() == ""

    def test_includes_header(self):
        daimonic.store_whisper("Patterns beneath the surface.")
        result = daimonic.format_for_prompt()
        assert "## Daimonic Intuition" in result

    def test_uses_embodied_recall_phrasing(self):
        daimonic.store_whisper("A whisper.")
        result = daimonic.format_for_prompt()
        assert "sensed an intuition" in result
        assert "```" in result

    def test_includes_whisper_content(self):
        daimonic.store_whisper("They need assurance, not answers.")
        result = daimonic.format_for_prompt()
        assert "They need assurance, not answers." in result

    def test_does_not_auto_consume(self):
        daimonic.store_whisper("Persistent.")
        daimonic.format_for_prompt()
        assert daimonic.get_active_whisper() == "Persistent."

    def test_explicit_consume_required(self):
        daimonic.store_whisper("Must consume explicitly.")
        daimonic.format_for_prompt()
        daimonic.consume_whisper()
        assert daimonic.get_active_whisper() is None
        assert daimonic.format_for_prompt() == ""


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
# invoke_kothar (fallback chain)
# ---------------------------------------------------------------------------

class TestInvokeKothar:
    """Tests for the invocation hierarchy."""

    @pytest.mark.asyncio
    async def test_returns_none_when_both_disabled(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", False)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", False)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_tries_daemon_first(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", True)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", False)

        async def mock_daemon(ctx):
            return "Daemon whisper"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result == "Daemon whisper"

    @pytest.mark.asyncio
    async def test_falls_back_to_groq(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", True)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", True)
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def mock_daemon_fail(ctx):
            return None

        async def mock_groq(ctx):
            return "Groq whisper"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon_fail)
        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result == "Groq whisper"

    @pytest.mark.asyncio
    async def test_daemon_success_skips_groq(self, monkeypatch):
        """When daemon succeeds, Groq should never be called."""
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", True)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", True)
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        groq_called = False

        async def mock_daemon(ctx):
            return "Daemon wins"

        async def mock_groq(ctx):
            nonlocal groq_called
            groq_called = True
            return "Should not reach"

        monkeypatch.setattr(daimonic, "_try_daemon", mock_daemon)
        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result == "Daemon wins"
        assert not groq_called

    @pytest.mark.asyncio
    async def test_groq_only_mode(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", False)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", True)
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def mock_groq(ctx):
            return "Groq only"

        monkeypatch.setattr(daimonic, "_try_groq", mock_groq)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result == "Groq only"

    @pytest.mark.asyncio
    async def test_groq_skipped_without_api_key(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", False)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", True)
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "")
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_ENABLED", True)
        monkeypatch.setattr(daimonic, "KOTHAR_GROQ_ENABLED", True)
        monkeypatch.setattr(daimonic, "GROQ_API_KEY", "test-key")

        async def fail(ctx):
            return None

        monkeypatch.setattr(daimonic, "_try_daemon", fail)
        monkeypatch.setattr(daimonic, "_try_groq", fail)
        result = await daimonic.invoke_kothar({"soul_state": {}})
        assert result is None


# ---------------------------------------------------------------------------
# _load_kothar_soul
# ---------------------------------------------------------------------------

class TestLoadKotharSoul:
    """Tests for Kothar soul.md loading."""

    def test_returns_none_for_missing_file(self, monkeypatch):
        monkeypatch.setattr(daimonic, "KOTHAR_SOUL_MD", "/nonexistent/soul.md")
        assert daimonic._load_kothar_soul() is None

    def test_loads_and_caches(self, tmp_path, monkeypatch):
        soul_file = tmp_path / "soul.md"
        soul_file.write_text("# Kothar\nTest soul.")
        monkeypatch.setattr(daimonic, "KOTHAR_SOUL_MD", str(soul_file))
        result = daimonic._load_kothar_soul()
        assert "# Kothar" in result
        # Second call uses cache
        soul_file.write_text("# Changed")
        assert "# Kothar" in daimonic._load_kothar_soul()
