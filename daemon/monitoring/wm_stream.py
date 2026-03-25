"""Working memory JSONL stream — tail-able log of all cognitive entries.

Companion to soul_log.py. While soul_log captures high-level cognitive phases
(stimulus, context, cognition, decision, memory, response), this stream
captures every individual working_memory entry as it is written to SQLite.

Usage::

    tail -f ~/.claudicle/working-memory-stream.jsonl | jq .
    tail -f ~/.claudicle/working-memory-stream.jsonl | jq 'select(.entry_type=="internalMonologue")'
    tail -f ~/.claudicle/working-memory-stream.jsonl | jq 'select(.trace_id=="a1b2c3d4e5f6")'
"""

import fcntl
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from config import CLAUDICLE_HOME, WM_STREAM_ENABLED

log = logging.getLogger(__name__)

# Rotate JSONL files at 10MB to prevent unbounded growth
_MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB


def _rotate_if_needed(path: str) -> None:
    """Rotate log file if it exceeds _MAX_LOG_BYTES."""
    try:
        if os.path.exists(path) and os.path.getsize(path) > _MAX_LOG_BYTES:
            rotated = path + ".1"
            os.replace(path, rotated)
            log.info("Rotated %s (>10MB) → %s", path, rotated)
    except Exception as e:
        log.warning("Log rotation failed for %s: %s", path, e)


WM_STREAM_PATH = os.environ.get(
    "CLAUDICLE_WM_STREAM_PATH",
    os.path.join(CLAUDICLE_HOME, "working-memory-stream.jsonl"),
)


def emit(
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
    """Append a working memory entry to the JSONL stream.

    Thread-safe via fcntl.flock. Never raises — failures are logged
    and swallowed (observability must not kill the pipeline).

    Signature mirrors working_memory.add() exactly.
    """
    if not WM_STREAM_ENABLED:
        return
    try:
        _rotate_if_needed(WM_STREAM_PATH)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "channel": channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "entry_type": entry_type,
            "content": content,
            "verb": verb,
            "metadata": metadata,
            "trace_id": trace_id,
            "display_name": display_name,
            "region": region,
        }
        line = json.dumps(entry, default=str) + "\n"
        with open(WM_STREAM_PATH, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        log.warning("Failed to write WM stream: %s", e)


def emit_lifecycle(
    event: str,
    channel: str,
    thread_ts: str,
    detail: Optional[dict] = None,
) -> None:
    """Emit a lifecycle event (checkpoint, rollback, delete) to the WM stream."""
    emit(channel=channel, thread_ts=thread_ts, user_id="system",
         entry_type="lifecycle", content=event, metadata=detail)
