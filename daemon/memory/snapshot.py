"""Immutable working memory snapshot for functional cognitive steps.

Adapts the Open Souls WorkingMemory pattern to Python:
- WorkingMemorySnapshot is frozen (copy-on-write via with_* methods)
- MemoryEntry is frozen (immutable record)
- CognitiveOutput is frozen (immutable result from pure cognitive steps)
- apply_output() commits a CognitiveOutput atomically at the pipeline boundary

All types are immutable. Cognitive steps compose via copy-on-write:
    output = (CognitiveOutput()
        .with_entry("internalMonologue", "thinking...", verb="thought")
        .with_entry("externalDialog", "hello", verb="said")
        .with_soul_state("emotionalState", "engaged"))

This enables pure cognitive steps: (snapshot, raw_text) → (dialogue, CognitiveOutput).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field, replace
from typing import Any, Optional

log = logging.getLogger("claudicle.snapshot")

from memory.db import memory_pool


# ---------------------------------------------------------------------------
# Immutable data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MemoryEntry:
    """A single working memory entry — immutable."""

    entry_type: str
    content: str
    verb: str = ""
    user_id: str = ""
    display_name: str = ""
    metadata: dict = field(default_factory=dict)
    trace_id: str = ""
    region: str = "default"
    target_channel: str = ""
    target_thread_ts: str = ""
    created_at: float = 0.0
    rowid: Optional[int] = None

    @staticmethod
    def from_row(row: dict) -> MemoryEntry:
        """Create from a sqlite3.Row dict."""
        meta = row.get("metadata")
        if isinstance(meta, str) and meta:
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        elif not isinstance(meta, dict):
            meta = {}

        return MemoryEntry(
            entry_type=row.get("entry_type", ""),
            content=row.get("content", ""),
            verb=row.get("verb") or "",
            user_id=row.get("user_id") or "",
            display_name=row.get("display_name") or "",
            metadata=meta,
            trace_id=row.get("trace_id") or "",
            region=row.get("region") or "default",
            created_at=row.get("created_at") or 0.0,
            rowid=row.get("rowid"),
        )


@dataclass(frozen=True)
class WorkingMemorySnapshot:
    """Immutable snapshot of working memory state.

    Open Souls pattern: all operations return new instances (copy-on-write).
    The snapshot is passed through the cognitive pipeline and enriched at
    each step without mutating the original.
    """

    entries: tuple[MemoryEntry, ...] = ()
    soul_state: dict[str, str] = field(default_factory=dict)
    user_model: str = ""
    trace_id: str = ""
    channel: str = ""
    thread_ts: str = ""

    def with_entry(self, entry: MemoryEntry) -> WorkingMemorySnapshot:
        """Return new snapshot with an appended entry."""
        return replace(self, entries=self.entries + (entry,))

    def with_entries(self, entries: tuple[MemoryEntry, ...]) -> WorkingMemorySnapshot:
        """Return new snapshot with additional entries appended."""
        return replace(self, entries=self.entries + entries)

    def with_soul_state(self, **updates: str) -> WorkingMemorySnapshot:
        """Return new snapshot with updated soul state keys."""
        return replace(self, soul_state={**self.soul_state, **updates})

    def with_user_model(self, model: str) -> WorkingMemorySnapshot:
        """Return new snapshot with updated user model."""
        return replace(self, user_model=model)

    def with_trace_id(self, trace_id: str) -> WorkingMemorySnapshot:
        """Return new snapshot with a new trace ID."""
        return replace(self, trace_id=trace_id)

    def get_region(self, region: str) -> tuple[MemoryEntry, ...]:
        """Get entries for a specific region."""
        return tuple(e for e in self.entries if e.region == region)

    def get_regions(self) -> set[str]:
        """Get distinct region names."""
        return {e.region for e in self.entries}


# ---------------------------------------------------------------------------
# Cognitive output — immutable result from pure cognitive steps
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CognitiveOutput:
    """Immutable output from a cognitive cycle.

    Copy-on-write via with_* methods — same pattern as WorkingMemorySnapshot.
    Each method returns a new instance; the original is never modified.

    Frozen copy-on-write output (evolved from the earlier mutable MemoryMutations):
        output = (CognitiveOutput()
            .with_entry("internalMonologue", "thinking...", verb="thought")
            .with_entry("externalDialog", "hello", verb="said")
            .with_soul_state("emotionalState", "engaged"))
    """

    entries: tuple[MemoryEntry, ...] = ()
    soul_state_updates: tuple[tuple[str, str], ...] = ()
    user_model_update: Optional[str] = None
    user_model_change_note: str = ""
    user_model_target_id: str = ""
    dossier_updates: tuple[dict, ...] = ()
    editorial_dossier_updates: tuple[tuple[str, str, str], ...] = ()  # (domain, content, change_note)
    scheduled_events: tuple[dict, ...] = ()

    def with_entry(
        self,
        entry_type: str,
        content: str,
        verb: str = "",
        user_id: str = "claudicle",
        trace_id: str = "",
        metadata: Optional[dict] = None,
        region: str = "default",
        display_name: str = "",
    ) -> CognitiveOutput:
        """Return new output with an appended memory entry."""
        entry = MemoryEntry(
            entry_type=entry_type,
            content=content,
            verb=verb,
            user_id=user_id,
            trace_id=trace_id,
            metadata=metadata or {},
            region=region,
            display_name=display_name,
            created_at=time.time(),
        )
        return replace(self, entries=self.entries + (entry,))

    def with_raw_entry(self, entry: MemoryEntry) -> CognitiveOutput:
        """Return new output with a pre-built MemoryEntry appended."""
        return replace(self, entries=self.entries + (entry,))

    def with_soul_state(self, key: str, value: str) -> CognitiveOutput:
        """Return new output with a soul state update appended."""
        return replace(self, soul_state_updates=self.soul_state_updates + ((key, value),))

    def with_soul_state_updates(self, updates: dict[str, str]) -> CognitiveOutput:
        """Return new output with multiple soul state updates."""
        return replace(self, soul_state_updates=self.soul_state_updates + tuple(updates.items()))

    def with_user_model(
        self,
        update: str,
        target_id: str,
        change_note: str = "",
    ) -> CognitiveOutput:
        """Return new output with a user model update."""
        return replace(self, user_model_update=update, user_model_change_note=change_note, user_model_target_id=target_id)

    def with_dossier(
        self,
        entity_name: str,
        content: str,
        entity_type: str = "subject",
        change_note: str = "",
    ) -> CognitiveOutput:
        """Return new output with a dossier update appended."""
        return replace(self, dossier_updates=self.dossier_updates + ({
            "entity_name": entity_name,
            "content": content,
            "entity_type": entity_type,
            "change_note": change_note,
        },))

    def with_editorial_dossier(
        self,
        domain: str,
        content: str,
        change_note: str = "",
    ) -> CognitiveOutput:
        """Return new output with an editorial dossier update appended."""
        return replace(
            self,
            editorial_dossier_updates=self.editorial_dossier_updates + (
                (domain, content, change_note),
            ),
        )

    def with_scheduled_event(
        self,
        action: str,
        content: str = "",
        delay_seconds: float = 0,
        target_process: str = "",
        channel: str = "",
        thread_ts: str = "",
    ) -> CognitiveOutput:
        """Return new output with a scheduled event appended."""
        return replace(self, scheduled_events=self.scheduled_events + ({
            "action": action,
            "content": content,
            "delay_seconds": delay_seconds,
            "target_process": target_process,
            "channel": channel,
            "thread_ts": thread_ts,
        },))

    def merge(self, other: CognitiveOutput) -> CognitiveOutput:
        """Return new output combining this and another (immutable merge).

        Last-write-wins for user_model: if other carries a user_model_update,
        the entire user_model group (update, change_note, target_id) is taken
        from other, even if other's change_note is empty.
        """
        return CognitiveOutput(
            entries=self.entries + other.entries,
            soul_state_updates=self.soul_state_updates + other.soul_state_updates,
            user_model_update=other.user_model_update if other.user_model_update is not None else self.user_model_update,
            user_model_change_note=other.user_model_change_note if other.user_model_update is not None else self.user_model_change_note,
            user_model_target_id=other.user_model_target_id if other.user_model_update is not None else self.user_model_target_id,
            dossier_updates=self.dossier_updates + other.dossier_updates,
            editorial_dossier_updates=self.editorial_dossier_updates + other.editorial_dossier_updates,
            scheduled_events=self.scheduled_events + other.scheduled_events,
        )

    @property
    def is_empty(self) -> bool:
        return (
            not self.entries
            and not self.soul_state_updates
            and self.user_model_update is None
            and not self.dossier_updates
            and not self.editorial_dossier_updates
            and not self.scheduled_events
        )

    @property
    def soul_state_dict(self) -> dict[str, str]:
        """Convert soul_state_updates tuples to a dict (convenience for apply)."""
        return dict(self.soul_state_updates)


# Deprecated alias — use CognitiveOutput directly. Will be removed in a future release.
MemoryMutations = CognitiveOutput


# ---------------------------------------------------------------------------
# Load / Apply — the boundary between pure and impure
# ---------------------------------------------------------------------------

def load_snapshot(
    channel: str,
    thread_ts: str,
    limit: int = 40,
    trace_id: str = "",
) -> WorkingMemorySnapshot:
    """Load an immutable snapshot from SQLite.

    Reads recent working memory entries and soul state into a frozen
    snapshot that cognitive steps can pass around without side effects.
    """
    from memory import working_memory, soul_memory

    entries_raw = working_memory.get_recent(channel, thread_ts, limit=limit)
    entries = tuple(MemoryEntry.from_row(e) for e in entries_raw)
    soul_state = soul_memory.get_soul_state()

    return WorkingMemorySnapshot(
        entries=entries,
        soul_state=soul_state,
        trace_id=trace_id,
        channel=channel,
        thread_ts=thread_ts,
    )


def query_snapshot(
    channel: Optional[str] = None,
    thread_ts: Optional[str] = None,
    entry_type: Optional[str] = None,
    user_id: Optional[str] = None,
    region: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    trace_id: Optional[str] = None,
    limit: int = 100,
) -> WorkingMemorySnapshot:
    """Query working memory and return an immutable snapshot.

    Pure read: returns a frozen WorkingMemorySnapshot containing
    matching entries and current soul state. No side effects.
    """
    from memory import working_memory, soul_memory

    entries_raw = working_memory.query(
        channel=channel, thread_ts=thread_ts, entry_type=entry_type,
        user_id=user_id, region=region, since=since, until=until,
        trace_id=trace_id, limit=limit,
    )
    entries = tuple(MemoryEntry.from_row(e) for e in entries_raw)
    soul_state = soul_memory.get_soul_state()

    return WorkingMemorySnapshot(
        entries=entries,
        soul_state=soul_state,
        channel=channel or "",
        thread_ts=thread_ts or "",
    )


def apply_output(
    output: CognitiveOutput,
    channel: str,
    thread_ts: str,
    internal: bool = False,
) -> None:
    """Apply a CognitiveOutput atomically at the pipeline boundary.

    This is the ONLY place where cognitive cycle side effects hit the DB.
    The output is immutable — this function is the impure boundary.

    internal: if True, suppress scheduling (prevents re-scheduling loops
    from internal/scheduled perceptions — Open Souls pattern).
    """
    from memory import working_memory, soul_state, user_models

    # 1. Add working memory entries
    for entry in output.entries:
        # Per-entry target overrides (e.g. subdaimon lessons → global thread)
        ch = entry.target_channel or channel
        ts = entry.target_thread_ts or thread_ts
        working_memory.add(
            channel=ch,
            thread_ts=ts,
            user_id=entry.user_id,
            entry_type=entry.entry_type,
            content=entry.content,
            verb=entry.verb or None,
            metadata=entry.metadata or None,
            trace_id=entry.trace_id or None,
            display_name=entry.display_name or None,
            region=entry.region,
        )

    # 2. Update soul state (via unified soul_state for transition logging)
    for key, value in output.soul_state_updates:
        soul_state.set_state_key(
            key, value, channel=channel,
            thread_info={"channel": channel, "thread_ts": thread_ts},
        )

    # 3. Update user model
    if output.user_model_update is not None and output.user_model_target_id:
        user_models.save(
            output.user_model_target_id,
            output.user_model_update,
            change_note=output.user_model_change_note,
            channel=channel,
            thread_ts=thread_ts,
        )

    # 4. Update dossiers
    # Note: save_dossier() invalidates the entity graph cache on each call
    for dossier in output.dossier_updates:
        user_models.save_dossier(
            dossier["entity_name"],
            dossier["content"],
            dossier.get("entity_type", "subject"),
            dossier.get("change_note", ""),
            channel=channel,
            thread_ts=thread_ts,
        )

    # 4.5. Write editorial dossier updates to filesystem (atomic via tempfile+rename)
    for domain, content, change_note in output.editorial_dossier_updates:
        try:
            import config as _cfg
            if _cfg.EDITORIAL_DOSSIER_ENABLED and _cfg.EDITORIAL_DOSSIER_BASE:
                import os
                import tempfile
                dossier_path = os.path.join(
                    _cfg.EDITORIAL_DOSSIER_BASE,
                    f"{domain}-editorial-record.md",
                )
                dossier_dir = os.path.dirname(dossier_path)
                os.makedirs(dossier_dir, exist_ok=True)
                # Atomic write: temp file + rename preserves existing on failure
                tmp_fd, tmp_path = tempfile.mkstemp(dir=dossier_dir, suffix=".tmp")
                try:
                    with os.fdopen(tmp_fd, "w") as f:
                        f.write(content)
                        f.flush()
                        os.fsync(f.fileno())
                    os.rename(tmp_path, dossier_path)
                    log.info("Editorial dossier updated: %s (%s)", domain, change_note[:60])
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
        except Exception as e:
            log.error("Failed to write editorial dossier for %s: %s", domain, e)

    # 5. Schedule events (daemon-only, gated by SCHEDULER_ENABLED)
    # Open Souls: internal perceptions never re-schedule (loop prevention)
    remaining_events = list(output.scheduled_events)

    # 6. Execute summon events immediately (not scheduler-gated)
    if remaining_events:
        summon_events = [e for e in remaining_events if e["action"] == "summon_daimon"]
        remaining_events = [e for e in remaining_events if e["action"] != "summon_daimon"]
        for event in summon_events:
            try:
                from daimonic.summoning import summon_entity
                summon_entity(
                    entity_name=event.get("content", ""),
                    channel=event.get("channel") or channel,
                    thread_ts=event.get("thread_ts") or thread_ts,
                    mode=event.get("target_process") or "whisper",
                )
            except Exception as exc:
                log.debug("summon_daimon best-effort failed for '%s': %s",
                          event.get("content", ""), exc)

    if remaining_events and not internal:
        try:
            import config as _cfg
            if getattr(_cfg, "SCHEDULER_ENABLED", False):
                import scheduler
                for event in remaining_events:
                    scheduler.schedule(
                        action=event["action"],
                        content=event.get("content", ""),
                        delay_seconds=event.get("delay_seconds", 0),
                        target_process=event.get("target_process", ""),
                        channel=event.get("channel") or channel,
                        thread_ts=event.get("thread_ts") or thread_ts,
                    )
        except ImportError:
            pass  # scheduler module not available (e.g. terminal sessions)


# Deprecated alias — use apply_output directly. Will be removed in a future release.
apply_mutations = apply_output
