"""Working memory checkpoints — point-in-time bookmarks for rollback.

A checkpoint captures the state of working memory at a specific moment,
enabling rollback to that state. Follows FP principles: checkpoints are
immutable snapshots; rollback creates new state by deletion, not mutation.

Use case: "Omit any workingMemory since Claudius last posted to eng-aldea
and the chirp squad, and have him start fresh from there."

    >>> cp = create_at_last_post("slack:C04ABC", "1234", target_channel="C_ENG_ALDEA")
    >>> rollback(cp.name, cp.channel, cp.thread_ts)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from memory.db import memory_pool


# ---------------------------------------------------------------------------
# Schema — auto-migrated via memory_pool
# ---------------------------------------------------------------------------

_CREATE_CHECKPOINTS = """
CREATE TABLE IF NOT EXISTS wm_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,
    thread_ts TEXT NOT NULL,
    created_at REAL NOT NULL,
    max_entry_id INTEGER NOT NULL,
    soul_state_json TEXT,
    metadata TEXT,
    UNIQUE(name, channel, thread_ts)
)
"""

memory_pool.add_migrations([_CREATE_CHECKPOINTS])


# ---------------------------------------------------------------------------
# Immutable data type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Checkpoint:
    """Immutable checkpoint record."""

    id: int
    name: str
    channel: str
    thread_ts: str
    created_at: float
    max_entry_id: int
    soul_state: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def from_row(row: dict) -> Checkpoint:
        soul_state = {}
        raw = row.get("soul_state_json")
        if raw:
            try:
                soul_state = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                pass
        meta = {}
        raw_meta = row.get("metadata")
        if raw_meta:
            try:
                meta = json.loads(raw_meta)
            except (json.JSONDecodeError, TypeError):
                pass
        return Checkpoint(
            id=row["id"],
            name=row["name"],
            channel=row["channel"],
            thread_ts=row["thread_ts"],
            created_at=row["created_at"],
            max_entry_id=row["max_entry_id"],
            soul_state=soul_state,
            metadata=meta,
        )


def _get_conn():
    return memory_pool.get_conn()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create(
    name: str,
    channel: str,
    thread_ts: str,
    metadata: Optional[dict] = None,
    _override_max_id: Optional[int] = None,
) -> Checkpoint:
    """Create a checkpoint at the current state of working memory.

    Captures the max entry id and current soul state. Replaces any
    existing checkpoint with the same name/channel/thread.
    """
    from memory import working_memory, soul_memory

    max_id = _override_max_id if _override_max_id is not None else working_memory.max_id(channel, thread_ts)
    soul_state = soul_memory.get_all()
    now = time.time()

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO wm_checkpoints
           (name, channel, thread_ts, created_at, max_entry_id, soul_state_json, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            channel,
            thread_ts,
            now,
            max_id,
            json.dumps(soul_state),
            json.dumps(metadata) if metadata else None,
        ),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM wm_checkpoints WHERE name = ? AND channel = ? AND thread_ts = ?",
        (name, channel, thread_ts),
    ).fetchone()

    cp = Checkpoint.from_row(dict(row))

    try:
        from monitoring.wm_stream import emit_lifecycle
        emit_lifecycle("checkpoint_created", channel, thread_ts, {
            "name": name, "max_entry_id": max_id,
        })
    except (ImportError, AttributeError):
        pass

    return cp


def create_at_last_post(
    channel: str,
    thread_ts: str,
    target_channel: str,
    user_id: str = "claudicle",
    name: Optional[str] = None,
) -> Optional[Checkpoint]:
    """Create a checkpoint at the last post by user_id to target_channel.

    Finds the most recent externalDialog entry by user_id on target_channel
    and creates a checkpoint at that entry's id.

    Returns None if no matching post found.
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT id FROM working_memory
           WHERE channel = ? AND user_id = ? AND entry_type = 'externalDialog'
           ORDER BY created_at DESC LIMIT 1""",
        (target_channel, user_id),
    ).fetchone()

    if row is None:
        return None

    cp_name = name or f"at-last-post-{target_channel}"
    return create(
        cp_name, channel, thread_ts,
        metadata={"target_channel": target_channel, "user_id": user_id},
        _override_max_id=row["id"],
    )


def get(name: str, channel: str, thread_ts: str) -> Optional[Checkpoint]:
    """Get a named checkpoint."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM wm_checkpoints WHERE name = ? AND channel = ? AND thread_ts = ?",
        (name, channel, thread_ts),
    ).fetchone()
    if row is None:
        return None
    return Checkpoint.from_row(dict(row))


def list_checkpoints(channel: Optional[str] = None) -> list[Checkpoint]:
    """List all checkpoints, optionally filtered by channel."""
    conn = _get_conn()
    if channel:
        rows = conn.execute(
            "SELECT * FROM wm_checkpoints WHERE channel = ? ORDER BY created_at DESC",
            (channel,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM wm_checkpoints ORDER BY created_at DESC"
        ).fetchall()
    return [Checkpoint.from_row(dict(r)) for r in rows]


def rollback(
    name: str,
    channel: str,
    thread_ts: str,
    restore_soul_state: bool = False,
    archive: bool = True,
) -> dict:
    """Rollback working memory to a named checkpoint.

    Deletes all entries with id > checkpoint.max_entry_id.
    Optionally restores soul state to the checkpointed values.

    Returns: {"deleted_count": N, "checkpoint": Checkpoint, "soul_state_restored": bool}
    """
    from memory import working_memory, soul_memory

    cp = get(name, channel, thread_ts)
    if cp is None:
        return {"deleted_count": 0, "checkpoint": None, "soul_state_restored": False}

    deleted = working_memory.delete_after(
        channel, thread_ts, cp.max_entry_id, archive=archive
    )

    restored = False
    if restore_soul_state and cp.soul_state:
        for key, value in cp.soul_state.items():
            soul_memory.set(key, value)
        restored = True

    try:
        from monitoring.wm_stream import emit_lifecycle
        emit_lifecycle("checkpoint_rollback", channel, thread_ts, {
            "name": name, "deleted_count": deleted, "soul_state_restored": restored,
        })
    except (ImportError, AttributeError):
        pass

    return {"deleted_count": deleted, "checkpoint": cp, "soul_state_restored": restored}


def delete(name: str, channel: str, thread_ts: str) -> bool:
    """Delete a checkpoint. Returns True if it existed."""
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM wm_checkpoints WHERE name = ? AND channel = ? AND thread_ts = ?",
        (name, channel, thread_ts),
    )
    conn.commit()
    return cursor.rowcount > 0
