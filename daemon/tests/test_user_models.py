"""Tests for daemon/user_models.py — templates, CRUD, interaction counting."""

import user_models


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
