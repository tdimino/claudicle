"""
Per-thread conversation memory for gating decisions and analytics.

Stores all cognitive outputs (internal monologue, external dialogue, mentalQuery
results, tool actions, user messages) with verbs intact. NOT injected into
prompts — conversation continuity comes from --resume SESSION_ID. Working memory
serves as metadata for the Samantha-Dreams gate (should_inject_user_model) and
for training data extraction.

Each cognitive cycle (one user message → one response) generates a trace_id
(UUID4) grouping all entries from that cycle. This enables self-inspection:
the soul can query its own cognitive history as first-class data.

Thread-safe: each thread gets its own SQLite connection via threading.local().
"""

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

from config import SOUL_NAME, WORKING_MEMORY_TTL_HOURS

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.db")

_CREATE_WORKING_MEMORY = """
    CREATE TABLE IF NOT EXISTS working_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT NOT NULL,
        thread_ts TEXT NOT NULL,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        verb TEXT,
        content TEXT NOT NULL,
        metadata TEXT,
        trace_id TEXT,
        created_at REAL NOT NULL
    )
"""

_MIGRATIONS = [
    # Add trace_id column to existing databases
    "ALTER TABLE working_memory ADD COLUMN trace_id TEXT",
    # Add display_name for multi-speaker attribution
    "ALTER TABLE working_memory ADD COLUMN display_name TEXT",
]

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute(_CREATE_WORKING_MEMORY)
        # Run migrations for existing databases
        for migration in _MIGRATIONS:
            try:
                _local.conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists
        _local.conn.commit()
    return _local.conn


def new_trace_id() -> str:
    """Generate a trace_id for a cognitive cycle.

    One trace groups all working_memory entries from a single
    message → cognitive pipeline → response cycle.
    """
    return uuid.uuid4().hex[:12]


def add(
    channel: str,
    thread_ts: str,
    user_id: str,
    entry_type: str,
    content: str,
    verb: Optional[str] = None,
    metadata: Optional[dict] = None,
    trace_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> None:
    """Store a working memory entry.

    Args:
        trace_id: Groups entries from a single cognitive cycle. Generate
                  with new_trace_id() at pipeline entry.
        display_name: Human-readable name for multi-speaker attribution.
    """
    conn = _get_conn()
    conn.execute(
        """INSERT INTO working_memory
           (channel, thread_ts, user_id, entry_type, verb, content, metadata, trace_id, display_name, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            channel,
            thread_ts,
            user_id,
            entry_type,
            verb,
            content,
            json.dumps(metadata) if metadata else None,
            trace_id,
            display_name,
            time.time(),
        ),
    )
    conn.commit()


def update_latest_verb(channel: str, thread_ts: str, user_id: str, verb: str) -> None:
    """Retroactively set the verb on the most recent userMessage from a user in a thread.

    Used by the stimulus_verb cognitive step to narrate incoming messages
    after the LLM has chosen an appropriate verb.
    """
    conn = _get_conn()
    conn.execute(
        """UPDATE working_memory SET verb = ?
           WHERE rowid = (
               SELECT rowid FROM working_memory
               WHERE channel = ? AND thread_ts = ? AND user_id = ? AND entry_type = 'userMessage'
               ORDER BY created_at DESC LIMIT 1
           )""",
        (verb, channel, thread_ts, user_id),
    )
    conn.commit()


def get_recent(channel: str, thread_ts: str, limit: int = 20) -> list[dict]:
    """Get recent working memory entries for a thread."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT entry_type, verb, content, user_id, display_name, metadata, trace_id, created_at
           FROM working_memory
           WHERE channel = ? AND thread_ts = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (channel, thread_ts, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_user_history(user_id: str, limit: int = 50) -> list[dict]:
    """Get recent working memory entries for a specific user across all threads."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT entry_type, verb, content, channel, thread_ts, display_name, metadata, created_at
           FROM working_memory
           WHERE user_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def format_for_prompt(entries: list[dict], soul_name: str = "") -> str:
    """Format working memory entries as pseudo-working memory for prompt injection.

    Produces lines like:
        Tom said: "Can you help me with CI/CD?"
        Sarah said: "I have a similar question."
        Claudius pondered: "Two perspectives on the same topic..."
        Claudius explained: "Here's how to set up..."
        Claudius evaluated: "Should update user model?" → true
    """
    soul_name = soul_name or SOUL_NAME
    if not entries:
        return ""

    lines = []
    for entry in entries:
        entry_type = entry["entry_type"]
        verb = entry.get("verb")
        content = entry["content"]
        meta = entry.get("metadata")

        if entry_type == "userMessage":
            speaker = entry.get("display_name") or "User"
            v = verb or "said"
            lines.append(f'{speaker} {v}: "{content}"')
        elif entry_type == "internalMonologue":
            v = verb or "thought"
            lines.append(f'{soul_name} {v}: "{content}"')
        elif entry_type == "externalDialog":
            v = verb or "said"
            lines.append(f'{soul_name} {v}: "{content}"')
        elif entry_type == "mentalQuery":
            if meta:
                try:
                    m = json.loads(meta) if isinstance(meta, str) else meta
                    result = m.get("result", "")
                    lines.append(
                        f'{soul_name} evaluated: "{content}" → {result}'
                    )
                except (json.JSONDecodeError, TypeError):
                    lines.append(f'{soul_name} evaluated: "{content}"')
            else:
                lines.append(f'{soul_name} evaluated: "{content}"')
        elif entry_type in ("toolAction", "onboardingStep"):
            lines.append(f"{soul_name} {content}")
        else:
            lines.append(f"{content}")

    return "\n".join(lines)


def get_trace(trace_id: str) -> list[dict]:
    """Get all entries for a cognitive cycle, ordered chronologically.

    This is the soul's window into a single thought process—every step
    from user message through monologue, dialogue, and decision gates.
    """
    conn = _get_conn()
    rows = conn.execute(
        """SELECT entry_type, verb, content, user_id, display_name, metadata, trace_id, created_at
           FROM working_memory
           WHERE trace_id = ?
           ORDER BY created_at ASC""",
        (trace_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_traces(channel: str, thread_ts: str, limit: int = 5) -> list[dict]:
    """Get the most recent trace_ids with summary info.

    Returns a list of {trace_id, started_at, step_count, entry_types}
    for the soul to review its recent cognitive history.
    """
    conn = _get_conn()
    rows = conn.execute(
        """SELECT trace_id, MIN(created_at) as started_at, COUNT(*) as step_count,
                  GROUP_CONCAT(DISTINCT entry_type) as entry_types
           FROM working_memory
           WHERE channel = ? AND thread_ts = ? AND trace_id IS NOT NULL
           GROUP BY trace_id
           ORDER BY started_at DESC
           LIMIT ?""",
        (channel, thread_ts, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recent_decisions(channel: str, thread_ts: str, limit: int = 10) -> list[dict]:
    """Get recent decision-gate entries (mentalQuery results).

    Returns the soul's recent boolean decisions: user model checks,
    dossier checks, soul state checks.
    """
    conn = _get_conn()
    rows = conn.execute(
        """SELECT entry_type, content, metadata, trace_id, created_at
           FROM working_memory
           WHERE channel = ? AND thread_ts = ?
             AND entry_type IN ('mentalQuery', 'decision')
           ORDER BY created_at DESC
           LIMIT ?""",
        (channel, thread_ts, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def cleanup(max_age_hours: Optional[int] = None) -> int:
    """Remove expired working memory entries. Returns count of deleted rows."""
    hours = max_age_hours or WORKING_MEMORY_TTL_HOURS
    conn = _get_conn()
    cutoff = time.time() - hours * 3600
    cursor = conn.execute(
        "DELETE FROM working_memory WHERE created_at < ?", (cutoff,)
    )
    conn.commit()
    return cursor.rowcount


def get_thread_daimon_modes(channel: str, thread_ts: str) -> dict:
    """Get per-thread daimon mode overrides from working memory."""
    entries = get_recent(channel, thread_ts, limit=20)
    for entry in reversed(entries):
        if entry.get("entry_type") == "daimonMode":
            try:
                return json.loads(entry.get("content", "{}"))
            except json.JSONDecodeError:
                pass
    return {}


def close() -> None:
    """Close the thread-local connection if open."""
    if hasattr(_local, "conn") and _local.conn is not None:
        _local.conn.close()
        _local.conn = None
