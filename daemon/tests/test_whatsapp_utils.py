"""Tests for adapters/whatsapp/_whatsapp_utils.py — phone normalization, gateway."""

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Import from adapter path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "adapters", "whatsapp"))
import _whatsapp_utils as utils


class TestNormalizePhone:
    """Tests for normalize_phone()."""

    def test_already_e164(self):
        assert utils.normalize_phone("+15551234567") == "+15551234567"

    def test_digits_only(self):
        assert utils.normalize_phone("15551234567") == "+15551234567"

    def test_with_parentheses(self):
        assert utils.normalize_phone("(555) 123-4567") == "+5551234567"

    def test_with_dashes(self):
        assert utils.normalize_phone("1-555-123-4567") == "+15551234567"

    def test_empty_string(self):
        assert utils.normalize_phone("") == ""

    def test_no_digits(self):
        assert utils.normalize_phone("abc") == "abc"

    def test_international(self):
        assert utils.normalize_phone("+447911123456") == "+447911123456"


class TestChannelDetection:
    """Tests for is_whatsapp_channel() and phone_from_channel()."""

    def test_is_whatsapp(self):
        assert utils.is_whatsapp_channel("whatsapp:+15551234567") is True

    def test_is_not_whatsapp(self):
        assert utils.is_whatsapp_channel("C01234567") is False

    def test_phone_from_channel(self):
        assert utils.phone_from_channel("whatsapp:+15551234567") == "+15551234567"

    def test_phone_from_plain_channel(self):
        assert utils.phone_from_channel("C01234567") == "C01234567"


class TestHealthCheck:
    """Tests for health_check()."""

    def test_unreachable(self, monkeypatch):
        import urllib.error
        monkeypatch.setattr(utils, "GATEWAY_URL", "http://localhost:99999")

        def fake_urlopen(*args, **kwargs):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        result = utils.health_check()
        assert result["status"] == "unreachable"

    def test_success(self, monkeypatch):
        class FakeResponse:
            def read(self): return json.dumps({"status": "ready"}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
        result = utils.health_check()
        assert result["status"] == "ready"


class TestSendMessage:
    """Tests for send_message()."""

    def test_success(self, monkeypatch):
        class FakeResponse:
            def read(self): return json.dumps({"ok": True, "length": 5}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse())
        result = utils.send_message("+15551234567", "hello")
        assert result["ok"] is True

    def test_http_error(self, monkeypatch):
        import urllib.error

        def fake_urlopen(*args, **kwargs):
            raise urllib.error.HTTPError(
                url="http://localhost:3847/send",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(urllib.error.HTTPError):
            utils.send_message("+15551234567", "hello")
