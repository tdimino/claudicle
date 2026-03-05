"""Tests for engine.compaction — context compaction system."""

import pytest
from engine.compaction import (
    ContextBudget,
    _parse_soul_sections,
    compact_soul,
    compact_user_model,
    get_channel_budget,
    get_reflection_budget,
    select_user_model_tier,
)


# ---------------------------------------------------------------------------
# Soul section parsing
# ---------------------------------------------------------------------------

ANNOTATED_SOUL = """# Claudius, Artifex Maximus

## Persona <!-- priority: core -->

You are Claudius.

## Speaking Style <!-- priority: core -->

- Direct and concise.

## Values <!-- priority: core -->

- Assumptions are the enemy.

## Daimons <!-- priority: extended -->

Kothar wa Khasis is your primary daimon.

## Cognitive Rhythm <!-- priority: extended -->

Between significant exchanges, invoke your sub-daimones.

## Relationship <!-- priority: extended -->

You remember people.
"""


class TestParseSoulSections:
    def test_parses_annotated_sections(self):
        sections = _parse_soul_sections(ANNOTATED_SOUL)
        assert len(sections) == 7  # title + 6 headings

    def test_core_sections_identified(self):
        sections = _parse_soul_sections(ANNOTATED_SOUL)
        core = [s for s in sections if s["priority"] == "core"]
        assert len(core) >= 4  # title + Persona + Speaking Style + Values

    def test_extended_sections_identified(self):
        sections = _parse_soul_sections(ANNOTATED_SOUL)
        extended = [s for s in sections if s["priority"] == "extended"]
        assert len(extended) == 3  # Daimons + Cognitive Rhythm + Relationship

    def test_unannotated_defaults_to_extended(self):
        text = "# Title\n\n## Foo\n\nContent.\n\n## Bar\n\nMore."
        sections = _parse_soul_sections(text)
        non_title = [s for s in sections if s["heading"]]
        for s in non_title:
            assert s["priority"] == "extended"


class TestCompactSoul:
    def test_no_budget_returns_unchanged(self):
        assert compact_soul(ANNOTATED_SOUL, 0) == ANNOTATED_SOUL

    def test_large_budget_returns_unchanged(self):
        assert compact_soul(ANNOTATED_SOUL, 100000) == ANNOTATED_SOUL

    def test_small_budget_keeps_only_core(self):
        result = compact_soul(ANNOTATED_SOUL, 150)
        assert "Claudius" in result
        # Extended sections should be dropped
        assert "Kothar" not in result

    def test_medium_budget_includes_some_extended(self):
        # Budget large enough for core but not all extended
        core_only = compact_soul(ANNOTATED_SOUL, 200)
        full = compact_soul(ANNOTATED_SOUL, 100000)
        assert len(core_only) < len(full)

    def test_preserves_section_order(self):
        result = compact_soul(ANNOTATED_SOUL, 100000)
        persona_pos = result.find("Persona")
        speaking_pos = result.find("Speaking Style")
        values_pos = result.find("Values")
        assert persona_pos < speaking_pos < values_pos


# ---------------------------------------------------------------------------
# User model compaction
# ---------------------------------------------------------------------------

SAMPLE_MODEL = """# Tom di Mino

## Persona

Tom is a poet and builder of AI systems.

## Worldview

Minoan-Semitic connections, AI as daimonic tradition.

## Speaking Style

Direct, no hedging, technically deep.

## Interests & Domains

Ancient Near East, Ugaritic, Python, AI agents.

## Working Patterns

Autonomous executor, parallel thinker.

## Notes

Likes em dashes attached to text.
"""


class TestCompactUserModel:
    def test_tier_3_returns_full(self):
        assert compact_user_model(SAMPLE_MODEL, tier=3) == SAMPLE_MODEL

    def test_tier_1_includes_persona(self):
        result = compact_user_model(SAMPLE_MODEL, tier=1)
        assert "poet" in result

    def test_tier_1_includes_worldview(self):
        result = compact_user_model(SAMPLE_MODEL, tier=1)
        assert "Minoan-Semitic" in result

    def test_tier_1_includes_speaking_style(self):
        result = compact_user_model(SAMPLE_MODEL, tier=1)
        assert "no hedging" in result

    def test_tier_1_excludes_interests(self):
        result = compact_user_model(SAMPLE_MODEL, tier=1)
        assert "Ugaritic" not in result

    def test_tier_1_excludes_working_patterns(self):
        result = compact_user_model(SAMPLE_MODEL, tier=1)
        assert "Autonomous executor" not in result

    def test_tier_2_includes_interests(self):
        result = compact_user_model(SAMPLE_MODEL, tier=2)
        assert "Ugaritic" in result

    def test_tier_2_includes_working_patterns(self):
        result = compact_user_model(SAMPLE_MODEL, tier=2)
        assert "Autonomous executor" in result

    def test_budget_truncation(self):
        result = compact_user_model(SAMPLE_MODEL, tier=3, budget=100)
        assert len(result) <= 100

    def test_empty_model_returns_unchanged(self):
        assert compact_user_model("", tier=1) == ""

    def test_fallback_when_no_sections_match(self):
        # Model with no standard headings — should return full model
        weird = "Just some text with no headings."
        result = compact_user_model(weird, tier=1)
        assert result == weird


# ---------------------------------------------------------------------------
# Context budget
# ---------------------------------------------------------------------------

class TestContextBudget:
    def test_default_no_limit(self):
        b = ContextBudget()
        assert b.total == 0
        assert b.soul == 0

    def test_consume_tracks_surplus(self):
        b = ContextBudget(soul=1000)
        surplus = b.consume("soul", 600)
        assert surplus == 400
        assert b.surplus_pool == 400

    def test_consume_no_budget_returns_zero(self):
        b = ContextBudget(soul=0)
        assert b.consume("soul", 100) == 0

    def test_available_includes_surplus(self):
        b = ContextBudget(soul=1000, user_model=500)
        b.consume("soul", 600)  # 400 surplus
        assert b.available("user_model") == 900  # 500 + 400 surplus

    def test_available_zero_when_no_budget(self):
        b = ContextBudget(soul=0)
        assert b.available("soul") == 0


class TestGetChannelBudget:
    def test_sms_channel(self):
        b = get_channel_budget("sms:+1234567890")
        assert b.total == 3000
        assert b.soul == 800

    def test_slack_channel(self):
        b = get_channel_budget("C04ABC123")
        assert b.total == 6000

    def test_terminal_channel(self):
        b = get_channel_budget("terminal:abc123")
        assert b.total == 0  # no limit

    def test_discord_channel(self):
        b = get_channel_budget("discord:123456")
        assert b.total == 6000  # same as slack

    def test_unknown_channel(self):
        b = get_channel_budget("unknown:foo")
        assert b.total == 0  # no compaction

    def test_reflection_budget(self):
        b = get_reflection_budget()
        assert b.total == 4000
        assert b.soul == 800


class TestSelectUserModelTier:
    def test_sms_no_gate(self):
        assert select_user_model_tier("sms:+1234567890", False) == 1

    def test_sms_with_gate(self):
        assert select_user_model_tier("sms:+1234567890", True) == 2

    def test_slack_no_gate(self):
        assert select_user_model_tier("C04ABC123", False) == 1

    def test_slack_with_gate(self):
        assert select_user_model_tier("C04ABC123", True) == 2

    def test_terminal(self):
        # Terminal without gate = tier 1
        assert select_user_model_tier("terminal:abc", False) == 1
