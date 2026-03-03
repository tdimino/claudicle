"""Persistent working memory for subdaimones.

Each subdaimon (hypermnesia, leb, zakar, etc.) gets persistent memory
that survives across invocations, souls, users, and projects. Built on the
existing working_memory and process_memory modules using convention-based
channel/thread namespacing.

Channel convention: daimon:{agent_name}
Thread convention:  {soul_id}:{user_id}:{project_slug}  (or "global")
Regions: default, comms, lessons, context

All reads return immutable snapshots. All writes go through boundary functions.
Honors the Open Souls Paradigm: side effects are described as data, applied
at the boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from memory import working_memory, process_memory
from memory.snapshot import (
    MemoryEntry,
    WorkingMemorySnapshot,
    CognitiveOutput,
    apply_output,
)


# ---------------------------------------------------------------------------
# Immutable boot context
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DaimonContext:
    """Immutable boot context for a subdaimon invocation."""

    agent_name: str
    soul_id: str
    user_id: str
    project: str
    channel: str      # daimon:{agent_name}
    thread_ts: str    # {soul_id}:{user_id}:{project}


def make_context(
    agent_name: str,
    soul_id: str = "default",
    user_id: str = "",
    project: str = "global",
) -> DaimonContext:
    """Create an immutable daimon context for a subdaimon invocation."""
    channel = f"daimon:{agent_name}"
    thread_ts = f"{soul_id}:{user_id}:{project}"
    return DaimonContext(
        agent_name=agent_name,
        soul_id=soul_id,
        user_id=user_id,
        project=project,
        channel=channel,
        thread_ts=thread_ts,
    )


# ---------------------------------------------------------------------------
# Memory loading (pure reads → immutable snapshots)
# ---------------------------------------------------------------------------

def load_memory(
    ctx: DaimonContext,
    limit: int = 20,
    regions: Optional[list[str]] = None,
) -> WorkingMemorySnapshot:
    """Load the subdaimon's persistent working memory as an immutable snapshot.

    Called at boot time to give the subdaimon its memory of prior invocations.
    """
    if regions:
        entries_raw = working_memory.get_regions(
            ctx.channel, ctx.thread_ts, regions, limit=limit
        )
    else:
        entries_raw = working_memory.get_recent(
            ctx.channel, ctx.thread_ts, limit=limit, exclude_regions=[]
        )
    entries = tuple(MemoryEntry.from_row(e) for e in entries_raw)
    return WorkingMemorySnapshot(
        entries=entries,
        channel=ctx.channel,
        thread_ts=ctx.thread_ts,
    )


def load_lessons(
    agent_name: str,
    soul_id: str = "default",
    limit: int = 20,
) -> WorkingMemorySnapshot:
    """Load cross-project lessons for a subdaimon.

    Returns lessons from the global thread (not project-scoped).
    These are the subdaimon's accumulated cross-project insights.
    """
    channel = f"daimon:{agent_name}"
    thread_ts = f"{soul_id}::global"
    entries_raw = working_memory.get_region(
        channel, thread_ts, "lessons", limit=limit
    )
    entries = tuple(MemoryEntry.from_row(e) for e in entries_raw)
    return WorkingMemorySnapshot(
        entries=entries,
        channel=channel,
        thread_ts=thread_ts,
    )


# ---------------------------------------------------------------------------
# Memory storage (boundary functions)
# ---------------------------------------------------------------------------

def store_output(ctx: DaimonContext, output: CognitiveOutput) -> None:
    """Store a subdaimon's cognitive output at the boundary.

    Thin wrapper around apply_output that uses the daimon's channel/thread.
    """
    apply_output(output, ctx.channel, ctx.thread_ts)


def store_invocation(
    ctx: DaimonContext,
    summary: str,
    trace_id: str = "",
) -> None:
    """Record that a subdaimon was invoked with a brief summary.

    Stored in the default region as an internalMonologue entry.
    """
    working_memory.add(
        channel=ctx.channel,
        thread_ts=ctx.thread_ts,
        user_id=ctx.agent_name,
        entry_type="internalMonologue",
        content=summary,
        verb="observed",
        trace_id=trace_id,
        metadata={"soul_id": ctx.soul_id, "user_id": ctx.user_id, "project": ctx.project},
        region="default",
    )


def store_lesson(
    agent_name: str,
    content: str,
    soul_id: str = "default",
    project: str = "",
    metadata: Optional[dict] = None,
) -> None:
    """Store a cross-project lesson learned by a subdaimon.

    Lessons are stored in the global thread's 'lessons' region.
    They persist across invocations and are loaded at boot.
    """
    channel = f"daimon:{agent_name}"
    thread_ts = f"{soul_id}::global"
    meta = metadata or {}
    if project:
        meta["source_project"] = project
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=agent_name,
        entry_type="daimonicIntuition",
        content=content,
        verb="learned",
        metadata=meta,
        region="lessons",
    )


def store_communication(
    ctx: DaimonContext,
    direction: str,
    counterpart: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """Store a communication log entry for a subdaimon.

    Tracks messages to/from Claude Code agent swarm leads and other agents.
    Stored in the 'comms' region.
    """
    meta = {**(metadata or {}), "direction": direction, "counterpart": counterpart}
    working_memory.add(
        channel=ctx.channel,
        thread_ts=ctx.thread_ts,
        user_id=counterpart if direction == "inbound" else ctx.agent_name,
        entry_type="toolAction",
        content=f"[{direction}] {counterpart}: {content}",
        metadata=meta,
        region="comms",
    )


# ---------------------------------------------------------------------------
# Process memory convenience wrappers
# ---------------------------------------------------------------------------

def get_state(agent_name: str, key: str, default=None):
    """Get persistent state for a subdaimon (survives across invocations)."""
    return process_memory.get(agent_name, key, default=default)


def set_state(agent_name: str, key: str, value):
    """Set persistent state for a subdaimon."""
    process_memory.set(agent_name, key, value)


# ---------------------------------------------------------------------------
# Boot formatting
# ---------------------------------------------------------------------------

def format_for_boot(
    ctx: DaimonContext,
    memory: WorkingMemorySnapshot,
    lessons: WorkingMemorySnapshot,
) -> str:
    """Format subdaimon memory for injection into the boot prompt.

    Produces a markdown section that soul-context.py appends to the
    subdaimon's boot context, giving it awareness of its prior work.
    """
    parts: list[str] = []

    if memory.entries:
        parts.append("## Prior Invocations\n")
        parts.append(working_memory.format_for_prompt(
            [_entry_to_dict(e) for e in memory.entries],
            soul_name=ctx.agent_name,
        ))

    if lessons.entries:
        parts.append("\n## Lessons Learned\n")
        for entry in lessons.entries:
            parts.append(f"- {entry.content}")

    return "\n".join(parts) if parts else ""


def _entry_to_dict(entry: MemoryEntry) -> dict:
    """Convert a MemoryEntry back to dict for format_for_prompt compatibility."""
    return {
        "entry_type": entry.entry_type,
        "content": entry.content,
        "verb": entry.verb,
        "user_id": entry.user_id,
        "display_name": entry.display_name,
        "metadata": entry.metadata,
        "trace_id": entry.trace_id,
        "region": entry.region,
        "created_at": entry.created_at,
    }
