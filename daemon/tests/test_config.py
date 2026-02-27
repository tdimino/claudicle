"""Tests for daemon/config.py — env var precedence, defaults, and validation."""

import importlib

import pytest
from pydantic import ValidationError

import config


@pytest.fixture(autouse=True)
def _reload_config_after_test():
    """Restore config module to clean state after every test.

    Tests that call importlib.reload(config) or set_active_soul() mutate
    module-level globals. Without cleanup, subsequent tests (and modules
    that did 'from config import X') see stale values.

    The reload may fail if monkeypatch set invalid env vars that haven't
    been cleaned up yet (autouse teardown runs before monkeypatch teardown).
    That's safe to ignore — monkeypatch will restore the env, and the next
    test's setup or reload will succeed.
    """
    yield
    try:
        importlib.reload(config)
    except Exception:
        pass


class TestEnvHelper:
    """Tests for _env() precedence logic."""

    def test_claudicle_prefix_reads(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TIMEOUT", "999")
        assert config._env("TIMEOUT", "120") == "999"

    def test_slack_daemon_fallback(self, monkeypatch):
        monkeypatch.setenv("SLACK_DAEMON_TIMEOUT", "888")
        assert config._env("TIMEOUT", "120") == "888"

    def test_claudicle_takes_precedence_over_slack_daemon(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TIMEOUT", "999")
        monkeypatch.setenv("SLACK_DAEMON_TIMEOUT", "888")
        assert config._env("TIMEOUT", "120") == "999"

    def test_default_when_neither_set(self):
        assert config._env("NONEXISTENT_KEY", "fallback") == "fallback"

    def test_empty_string_overrides_default(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_FOO", "")
        assert config._env("FOO", "bar") == ""


class TestConfigDefaults:
    """Tests for module-level config values after reload."""

    def test_pipeline_mode_defaults_to_unified(self, monkeypatch):
        monkeypatch.delenv("CLAUDICLE_PIPELINE_MODE", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_PIPELINE_MODE", raising=False)
        importlib.reload(config)
        assert config.PIPELINE_MODE == "unified"

    def test_session_ttl_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDICLE_SESSION_TTL", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_SESSION_TTL", raising=False)
        importlib.reload(config)
        assert config.SESSION_TTL_HOURS == 24

    def test_soul_engine_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDICLE_SOUL_ENGINE", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_SOUL_ENGINE", raising=False)
        importlib.reload(config)
        assert config.SOUL_ENGINE_ENABLED is True


class TestPydanticValidation:
    """Tests for pydantic-settings coercion and validation."""

    def test_int_field_coercion(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_SESSION_TTL", "48")
        importlib.reload(config)
        assert config.SESSION_TTL_HOURS == 48
        assert isinstance(config.SESSION_TTL_HOURS, int)

    def test_bool_field_parses_truthy_strings(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_SOUL_ENGINE", "yes")
        importlib.reload(config)
        assert config.SOUL_ENGINE_ENABLED is True

    def test_bool_field_parses_falsey_strings(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_SOUL_ENGINE", "off")
        importlib.reload(config)
        assert config.SOUL_ENGINE_ENABLED is False

    def test_invalid_int_raises_validation_error(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_SESSION_TTL", "not-an-int")
        with pytest.raises(ValidationError):
            importlib.reload(config)


class TestBackwardsCompatibility:
    """Tests for compatibility with existing module-level access patterns."""

    def test_settings_values_reexported_as_module_globals(self, monkeypatch):
        monkeypatch.setenv("CLAUDICLE_TIMEOUT", "321")
        importlib.reload(config)
        assert config.CLAUDE_TIMEOUT == 321
        assert config.settings.CLAUDE_TIMEOUT == 321

    def test_set_active_soul_mutates_module_global(self, monkeypatch):
        monkeypatch.delenv("CLAUDICLE_SOUL_NAME", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_SOUL_NAME", raising=False)
        importlib.reload(config)

        config.set_active_soul("Apollo")
        assert config.SOUL_NAME == "Apollo"
        # autouse fixture handles cleanup via reload
