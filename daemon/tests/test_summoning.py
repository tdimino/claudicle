"""Tests for daemon/daimonic/summoning.py — entity-to-daimon synthesis."""

import pytest

from daimonic import registry as daimon_registry
from daimonic import whispers
from daimonic.summoning import (
    _resolve_entity,
    dismiss_entity,
    list_summoned,
    summon_entity,
    synthesize_soul_md,
    _SUMMONED_PREFIX,
)
from memory import user_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_daimon_registry():
    """Save/restore daimon registry and whisper cache between tests."""
    saved_registry = dict(daimon_registry._registry)
    saved_cache = dict(whispers._soul_md_cache)
    yield
    daimon_registry._registry.clear()
    daimon_registry._registry.update(saved_registry)
    whispers._soul_md_cache.clear()
    whispers._soul_md_cache.update(saved_cache)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_dossier(name: str, content: str, entity_type: str = "subject"):
    """Insert a dossier directly for testing."""
    user_models.save_dossier(name, content, entity_type)


def _seed_user(user_id: str, content: str, display_name: str = ""):
    """Insert a user model directly for testing."""
    user_models.save(user_id, content, display_name=display_name)


# ---------------------------------------------------------------------------
# _resolve_entity
# ---------------------------------------------------------------------------

class TestResolveEntity:
    def test_resolve_dossier_by_name(self):
        _seed_dossier("Knossos", "# Knossos\nMinoan palace.")
        result = _resolve_entity("Knossos")
        assert result is not None
        entity_id, name, entity_type, md = result
        assert entity_id == "dossier:knossos"
        assert name == "Knossos"
        assert "Minoan palace" in md

    def test_resolve_user_by_id(self):
        _seed_user("U123", "# Alice\nEngineer.", display_name="Alice")
        result = _resolve_entity("U123")
        assert result is not None
        entity_id, name, entity_type, md = result
        assert entity_id == "U123"
        assert name == "Alice"
        assert entity_type == "user"

    def test_resolve_dossier_by_alias(self):
        # Use inline list format (what frontmatter.py supports)
        _seed_dossier(
            "Kothar wa Khasis",
            "---\naliases: [Kothar, Hephaestus]\n---\n# Kothar\nDivine craftsman.",
        )
        result = _resolve_entity("Hephaestus")
        assert result is not None
        assert result[1] == "Kothar wa Khasis"

    def test_resolve_nonexistent(self):
        assert _resolve_entity("Nonexistent Entity") is None

    def test_resolve_case_insensitive(self):
        _seed_dossier("Ugarit", "# Ugarit\nAncient city.")
        result = _resolve_entity("ugarit")
        assert result is not None
        assert result[1] == "Ugarit"


# ---------------------------------------------------------------------------
# synthesize_soul_md
# ---------------------------------------------------------------------------

class TestSynthesizeSoulMd:
    def test_user_template(self):
        soul = synthesize_soul_md(
            "U123", "# Alice\n## Speaking Style\nDirect and concise.\n## Expertise\nPython.",
            "user", "Alice",
        )
        assert "Alice" in soul
        assert "Origin" in soul
        assert "Direct and concise" in soul
        assert "Source Material" in soul

    def test_person_template(self):
        soul = synthesize_soul_md(
            "dossier:michael astour", "# Michael Astour\nScholar of Semitic studies.",
            "person", "Michael Astour",
        )
        assert "Michael Astour" in soul
        assert "understood through" in soul
        assert "Speak as" in soul

    def test_subject_template(self):
        soul = synthesize_soul_md(
            "dossier:knossos", "# Knossos\nMinoan palace complex.",
            "subject", "Knossos",
        )
        assert "Knossos" in soul
        assert "voice of" in soul
        assert "domain expert" in soul

    def test_unknown_type_falls_back_to_subject(self):
        soul = synthesize_soul_md("x", "content", "unknown_type", "X")
        assert "domain expert" in soul

    def test_entity_content_capped(self):
        long_content = "x" * 5000
        soul = synthesize_soul_md("x", long_content, "subject", "X")
        # Content should be capped at 3000 chars
        assert len(soul) < 5000

    def test_speaking_style_extraction(self):
        content = "# User\n## Speaking Style\nLaconic. Favors one-word answers.\n## Other\nStuff."
        soul = synthesize_soul_md("U1", content, "user", "TestUser")
        assert "Laconic" in soul
        assert "one-word" in soul


# ---------------------------------------------------------------------------
# summon_entity
# ---------------------------------------------------------------------------

class TestSummonEntity:
    def test_summon_registers_daimon(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Knossos", "# Knossos\nMinoan palace.")
        result = summon_entity("Knossos", invoke_immediately=False)
        assert result is None
        summoned = list_summoned()
        assert len(summoned) == 1
        assert summoned[0].display_name == "Knossos"
        assert summoned[0].enabled is True

    def test_summon_caches_soul_md(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Ugarit", "# Ugarit\nAncient coastal city.")
        summon_entity("Ugarit", invoke_immediately=False)
        reg_name = f"{_SUMMONED_PREFIX}dossier:ugarit"
        cache_key = f"__summoned__{reg_name}"
        assert cache_key in whispers._soul_md_cache
        assert "Ugarit" in whispers._soul_md_cache[cache_key]

    def test_summon_nonexistent_returns_none(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        result = summon_entity("Does Not Exist", invoke_immediately=False)
        assert result is None
        assert len(list_summoned()) == 0

    def test_summon_already_summoned(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Knossos", "# Knossos\nPalace.")
        summon_entity("Knossos", invoke_immediately=False)
        result = summon_entity("Knossos", invoke_immediately=False)
        assert result is None
        assert len(list_summoned()) == 1

    def test_summon_max_active(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        monkeypatch.setattr("config.SUMMONING_MAX_ACTIVE", 2, raising=False)
        _seed_dossier("A", "a")
        _seed_dossier("B", "b")
        _seed_dossier("C", "c")
        summon_entity("A", invoke_immediately=False)
        summon_entity("B", invoke_immediately=False)
        result = summon_entity("C", invoke_immediately=False)
        assert result is None
        assert len(list_summoned()) == 2

    def test_summon_user_model(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_user("U999", "# Bob\nA developer.", display_name="Bob")
        summon_entity("U999", invoke_immediately=False)
        summoned = list_summoned()
        assert len(summoned) == 1
        assert summoned[0].display_name == "Bob"


# ---------------------------------------------------------------------------
# dismiss_entity
# ---------------------------------------------------------------------------

class TestDismissEntity:
    def test_dismiss_removes_from_registry(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Knossos", "# Knossos\nPalace.")
        summon_entity("Knossos", invoke_immediately=False)
        assert len(list_summoned()) == 1
        dismissed = dismiss_entity("Knossos")
        assert dismissed is True
        assert len(list_summoned()) == 0

    def test_dismiss_clears_cache(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Ugarit", "# Ugarit\nCity.")
        summon_entity("Ugarit", invoke_immediately=False)
        reg_name = f"{_SUMMONED_PREFIX}dossier:ugarit"
        cache_key = f"__summoned__{reg_name}"
        assert cache_key in whispers._soul_md_cache
        dismiss_entity("Ugarit")
        assert cache_key not in whispers._soul_md_cache

    def test_dismiss_nonexistent(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        assert dismiss_entity("Not Summoned") is False

    def test_dismiss_frees_slot(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        monkeypatch.setattr("config.SUMMONING_MAX_ACTIVE", 1, raising=False)
        _seed_dossier("A", "a")
        _seed_dossier("B", "b")
        summon_entity("A", invoke_immediately=False)
        summon_entity("B", invoke_immediately=False)
        assert len(list_summoned()) == 1
        assert list_summoned()[0].display_name == "A"
        dismiss_entity("A")
        summon_entity("B", invoke_immediately=False)
        assert len(list_summoned()) == 1
        assert list_summoned()[0].display_name == "B"


# ---------------------------------------------------------------------------
# list_summoned
# ---------------------------------------------------------------------------

class TestListSummoned:
    def test_empty(self):
        assert list_summoned() == []

    def test_excludes_non_summoned_daimons(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        daimon_registry.register(daimon_registry.DaimonConfig(
            name="kothar", display_name="Kothar", soul_md="test",
            enabled=True, mode="whisper",
        ))
        _seed_dossier("Knossos", "# Knossos\nPalace.")
        summon_entity("Knossos", invoke_immediately=False)
        summoned = list_summoned()
        assert len(summoned) == 1
        assert summoned[0].name.startswith(_SUMMONED_PREFIX)

    def test_multiple_summoned(self, monkeypatch):
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("A", "a")
        _seed_dossier("B", "b")
        summon_entity("A", invoke_immediately=False)
        summon_entity("B", invoke_immediately=False)
        assert len(list_summoned()) == 2


# ---------------------------------------------------------------------------
# Cache trick validation
# ---------------------------------------------------------------------------

class TestCacheTrick:
    def test_load_soul_md_uses_cache(self, monkeypatch):
        """Verify that _load_soul_md returns cached content for summoned daimons."""
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("TestEntity", "# Test\nSome content.")
        summon_entity("TestEntity", invoke_immediately=False)

        summoned = list_summoned()
        assert len(summoned) == 1
        daimon = summoned[0]

        assert daimon.soul_md.startswith("__summoned__")

        loaded = whispers._load_soul_md(daimon.soul_md)
        assert loaded is not None
        assert "Test" in loaded
        assert "Source Material" in loaded

    def test_load_soul_md_synthetic_key_returns_none_not_blacklist(self, monkeypatch):
        """After dismiss, _load_soul_md should return None without blacklisting the key."""
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("CacheBug", "# Cache\nTest.")
        summon_entity("CacheBug", invoke_immediately=False)
        summoned = list_summoned()
        cache_key = summoned[0].soul_md

        # Dismiss removes from cache
        dismiss_entity("CacheBug")
        assert cache_key not in whispers._soul_md_cache

        # Calling _load_soul_md on a missing __summoned__ key should
        # return None WITHOUT writing None to the cache (no blacklisting)
        result = whispers._load_soul_md(cache_key)
        assert result is None
        assert cache_key not in whispers._soul_md_cache  # NOT blacklisted

        # Re-summon should work because cache was not blacklisted
        summon_entity("CacheBug", invoke_immediately=False)
        assert len(list_summoned()) == 1
        reloaded = whispers._load_soul_md(cache_key)
        assert reloaded is not None
        assert "Cache" in reloaded


# ---------------------------------------------------------------------------
# Whisper key consistency (regression for summoned daimon whisper mismatch)
# ---------------------------------------------------------------------------

class TestWhisperKeyConsistency:
    """Verify that store_whisper, format_for_prompt, and consume_all_whispers
    use the same key derivation for summoned daimons."""

    def test_store_and_format_use_same_key(self, monkeypatch):
        """Whispers stored via store_whisper should be found by format_for_prompt."""
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Knossos", "# Knossos\nMinoan palace.")
        summon_entity("Knossos", invoke_immediately=False)

        # Store a whisper using display_name (what invoke_daimon does)
        whispers.store_whisper("A bull leaps in the central court.", source="Knossos")

        # format_for_prompt should find it via the daimon registry
        prompt = whispers.format_for_prompt()
        assert "bull leaps" in prompt
        assert "Knossos whispers" in prompt

    def test_consume_clears_summoned_whisper(self, monkeypatch):
        """consume_all_whispers should clear whispers from summoned daimons."""
        monkeypatch.setattr("config.GROQ_API_KEY", "")
        _seed_dossier("Ugarit", "# Ugarit\nCoastal city.")
        summon_entity("Ugarit", invoke_immediately=False)

        whispers.store_whisper("Ships anchor at the harbor.", source="Ugarit")
        assert whispers.format_for_prompt()  # non-empty

        whispers.consume_all_whispers()
        assert whispers.format_for_prompt() == ""  # cleared

    def test_whisper_key_helper_matches_store(self):
        """_whisper_soul_key should produce the same key as store_whisper."""
        from memory import soul_memory

        whispers.store_whisper("test content", source="Kothar wa Khasis")
        key = whispers._whisper_soul_key("Kothar wa Khasis")
        assert key == "daimonic_whisper_kothar"
        assert soul_memory.get(key) == "test content"
