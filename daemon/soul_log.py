"""Structured soul log — JSONL cognitive cycle stream.

Append-only JSONL capturing the full cognitive cycle as self-describing
phases threaded by trace_id. Designed for ``tail -f`` observability,
monitor TUI consumption, and downstream analytics.

Coexists with slack_log.py (raw Slack events) and working_memory.py
(SQLite cognitive store). Does NOT duplicate SQLite data — this is
the streaming observability layer.

Phases: stimulus, context, cognition, decision, memory, response, error.

Usage::

    from soul_log import emit
    emit("stimulus", trace_id, channel, thread_ts, user_id="U123", text="hello")
"""

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from config import CLAUDIUS_HOME, SOUL_LOG_ENABLED

log = logging.getLogger(__name__)

LOG_PATH = os.environ.get(
    "CLAUDIUS_SOUL_LOG",
    os.path.join(CLAUDIUS_HOME, "soul-stream.jsonl"),
)


def emit(
    phase: str,
    trace_id: str,
    channel: str = "",
    thread_ts: str = "",
    **kwargs: Any,
) -> None:
    """Append a phase entry to the soul stream JSONL.

    Thread-safe via fcntl.flock. Never raises — failures are
    logged and swallowed (observability must not kill the pipeline).

    Args:
        phase: One of stimulus, context, cognition, decision,
               memory, response, error.
        trace_id: 12-char hex grouping all entries in this cycle.
        channel: Slack channel ID or synthetic channel identifier.
        thread_ts: Thread timestamp for thread identity.
        **kwargs: Phase-specific fields merged into the entry.
    """
    if not SOUL_LOG_ENABLED:
        return
    try:
        entry = {
            "phase": phase,
            "trace_id": trace_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
            "thread_ts": thread_ts,
            **kwargs,
        }
        line = json.dumps(entry, default=str) + "\n"
        with open(LOG_PATH, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        log.warning("Failed to write soul log: %s", e)


def read_log(path: Optional[str] = None, last_n: int = 0) -> list[dict]:
    """Read JSONL log entries. Returns list of dicts.

    Malformed lines are skipped with a warning.

    Args:
        path: Log file path (defaults to LOG_PATH).
        last_n: If positive, return only the last N entries.
    """
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.readlines()
    if last_n:
        lines = lines[-last_n:]
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("Skipping malformed soul log line: %r", line[:120])
    return entries


def read_trace(trace_id: str, path: Optional[str] = None) -> list[dict]:
    """Read all entries for a specific trace_id, ordered by ts.

    Args:
        trace_id: The trace_id to filter by.
        path: Log file path (defaults to LOG_PATH).
    """
    all_entries = read_log(path)
    return [e for e in all_entries if e.get("trace_id") == trace_id]
