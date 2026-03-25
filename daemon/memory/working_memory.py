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
import time
import uuid
from typing import Any, Optional

import config
from config import WORKING_MEMORY_TTL_HOURS
from memory.db import memory_pool

# ---------------------------------------------------------------------------
# Schema & migrations — registered with the shared connection pool
# ---------------------------------------------------------------------------

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
    # Add region for scoped memory reads/writes
    "ALTER TABLE working_memory ADD COLUMN region TEXT DEFAULT 'default'",
    # Archive table for compressed working memory entries
    """CREATE TABLE IF NOT EXISTS working_memory_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT NOT NULL,
        thread_ts TEXT NOT NULL,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        verb TEXT,
        content TEXT NOT NULL,
        metadata TEXT,
        trace_id TEXT,
        display_name TEXT,
        region TEXT DEFAULT 'default',
        created_at REAL NOT NULL,
        archived_at REAL NOT NULL,
        compression_trace_id TEXT
    )""",
    # Archive indexes
    "CREATE INDEX IF NOT EXISTS idx_archive_thread ON working_memory_archive(channel, thread_ts)",
    "CREATE INDEX IF NOT EXISTS idx_archive_user ON working_memory_archive(user_id)",
    # Performance indexes for Soul Debugger concurrent reads and dashboard queries
    "CREATE INDEX IF NOT EXISTS idx_wm_channel_thread_created ON working_memory(channel, thread_ts, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_wm_created_at ON working_memory(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_wm_trace_id ON working_memory(trace_id)",
    # idx_wm_entry_type dropped: low cardinality (12 values), never queried alone,
    # composite index on (channel, thread_ts, created_at) already narrows results
    "DROP INDEX IF EXISTS idx_wm_entry_type",
]

# Register our migrations with the shared pool
memory_pool.add_migrations([_CREATE_WORKING_MEMORY] + _MIGRATIONS)

# Backward compat — tests monkeypatch these
DB_PATH = memory_pool.db_path


def _get_conn() -> sqlite3.Connection:
    return memory_pool.get_conn()


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
    region: str = "default",
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
           (channel, thread_ts, user_id, entry_type, verb, content, metadata, trace_id, display_name, region, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            region,
            time.time(),
        ),
    )
    conn.commit()

    # Stream to tail-able JSONL (best-effort, never blocks)
    try:
        from monitoring.wm_stream import emit as wm_emit
        wm_emit(
            channel=channel, thread_ts=thread_ts, user_id=user_id,
            entry_type=entry_type, content=content, verb=verb,
            metadata=metadata, trace_id=trace_id, display_name=display_name,
            region=region,
        )
    except Exception:
        pass  # observability must not kill the pipeline


def add_monologue(
    channel: str,
    thread_ts: str,
    content: str,
    verb: str = "thought",
    trace_id: Optional[str] = None,
    soul_name: str = "",
) -> None:
    """Convenience wrapper for internal monologue entries."""
    add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudicle",
        entry_type="internalMonologue",
        content=content,
        verb=verb,
        trace_id=trace_id,
        display_name=soul_name or config.SOUL_NAME,
    )


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


def get_recent(
    channel: str,
    thread_ts: str,
    limit: int = 20,
    exclude_regions: Optional[list[str]] = None,
) -> list[dict]:
    """Get recent working memory entries for a thread."""
    if exclude_regions is None:
        exclude_regions = ["summary"]

    conn = _get_conn()
    where_clause = "WHERE channel = ? AND thread_ts = ?"
    params: list[Any] = [channel, thread_ts]

    if exclude_regions:
        placeholders = ", ".join(["?"] * len(exclude_regions))
        where_clause += f" AND region NOT IN ({placeholders})"
        params.extend(exclude_regions)

    params.append(limit)
    rows = conn.execute(
        f"""SELECT entry_type, verb, content, user_id, display_name, metadata, trace_id, region, created_at
           FROM working_memory
           {where_clause}
           ORDER BY created_at DESC
           LIMIT ?""",
        tuple(params),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_region(channel: str, thread_ts: str, region: str, limit: int = 50) -> list[dict]:
    """Get entries for a specific region in chronological order."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT rowid, entry_type, verb, content, user_id, display_name, metadata, trace_id, region, created_at
           FROM working_memory
           WHERE channel = ? AND thread_ts = ? AND region = ?
           ORDER BY created_at ASC
           LIMIT ?""",
        (channel, thread_ts, region, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_region_names(channel: str, thread_ts: str) -> list[str]:
    """Get distinct region names for a thread."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT DISTINCT region
           FROM working_memory
           WHERE channel = ? AND thread_ts = ?""",
        (channel, thread_ts),
    ).fetchall()
    return [r["region"] for r in rows]


def replace_region(
    channel: str, thread_ts: str, region: str, entries: list[dict]
) -> None:
    """Atomically replace all entries in a region."""
    conn = _get_conn()
    with conn:
        conn.execute(
            """DELETE FROM working_memory
               WHERE channel = ? AND thread_ts = ? AND region = ?""",
            (channel, thread_ts, region),
        )
        for entry in entries:
            metadata = entry.get("metadata")
            conn.execute(
                """INSERT INTO working_memory
                   (channel, thread_ts, user_id, entry_type, verb, content, metadata, trace_id, display_name, region, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    channel,
                    thread_ts,
                    entry.get("user_id", "claudicle"),
                    entry.get("entry_type", "memorySummary"),
                    entry.get("verb"),
                    entry.get("content", ""),
                    json.dumps(metadata) if isinstance(metadata, dict) else metadata,
                    entry.get("trace_id"),
                    entry.get("display_name"),
                    region,
                    entry.get("created_at", time.time()),
                ),
            )


def archive_entries(
    entries: list[dict],
    channel: str,
    thread_ts: str,
    compression_trace_id: str,
    archive: bool = True,
) -> int:
    """Archive and delete entries atomically. Returns deleted row count."""
    conn = _get_conn()
    deleted_count = 0

    with conn:
        for entry in entries:
            metadata = entry.get("metadata")
            metadata_value = (
                json.dumps(metadata) if isinstance(metadata, dict) else metadata
            )
            region = entry.get("region", "default")
            created_at = entry.get("created_at", time.time())
            rowid = entry.get("rowid")

            if archive:
                conn.execute(
                    """INSERT INTO working_memory_archive
                       (channel, thread_ts, user_id, entry_type, verb, content, metadata, trace_id, display_name, region, created_at, archived_at, compression_trace_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        channel,
                        thread_ts,
                        entry.get("user_id", ""),
                        entry.get("entry_type", ""),
                        entry.get("verb"),
                        entry.get("content", ""),
                        metadata_value,
                        entry.get("trace_id"),
                        entry.get("display_name"),
                        region,
                        created_at,
                        time.time(),
                        compression_trace_id,
                    ),
                )

            if rowid is None:
                row = conn.execute(
                    """SELECT rowid AS wm_rowid FROM working_memory
                       WHERE channel = ? AND thread_ts = ? AND region = ? AND entry_type = ? AND content = ? AND created_at = ?
                       ORDER BY rowid ASC LIMIT 1""",
                    (
                        channel,
                        thread_ts,
                        region,
                        entry.get("entry_type", "memorySummary"),
                        entry.get("content", ""),
                        created_at,
                    ),
                ).fetchone()
                if row is not None:
                    rowid = row["wm_rowid"]

            if rowid is not None:
                cursor = conn.execute(
                    "DELETE FROM working_memory WHERE rowid = ?", (rowid,)
                )
                deleted_count += cursor.rowcount

    return deleted_count


def get_regions(
    channel: str, thread_ts: str, regions: list[str], limit: int = 200
) -> list[dict]:
    """Get entries from multiple regions in chronological order."""
    if not regions:
        return []

    placeholders = ", ".join(["?"] * len(regions))
    params: list[Any] = [channel, thread_ts, *regions, limit]
    conn = _get_conn()
    rows = conn.execute(
        f"""SELECT rowid, entry_type, verb, content, user_id, display_name, metadata, trace_id, region, created_at
           FROM working_memory
           WHERE channel = ? AND thread_ts = ? AND region IN ({placeholders})
           ORDER BY created_at ASC
           LIMIT ?""",
        tuple(params),
    ).fetchall()
    return [dict(r) for r in rows]


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


def format_for_prompt(
    entries: list[dict],
    soul_name: str = "",
    region_order: Optional[list[str]] = None,
) -> str:
    """Format working memory entries as pseudo-working memory for prompt injection.

    Produces lines like:
        Tom said: "Can you help me with CI/CD?"
        Sarah said: "I have a similar question."
        Claudius pondered: "Two perspectives on the same topic..."
        Claudius explained: "Here's how to set up..."
        Claudius evaluated: "Should update user model?" → true
    """
    soul_name = soul_name or config.SOUL_NAME
    if not entries:
        return ""

    if region_order is not None:
        region_rank = {name: idx for idx, name in enumerate(region_order)}
        entries = sorted(
            entries,
            key=lambda e: (
                region_rank.get(e.get("region"), len(region_rank)),
            ),
        )

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
        elif entry_type == "modelShed":
            lines.append(f"{soul_name} shed: {content}")
        elif entry_type == "memorySummary":
            lines.append(f"{soul_name} recalls from earlier: {content}")
        elif entry_type == "soulStateShift":
            field_label = ""
            if meta:
                try:
                    m = json.loads(meta) if isinstance(meta, str) else meta
                    field_label = m.get("field", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            if field_label == "mood":
                lines.append(f"{soul_name}'s mood shifted to {content}")
            elif field_label == "topic":
                lines.append(f"{soul_name} shifted focus to {content}")
            else:
                lines.append(f"{soul_name} shifted {field_label or 'state'} to {content}")
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


def query(
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
    entry_type: Optional[str] = None,
    user_id: Optional[str] = None,
    region: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    trace_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Flexible AND-combined filter query. Returns chronological entries.

    All parameters are optional AND-combined filters. None means no filter
    on that dimension. This is the general-purpose superset of get_recent(),
    get_trace(), and get_user_history().
    """
    conn = _get_conn()
    clauses: list[str] = []
    params: list[Any] = []

    if channel is not None:
        clauses.append("channel = ?")
        params.append(channel)
    if thread_ts is not None:
        clauses.append("thread_ts = ?")
        params.append(thread_ts)
    if entry_type is not None:
        clauses.append("entry_type = ?")
        params.append(entry_type)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if region is not None:
        clauses.append("region = ?")
        params.append(region)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    if trace_id is not None:
        clauses.append("trace_id = ?")
        params.append(trace_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"""SELECT id, entry_type, verb, content, user_id, display_name,
                   metadata, trace_id, region, channel, thread_ts, created_at
           FROM working_memory
           {where}
           ORDER BY created_at ASC
           LIMIT ?""",
        tuple(params),
    ).fetchall()
    return [dict(r) for r in rows]


def stats(channel: Optional[str] = None) -> dict:
    """Working memory statistics.

    Returns counts by channel, entry_type, region, plus oldest/newest
    timestamps and archive count. Optionally filtered to a single channel.
    """
    conn = _get_conn()
    where = "WHERE channel = ?" if channel else ""
    params: tuple = (channel,) if channel else ()

    total = conn.execute(
        f"SELECT COUNT(*) as cnt FROM working_memory {where}", params
    ).fetchone()["cnt"]

    by_channel = {}
    for row in conn.execute(
        f"SELECT channel, COUNT(*) as cnt FROM working_memory {where} GROUP BY channel",
        params,
    ).fetchall():
        by_channel[row["channel"]] = row["cnt"]

    by_entry_type = {}
    for row in conn.execute(
        f"SELECT entry_type, COUNT(*) as cnt FROM working_memory {where} GROUP BY entry_type",
        params,
    ).fetchall():
        by_entry_type[row["entry_type"]] = row["cnt"]

    by_region = {}
    for row in conn.execute(
        f"SELECT region, COUNT(*) as cnt FROM working_memory {where} GROUP BY region",
        params,
    ).fetchall():
        by_region[row["region"]] = row["cnt"]

    bounds = conn.execute(
        f"SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM working_memory {where}",
        params,
    ).fetchone()

    archive_count = conn.execute(
        f"SELECT COUNT(*) as cnt FROM working_memory_archive {where}", params
    ).fetchone()["cnt"]

    return {
        "total_entries": total,
        "by_channel": by_channel,
        "by_entry_type": by_entry_type,
        "by_region": by_region,
        "oldest_entry": bounds["oldest"],
        "newest_entry": bounds["newest"],
        "archive_count": archive_count,
    }


def delete_after(
    channel: str,
    thread_ts: str,
    after_id: int,
    archive: bool = True,
) -> int:
    """Delete entries with id > after_id. Optionally archive first.

    Returns count of deleted rows. Used by checkpoint rollback to remove
    all entries that came after a checkpointed state.
    """
    conn = _get_conn()
    if archive:
        with conn:
            rows = conn.execute(
                """SELECT rowid, entry_type, verb, content, user_id, display_name,
                          metadata, trace_id, region, created_at
                   FROM working_memory
                   WHERE channel = ? AND thread_ts = ? AND id > ?
                   ORDER BY id ASC""",
                (channel, thread_ts, after_id),
            ).fetchall()
            entries = [dict(r) for r in rows]
            if entries:
                trace = new_trace_id()
                return archive_entries(entries, channel, thread_ts, trace, archive=True)
            return 0

    cursor = conn.execute(
        "DELETE FROM working_memory WHERE channel = ? AND thread_ts = ? AND id > ?",
        (channel, thread_ts, after_id),
    )
    conn.commit()
    return cursor.rowcount


def delete_by_filter(
    channel: str,
    thread_ts: str,
    entry_type: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    trace_id: Optional[str] = None,
    archive: bool = True,
) -> int:
    """Delete entries matching specific criteria.

    Selective deletion: remove specific types, time ranges, or traces
    while preserving everything else. Archives by default.
    """
    conn = _get_conn()
    clauses = ["channel = ?", "thread_ts = ?"]
    params: list[Any] = [channel, thread_ts]

    if entry_type is not None:
        clauses.append("entry_type = ?")
        params.append(entry_type)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("created_at <= ?")
        params.append(until)
    if trace_id is not None:
        clauses.append("trace_id = ?")
        params.append(trace_id)

    where = " AND ".join(clauses)

    if archive:
        with conn:
            rows = conn.execute(
                f"""SELECT rowid, entry_type, verb, content, user_id, display_name,
                           metadata, trace_id, region, created_at
                    FROM working_memory WHERE {where}
                    ORDER BY created_at ASC""",
                tuple(params),
            ).fetchall()
            entries = [dict(r) for r in rows]
            if entries:
                trace = new_trace_id()
                return archive_entries(entries, channel, thread_ts, trace, archive=True)
            return 0

    cursor = conn.execute(
        f"DELETE FROM working_memory WHERE {where}", tuple(params)
    )
    conn.commit()
    return cursor.rowcount


def max_id(channel: Optional[str] = None, thread_ts: Optional[str] = None) -> int:
    """Get the maximum entry id, optionally scoped to a channel/thread.

    Used by checkpoint system to record the high-water mark.
    """
    conn = _get_conn()
    if channel and thread_ts:
        row = conn.execute(
            "SELECT MAX(id) as max_id FROM working_memory WHERE channel = ? AND thread_ts = ?",
            (channel, thread_ts),
        ).fetchone()
    elif channel:
        row = conn.execute(
            "SELECT MAX(id) as max_id FROM working_memory WHERE channel = ?",
            (channel,),
        ).fetchone()
    else:
        row = conn.execute("SELECT MAX(id) as max_id FROM working_memory").fetchone()
    return row["max_id"] or 0


def cleanup(max_age_hours: Optional[int] = None) -> int:
    """Remove expired working memory entries. Returns count of deleted rows.

    Subdaimon memory (channel prefix 'daimon:') is exempt from default
    TTL cleanup — it uses DAIMON_MEMORY_TTL_HOURS instead.
    """
    hours = max_age_hours or WORKING_MEMORY_TTL_HOURS
    conn = _get_conn()
    cutoff = time.time() - hours * 3600
    cursor = conn.execute(
        "DELETE FROM working_memory WHERE created_at < ? AND channel NOT LIKE 'daimon:%'",
        (cutoff,),
    )
    conn.commit()
    deleted = cursor.rowcount

    # Separate TTL for daimon channels
    daimon_hours = config.DAIMON_MEMORY_TTL_HOURS
    daimon_cutoff = time.time() - daimon_hours * 3600
    cursor2 = conn.execute(
        "DELETE FROM working_memory WHERE created_at < ? AND channel LIKE 'daimon:%'",
        (daimon_cutoff,),
    )
    conn.commit()
    return deleted + cursor2.rowcount


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
    memory_pool.close()
