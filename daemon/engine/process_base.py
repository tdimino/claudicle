"""Process base types for the mental process state machine.

Maps to Open Souls' MentalProcess concept: each process is a callable
behavioral mode that composes cognitive steps imperatively. The soul
routes perceptions through the active process, which produces a
ProcessResult carrying dialogue, cognitive output, and optional transition.

All types are frozen dataclasses (copy-on-write, same as snapshot.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from memory.snapshot import CognitiveOutput, WorkingMemorySnapshot


@dataclass(frozen=True)
class ProcessTransition:
    """Describes a transition to another mental process.

    target: process module name (e.g. "focused_process")
    params: optional dict passed to the target process
    execute_now: if True, chain immediately on same perception (depth-capped)
    """
    target: str
    params: dict = field(default_factory=dict)
    execute_now: bool = False


@dataclass(frozen=True)
class ProcessResult:
    """Immutable result from a mental process run.

    dialogue: external response text for the user
    output: frozen CognitiveOutput describing all side effects
    transition: optional transition to another process
    """
    dialogue: str
    output: CognitiveOutput = field(default_factory=CognitiveOutput)
    transition: ProcessTransition | None = None


class MentalProcess(Protocol):
    """Protocol for mental process modules.

    Every process module in daemon/processes/ must export a run()
    function matching this signature.
    """
    async def run(
        self,
        text: str,
        user_id: str,
        channel: str,
        thread_ts: str,
        snapshot: WorkingMemorySnapshot,
        params: dict | None = None,
    ) -> ProcessResult: ...
