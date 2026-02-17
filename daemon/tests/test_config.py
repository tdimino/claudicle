"""Tests for daemon/config.py — env var precedence and defaults."""

import importlib
import os

import config


class TestEnvHelper:
    """Tests for _env() precedence logic."""

    def test_claudius_prefix_reads(self, monkeypatch):
        monkeypatch.setenv("CLAUDIUS_TIMEOUT", "999")
        assert config._env("TIMEOUT", "120") == "999"

    def test_slack_daemon_fallback(self, monkeypatch):
        monkeypatch.setenv("SLACK_DAEMON_TIMEOUT", "888")
        assert config._env("TIMEOUT", "120") == "888"

    def test_claudius_takes_precedence_over_slack_daemon(self, monkeypatch):
        monkeypatch.setenv("CLAUDIUS_TIMEOUT", "999")
        monkeypatch.setenv("SLACK_DAEMON_TIMEOUT", "888")
        assert config._env("TIMEOUT", "120") == "999"

    def test_default_when_neither_set(self):
        assert config._env("NONEXISTENT_KEY", "fallback") == "fallback"

    def test_empty_string_overrides_default(self, monkeypatch):
        monkeypatch.setenv("CLAUDIUS_FOO", "")
        assert config._env("FOO", "bar") == ""


class TestConfigDefaults:
    """Tests for module-level config values after reload."""

    def test_pipeline_mode_defaults_to_unified(self, monkeypatch):
        monkeypatch.delenv("CLAUDIUS_PIPELINE_MODE", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_PIPELINE_MODE", raising=False)
        importlib.reload(config)
        assert config.PIPELINE_MODE == "unified"

    def test_session_ttl_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDIUS_SESSION_TTL", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_SESSION_TTL", raising=False)
        importlib.reload(config)
        assert config.SESSION_TTL_HOURS == 24

    def test_soul_engine_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("CLAUDIUS_SOUL_ENGINE", raising=False)
        monkeypatch.delenv("SLACK_DAEMON_SOUL_ENGINE", raising=False)
        importlib.reload(config)
        assert config.SOUL_ENGINE_ENABLED is True
