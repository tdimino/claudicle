"""Tests for daemon lifecycle primitives — PID file, liveness, version, config hash."""

import fcntl
import os
import signal
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import lifecycle
from config import Settings


class TestVersionFile:
    def test_read_version_from_file(self, tmp_path, monkeypatch):
        version_file = tmp_path / "VERSION"
        version_file.write_text("0.15.0\n")
        monkeypatch.setattr(lifecycle, "VERSION_FILE", version_file)
        assert lifecycle.read_version() == "0.15.0"

    def test_read_version_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lifecycle, "VERSION_FILE", tmp_path / "MISSING")
        assert lifecycle.read_version() == "0.0.0"

    def test_read_version_strips_whitespace(self, tmp_path, monkeypatch):
        version_file = tmp_path / "VERSION"
        version_file.write_text("  0.15.0  \n\n")
        monkeypatch.setattr(lifecycle, "VERSION_FILE", version_file)
        assert lifecycle.read_version() == "0.15.0"


class TestPidFile:
    def test_write_and_read_pid(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)

        lifecycle.write_pid(12345)
        info = lifecycle.read_pid()

        assert info is not None
        assert info.pid == 12345
        assert info.version != ""
        assert info.start_time != ""

    def test_read_pid_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lifecycle, "PIDFILE", tmp_path / "nonexistent.pid")
        assert lifecycle.read_pid() is None

    def test_read_pid_malformed(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        pid_file.write_text("not-a-number\n")
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        assert lifecycle.read_pid() is None

    def test_read_pid_too_few_lines(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        pid_file.write_text("12345\n")
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        assert lifecycle.read_pid() is None

    def test_write_pid_creates_parent_dirs(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "deep" / "nested" / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        lifecycle.write_pid(99999)
        assert pid_file.exists()
        info = lifecycle.read_pid()
        assert info.pid == 99999

    def test_write_pid_defaults_to_current_process(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        lifecycle.write_pid()
        info = lifecycle.read_pid()
        assert info.pid == os.getpid()

    def test_remove_pid(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        pid_file.write_text("12345\n0.15.0\n2026-01-01T00:00:00Z\n")
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)

        lifecycle.remove_pid()
        assert not pid_file.exists()

    def test_remove_pid_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lifecycle, "PIDFILE", tmp_path / "nonexistent.pid")
        lifecycle.remove_pid()  # should not raise

    def test_write_pid_atomic(self, tmp_path, monkeypatch):
        """Verify no partial writes — file should always contain all 3 lines."""
        pid_file = tmp_path / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)

        for i in range(10):
            lifecycle.write_pid(10000 + i)
            content = pid_file.read_text()
            lines = content.strip().splitlines()
            assert len(lines) == 3, f"Iteration {i}: expected 3 lines, got {len(lines)}"
            assert lines[0] == str(10000 + i)


class TestLiveness:
    def test_is_alive_current_process(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        lifecycle.write_pid()
        info = lifecycle.read_pid()
        assert lifecycle.is_alive(info) is True

    def test_is_alive_none(self):
        assert lifecycle.is_alive(None) is False

    def test_is_alive_dead_process(self):
        info = lifecycle.DaemonInfo(pid=99999999, version="0.0.0", start_time="")
        assert lifecycle.is_alive(info) is False


class TestStopDaemon:
    def test_stop_daemon_not_running(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lifecycle, "PIDFILE", tmp_path / "claudicle.pid")
        result = lifecycle.stop_daemon()
        assert result is False

    def test_stop_daemon_stale_pid(self, tmp_path, monkeypatch):
        pid_file = tmp_path / "claudicle.pid"
        pid_file.write_text("99999999\n0.15.0\n2026-01-01T00:00:00Z\n")
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)

        result = lifecycle.stop_daemon()
        assert result is False
        assert not pid_file.exists()  # Stale PID file cleaned up


class TestEnsureDaemon:
    def test_ensure_daemon_already_running(self, tmp_path, monkeypatch):
        """When daemon is alive and version matches, ensure_daemon returns True."""
        pid_file = tmp_path / "claudicle.pid"
        lock_path = tmp_path / ".claudicle-start.lock"
        version_file = tmp_path / "VERSION"
        version_file.write_text("0.15.0\n")

        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        monkeypatch.setattr(lifecycle, "VERSION_FILE", version_file)

        # Write PID file for current process (so is_alive returns True)
        lifecycle.write_pid()

        result = lifecycle.ensure_daemon()
        assert result is True

    def test_ensure_daemon_not_running_spawns(self, tmp_path, monkeypatch):
        """When daemon is not running, ensure_daemon tries to spawn it."""
        pid_file = tmp_path / "claudicle.pid"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        monkeypatch.setattr(lifecycle, "LOG_FILE", tmp_path / "daemon.log")

        mock_popen = MagicMock()
        with patch("lifecycle.subprocess.Popen", mock_popen):
            result = lifecycle.ensure_daemon()

        # Returns False (fire-and-forget, not yet available)
        assert result is False
        mock_popen.assert_called_once()

    def test_ensure_daemon_version_mismatch_restarts(self, tmp_path, monkeypatch):
        """Version mismatch triggers stop and then spawn attempt."""
        pid_file = tmp_path / "claudicle.pid"
        version_file = tmp_path / "VERSION"
        version_file.write_text("0.16.0\n")  # Installed version is newer

        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)
        monkeypatch.setattr(lifecycle, "VERSION_FILE", version_file)
        monkeypatch.setattr(lifecycle, "LOG_FILE", tmp_path / "daemon.log")

        # Write PID file with old version (current PID so is_alive returns True)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(f"{os.getpid()}\n0.15.0\n2026-01-01T00:00:00Z\n")

        stop_calls = []

        def mock_stop(info=None):
            stop_calls.append(info)
            # Simulate stop: remove the PID file so the restart path kicks in
            try:
                pid_file.unlink()
            except FileNotFoundError:
                pass
            return True

        mock_popen = MagicMock()
        with patch.object(lifecycle, "stop_daemon", mock_stop), \
             patch("lifecycle.subprocess.Popen", mock_popen):
            result = lifecycle.ensure_daemon()

        assert len(stop_calls) == 1
        mock_popen.assert_called_once()

    def test_ensure_daemon_lock_prevents_concurrent(self, tmp_path, monkeypatch):
        """Second caller with lock held returns False immediately."""
        pid_file = tmp_path / "claudicle.pid"
        lock_path = pid_file.parent / ".claudicle-start.lock"
        monkeypatch.setattr(lifecycle, "PIDFILE", pid_file)

        # Acquire the lock first
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            result = lifecycle.ensure_daemon()
            assert result is False  # Lock held by us, returns immediately
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()


class TestConfigHash:
    def test_config_hash_deterministic(self):
        s = Settings()
        h1 = s.global_config_hash
        h2 = s.global_config_hash
        assert h1 == h2
        assert len(h1) == 8  # truncated SHA-256

    def test_config_hash_changes_with_soul_name(self):
        s1 = Settings(SOUL_NAME="Claudius")
        s2 = Settings(SOUL_NAME="Kothar")
        assert s1.global_config_hash != s2.global_config_hash

    def test_config_hash_changes_with_provider(self):
        s1 = Settings(DEFAULT_PROVIDER="claude_cli")
        s2 = Settings(DEFAULT_PROVIDER="groq")
        assert s1.global_config_hash != s2.global_config_hash

    def test_config_hash_stable_across_per_operation_changes(self):
        """Per-operation settings (compression threshold, etc.) don't affect hash."""
        s1 = Settings(COMPRESSION_THRESHOLD=50)
        s2 = Settings(COMPRESSION_THRESHOLD=100)
        assert s1.global_config_hash == s2.global_config_hash


class TestDaemonHealth:
    def test_daemon_health_unreachable(self):
        result = lifecycle.daemon_health("http://127.0.0.1:59999")
        assert result is None

    def test_daemon_version_unreachable(self):
        result = lifecycle.daemon_version("http://127.0.0.1:59999")
        assert result is None
