"""Perception processor — typed perception classification.

Maps to Open Souls' Perception concept: every incoming stimulus is
classified into a typed Perception before being routed to a mental
process. Phase 2 uses fast-path heuristics only (no LLM classification).

The Perception dataclass is frozen (same pattern as snapshot.py).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Perception:
    """Typed incoming perception — immutable.

    action: "userMessage", "scheduledEvent", "systemNotification", "inactivityTimeout"
    content: message text or event content
    user_id: who triggered this perception
    channel: channel identifier
    thread_ts: thread identifier
    display_name: optional display name
    internal: True for scheduled/system perceptions (prevents re-scheduling loops)
    metadata: optional extra data
    created_at: timestamp of perception creation
    """
    action: str
    content: str
    user_id: str
    channel: str
    thread_ts: str
    display_name: str = ""
    internal: bool = False
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class PerceptionProcessor:
    """Classify incoming messages into typed Perceptions.

    Phase 2: heuristic-only fast-path classification.
    Phase 3+: will add LLM-based classification for ambiguous cases.
    """

    def classify(
        self,
        text: str,
        user_id: str,
        channel: str,
        thread_ts: str,
        display_name: str = "",
        queue_depth: int = 0,
    ) -> Perception:
        """Classify an incoming message into a Perception.

        Fast-path heuristics:
        - Empty/whitespace → skip (returns action="skip")
        - Slash commands → action="command"
        - File-only messages → action="fileUpload"
        - Everything else → action="userMessage"
        """
        stripped = text.strip() if text else ""

        # Skip empty messages
        if not stripped:
            return Perception(
                action="skip",
                content="",
                user_id=user_id,
                channel=channel,
                thread_ts=thread_ts,
                display_name=display_name,
            )

        # Slash commands
        if stripped.startswith("/"):
            return Perception(
                action="command",
                content=stripped,
                user_id=user_id,
                channel=channel,
                thread_ts=thread_ts,
                display_name=display_name,
            )

        # Default: user message
        return Perception(
            action="userMessage",
            content=stripped,
            user_id=user_id,
            channel=channel,
            thread_ts=thread_ts,
            display_name=display_name,
        )

    def from_scheduled_event(
        self,
        action: str,
        content: str,
        channel: str = "scheduler",
        thread_ts: str = "scheduled",
        metadata: dict | None = None,
    ) -> Perception:
        """Create a Perception from a scheduled event.

        Always internal=True to prevent infinite re-scheduling loops.
        """
        return Perception(
            action=action,
            content=content,
            user_id="system",
            channel=channel,
            thread_ts=thread_ts,
            internal=True,
            metadata=metadata or {},
        )

    def from_system(
        self,
        action: str,
        content: str,
        channel: str = "system",
        thread_ts: str = "system",
    ) -> Perception:
        """Create a system notification Perception."""
        return Perception(
            action=action,
            content=content,
            user_id="system",
            channel=channel,
            thread_ts=thread_ts,
            internal=True,
        )


# Module-level singleton
processor = PerceptionProcessor()
