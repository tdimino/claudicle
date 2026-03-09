"""
Model/dossier shedding with structured archaeology.

When a userModel or dossier is updated, the old version is preserved with
structured metadata: internal monologue (why), diff (what changed), and
meta commentary (out-of-character epistemic reflection). The shedding event
becomes a first-class working memory entry (entry_type="modelShed").

Mirrors the soul_state.py pattern: structured records in a dedicated SQLite
table + narrative entries in working memory. Git commits (via git_tracker.py)
still happen for the new version; this module adds the archaeology layer.

The schema registers with memory_pool (shared DB) following the same pattern
as soul_state.py's soul_state_transitions table.
"""

import difflib
import logging
import time
from dataclasses import dataclass
from typing import Optional

from memory.db import memory_pool

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema — registered with the shared connection pool
# ---------------------------------------------------------------------------

_CREATE_MODEL_SHEDS = """
    CREATE TABLE IF NOT EXISTS model_sheds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        old_content TEXT NOT NULL,
        new_content TEXT NOT NULL,
        diff TEXT NOT NULL,
        monologue TEXT,
        change_note TEXT,
        meta_commentary TEXT,
        trace_id TEXT,
        channel TEXT NOT NULL DEFAULT '',
        thread_ts TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
"""

_CREATE_SHEDS_ENTITY_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_model_sheds_entity
    ON model_sheds(entity_id, created_at DESC)
"""

_CREATE_SHEDS_TIME_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_model_sheds_time
    ON model_sheds(created_at DESC)
"""

_CREATE_SHEDS_TYPE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_model_sheds_type
    ON model_sheds(entity_type, created_at DESC)
"""

memory_pool.add_migrations([
    _CREATE_MODEL_SHEDS,
    _CREATE_SHEDS_ENTITY_INDEX,
    _CREATE_SHEDS_TIME_INDEX,
    _CREATE_SHEDS_TYPE_INDEX,
])


def _get_conn():
    return memory_pool.get_conn()


# ---------------------------------------------------------------------------
# Frozen data type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ShedRecord:
    """Immutable record of a model/dossier shedding event."""

    id: int = 0
    entity_id: str = ""
    entity_name: str = ""
    entity_type: str = ""
    old_content: str = ""
    new_content: str = ""
    diff: str = ""
    monologue: str = ""
    change_note: str = ""
    meta_commentary: str = ""
    trace_id: str = ""
    channel: str = ""
    thread_ts: str = ""
    created_at: float = 0.0

    @staticmethod
    def from_row(row: dict) -> "ShedRecord":
        return ShedRecord(
            id=row.get("id", 0),
            entity_id=row.get("entity_id", ""),
            entity_name=row.get("entity_name", ""),
            entity_type=row.get("entity_type", ""),
            old_content=row.get("old_content", ""),
            new_content=row.get("new_content", ""),
            diff=row.get("diff", ""),
            monologue=row.get("monologue") or "",
            change_note=row.get("change_note") or "",
            meta_commentary=row.get("meta_commentary") or "",
            trace_id=row.get("trace_id") or "",
            channel=row.get("channel") or "",
            thread_ts=row.get("thread_ts") or "",
            created_at=row.get("created_at", 0.0),
        )


# ---------------------------------------------------------------------------
# Pure diff generation
# ---------------------------------------------------------------------------

def generate_diff(old_md: str, new_md: str, context_lines: int = 3) -> str:
    """Generate a human-readable unified diff between two markdown versions.

    Pure function: (old, new) -> diff_string.
    """
    old_lines = old_md.splitlines(keepends=True)
    new_lines = new_md.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile="before", tofile="after",
        n=context_lines,
    ))
    if not diff_lines:
        return "(no changes)"
    return "".join(diff_lines)


def _summarize_diff(diff: str) -> str:
    """Extract a compact summary from a unified diff for working memory."""
    if diff == "(no changes)":
        return "no changes"
    added, removed = 0, 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return f"+{added} lines, -{removed} lines"


# ---------------------------------------------------------------------------
# Core shed ceremony
# ---------------------------------------------------------------------------

def shed_model(
    user_id: str,
    old_md: str,
    new_md: str,
    monologue: str = "",
    change_note: str = "",
    channel: str = "",
    thread_ts: str = "",
    trace_id: str = "",
    display_name: str = "",
    entity_type: str = "user",
) -> ShedRecord:
    """Record a model shedding event.

    1. Generate diff
    2. Store shed record in model_sheds table
    3. Write narrative working memory entry (entry_type="modelShed")
    4. Emit to soul stream
    5. Request async meta commentary (best-effort)

    Returns the frozen ShedRecord.
    """
    try:
        from config import MODEL_SHED_ENABLED
        if not MODEL_SHED_ENABLED:
            return ShedRecord()
    except (ImportError, AttributeError):
        pass

    diff = generate_diff(old_md, new_md)
    now = time.time()
    name = display_name or user_id

    conn = _get_conn()
    cursor = conn.execute(
        """INSERT INTO model_sheds
           (entity_id, entity_name, entity_type, old_content, new_content,
            diff, monologue, change_note, meta_commentary, trace_id,
            channel, thread_ts, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, entity_type, old_md, new_md, diff,
         monologue, change_note, "", trace_id, channel, thread_ts, now),
    )
    conn.commit()
    shed_id = cursor.lastrowid

    # Narrative working memory entry
    _write_shed_to_working_memory(
        entity_name=name, entity_type=entity_type,
        change_note=change_note, diff_summary=_summarize_diff(diff),
        channel=channel, thread_ts=thread_ts, trace_id=trace_id,
    )

    # Soul stream emit
    _emit_shed_event(
        shed_id=shed_id, entity_id=user_id, entity_name=name,
        entity_type=entity_type, change_note=change_note,
        trace_id=trace_id, channel=channel, thread_ts=thread_ts,
    )

    record = ShedRecord(
        id=shed_id, entity_id=user_id, entity_name=name,
        entity_type=entity_type, old_content=old_md, new_content=new_md,
        diff=diff, monologue=monologue, change_note=change_note,
        meta_commentary="", trace_id=trace_id,
        channel=channel, thread_ts=thread_ts, created_at=now,
    )

    # Best-effort meta commentary
    _request_meta_commentary(shed_id, record)

    return record


def shed_dossier(
    entity_name: str,
    old_md: str,
    new_md: str,
    monologue: str = "",
    change_note: str = "",
    entity_type: str = "subject",
    channel: str = "",
    thread_ts: str = "",
    trace_id: str = "",
) -> ShedRecord:
    """Record a dossier shedding event."""
    entity_id = f"dossier:{entity_name.lower().strip()}"
    return shed_model(
        user_id=entity_id,
        old_md=old_md, new_md=new_md,
        monologue=monologue, change_note=change_note,
        channel=channel, thread_ts=thread_ts,
        trace_id=trace_id,
        display_name=entity_name,
        entity_type=entity_type,
    )


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------

def get_sheds(
    entity_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = 20,
) -> list[ShedRecord]:
    """Query shed records with flexible filtering."""
    conn = _get_conn()
    clauses: list[str] = []
    params: list = []
    if entity_id:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    if until:
        clauses.append("created_at <= ?")
        params.append(until)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM model_sheds {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params),
    ).fetchall()
    return [ShedRecord.from_row(dict(r)) for r in rows]


def get_shed(shed_id: int) -> Optional[ShedRecord]:
    """Get a single shed record by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM model_sheds WHERE id = ?", (shed_id,)
    ).fetchone()
    return ShedRecord.from_row(dict(row)) if row else None


def get_entity_archaeology(entity_id: str, limit: int = 10) -> list[ShedRecord]:
    """Get the full shedding history for an entity, newest first."""
    return get_sheds(entity_id=entity_id, limit=limit)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_shed_to_working_memory(
    entity_name: str,
    entity_type: str,
    change_note: str,
    diff_summary: str,
    channel: str,
    thread_ts: str,
    trace_id: str,
) -> None:
    """Write a modelShed narrative entry to working memory."""
    if not channel:
        return
    try:
        from memory import working_memory
        content = f"shed {entity_type} model for {entity_name}"
        if change_note:
            content += f": {change_note}"
        if diff_summary:
            content += f" ({diff_summary})"
        working_memory.add(
            channel=channel, thread_ts=thread_ts,
            user_id="claudicle", entry_type="modelShed",
            content=content, verb="shed",
            metadata={
                "entity_name": entity_name,
                "entity_type": entity_type,
                "change_note": change_note,
                "diff_summary": diff_summary,
            },
            trace_id=trace_id,
        )
    except Exception as e:
        log.warning("Failed to write modelShed to working memory: %s", e)


def _emit_shed_event(
    shed_id: int,
    entity_id: str,
    entity_name: str,
    entity_type: str,
    change_note: str,
    trace_id: str,
    channel: str,
    thread_ts: str,
) -> None:
    """Emit to soul stream JSONL."""
    try:
        from monitoring import soul_log
        soul_log.emit(
            "memory", trace_id, channel=channel, thread_ts=thread_ts,
            action="model_shed", shed_id=shed_id,
            entity_id=entity_id, entity_name=entity_name,
            entity_type=entity_type, change_note=change_note or "",
        )
    except Exception as e:
        log.warning("Failed to emit shed event: %s", e)


def _request_meta_commentary(shed_id: int, record: ShedRecord) -> None:
    """Generate meta commentary via lightweight LLM call (best-effort).

    Runs synchronously but swallows all errors. The meta commentary
    is a bonus — failure must not block the pipeline.
    """
    try:
        from config import MODEL_SHED_META_COMMENTARY
        if not MODEL_SHED_META_COMMENTARY:
            return
    except (ImportError, AttributeError):
        return

    try:
        from engine.llm_client import call_llm
        prompt = _build_meta_commentary_prompt(record)
        commentary = call_llm(prompt)
        if commentary:
            commentary = commentary.strip()[:500]
            conn = _get_conn()
            conn.execute(
                "UPDATE model_sheds SET meta_commentary = ? WHERE id = ?",
                (commentary, shed_id),
            )
            conn.commit()
    except Exception as e:
        log.debug("Meta commentary generation failed (best-effort): %s", e)


def _build_meta_commentary_prompt(record: ShedRecord) -> str:
    """Build the prompt for out-of-character epistemic reflection."""
    return (
        "You are an epistemic observer stepping outside the soul to reflect on "
        "how its understanding of an entity is evolving.\n\n"
        f"Entity: {record.entity_name} ({record.entity_type})\n"
        f"Change: {record.change_note}\n\n"
        f"Diff:\n{record.diff[:1000]}\n\n"
        f"Soul's internal monologue about this change:\n{record.monologue[:500]}\n\n"
        "In 1-3 sentences, reflect on what this change reveals about how the "
        "soul's understanding is evolving. Note patterns, corrections, deepening, "
        "or surprising shifts. Write in third person about the soul. Be specific."
    )
