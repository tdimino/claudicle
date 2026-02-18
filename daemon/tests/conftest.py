"""Shared fixtures for the Claudius test suite.

Seven fixture categories:
1. DB isolation — monkeypatch DB_PATH, reset threading.local()
2. Clean env — strip all CLAUDIUS_*, SLACK_DAEMON_*, WHATSAPP_*, API key vars
3. Context module cache reset — nullify soul/skills caches, zero interaction counter
4. Provider registry reset — save/restore provider registry
5. Daimonic isolation — mock daimonic calls to prevent side effects
6. MockProvider — fake LLM provider recording calls
7. Sample soul files — minimal soul.md / skills.md in tmp_path
8. Inbox helpers — create inbox.jsonl, write entries
"""

import json
import os
import threading

import pytest

import working_memory
import user_models
import soul_memory
import session_store

from tests.helpers import (
    MockProvider,
    SAMPLE_SOUL_MD,
    SAMPLE_SKILLS_MD,
    make_inbox_entry,
    write_inbox_entry,
)


# ---------------------------------------------------------------------------
# 1. DB Isolation (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_databases(tmp_path, monkeypatch):
    """Redirect all SQLite DBs to tmp_path, reset thread-local connections."""
    mem_db = str(tmp_path / "memory.db")
    sess_db = str(tmp_path / "sessions.db")

    import soul_engine

    for mod in [working_memory, user_models, soul_memory]:
        monkeypatch.setattr(mod, "DB_PATH", mem_db)
        monkeypatch.setattr(mod, "_local", threading.local())

    monkeypatch.setattr(session_store, "DB_PATH", sess_db)
    monkeypatch.setattr(session_store, "_local", threading.local())

    # Reset trace_id stash to prevent bleed between tests
    soul_engine._trace_local = threading.local()

    yield tmp_path

    for mod in [working_memory, user_models, soul_memory, session_store]:
        mod.close()


# ---------------------------------------------------------------------------
# 2. Clean Environment (autouse)
# ---------------------------------------------------------------------------

_PREFIXES = ("CLAUDIUS_", "SLACK_DAEMON_", "WHATSAPP_")
_API_KEYS = (
    "ANTHROPIC_API_KEY", "GROQ_API_KEY", "OPENAI_COMPAT_BASE_URL",
    "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove all CLAUDIUS_/SLACK_DAEMON_/API key env vars."""
    for key in list(os.environ):
        if any(key.startswith(p) for p in _PREFIXES) or key in _API_KEYS:
            monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# 3. Context Module Cache Reset (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_context_caches():
    """Clear context module caches and interaction counter before each test."""
    import context
    context._soul_cache = None
    context._skills_cache = None
    context._interaction_count = 0
    yield
    context._soul_cache = None
    context._skills_cache = None
    context._interaction_count = 0


# ---------------------------------------------------------------------------
# 4. Provider Registry Reset (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_provider_registry():
    """Save and restore provider registry between tests."""
    from providers import _registry
    snapshot = dict(_registry)
    yield
    _registry.clear()
    _registry.update(snapshot)


# ---------------------------------------------------------------------------
# 5. Daimonic Isolation (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_daimonic(monkeypatch, request):
    """Prevent live daimonic calls during tests (except test_daimonic)."""
    if "test_daimonic" in request.module.__name__:
        return
    import daimonic
    monkeypatch.setattr(daimonic, "format_for_prompt", lambda: "")
    monkeypatch.setattr(daimonic, "consume_all_whispers", lambda: None)


# ---------------------------------------------------------------------------
# 6. MockProvider fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_provider():
    """Create a MockProvider instance."""
    return MockProvider()


@pytest.fixture
def mock_provider_factory():
    """Factory fixture to create MockProviders with custom settings."""
    def _make(name="mock", response=""):
        return MockProvider(name=name, response=response)
    return _make


# ---------------------------------------------------------------------------
# 7. Sample Soul Files
# ---------------------------------------------------------------------------

@pytest.fixture
def soul_md_path(tmp_path):
    """Write minimal soul.md and return its path."""
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    p = soul_dir / "soul.md"
    p.write_text(SAMPLE_SOUL_MD)
    return str(p)


@pytest.fixture
def skills_md_path(tmp_path):
    """Write minimal skills.md and return its path."""
    p = tmp_path / "skills.md"
    p.write_text(SAMPLE_SKILLS_MD)
    return str(p)


# ---------------------------------------------------------------------------
# 8. Inbox Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def inbox_file(tmp_path):
    """Create an empty inbox.jsonl and return its path."""
    p = tmp_path / "inbox.jsonl"
    p.write_text("")
    return str(p)
