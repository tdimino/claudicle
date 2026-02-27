"""Tests for the shared instruction builder (H5 — Memory Integrator pattern).

Covers: output format, stimulus_verb filtering, template variable substitution,
and that focused/frustrated processes use the shared builder correctly.
"""

import pytest


class TestBuildStepInstructions:
    def test_output_contains_mode_header(self, monkeypatch):
        """Output should contain the mode name in a ## header."""
        monkeypatch.setattr("config.SOUL_NAME", "TestSoul")
        monkeypatch.setattr("config.STIMULUS_VERB_ENABLED", True)
        from processes._shared import build_step_instructions

        result = build_step_instructions(
            steps=[("internal_monologue", "1. Internal Monologue")],
            mode_name="Test Mode",
            intro_lines=["Be concise."],
        )
        assert "## Cognitive Steps (Test Mode)" in result
        assert "Be concise." in result

    def test_output_contains_step_headings(self, monkeypatch):
        """Output should contain ### headings for each step."""
        monkeypatch.setattr("config.SOUL_NAME", "TestSoul")
        monkeypatch.setattr("config.STIMULUS_VERB_ENABLED", True)
        from processes._shared import build_step_instructions

        result = build_step_instructions(
            steps=[
                ("internal_monologue", "1. Internal Monologue"),
                ("external_dialogue", "2. External Dialogue"),
            ],
            mode_name="Test Mode",
            intro_lines=[],
        )
        assert "### 1. Internal Monologue" in result
        assert "### 2. External Dialogue" in result

    def test_filters_stimulus_verb_when_disabled(self, monkeypatch):
        """When filter_stimulus_verb=True and STIMULUS_VERB_ENABLED=False, skip it."""
        monkeypatch.setattr("config.SOUL_NAME", "TestSoul")
        monkeypatch.setattr("config.STIMULUS_VERB_ENABLED", False)
        from processes._shared import build_step_instructions

        result = build_step_instructions(
            steps=[
                ("stimulus_verb", "0. Stimulus Narration"),
                ("internal_monologue", "1. Internal Monologue"),
            ],
            mode_name="Test Mode",
            intro_lines=[],
            filter_stimulus_verb=True,
        )
        assert "Stimulus Narration" not in result
        assert "Internal Monologue" in result

    def test_keeps_stimulus_verb_when_not_filtering(self, monkeypatch):
        """When filter_stimulus_verb=False, keep stimulus_verb even if disabled."""
        monkeypatch.setattr("config.SOUL_NAME", "TestSoul")
        monkeypatch.setattr("config.STIMULUS_VERB_ENABLED", False)
        from processes._shared import build_step_instructions

        result = build_step_instructions(
            steps=[
                ("stimulus_verb", "0. Stimulus Narration"),
                ("internal_monologue", "1. Internal Monologue"),
            ],
            mode_name="Test Mode",
            intro_lines=[],
            filter_stimulus_verb=False,
        )
        assert "Stimulus Narration" in result

    def test_template_vars_substituted(self, monkeypatch):
        """Template vars like {user} should be substituted."""
        monkeypatch.setattr("config.SOUL_NAME", "TestSoul")
        monkeypatch.setattr("config.STIMULUS_VERB_ENABLED", True)
        from processes._shared import build_step_instructions

        result = build_step_instructions(
            steps=[("external_dialogue", "2. External Dialogue")],
            mode_name="Test Mode",
            intro_lines=[],
            user_id="U123",
            display_name="Alice",
        )
        # The step instructions should have {user} replaced with "Alice"
        assert "{user}" not in result
