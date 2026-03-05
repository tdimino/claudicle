"""Tests for daemon/user_models.py — templates, CRUD, interaction counting."""

from config import DEFAULT_USER_NAME
from memory import user_models


class TestEnsureExists:
    """Tests for ensure_exists() template creation."""

    def test_creates_template(self):
        model = user_models.ensure_exists("U1", display_name="Alice")
        assert "# Alice" in model
        assert "Persona" in model

    def test_idempotent(self):
        m1 = user_models.ensure_exists("U1", "Alice")
        m2 = user_models.ensure_exists("U1", "Alice")
        assert m1 == m2

    def test_uses_user_id_when_no_display_name(self):
        model = user_models.ensure_exists("U99")
        assert "# U99" in model


class TestSaveGet:
    """Tests for save() and get() round-trip."""

    def test_round_trip(self):
        user_models.save("U1", "# Custom Model\nSome content", "Alice")
        result = user_models.get("U1")
        assert result == "# Custom Model\nSome content"

    def test_get_nonexistent(self):
        assert user_models.get("NONEXISTENT") is None

    def test_save_updates_existing(self):
        user_models.save("U1", "v1", "Alice")
        user_models.save("U1", "v2")
        assert user_models.get("U1") == "v2"

    def test_display_name_preserved_on_update(self):
        user_models.save("U1", "v1", "Alice")
        user_models.save("U1", "v2")  # no display_name
        assert user_models.get_display_name("U1") == "Alice"


class TestGetDisplayName:
    """Tests for get_display_name()."""

    def test_returns_name(self):
        user_models.save("U1", "model", "Bob")
        assert user_models.get_display_name("U1") == "Bob"

    def test_returns_none_for_unknown(self):
        assert user_models.get_display_name("NOPE") is None


class TestFrontmatter:
    """Tests for YAML frontmatter in user model template."""

    def test_template_has_frontmatter(self):
        model = user_models.ensure_exists("U1", "Alice")
        assert model.startswith("---")
        assert "userName:" in model
        assert "userId:" in model
        assert "type: user-model" in model

    def test_frontmatter_interpolated(self):
        model = user_models.ensure_exists("U_TEST", "TestUser")
        meta = user_models.parse_frontmatter(model)
        assert meta["userName"] == "TestUser"
        assert meta["userId"] == "U_TEST"
        assert meta["type"] == "user-model"

    def test_parse_frontmatter_empty(self):
        assert user_models.parse_frontmatter("") == {}
        assert user_models.parse_frontmatter("no frontmatter") == {}

    def test_parse_frontmatter_no_closing(self):
        assert user_models.parse_frontmatter("---\ntitle: x\n") == {}

    def test_get_user_name(self):
        user_models.ensure_exists("U_NAME", "NameTest")
        name = user_models.get_user_name("U_NAME")
        assert name == "NameTest"

    def test_get_user_name_nonexistent(self):
        assert user_models.get_user_name("GHOST") is None

    def test_get_user_name_no_frontmatter(self):
        user_models.save("U_RAW", "# Plain model\nNo frontmatter here")
        assert user_models.get_user_name("U_RAW") is None


class TestOnboardingComplete:
    """Tests for onboardingComplete field in user model template."""

    def test_default_name_gets_onboarding_false(self):
        """Users with default name (Human) need onboarding."""
        model = user_models.ensure_exists("U1", DEFAULT_USER_NAME)
        meta = user_models.parse_frontmatter(model)
        assert meta["onboardingComplete"] == "false"

    def test_real_name_gets_onboarding_true(self):
        """Users with real names (from Slack API) skip onboarding."""
        model = user_models.ensure_exists("U1", "Alice")
        meta = user_models.parse_frontmatter(model)
        assert meta["onboardingComplete"] == "true"

    def test_no_display_name_gets_onboarding_false(self):
        """Users with no display_name need onboarding (unknown identity)."""
        model = user_models.ensure_exists("U99")
        meta = user_models.parse_frontmatter(model)
        assert meta["onboardingComplete"] == "false"


class TestInteractionCounting:
    """Tests for increment_interaction() and should_check_update()."""

    def test_initial_count_is_zero(self):
        assert user_models.get_interaction_count("U1") == 0

    def test_increment(self):
        user_models.ensure_exists("U1", "Test")
        user_models.increment_interaction("U1")
        assert user_models.get_interaction_count("U1") == 2  # save() sets to 1, +1

    def test_should_check_at_interval(self):
        """should_check_update triggers at USER_MODEL_UPDATE_INTERVAL boundaries."""
        import config
        interval = config.USER_MODEL_UPDATE_INTERVAL

        user_models.ensure_exists("U1", "Test")
        # After ensure_exists: count=1. Need to reach `interval`.
        for _ in range(interval - 1):
            user_models.increment_interaction("U1")
        assert user_models.should_check_update("U1") is True

    def test_should_not_check_before_interval(self):
        user_models.ensure_exists("U1", "Test")
        # count=1, not at interval boundary
        assert user_models.should_check_update("U1") is False

    def test_nonexistent_user_never_checks(self):
        assert user_models.should_check_update("GHOST") is False


# ---------------------------------------------------------------------------
# Tier 3: Modular user models
# ---------------------------------------------------------------------------


class TestModuleCRUD:
    """Tests for save_module, get_module, get_modules, list_modules, delete_module.

    Only 3 valid modules: expertise, history, preferences.
    Identity sections (persona, style, context, worldview) live in core model_md.
    """

    def test_save_and_get_module(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "Python, TypeScript, Ugaritic")
        result = user_models.get_module("U1", "expertise")
        assert "Python" in result

    def test_get_module_nonexistent(self):
        assert user_models.get_module("U1", "expertise") is None

    def test_save_module_updates_existing(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "v1")
        user_models.save_module("U1", "expertise", "v2")
        assert user_models.get_module("U1", "expertise") == "v2"

    def test_invalid_module_name_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid module name"):
            user_models.save_module("U1", "invalid_name", "content")

    def test_identity_sections_rejected_as_modules(self):
        """persona, style, context are identity — not valid modules."""
        import pytest
        for name in ("persona", "style", "context"):
            with pytest.raises(ValueError, match="Invalid module name"):
                user_models.save_module("U1", name, "content")

    def test_get_modules_all(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "expertise content")
        user_models.save_module("U1", "history", "history content")
        modules = user_models.get_modules("U1")
        assert set(modules.keys()) == {"expertise", "history"}
        assert "expertise content" in modules["expertise"]

    def test_get_modules_filtered(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "e")
        user_models.save_module("U1", "history", "h")
        user_models.save_module("U1", "preferences", "p")
        modules = user_models.get_modules("U1", ["expertise", "preferences"])
        assert set(modules.keys()) == {"expertise", "preferences"}

    def test_list_modules(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "x")
        user_models.save_module("U1", "history", "h")
        names = user_models.list_modules("U1")
        assert names == ["expertise", "history"]  # sorted

    def test_list_modules_empty(self):
        assert user_models.list_modules("GHOST") == []

    def test_has_modules(self):
        user_models.ensure_exists("U1", "Alice")
        assert user_models.has_modules("U1") is False
        user_models.save_module("U1", "expertise", "e")
        assert user_models.has_modules("U1") is True

    def test_delete_module(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.save_module("U1", "expertise", "e")
        assert user_models.delete_module("U1", "expertise") is True
        assert user_models.get_module("U1", "expertise") is None
        assert user_models.has_modules("U1") is False

    def test_delete_nonexistent_module(self):
        assert user_models.delete_module("U1", "expertise") is False

    def test_modules_isolated_per_user(self):
        user_models.ensure_exists("U1", "Alice")
        user_models.ensure_exists("U2", "Bob")
        user_models.save_module("U1", "expertise", "Alice expertise")
        user_models.save_module("U2", "expertise", "Bob expertise")
        assert "Alice" in user_models.get_module("U1", "expertise")
        assert "Bob" in user_models.get_module("U2", "expertise")

    def test_valid_modules_constant(self):
        expected = {"expertise", "history", "preferences"}
        assert user_models.VALID_MODULES == expected


class TestSelectModules:
    """Tests for select_modules() channel defaults + keyword activation.

    Only optional modules (expertise, history, preferences) are selectable.
    Identity sections are always in core.
    """

    def test_sms_channel_default_empty(self):
        result = user_models.select_modules("sms:+1234567890")
        assert result == []

    def test_slack_channel_default_expertise(self):
        result = user_models.select_modules("C04ABC123")
        assert "expertise" in result

    def test_terminal_channel_default(self):
        result = user_models.select_modules("terminal:abc123")
        assert "expertise" in result
        assert "preferences" in result

    def test_discord_channel_default_empty(self):
        result = user_models.select_modules("discord:1234")
        assert result == []

    def test_dm_channel_treated_as_slack(self):
        result = user_models.select_modules("D04ABC123")
        assert "expertise" in result

    def test_keyword_coding_adds_expertise(self):
        result = user_models.select_modules("sms:+123", "I've been coding in Python")
        assert "expertise" in result

    def test_keyword_domain_adds_expertise(self):
        result = user_models.select_modules("sms:+123", "What domain are you working in?")
        assert "expertise" in result

    def test_keyword_remember_adds_history(self):
        result = user_models.select_modules("sms:+123", "Do you remember our last conversation?")
        assert "history" in result

    def test_keyword_memory_adds_history(self):
        result = user_models.select_modules("sms:+123", "Check your memory for that")
        assert "history" in result

    def test_keyword_workflow_adds_preferences(self):
        result = user_models.select_modules("sms:+123", "I prefer a specific workflow")
        assert "preferences" in result

    def test_multiple_keywords_deduplicated(self):
        result = user_models.select_modules(
            "sms:+123", "I've been coding and prefer a new workflow"
        )
        # Should have expertise, preferences — no duplicates
        assert len(result) == len(set(result))
        assert "expertise" in result
        assert "preferences" in result

    def test_no_keywords_empty_message(self):
        result = user_models.select_modules("sms:+123", "")
        assert result == []

    def test_unknown_channel_no_defaults(self):
        result = user_models.select_modules("custom:xyz")
        assert result == []


class TestGetWithModules:
    """Tests for get_with_modules() assembly."""

    def test_no_modules_returns_core(self):
        user_models.save("U1", "# Alice\nCore model content", "Alice")
        result = user_models.get_with_modules("U1", "sms:+123")
        assert result == "# Alice\nCore model content"

    def test_with_modules_appends_selected(self):
        user_models.save("U1", "# Alice\nCore model", "Alice")
        user_models.save_module("U1", "expertise", "Python, TypeScript, Ugaritic")
        user_models.save_module("U1", "history", "Met at PyCon 2024")
        # Slack channel loads expertise by default
        result = user_models.get_with_modules("U1", "C04ABC")
        assert "Core model" in result
        assert "Module: Expertise" in result
        assert "Ugaritic" in result
        # History not loaded by default for Slack
        assert "PyCon" not in result

    def test_keyword_triggers_additional_modules(self):
        user_models.save("U1", "# Alice\nCore", "Alice")
        user_models.save_module("U1", "expertise", "Python expertise")
        # SMS + "coding" keyword → loads expertise
        result = user_models.get_with_modules("U1", "sms:+123", "What coding language?")
        assert "Python expertise" in result

    def test_explicit_module_names_override(self):
        user_models.save("U1", "# Alice\nCore", "Alice")
        user_models.save_module("U1", "history", "Past conversation notes")
        user_models.save_module("U1", "preferences", "Prefers concise answers")
        result = user_models.get_with_modules(
            "U1", "sms:+123", module_names=["history", "preferences"]
        )
        assert "Past conversation" in result
        assert "concise answers" in result

    def test_nonexistent_user_returns_empty(self):
        result = user_models.get_with_modules("GHOST", "sms:+123")
        assert result == ""

    def test_missing_module_silently_skipped(self):
        user_models.save("U1", "# Alice\nCore", "Alice")
        user_models.save_module("U1", "expertise", "e")
        # Request expertise + history, but only expertise exists
        result = user_models.get_with_modules(
            "U1", "sms:+123", module_names=["expertise", "history"]
        )
        assert "Module: Expertise" in result
        assert "Module: History" not in result
