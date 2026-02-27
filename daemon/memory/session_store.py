"""
SQLite store mapping Slack threads to Claude Code session IDs.

Enables multi-turn conversations: when a user @mentions the bot in a thread,
subsequent replies in the same thread resume the same Claude session.

Thread-safe: each thread gets its own SQLite connection via threading.local().
"""

import sqlite3
import time
from typing import Optional

from config import SESSION_TTL_HOURS
from memory.db import session_pool

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS sessions (
        channel TEXT NOT NULL,
        thread_ts TEXT NOT NULL,
        session_id TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_used REAL NOT NULL,
        PRIMARY KEY (channel, thread_ts)
    )
"""

# Register schema with the session pool
session_pool.add_migration(_CREATE_TABLE)

# Backward compat — tests monkeypatch these
DB_PATH = session_pool.db_path


def _get_conn() -> sqlite3.Connection:
    return session_pool.get_conn()


def get(channel: str, thread_ts: str) -> Optional[str]:
    """Get Claude session ID for a Slack thread, or None if expired/missing."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT session_id, last_used FROM sessions WHERE channel = ? AND thread_ts = ?",
        (channel, thread_ts),
    ).fetchone()
    if row is None:
        return None
    session_id, last_used = row
    if time.time() - last_used > SESSION_TTL_HOURS * 3600:
        conn.execute(
            "DELETE FROM sessions WHERE channel = ? AND thread_ts = ?",
            (channel, thread_ts),
        )
        conn.commit()
        return None
    return session_id


def save(channel: str, thread_ts: str, session_id: str) -> None:
    """Save or update a thread→session mapping."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO sessions (channel, thread_ts, session_id, created_at, last_used)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(channel, thread_ts)
           DO UPDATE SET session_id = excluded.session_id, last_used = excluded.last_used""",
        (channel, thread_ts, session_id, now, now),
    )
    conn.commit()


def touch(channel: str, thread_ts: str) -> None:
    """Update last_used timestamp for a thread."""
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET last_used = ? WHERE channel = ? AND thread_ts = ?",
        (time.time(), channel, thread_ts),
    )
    conn.commit()


def cleanup() -> int:
    """Remove expired sessions. Returns count of deleted rows."""
    conn = _get_conn()
    cutoff = time.time() - SESSION_TTL_HOURS * 3600
    cursor = conn.execute("DELETE FROM sessions WHERE last_used < ?", (cutoff,))
    conn.commit()
    return cursor.rowcount


def close() -> None:
    """Close the thread-local connection if open."""
    session_pool.close()
