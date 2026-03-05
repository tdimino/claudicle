"""
Cross-thread persistent soul memory for Claudicle.

Unlike working memory (thread-scoped, TTL-expired) or user models (per-user),
soul memory is global state that persists across all threads and sessions.
It represents Claudicle's ongoing awareness of what it's working on, its
emotional state, and accumulated context.

Multi-soul: each soul profile has its own memory namespace via soul_id column.
Single-soul installations use the default soul_id transparently.

Modeled after the Aldea Soul Engine's useSoulMemory hook, adapted for
SQLite single-process persistence.

Thread-safe: uses threading.local() for SQLite connections.
"""

import logging
import os
import sqlite3
import threading
import time
from typing import Optional

import config
from memory.db import memory_pool

log = logging.getLogger(__name__)

SOUL_MEMORY_DEFAULTS = {
    "currentProject": "",
    "currentTask": "",
    "currentTopic": "",
    "emotionalState": "neutral",
    "conversationSummary": "",
    "currentProcess": "main_process",
    "previousProcess": "",
    "processTurnCount": "0",
}

_CREATE_SOUL_MEMORY = """
    CREATE TABLE IF NOT EXISTS soul_memory (
        key TEXT NOT NULL,
        soul_id TEXT NOT NULL DEFAULT 'default',
        value TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (key, soul_id)
    )
"""

# Complex migration: add soul_id column with table rename.
# Runs as a callable migration in the shared pool.
_migrated = False
_migration_lock = threading.Lock()


def _migrate_soul_memory(conn: sqlite3.Connection) -> None:
    """Create or migrate the soul_memory table to include soul_id."""
    global _migrated
    if _migrated:
        return
    with _migration_lock:
        if _migrated:
            return

        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='soul_memory'"
        )
        if cur.fetchone() is None:
            conn.execute(_CREATE_SOUL_MEMORY)
            _migrated = True
            return

        cols = [row[1] for row in conn.execute("PRAGMA table_info(soul_memory)")]
        if "soul_id" in cols:
            _migrated = True
            return

        log.info("Migrating soul_memory table to add soul_id column")
        conn.execute("""
            CREATE TABLE soul_memory_new (
                key TEXT NOT NULL,
                soul_id TEXT NOT NULL DEFAULT 'default',
                value TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (key, soul_id)
            )
        """)
        conn.execute("""
            INSERT INTO soul_memory_new (key, soul_id, value, updated_at)
            SELECT key, 'default', value, updated_at FROM soul_memory
        """)
        conn.execute("DROP TABLE soul_memory")
        conn.execute("ALTER TABLE soul_memory_new RENAME TO soul_memory")
        conn.commit()
        log.info("Migration complete: soul_memory now has soul_id column")
        _migrated = True


# Register with the shared pool
memory_pool.add_migration(_migrate_soul_memory)

# Backward compat — tests monkeypatch these
DB_PATH = memory_pool.db_path


def _get_conn() -> sqlite3.Connection:
    return memory_pool.get_conn()


def _default_soul_id() -> str:
    """Get the current soul's ID for memory scoping."""
    name = config.SOUL_NAME
    return name.lower() if name else "default"


def get(key: str, soul_id: Optional[str] = None) -> Optional[str]:
    """Get a soul memory value, or None if not set."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM soul_memory WHERE key = ? AND soul_id = ?", (key, sid)
    ).fetchone()
    if row is None:
        return SOUL_MEMORY_DEFAULTS.get(key)
    return row["value"]


def set(key: str, value: str, soul_id: Optional[str] = None) -> None:
    """Set a soul memory value."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO soul_memory (key, soul_id, value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(key, soul_id)
           DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, sid, value, time.time()),
    )
    conn.commit()


def get_all(soul_id: Optional[str] = None) -> dict[str, str]:
    """Get all soul memory values, merged with defaults for missing keys."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT key, value FROM soul_memory WHERE soul_id = ?", (sid,)
    ).fetchall()
    result = dict(SOUL_MEMORY_DEFAULTS)
    for row in rows:
        result[row["key"]] = row["value"]
    return result


def get_soul_state(soul_id: Optional[str] = None) -> dict[str, str]:
    """Get only canonical soul state, excluding process memory and whisper keys."""
    return {
        k: v for k, v in get_all(soul_id=soul_id).items()
        if not k.startswith(("proc:", "daimonic_whisper_"))
    }


def delete(key: str, soul_id: Optional[str] = None) -> bool:
    """Delete a soul memory key entirely. Returns True if it existed."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM soul_memory WHERE key = ? AND soul_id = ?", (key, sid)
    )
    conn.commit()
    return cursor.rowcount > 0


def format_for_prompt(soul_id: Optional[str] = None) -> str:
    """Format soul memory as a prompt section.

    Returns a '## Soul State' markdown section, or empty string
    if all values are at their defaults (nothing to report).
    """
    state = get_soul_state(soul_id=soul_id)

    # Skip if everything is empty/default
    has_content = any(
        state.get(k) and state.get(k) != SOUL_MEMORY_DEFAULTS.get(k)
        for k in SOUL_MEMORY_DEFAULTS
    )
    if not has_content:
        return ""

    lines = ["## Soul State", ""]
    if state.get("currentProject"):
        lines.append(f"- **Current Project**: {state['currentProject']}")
    if state.get("currentTask"):
        lines.append(f"- **Current Task**: {state['currentTask']}")
    if state.get("emotionalState") and state["emotionalState"] != "neutral":
        lines.append(f"- **Emotional State**: {state['emotionalState']}")
    if state.get("currentTopic"):
        lines.append(f"- **Current Topic**: {state['currentTopic']}")
    if state.get("conversationSummary"):
        lines.append(f"- **Recent Context**: {state['conversationSummary']}")
    if state.get("currentProcess") and state["currentProcess"] != "main_process":
        lines.append(f"- **Active Process**: {state['currentProcess']}")

    return "\n".join(lines)


def close() -> None:
    """Close the thread-local connection if open."""
    memory_pool.close()
