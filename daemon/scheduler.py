"""Scheduled events store for Claudicle.

SQLite-backed event scheduling with CRUD operations, overdue protection,
and batch limiting for restart safety. Events are created via the
<schedule_event> XML tag in cognitive responses or programmatically.

Maps to Open Souls' scheduled events pattern: the soul can schedule
future perceptions that fire through the process router.
"""

import json
import logging
import time
import uuid

from memory.db import memory_pool

log = logging.getLogger("claudicle.scheduler")

_CREATE_SCHEDULED_EVENTS = """
    CREATE TABLE IF NOT EXISTS scheduled_events (
        id TEXT PRIMARY KEY,
        fire_at REAL NOT NULL,
        perception_action TEXT NOT NULL,
        perception_content TEXT DEFAULT '',
        target_process TEXT DEFAULT '',
        channel TEXT,
        thread_ts TEXT,
        metadata TEXT DEFAULT '{}',
        internal INTEGER DEFAULT 1,
        created_at REAL DEFAULT (strftime('%s', 'now')),
        fired INTEGER DEFAULT 0
    )
"""


def _init_table(conn):
    """Migration: create scheduled_events table if it doesn't exist."""
    conn.execute(_CREATE_SCHEDULED_EVENTS)


memory_pool.add_migration(_init_table)


def _get_conn():
    return memory_pool.get_conn()


def schedule(
    action: str,
    content: str = "",
    delay_seconds: float = 0,
    target_process: str = "",
    channel: str | None = None,
    thread_ts: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Schedule an event to fire after delay_seconds.

    Returns the event ID, or empty string if the pending cap is reached.
    """
    try:
        import config as _cfg
        max_events = getattr(_cfg, "SCHEDULER_MAX_EVENTS", 100)
    except ImportError:
        max_events = 100
    if count_pending() >= max_events:
        log.warning("Scheduler cap reached (%d), dropping event: %s", max_events, action)
        return ""
    event_id = str(uuid.uuid4())[:12]
    fire_at = time.time() + delay_seconds
    conn = _get_conn()
    conn.execute(
        """INSERT INTO scheduled_events
           (id, fire_at, perception_action, perception_content, target_process,
            channel, thread_ts, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            event_id,
            fire_at,
            action,
            content,
            target_process,
            channel,
            thread_ts,
            json.dumps(metadata or {}),
        ),
    )
    conn.commit()
    log.info("Scheduled event %s: action=%s, fire_at=%.0f", event_id, action, fire_at)
    return event_id


def schedule_at(
    action: str,
    content: str = "",
    fire_at: float = 0,
    **kwargs,
) -> str:
    """Schedule an event to fire at a specific timestamp."""
    delay = max(0, fire_at - time.time())
    return schedule(action, content, delay_seconds=delay, **kwargs)


def cancel(event_id: str) -> bool:
    """Cancel a pending event. Returns True if it was found and cancelled."""
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM scheduled_events WHERE id = ? AND fired = 0",
        (event_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_due_events(max_batch: int = 5, max_overdue_ratio: float = 2.0) -> list[dict]:
    """Get events that are due to fire, capped for restart safety.

    max_batch: maximum events returned per call
    max_overdue_ratio: events overdue by more than this ratio of their
                       intended delay are auto-expired (marked fired)
    """
    now = time.time()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM scheduled_events
           WHERE fire_at <= ? AND fired = 0
           ORDER BY fire_at ASC""",
        (now,),
    ).fetchall()

    due = []
    for row in rows:
        row_dict = dict(row)
        # Auto-expire massively overdue events
        intended_delay = row_dict["fire_at"] - row_dict["created_at"]
        if intended_delay > 0:
            actual_overdue = now - row_dict["fire_at"]
            if actual_overdue > max_overdue_ratio * intended_delay:
                mark_fired(row_dict["id"])
                log.warning("Auto-expired overdue event %s", row_dict["id"])
                continue

        # Parse metadata
        try:
            row_dict["metadata"] = json.loads(row_dict.get("metadata") or "{}")
        except (json.JSONDecodeError, TypeError):
            row_dict["metadata"] = {}

        due.append(row_dict)
        if len(due) >= max_batch:
            break

    return due


def mark_fired(event_id: str) -> None:
    """Mark an event as fired."""
    conn = _get_conn()
    conn.execute(
        "UPDATE scheduled_events SET fired = 1 WHERE id = ?",
        (event_id,),
    )
    conn.commit()


def pending(channel: str | None = None) -> list[dict]:
    """Get all pending (unfired) events, optionally filtered by channel."""
    conn = _get_conn()
    if channel:
        rows = conn.execute(
            "SELECT * FROM scheduled_events WHERE fired = 0 AND channel = ? ORDER BY fire_at",
            (channel,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scheduled_events WHERE fired = 0 ORDER BY fire_at"
        ).fetchall()
    return [dict(r) for r in rows]


def cleanup(max_age_days: int = 30) -> int:
    """Remove old fired events. Returns count of deleted rows."""
    cutoff = time.time() - (max_age_days * 86400)
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM scheduled_events WHERE fired = 1 AND created_at < ?",
        (cutoff,),
    )
    conn.commit()
    return cursor.rowcount


def count_pending() -> int:
    """Count total pending events (for cap enforcement)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) FROM scheduled_events WHERE fired = 0"
    ).fetchone()
    return row[0] if row else 0
