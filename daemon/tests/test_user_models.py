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
