"""Tests for daemon/claude_handler.py — subprocess handler, session store."""

import json
from unittest.mock import patch, MagicMock

import pytest

import claude_handler
import context
import session_store
import soul_engine
import working_memory


class TestProcess:
    """Tests for claude_handler.process() — subprocess `claude -p`."""

    @pytest.fixture
    def mock_subprocess(self, monkeypatch):
        """Mock subprocess.run to return successful JSON output."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({
            "result": '<external_dialogue verb="said">Hello!</external_dialogue>\n<user_model_check>false</user_model_check>',
            "session_id": "sess-123",
        })
        mock.return_value.stderr = ""
        monkeypatch.setattr("subprocess.run", mock)
        return mock

    def test_new_session(self, mock_subprocess, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", True)
        result = claude_handler.process("hi", "C1", "T1", user_id="U1")
        assert "Hello!" in result
        # Session saved
        assert session_store.get("C1", "T1") == "sess-123"

    def test_resumes_session(self, mock_subprocess, monkeypatch, soul_md_path):
        monkeypatch.setattr(context, "_SOUL_MD_PATH", soul_md_path)
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", True)
        session_store.save("C1", "T1", "old-sess")
        claude_handler.process("hi", "C1", "T1", user_id="U1")
        cmd = mock_subprocess.call_args[0][0]
        assert "--resume" in cmd
        assert "old-sess" in cmd

    def test_soul_engine_off(self, mock_subprocess, monkeypatch):
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock_subprocess.return_value.stdout = json.dumps({
            "result": "Raw response",
            "session_id": "sess-456",
        })
        result = claude_handler.process("hi", "C1", "T1")
        assert result == "Raw response"

    def test_timeout_handling(self, monkeypatch):
        import subprocess
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        monkeypatch.setattr(
            "subprocess.run",
            MagicMock(side_effect=subprocess.TimeoutExpired("claude", 120)),
        )
        result = claude_handler.process("hi", "C1", "T1")
        assert "Timed out" in result

    def test_json_parse_failure(self, monkeypatch):
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = "not json"
        mock.return_value.stderr = ""
        monkeypatch.setattr("subprocess.run", mock)
        result = claude_handler.process("hi", "C1", "T1")
        assert result == "not json"

    def test_is_error_flag(self, monkeypatch):
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({
            "result": "Credit balance too low",
            "is_error": True,
        })
        mock.return_value.stderr = ""
        monkeypatch.setattr("subprocess.run", mock)
        result = claude_handler.process("hi", "C1", "T1")
        assert "Claude error" in result

    def test_session_touch_on_resume(self, mock_subprocess, monkeypatch):
        """When resuming and no new session_id returned, touch the session."""
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock_subprocess.return_value.stdout = json.dumps({
            "result": "response",
        })
        session_store.save("C1", "T1", "existing-sess")
        claude_handler.process("hi", "C1", "T1")
        # Session should still be valid (touched)
        assert session_store.get("C1", "T1") == "existing-sess"

    def test_strips_claude_code_env(self, mock_subprocess, monkeypatch):
        """CLAUDE_CODE_* env vars are stripped to prevent nested sessions."""
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock_subprocess.return_value.stdout = json.dumps({"result": "ok"})
        monkeypatch.setenv("CLAUDE_CODE_SSE_PORT", "1234")

        claude_handler.process("hi", "C1", "T1")
        call_kwargs = mock_subprocess.call_args[1]
        env = call_kwargs.get("env", {})
        assert env.get("CLAUDE_CODE_SSE_PORT", "MISSING") != "1234"

    def test_response_truncation(self, monkeypatch):
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        monkeypatch.setattr(claude_handler, "MAX_RESPONSE_LENGTH", 20)
        mock = MagicMock()
        mock.return_value.returncode = 0
        mock.return_value.stdout = json.dumps({"result": "x" * 100, "session_id": "s1"})
        mock.return_value.stderr = ""
        monkeypatch.setattr("subprocess.run", mock)
        result = claude_handler.process("hi", "C1", "T1")
        assert "_(truncated)_" in result

    def test_nonzero_returncode_with_json(self, monkeypatch):
        monkeypatch.setattr(claude_handler, "SOUL_ENGINE_ENABLED", False)
        mock = MagicMock()
        mock.return_value.returncode = 1
        mock.return_value.stdout = json.dumps({"result": "some error"})
        mock.return_value.stderr = ""
        monkeypatch.setattr("subprocess.run", mock)
        result = claude_handler.process("hi", "C1", "T1")
        assert "Error running Claude" in result
