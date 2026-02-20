"""
Per-user model and entity dossier management for the pseudo soul engine.

Each Slack user gets a markdown profile (modeled after tom/tomModel.md) stored in
~/.claude/userModels/{name}/. Claudicle uses these to personalize interactions.
Claudicle can also autonomously create dossiers for third-party people and subjects
encountered in conversation.

Models are stored in the same SQLite DB as working memory and updated periodically
via a mentalQuery boolean check.

Thread-safe: shares the same threading.local() DB connection pattern as working_memory.
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import date
from typing import Optional

from config import USER_MODEL_UPDATE_INTERVAL

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

_USER_MODEL_TEMPLATE = """---
title: "{display_name}"
type: user-model
userName: "{display_name}"
userId: "{user_id}"
created: "{date}"
updated: "{date}"
status: active
onboardingComplete: {onboarding_complete}
role: "{role}"
---

# {display_name}

## Persona
Unknown — first interaction.

## Speaking Style
Not yet observed.

## Conversational Context
Not yet observed.

## Worldview
Not yet observed.

## Interests & Domains
Not yet observed.

## Working Patterns
Not yet observed.

## Most Potent Memories
No shared memories yet.
"""

_CREATE_USER_MODELS = """
    CREATE TABLE IF NOT EXISTS user_models (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        model_md TEXT NOT NULL,
        interaction_count INTEGER DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
"""

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute(_CREATE_USER_MODELS)
        # Migrate: add entity_type column if missing (for dossier support)
        try:
            _local.conn.execute(
                "ALTER TABLE user_models ADD COLUMN entity_type TEXT DEFAULT 'user'"
            )
            _local.conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass  # Column already exists, expected
            else:
                log.error("Migration failed: ALTER TABLE user_models ADD entity_type: %s", e)
        _local.conn.commit()
    return _local.conn


def get(user_id: str) -> Optional[str]:
    """Get the markdown user model for a Slack user, or None if not yet created."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT model_md FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return row["model_md"]


def get_display_name(user_id: str) -> Optional[str]:
    """Get the cached display name for a user."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT display_name FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return row["display_name"]


def save(user_id: str, model_md: str, display_name: Optional[str] = None, change_note: str = "") -> None:
    """Save or update a user model. Increments interaction count on update."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_models (user_id, display_name, model_md, interaction_count, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?)
           ON CONFLICT(user_id)
           DO UPDATE SET
               model_md = excluded.model_md,
               display_name = COALESCE(excluded.display_name, user_models.display_name),
               updated_at = excluded.updated_at""",
        (user_id, display_name, model_md, now, now),
    )
    conn.commit()

    # Git-track the change
    try:
        from config import MEMORY_GIT_ENABLED
        if MEMORY_GIT_ENABLED:
            from memory import git_tracker as memory_git
            name = display_name or get_display_name(user_id) or user_id
            memory_git.export_user_model(user_id, name, model_md, change_note)
    except Exception as e:
        log.warning("Git memory tracking failed (best-effort): %s", e)


def ensure_exists(user_id: str, display_name: Optional[str] = None) -> str:
    """Ensure a user model exists, creating a blank template if needed. Returns the model."""
    model = get(user_id)
    if model is not None:
        return model
    name = display_name or user_id
    today = date.today().isoformat()
    # Skip onboarding for users with known real names (e.g. from Slack API).
    # Needs onboarding when: no display_name given, or display_name is the default.
    from config import DEFAULT_USER_NAME, PRIMARY_USER_ID
    onboarding_complete = "true" if (display_name and display_name != DEFAULT_USER_NAME) else "false"
    role = "primary" if user_id == PRIMARY_USER_ID else "standard"
    model = (
        _USER_MODEL_TEMPLATE
        .replace("{display_name}", name)
        .replace("{user_id}", user_id)
        .replace("{date}", today)
        .replace("{onboarding_complete}", onboarding_complete)
        .replace("{role}", role)
    )
    save(user_id, model, display_name)
    return model


def parse_frontmatter(model_md: str) -> dict:
    """Extract YAML frontmatter from a user model or dossier markdown string.

    Returns an empty dict if no frontmatter is found.
    """
    if not model_md or not model_md.startswith("---"):
        return {}
    end = model_md.find("---", 3)
    if end == -1:
        return {}
    raw = model_md[3:end].strip()
    # Simple key: value parsing — avoids yaml dependency
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value:
            result[key] = value
    return result


def get_user_name(user_id: str) -> Optional[str]:
    """Get the authoritative display name from the user model's frontmatter.

    Returns userName from YAML frontmatter if present, otherwise None.
    This is the canonical source for how to address a user — takes precedence
    over Slack display_name or user_id.
    """
    model = get(user_id)
    if not model:
        return None
    meta = parse_frontmatter(model)
    return meta.get("userName")


def should_check_update(user_id: str) -> bool:
    """Return True if it's time to check whether the user model needs updating.

    Triggers every USER_MODEL_UPDATE_INTERVAL interactions.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT interaction_count FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return False
    return row["interaction_count"] % USER_MODEL_UPDATE_INTERVAL == 0


def increment_interaction(user_id: str) -> None:
    """Bump the interaction counter for a user."""
    conn = _get_conn()
    conn.execute(
        "UPDATE user_models SET interaction_count = interaction_count + 1, updated_at = ? WHERE user_id = ?",
        (time.time(), user_id),
    )
    conn.commit()


def get_interaction_count(user_id: str) -> int:
    """Get the current interaction count for a user."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT interaction_count FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return 0
    return row["interaction_count"]


def close() -> None:
    """Close the thread-local connection if open."""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None


# ---------------------------------------------------------------------------
# Dossier API — autonomous entity modeling (people, subjects, topics)
# ---------------------------------------------------------------------------

def _dossier_id(entity_name: str) -> str:
    """Create a stable ID for a dossier entity."""
    return f"dossier:{entity_name.lower().strip()}"


def save_dossier(
    entity_name: str,
    model_md: str,
    entity_type: str = "subject",
    change_note: str = "",
) -> None:
    """Save or update a dossier for a person or subject."""
    entity_id = _dossier_id(entity_name)
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_models
               (user_id, display_name, model_md, entity_type, interaction_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)
           ON CONFLICT(user_id)
           DO UPDATE SET
               model_md = excluded.model_md,
               display_name = excluded.display_name,
               entity_type = excluded.entity_type,
               updated_at = excluded.updated_at""",
        (entity_id, entity_name, model_md, entity_type, now, now),
    )
    conn.commit()
    log.info("Saved dossier for %s (%s): %s", entity_name, entity_type, change_note or "no note")

    # Git-track the change
    try:
        from config import MEMORY_GIT_ENABLED
        if MEMORY_GIT_ENABLED:
            from memory import git_tracker as memory_git
            memory_git.export_dossier(entity_name, model_md, entity_type, change_note)
    except Exception as e:
        log.warning("Git memory tracking failed (best-effort): %s", e)


def get_dossier(entity_name: str) -> Optional[str]:
    """Get a dossier by entity name, or None if not found."""
    entity_id = _dossier_id(entity_name)
    conn = _get_conn()
    row = conn.execute(
        "SELECT model_md FROM user_models WHERE user_id = ?", (entity_id,)
    ).fetchone()
    return row["model_md"] if row else None


def list_dossiers(entity_type: Optional[str] = None) -> list[dict]:
    """List all dossiers, optionally filtered by type ('person' or 'subject')."""
    conn = _get_conn()
    if entity_type:
        rows = conn.execute(
            "SELECT user_id, display_name, entity_type, updated_at FROM user_models "
            "WHERE user_id LIKE 'dossier:%' AND entity_type = ? ORDER BY updated_at DESC",
            (entity_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT user_id, display_name, entity_type, updated_at FROM user_models "
            "WHERE user_id LIKE 'dossier:%' ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "entity_id": row["user_id"],
            "name": row["display_name"],
            "type": row["entity_type"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def get_relevant_dossiers(text: str, limit: int = 3) -> list[str]:
    """Find dossier entity names that appear in the given text (case-insensitive)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT display_name FROM user_models WHERE user_id LIKE 'dossier:%'"
    ).fetchall()
    text_lower = text.lower()
    matches = [
        row["display_name"]
        for row in rows
        if row["display_name"] and row["display_name"].lower() in text_lower
    ]
    return matches[:limit]
