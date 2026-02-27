"""Tests for new cognitive steps (Feature 3) and postProcess hooks (Feature 5).

Covers: brainstorm/decision/instruction extraction, extract_tag_with_attrs,
post_process hooks (cap_brainstorm, validate_decision), utility step registration.
"""

import json

import pytest

from cognitive_steps.steps import (
    BRAINSTORM,
    DECISION,
    INSTRUCTION,
    STEP_INSTRUCTIONS,
    STEP_REGISTRY,
    UTILITY_STEPS,
)
from engine.helpers import extract_tag, extract_tag_with_attrs
from engine.soul_engine import parse_cognitive_response
from memory.snapshot import CognitiveOutput


# ---------------------------------------------------------------------------
# extract_tag_with_attrs
# ---------------------------------------------------------------------------

class TestExtractTagWithAttrs:
    def test_single_attr(self):
        text = '<brainstorm count="3">["a", "b", "c"]</brainstorm>'
        content, attrs = extract_tag_with_attrs(text, "brainstorm")
        assert content == '["a", "b", "c"]'
        assert attrs == {"count": "3"}

    def test_multiple_attrs(self):
        text = '<decision options="a,b,c" reasoning="because">a</decision>'
        content, attrs = extract_tag_with_attrs(text, "decision")
        assert content == "a"
        assert attrs == {"options": "a,b,c", "reasoning": "because"}

    def test_no_attrs(self):
        text = "<instruction>step 1\nstep 2</instruction>"
        content, attrs = extract_tag_with_attrs(text, "instruction")
        assert content == "step 1\nstep 2"
        assert attrs == {}

    def test_not_found(self):
        content, attrs = extract_tag_with_attrs("no tags here", "brainstorm")
        assert content == ""
        assert attrs == {}

    def test_multiline_content(self):
        text = '<brainstorm count="2">\n["idea 1",\n "idea 2"]\n</brainstorm>'
        content, attrs = extract_tag_with_attrs(text, "brainstorm")
        assert "idea 1" in content
        assert attrs["count"] == "2"


# ---------------------------------------------------------------------------
# Utility step registration
# ---------------------------------------------------------------------------

class TestUtilityStepRegistration:
    def test_utility_steps_in_registry(self):
        """Utility steps should be in STEP_REGISTRY."""
        assert "brainstorm" in STEP_REGISTRY
        assert "decision" in STEP_REGISTRY
        assert "instruction" in STEP_REGISTRY

    def test_utility_steps_in_instructions(self):
        """Utility steps should be in STEP_INSTRUCTIONS."""
        assert "brainstorm" in STEP_INSTRUCTIONS
        assert "decision" in STEP_INSTRUCTIONS
        assert "instruction" in STEP_INSTRUCTIONS

    def test_utility_category(self):
        """Utility steps should have category='utility'."""
        for step in UTILITY_STEPS:
            assert step.category == "utility"

    def test_utility_steps_not_in_all_steps(self):
        """Utility steps should NOT be in ALL_STEPS (unified mode)."""
        from cognitive_steps.steps import ALL_STEPS
        all_names = {s.name for s in ALL_STEPS}
        for step in UTILITY_STEPS:
            assert step.name not in all_names


# ---------------------------------------------------------------------------
# Extraction in parse_cognitive_response
# ---------------------------------------------------------------------------

class TestUtilityExtraction:
    def test_brainstorm_extraction(self):
        raw = (
            '<internal_monologue verb="thought">thinking</internal_monologue>\n'
            '<external_dialogue verb="said">hello</external_dialogue>\n'
            '<brainstorm count="2">["idea1", "idea2"]</brainstorm>'
        )
        dialogue, output = parse_cognitive_response(raw, "user1", "trace1")
        brainstorm_entries = [e for e in output.entries if e.entry_type == "brainstorm"]
        assert len(brainstorm_entries) == 1
        assert '["idea1", "idea2"]' in brainstorm_entries[0].content
        assert brainstorm_entries[0].metadata.get("count") == "2"

    def test_decision_extraction(self):
        raw = (
            '<internal_monologue verb="thought">thinking</internal_monologue>\n'
            '<external_dialogue verb="said">hello</external_dialogue>\n'
            '<decision options="a,b,c" reasoning="b is best">b</decision>'
        )
        dialogue, output = parse_cognitive_response(raw, "user1", "trace1")
        decision_entries = [e for e in output.entries if e.entry_type == "decision"]
        assert len(decision_entries) == 1
        assert decision_entries[0].content == "b"
        assert decision_entries[0].metadata.get("options") == "a,b,c"
        assert decision_entries[0].metadata.get("reasoning") == "b is best"

    def test_instruction_extraction(self):
        raw = (
            '<internal_monologue verb="thought">thinking</internal_monologue>\n'
            '<external_dialogue verb="said">hello</external_dialogue>\n'
            '<instruction>Step 1: do this\nStep 2: do that</instruction>'
        )
        dialogue, output = parse_cognitive_response(raw, "user1", "trace1")
        instruction_entries = [e for e in output.entries if e.entry_type == "instruction"]
        assert len(instruction_entries) == 1
        assert "Step 1" in instruction_entries[0].content

    def test_no_utility_tags_is_fine(self):
        """Normal responses without utility tags should work unchanged."""
        raw = (
            '<internal_monologue verb="thought">thinking</internal_monologue>\n'
            '<external_dialogue verb="said">hello</external_dialogue>'
        )
        dialogue, output = parse_cognitive_response(raw, "user1", "trace1")
        assert dialogue == "hello"
        utility_entries = [e for e in output.entries if e.entry_type in ("brainstorm", "decision", "instruction")]
        assert len(utility_entries) == 0


# ---------------------------------------------------------------------------
# postProcess hooks
# ---------------------------------------------------------------------------

class TestPostProcessHooks:
    def test_cap_brainstorm(self):
        """cap_brainstorm should truncate to count attribute."""
        from cognitive_steps.hooks import cap_brainstorm
        raw = '<brainstorm count="2">["a", "b", "c", "d"]</brainstorm>'
        output = CognitiveOutput().with_entry("brainstorm", '["a", "b", "c", "d"]')
        result = cap_brainstorm(raw, output)
        brainstorm = [e for e in result.entries if e.entry_type == "brainstorm"]
        assert len(brainstorm) == 1
        ideas = json.loads(brainstorm[0].content)
        assert len(ideas) == 2
        assert ideas == ["a", "b"]

    def test_cap_brainstorm_already_within_limit(self):
        """cap_brainstorm should not modify if within limit."""
        from cognitive_steps.hooks import cap_brainstorm
        raw = '<brainstorm count="5">["a", "b"]</brainstorm>'
        output = CognitiveOutput().with_entry("brainstorm", '["a", "b"]')
        result = cap_brainstorm(raw, output)
        brainstorm = [e for e in result.entries if e.entry_type == "brainstorm"]
        ideas = json.loads(brainstorm[0].content)
        assert len(ideas) == 2

    def test_validate_decision_valid(self):
        """validate_decision should not modify if choice is valid."""
        from cognitive_steps.hooks import validate_decision
        raw = '<decision options="a,b,c">b</decision>'
        output = CognitiveOutput().with_entry("decision", "b", metadata={"options": "a,b,c"})
        result = validate_decision(raw, output)
        decision = [e for e in result.entries if e.entry_type == "decision"]
        assert decision[0].content == "b"

    def test_validate_decision_corrects_invalid(self):
        """validate_decision should correct to first option if choice is invalid."""
        from cognitive_steps.hooks import validate_decision
        raw = '<decision options="a,b,c">z</decision>'
        output = CognitiveOutput().with_entry("decision", "z", metadata={"options": "a,b,c"})
        result = validate_decision(raw, output)
        decision = [e for e in result.entries if e.entry_type == "decision"]
        assert decision[0].content == "a"
        assert decision[0].metadata.get("corrected_from") == "z"


# ---------------------------------------------------------------------------
# CognitiveStep post_process field
# ---------------------------------------------------------------------------

class TestPostProcessField:
    def test_default_is_none(self):
        """post_process should default to None."""
        assert BRAINSTORM.post_process is None
        assert DECISION.post_process is None

    def test_can_assign_hook(self):
        """Should be able to create a step with a post_process hook."""
        from cognitive_steps.steps import CognitiveStep

        def my_hook(raw, output):
            return output

        step = CognitiveStep(
            name="test", prompt="test", xml_tag="test",
            category="utility", post_process=my_hook,
        )
        assert step.post_process is my_hook
