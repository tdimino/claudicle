"""Shared fixtures for the Claudius test suite.

Seven fixture categories:
1. DB isolation — monkeypatch DB_PATH, reset threading.local()
2. Clean env — strip all CLAUDIUS_*, SLACK_DAEMON_*, API key vars
3. Soul engine cache reset — nullify module-level caches
4. Pipeline counter reset — zero out interaction counter
5. MockProvider — fake LLM provider recording calls
6. Sample soul files — minimal soul.md / skills.md in tmp_path
7. Inbox helpers — create inbox.jsonl, write entries
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

    for mod in [working_memory, user_models, soul_memory]:
        monkeypatch.setattr(mod, "DB_PATH", mem_db)
        monkeypatch.setattr(mod, "_local", threading.local())

    monkeypatch.setattr(session_store, "DB_PATH", sess_db)
    monkeypatch.setattr(session_store, "_local", threading.local())

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
# 3. Soul Engine Cache Reset (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_soul_engine_caches():
    """Clear soul_engine module-level caches before each test."""
    import soul_engine
    soul_engine._soul_cache = None
    soul_engine._skills_cache = None
    soul_engine._global_interaction_count = 0
    yield
    soul_engine._soul_cache = None
    soul_engine._skills_cache = None
    soul_engine._global_interaction_count = 0


# ---------------------------------------------------------------------------
# 4. Pipeline Counter Reset (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_pipeline_counter():
    """Zero out pipeline interaction counter."""
    import pipeline
    pipeline._pipeline_interaction_count = 0
    yield
    pipeline._pipeline_interaction_count = 0


# ---------------------------------------------------------------------------
# 4b. Provider Registry Reset (autouse)
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
# 5. MockProvider fixture
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
# 6. Sample Soul Files
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
# 7. Inbox Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def inbox_file(tmp_path):
    """Create an empty inbox.jsonl and return its path."""
    p = tmp_path / "inbox.jsonl"
    p.write_text("")
    return str(p)
