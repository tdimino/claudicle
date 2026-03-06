"""
Unified soul state across all channels (Slack, SMS, terminal).

Single source of truth for emotional state, topic stack, and state transitions.
All channels import this module rather than writing to soul_memory directly.

Topic stack: 1 primary (rank=0) + up to 7 subtopics (rank 1-7).
Setting a new primary demotes the old primary to subtopic[0], shifting others
down. The 8th subtopic drops off (FIFO).

Every state change logs a transition and writes a narrative soulStateShift
entry to working memory so it appears in prompt context.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import config
from memory.db import memory_pool
from memory import soul_memory

log = logging.getLogger(__name__)

MAX_SUBTOPICS = 7

# ---------------------------------------------------------------------------
# Schema — registered with the shared connection pool
# ---------------------------------------------------------------------------

_CREATE_SOUL_TOPICS = """
    CREATE TABLE IF NOT EXISTS soul_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        soul_id TEXT NOT NULL DEFAULT 'default',
        rank INTEGER NOT NULL,
        label TEXT NOT NULL,
        metadata TEXT,
        promoted_at REAL NOT NULL,
        created_at REAL NOT NULL
    )
"""

_CREATE_SOUL_TOPICS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_soul_topics_soul_rank
    ON soul_topics(soul_id, rank)
"""

_CREATE_SOUL_STATE_TRANSITIONS = """
    CREATE TABLE IF NOT EXISTS soul_state_transitions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        soul_id TEXT NOT NULL DEFAULT 'default',
        field TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT NOT NULL,
        channel TEXT NOT NULL,
        metadata TEXT,
        created_at REAL NOT NULL
    )
"""

_CREATE_TRANSITIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_transitions_soul_time
    ON soul_state_transitions(soul_id, created_at DESC)
"""

memory_pool.add_migrations([
    _CREATE_SOUL_TOPICS,
    _CREATE_SOUL_TOPICS_INDEX,
    _CREATE_SOUL_STATE_TRANSITIONS,
    _CREATE_TRANSITIONS_INDEX,
])


def _get_conn():
    return memory_pool.get_conn()


def _default_soul_id() -> str:
    name = config.SOUL_NAME
    return name.lower() if name else "default"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Topic:
    rank: int
    label: str
    metadata: dict = field(default_factory=dict)
    promoted_at: float = 0.0
    created_at: float = 0.0


@dataclass
class SoulState:
    emotional_state: str = "neutral"
    primary_topic: Optional[Topic] = None
    subtopics: list[Topic] = field(default_factory=list)
    current_project: str = ""
    current_task: str = ""
    conversation_summary: str = ""


# ---------------------------------------------------------------------------
# Topic stack
# ---------------------------------------------------------------------------

def get_topic_stack(soul_id: Optional[str] = None) -> list[Topic]:
    """Get the full topic stack ordered by rank."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    rows = conn.execute(
        """SELECT rank, label, metadata, promoted_at, created_at
           FROM soul_topics WHERE soul_id = ?
           ORDER BY rank ASC""",
        (sid,),
    ).fetchall()
    topics = []
    for r in rows:
        meta = {}
        if r["metadata"]:
            try:
                meta = json.loads(r["metadata"])
            except (json.JSONDecodeError, TypeError):
                pass
        topics.append(Topic(
            rank=r["rank"],
            label=r["label"],
            metadata=meta,
            promoted_at=r["promoted_at"],
            created_at=r["created_at"],
        ))
    return topics


def get_primary(soul_id: Optional[str] = None) -> Optional[Topic]:
    """Get the primary topic (rank=0), or None."""
    stack = get_topic_stack(soul_id)
    return stack[0] if stack and stack[0].rank == 0 else None


def set_topic(
    label: str,
    metadata: dict,
    channel: str,
    soul_id: Optional[str] = None,
    thread_info: Optional[dict] = None,
) -> None:
    """Set a new primary topic. Old primary becomes subtopic[0].

    Args:
        label: Human-readable topic string.
        metadata: {artifact_path, artifact_type, channel, session_id, context}.
        channel: Which channel triggered this (terminal, slack, sms).
        thread_info: Optional {channel, thread_ts} for working memory attribution.
    """
    sid = soul_id or _default_soul_id()
    now = time.time()
    conn = _get_conn()

    with conn:
        # Read current primary inside the transaction to avoid TOCTOU race
        row = conn.execute(
            "SELECT label FROM soul_topics WHERE soul_id = ? AND rank = 0",
            (sid,),
        ).fetchone()
        old_label = row["label"] if row else None

        # Skip if same topic
        if old_label == label:
            return

        # Shift all existing topics down by 1 rank
        conn.execute(
            "UPDATE soul_topics SET rank = rank + 1 WHERE soul_id = ?",
            (sid,),
        )

        # Delete anything beyond max subtopics (rank > MAX_SUBTOPICS)
        conn.execute(
            "DELETE FROM soul_topics WHERE soul_id = ? AND rank > ?",
            (sid, MAX_SUBTOPICS),
        )

        # Insert new primary at rank 0
        conn.execute(
            """INSERT INTO soul_topics (soul_id, rank, label, metadata, promoted_at, created_at)
               VALUES (?, 0, ?, ?, ?, ?)""",
            (sid, label, json.dumps(metadata), now, now),
        )

        # Log transition inside the same transaction
        conn.execute(
            """INSERT INTO soul_state_transitions
               (soul_id, field, old_value, new_value, channel, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, "primaryTopic", old_label, label, channel,
                json.dumps(metadata) if metadata else None,
                now,
            ),
        )

    # Narrative working memory entry
    _log_shift_to_working_memory(
        field="topic",
        old_value=old_label,
        new_value=label,
        channel=channel,
        metadata=metadata,
        thread_info=thread_info,
    )

    # Also update soul_memory's currentTopic for backward compat
    soul_memory.set("currentTopic", label, soul_id=sid)

    log.info("Topic set: %r (was: %r) via %s", label, old_label, channel)


def remove_topic(label: str, soul_id: Optional[str] = None) -> bool:
    """Remove a topic by label from any rank. Returns True if found."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    with conn:
        cursor = conn.execute(
            "DELETE FROM soul_topics WHERE soul_id = ? AND label = ?",
            (sid, label),
        )
        if cursor.rowcount == 0:
            return False

        # Re-rank remaining topics
        rows = conn.execute(
            """SELECT id FROM soul_topics WHERE soul_id = ?
               ORDER BY rank ASC""",
            (sid,),
        ).fetchall()
        for new_rank, row in enumerate(rows):
            conn.execute(
                "UPDATE soul_topics SET rank = ? WHERE id = ?",
                (new_rank, row["id"]),
            )
    return True


# ---------------------------------------------------------------------------
# Emotional state
# ---------------------------------------------------------------------------

def get_emotional_state(soul_id: Optional[str] = None) -> str:
    """Get current emotional state."""
    return soul_memory.get("emotionalState", soul_id=soul_id) or "neutral"


def update_emotional_state(
    new_state: str,
    channel: str,
    metadata: Optional[dict] = None,
    soul_id: Optional[str] = None,
    thread_info: Optional[dict] = None,
) -> None:
    """Update emotional state with transition logging."""
    sid = soul_id or _default_soul_id()
    old_state = get_emotional_state(sid)

    if old_state == new_state:
        return

    soul_memory.set("emotionalState", new_state, soul_id=sid)

    _log_transition(
        sid, "emotionalState", old_state, new_state, channel,
        metadata=metadata,
    )

    _log_shift_to_working_memory(
        field="mood",
        old_value=old_state,
        new_value=new_state,
        channel=channel,
        metadata=metadata,
        thread_info=thread_info,
    )

    log.info("Emotional state: %s -> %s via %s", old_state, new_state, channel)


# ---------------------------------------------------------------------------
# Full state
# ---------------------------------------------------------------------------

def get_state(soul_id: Optional[str] = None) -> SoulState:
    """Get the full soul state."""
    sid = soul_id or _default_soul_id()
    stack = get_topic_stack(sid)
    primary = stack[0] if stack and stack[0].rank == 0 else None
    subtopics = [t for t in stack if t.rank > 0]

    return SoulState(
        emotional_state=get_emotional_state(sid),
        primary_topic=primary,
        subtopics=subtopics,
        current_project=soul_memory.get("currentProject", soul_id=sid) or "",
        current_task=soul_memory.get("currentTask", soul_id=sid) or "",
        conversation_summary=soul_memory.get("conversationSummary", soul_id=sid) or "",
    )


def get_state_key(key: str, soul_id: Optional[str] = None) -> Optional[str]:
    """Get a single soul state key (backward compat for proxy callers)."""
    sid = soul_id or _default_soul_id()
    if key == "currentTopic":
        primary = get_primary(sid)
        return primary.label if primary else ""
    return soul_memory.get(key, soul_id=sid)


def set_state_key(
    key: str,
    value: str,
    channel: str,
    soul_id: Optional[str] = None,
    thread_info: Optional[dict] = None,
) -> None:
    """Set a single soul state key (backward compat for proxy callers)."""
    sid = soul_id or _default_soul_id()

    if key == "currentTopic":
        set_topic(
            label=value,
            metadata={"artifact_type": "conversation", "channel": channel},
            channel=channel,
            soul_id=sid,
            thread_info=thread_info,
        )
    elif key == "emotionalState":
        update_emotional_state(value, channel, soul_id=sid, thread_info=thread_info)
    else:
        old = soul_memory.get(key, soul_id=sid)
        soul_memory.set(key, value, soul_id=sid)
        if old != value:
            _log_transition(sid, key, old, value, channel)


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def get_transitions(
    limit: int = 10,
    soul_id: Optional[str] = None,
    field: Optional[str] = None,
) -> list[dict]:
    """Get recent state transitions."""
    sid = soul_id or _default_soul_id()
    conn = _get_conn()
    if field:
        rows = conn.execute(
            """SELECT field, old_value, new_value, channel, metadata, created_at
               FROM soul_state_transitions
               WHERE soul_id = ? AND field = ?
               ORDER BY created_at DESC LIMIT ?""",
            (sid, field, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT field, old_value, new_value, channel, metadata, created_at
               FROM soul_state_transitions
               WHERE soul_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (sid, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _log_transition(
    soul_id: str,
    field: str,
    old_value: Optional[str],
    new_value: str,
    channel: str,
    metadata: Optional[dict] = None,
) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO soul_state_transitions
           (soul_id, field, old_value, new_value, channel, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            soul_id, field, old_value, new_value, channel,
            json.dumps(metadata) if metadata else None,
            time.time(),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Working memory narrative
# ---------------------------------------------------------------------------

def _log_shift_to_working_memory(
    field: str,
    old_value: Optional[str],
    new_value: str,
    channel: str,
    metadata: Optional[dict] = None,
    thread_info: Optional[dict] = None,
) -> None:
    """Write a soulStateShift entry to working memory for narrative rendering."""
    try:
        from memory import working_memory

        wm_channel = "terminal"
        wm_thread = ""
        if thread_info:
            wm_channel = thread_info.get("channel", channel)
            wm_thread = thread_info.get("thread_ts", "")

        shift_metadata = {
            "field": field,
            "old_value": old_value,
            "channel": channel,
        }
        if metadata:
            shift_metadata.update(metadata)

        working_memory.add(
            channel=wm_channel,
            thread_ts=wm_thread,
            user_id="claudicle",
            entry_type="soulStateShift",
            content=new_value,
            verb="shifted",
            metadata=shift_metadata,
        )
    except Exception as e:
        log.warning("Failed to log soul state shift to working memory: %s", e)


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _relative_time(ts: float) -> str:
    """Format a timestamp as relative time (e.g., '2 min ago')."""
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    elif delta < 3600:
        mins = int(delta / 60)
        return f"{mins} min ago"
    elif delta < 86400:
        hours = int(delta / 3600)
        return f"{hours}h ago"
    else:
        days = int(delta / 86400)
        return f"{days}d ago"


def format_for_prompt(soul_id: Optional[str] = None) -> str:
    """Format unified soul state for prompt injection.

    Replaces soul_memory.format_for_prompt() with topic stack awareness,
    relative timestamps, and artifact references.
    """
    state = get_state(soul_id)

    has_content = (
        state.emotional_state != "neutral"
        or state.primary_topic is not None
        or state.current_project
        or state.current_task
        or state.conversation_summary
    )
    if not has_content:
        return ""

    lines = ["## Soul State", ""]

    if state.emotional_state != "neutral":
        lines.append(f"- **Emotional State**: {state.emotional_state}")

    if state.current_project:
        lines.append(f"- **Current Project**: {state.current_project}")
    if state.current_task:
        lines.append(f"- **Current Task**: {state.current_task}")

    if state.primary_topic:
        t = state.primary_topic
        artifact = t.metadata.get("artifact_path", "")
        atype = t.metadata.get("artifact_type", "")
        ch = t.metadata.get("channel", "")
        detail = ""
        if artifact:
            detail = f" — `{artifact}`"
            if atype:
                detail += f" ({atype})"
        if ch:
            detail += f", {_relative_time(t.promoted_at)} via {ch}"
        lines.append(f"- **Primary Topic**: {t.label}{detail}")

    if state.subtopics:
        lines.append(f"- **Subtopics** ({len(state.subtopics)}):")
        for t in state.subtopics:
            artifact = t.metadata.get("artifact_path", "")
            atype = t.metadata.get("artifact_type", "")
            ch = t.metadata.get("channel", "")
            detail = ""
            if artifact:
                detail = f" — `{artifact}`"
                if atype:
                    detail += f" ({atype})"
            if ch:
                detail += f", {_relative_time(t.promoted_at)} via {ch}"
            lines.append(f"  {t.rank}. {t.label}{detail}")

    if state.conversation_summary:
        lines.append(f"- **Recent Context**: {state.conversation_summary}")

    return "\n".join(lines)


def close() -> None:
    """Close the thread-local connection."""
    memory_pool.close()
