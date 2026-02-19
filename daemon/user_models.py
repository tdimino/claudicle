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
import sqlite3
import threading
import time
from typing import Optional

from config import USER_MODEL_UPDATE_INTERVAL

log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

_USER_MODEL_TEMPLATE = """# {display_name}

## Persona
{Unknown — first interaction.}

## Speaking Style
{Not yet observed.}

## Conversational Context
{Not yet observed.}

## Worldview
{Not yet observed.}

## Interests & Domains
{Not yet observed.}

## Working Patterns
{Not yet observed.}

## Most Potent Memories
{No shared memories yet.}
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
            import memory_git
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
    model = _USER_MODEL_TEMPLATE.replace("{display_name}", name)
    save(user_id, model, display_name)
    return model


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
            import memory_git
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
