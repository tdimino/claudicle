"""Mental process router — single entry point for all cognitive cycles.

Routes each perception through the active mental process (stored in
soul_memory as currentProcess). Handles process transitions with
copy-on-write process memory cleanup and executeNow chaining.

Maps to Open Souls' MentalProcess dispatch pattern.
"""

import importlib
import logging
import pathlib
from types import ModuleType
from typing import Optional

from memory import soul_memory
from memory.process_memory import clear as clear_process_memory
from memory.snapshot import WorkingMemorySnapshot, apply_output
from monitoring import soul_log

from engine.process_base import ProcessResult

log = logging.getLogger("claudicle.process_router")

MAX_EXECUTE_NOW_DEPTH = 3
_DEFAULT_PROCESS = "main_process"
_valid_processes: set[str] | None = None


def _discover_valid_processes() -> set[str]:
    """Auto-discover valid process names from the processes/ directory."""
    global _valid_processes
    if _valid_processes is not None:
        return _valid_processes

    processes_dir = pathlib.Path(__file__).parent.parent / "processes"
    valid = set()
    for f in processes_dir.glob("*.py"):
        name = f.stem
        if name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"processes.{name}")
            if hasattr(mod, "run"):
                valid.add(name)
        except (ImportError, ModuleNotFoundError):
            pass
    _valid_processes = valid
    log.info("Discovered valid processes: %s", valid)
    return valid


def _validate_process(name: str) -> bool:
    """Check if a process name is in the discovered valid set."""
    return name in _discover_valid_processes()


def _load_process(name: str) -> ModuleType:
    """Import daemon/processes/{name}.py. Falls back to main_process."""
    try:
        return importlib.import_module(f"processes.{name}")
    except (ImportError, ModuleNotFoundError):
        log.warning("Process '%s' not found, falling back to '%s'", name, _DEFAULT_PROCESS)
        return importlib.import_module(f"processes.{_DEFAULT_PROCESS}")


def _emit_transition(
    from_process: str,
    to_process: str,
    trigger: str = "",
    execute_now: bool = False,
    trace_id: str = "",
    channel: str = "",
    thread_ts: str = "",
) -> None:
    """Emit a process transition event to soul-stream."""
    soul_log.emit(
        "processTransition", trace_id,
        channel=channel, thread_ts=thread_ts,
        **{"from": from_process, "to": to_process,
           "trigger": trigger, "execute_now": execute_now},
    )


async def route(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    snapshot: WorkingMemorySnapshot,
    display_name: Optional[str] = None,
    trace_id: str = "",
    depth: int = 0,
    internal: bool = False,
    target_process: str = "",
    params: dict | None = None,
) -> ProcessResult:
    """Route a perception through the current mental process.

    Reads currentProcess from soul_memory, loads the process module,
    calls its run(), handles transitions (including executeNow chaining
    up to MAX_EXECUTE_NOW_DEPTH).

    internal: True for scheduled/system perceptions (suppresses re-scheduling)
    target_process: override current process (e.g. from scheduled events)
    params: transition params forwarded to the target process

    Returns the final ProcessResult with dialogue and output.
    """
    current = target_process or soul_memory.get("currentProcess") or _DEFAULT_PROCESS

    process_module = _load_process(current)
    result = await process_module.run(
        text=text,
        user_id=user_id,
        channel=channel,
        thread_ts=thread_ts,
        snapshot=snapshot,
        display_name=display_name,
        params=params,
    )

    # Apply cognitive output at the boundary
    apply_output(result.output, channel, thread_ts, internal=internal)

    # Handle process transition
    if result.transition:
        target = result.transition.target

        if not _validate_process(target):
            log.error(
                "Invalid process transition target '%s' — ignoring transition",
                target,
            )
        else:
            soul_memory.set("previousProcess", current)
            soul_memory.set("currentProcess", target)
            soul_memory.set("processTurnCount", "0")
            clear_process_memory(current)

            _emit_transition(
                from_process=current,
                to_process=target,
                execute_now=result.transition.execute_now,
                trace_id=trace_id,
                channel=channel,
                thread_ts=thread_ts,
            )
            log.info("Process transition: %s → %s", current, target)

            if result.transition.execute_now:
                if depth >= MAX_EXECUTE_NOW_DEPTH:
                    log.warning("executeNow depth limit reached at %d", depth)
                    return result
                return await route(
                    text, user_id, channel, thread_ts,
                    snapshot, display_name, trace_id,
                    depth=depth + 1,
                    internal=internal,
                    params=result.transition.params,
                )

    # Increment turn counter for current process
    turn_count = soul_memory.get("processTurnCount") or "0"
    soul_memory.set("processTurnCount", str(int(turn_count) + 1))

    return result
