"""Tests for engine/onboarding.py — first ensoulment mental process."""

import json

from engine import context, onboarding, soul_engine
from memory import user_models, working_memory
from config import DEFAULT_USER_NAME


class TestNeedsOnboarding:
    """Detection: does this user need onboarding?"""

    def test_new_user_with_default_name_needs_onboarding(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        assert onboarding.needs_onboarding("U1") is True

    def test_slack_user_with_real_name_skips_onboarding(self):
        user_models.ensure_exists("U1", "Alice")
        assert onboarding.needs_onboarding("U1") is False

    def test_completed_user_does_not_need_onboarding(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        assert onboarding.needs_onboarding("U1") is True
        # Simulate completion
        model = user_models.get("U1")
        updated = model.replace("onboardingComplete: false", "onboardingComplete: true")
        user_models.save("U1", updated)
        assert onboarding.needs_onboarding("U1") is False

    def test_nonexistent_user_does_not_need_onboarding(self):
        assert onboarding.needs_onboarding("GHOST") is False


class TestGetStage:
    """Stage tracking from working memory entries."""

    def test_initial_stage_is_zero(self):
        assert onboarding.get_stage("C1", "T1", "U1") == 0

    def test_stage_advances_after_completion(self):
        working_memory.add(
            "C1", "T1", "claudicle", "onboardingStep",
            "Completed onboarding stage 0",
            metadata={"stage": 0, "name": "Alice"},
        )
        assert onboarding.get_stage("C1", "T1", "U1") == 1

    def test_all_stages_complete_returns_four(self):
        for s in range(4):
            working_memory.add(
                "C1", "T1", "claudicle", "onboardingStep",
                f"Completed onboarding stage {s}",
                metadata={"stage": s},
            )
        assert onboarding.get_stage("C1", "T1", "U1") == 4


class TestBuildInstructions:
    """Instruction generation per stage."""

    def test_stage_0_greeting(self):
        instructions = onboarding.build_instructions(0, "U1", "Claudius")
        assert "First Ensoulment" in instructions
        assert "Claudius" in instructions
        assert "<user_name>" in instructions

    def test_stage_1_primary_check(self):
        user_models.ensure_exists("U1", "Alice")
        instructions = onboarding.build_instructions(1, "U1", "Claudius")
        assert "Alice" in instructions
        assert "<is_primary>" in instructions
        assert "primary user" in instructions.lower()

    def test_stage_2_persona(self):
        user_models.ensure_exists("U1", "Alice")
        instructions = onboarding.build_instructions(2, "U1", "Claudius")
        assert "Alice" in instructions
        assert "<persona_notes>" in instructions

    def test_stage_3_skills(self):
        user_models.ensure_exists("U1", "Alice")
        instructions = onboarding.build_instructions(3, "U1", "Claudius")
        assert "Alice" in instructions
        assert "<selected_skills>" in instructions


class TestParseResponse:
    """Response parsing and model updates per stage."""

    def test_stage_0_extracts_name(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        raw = (
            '<user_name>Alice</user_name>\n'
            '<onboarding_greeting>Hello Alice! I am Claudius.</onboarding_greeting>'
        )
        dialogue = onboarding.parse_response(raw, 0, "U1", "C1", "T1", "trace1")
        assert dialogue == "Hello Alice! I am Claudius."

    def test_stage_0_updates_user_model(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        raw = (
            '<user_name>Alice</user_name>\n'
            '<onboarding_greeting>Welcome!</onboarding_greeting>'
        )
        onboarding.parse_response(raw, 0, "U1", "C1", "T1", "trace1")

        # User model should now have "Alice" instead of default
        model = user_models.get("U1")
        assert 'userName: "Alice"' in model
        assert "# Alice" in model

    def test_stage_1_extracts_primary_yes(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        raw = (
            '<onboarding_dialogue>Welcome, primary user!</onboarding_dialogue>\n'
            '<is_primary>yes</is_primary>'
        )
        dialogue = onboarding.parse_response(raw, 1, "U1", "C1", "T1", "trace1")
        assert dialogue == "Welcome, primary user!"

        model = user_models.get("U1")
        assert 'role: "primary"' in model

    def test_stage_1_extracts_primary_no(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        raw = (
            '<onboarding_dialogue>Got it, you are a guest.</onboarding_dialogue>\n'
            '<is_primary>no</is_primary>'
        )
        dialogue = onboarding.parse_response(raw, 1, "U1", "C1", "T1", "trace1")
        assert dialogue == "Got it, you are a guest."

        model = user_models.get("U1")
        assert 'role: "standard"' in model

    def test_stage_2_extracts_persona(self):
        user_models.ensure_exists("U1", "Alice")
        raw = (
            '<onboarding_dialogue>Tell me about yourself!</onboarding_dialogue>\n'
            '<persona_notes>- Loves AI\n- Works in tech</persona_notes>'
        )
        dialogue = onboarding.parse_response(raw, 2, "U1", "C1", "T1", "trace1")
        assert dialogue == "Tell me about yourself!"

        # Persona notes should be applied
        model = user_models.get("U1")
        assert "Loves AI" in model

    def test_stage_3_marks_complete(self):
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        raw = (
            '<onboarding_dialogue>Great choices!</onboarding_dialogue>\n'
            '<selected_skills>rlama, firecrawl</selected_skills>'
        )
        onboarding.parse_response(raw, 3, "U1", "C1", "T1", "trace1")

        # Should be marked complete
        model = user_models.get("U1")
        assert "onboardingComplete: true" in model

    def test_fallback_strips_tags(self):
        raw = "Just some plain text response"
        dialogue = onboarding.parse_response(raw, 0, "U1", "C1", "T1", "trace1")
        assert dialogue == "Just some plain text response"


class TestEnsureExistsRole:
    """Role assignment via ensure_exists()."""

    def test_primary_user_gets_primary_role(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "PRIMARY_USER_ID", "U_PRIMARY")
        user_models.ensure_exists("U_PRIMARY", "Tom")
        model = user_models.get("U_PRIMARY")
        assert 'role: "primary"' in model

    def test_other_user_gets_standard_role(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "PRIMARY_USER_ID", "U_PRIMARY")
        user_models.ensure_exists("U_OTHER", "Alice")
        model = user_models.get("U_OTHER")
        assert 'role: "standard"' in model


class TestOnboardingRoundTrip:
    """Full 4-stage onboarding cycle."""

    def test_four_stage_interview(self, monkeypatch, soul_md_path):
        """Simulate a complete onboarding: name → primary? → persona → skills."""
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr("config.ONBOARDING_ENABLED", True)

        # Create user with default name → triggers onboarding
        user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        assert onboarding.needs_onboarding("U1") is True

        # Stage 0: Greeting — user provides name
        soul_engine.store_user_message("Hi there", "U1", "C1", "T1")
        raw0 = (
            '<user_name>Tom</user_name>\n'
            '<onboarding_greeting>Hello Tom! I am Claudius, your soul companion.</onboarding_greeting>'
        )
        dialogue0 = soul_engine.parse_response(raw0, "U1", "C1", "T1")
        assert "Tom" in dialogue0
        assert onboarding.get_stage("C1", "T1", "U1") == 1

        # Verify name was learned
        model = user_models.get("U1")
        assert 'userName: "Tom"' in model

        # Stage 1: Primary user check
        soul_engine.store_user_message("Yes, I set you up", "U1", "C1", "T1")
        raw1 = (
            '<onboarding_dialogue>Understood, Tom. You are my primary.</onboarding_dialogue>\n'
            '<is_primary>yes</is_primary>'
        )
        dialogue1 = soul_engine.parse_response(raw1, "U1", "C1", "T1")
        assert "primary" in dialogue1.lower()
        assert onboarding.get_stage("C1", "T1", "U1") == 2

        # Verify role was set
        model = user_models.get("U1")
        assert 'role: "primary"' in model

        # Stage 2: Persona definition
        soul_engine.store_user_message("I want you to be direct and technical", "U1", "C1", "T1")
        raw2 = (
            '<onboarding_dialogue>Got it, Tom. Direct and technical it is.</onboarding_dialogue>\n'
            '<persona_notes>- Prefers direct communication\n- Technical focus</persona_notes>'
        )
        dialogue2 = soul_engine.parse_response(raw2, "U1", "C1", "T1")
        assert "Direct and technical" in dialogue2
        assert onboarding.get_stage("C1", "T1", "U1") == 3

        # Verify persona was applied
        model = user_models.get("U1")
        assert "direct communication" in model

        # Stage 3: Skills selection
        soul_engine.store_user_message("Give me everything", "U1", "C1", "T1")
        raw3 = (
            '<onboarding_dialogue>All skills activated. Let\'s get to work.</onboarding_dialogue>\n'
            '<selected_skills>all</selected_skills>'
        )
        dialogue3 = soul_engine.parse_response(raw3, "U1", "C1", "T1")
        assert "All skills activated" in dialogue3

        # Verify onboarding complete
        assert onboarding.needs_onboarding("U1") is False
        model = user_models.get("U1")
        assert "onboardingComplete: true" in model
