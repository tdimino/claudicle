"""
Claudicle session index — tracks sessions Claudicle creates or intercedes in.

Stored at $CLAUDICLE_HOME/session-index.json. Gives Claudicle visibility
over its own sessions independently of Claude Code's sessions-index.json.
"""

import datetime
import fcntl
import json
import logging
import os
import pathlib
import threading
from typing import Optional

from config import CLAUDICLE_HOME

log = logging.getLogger("claudicle.session_index")

INDEX_PATH = pathlib.Path(CLAUDICLE_HOME) / "session-index.json"
_lock = threading.Lock()


def _load() -> dict:
    if not INDEX_PATH.exists():
        return {"sessions": {}}
    try:
        return json.loads(INDEX_PATH.read_text())
    except json.JSONDecodeError as e:
        log.error("session-index.json corrupted (JSON parse error: %s) — starting with empty index", e)
        return {"sessions": {}}
    except OSError as e:
        log.error("Failed to read session-index.json: %s", e)
        return {"sessions": {}}


def _save(data: dict):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    tmp = INDEX_PATH.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(INDEX_PATH)
    except OSError as e:
        log.error("Failed to save session index: %s", e)


def register(
    session_id: str,
    channel: str,
    thread_ts: str,
    user_id: str,
    display_name: Optional[str] = None,
    channel_name: Optional[str] = None,
    title: Optional[str] = None,
    origin: str = "slack",
):
    """Register a new session in Claudicle's index."""
    with _lock:
        data = _load()
        now = datetime.datetime.now().isoformat(timespec="seconds")

        data["sessions"][session_id] = {
            "channel": channel,
            "channel_name": channel_name or channel,
            "thread_ts": thread_ts,
            "user_id": user_id,
            "display_name": display_name or user_id,
            "origin": origin,
            "created_at": now,
            "last_active": now,
            "turn_count": 1,
            "custom_title": title or "",
        }
        _save(data)
    log.info("Registered session %s (origin=%s, channel=%s)", session_id[:8], origin, channel_name or channel)


def touch(session_id: str):
    """Update last_active and increment turn_count."""
    with _lock:
        data = _load()
        entry = data["sessions"].get(session_id)
        if not entry:
            return
        entry["last_active"] = datetime.datetime.now().isoformat(timespec="seconds")
        entry["turn_count"] = entry.get("turn_count", 0) + 1
        _save(data)


def get(session_id: str) -> Optional[dict]:
    """Return metadata for a session, or None."""
    data = _load()
    return data["sessions"].get(session_id)


def list_active(hours: int = 72) -> dict:
    """List sessions active within the given window."""
    data = _load()
    now = datetime.datetime.now()
    active = {}
    for sid, entry in data["sessions"].items():
        try:
            last = datetime.datetime.fromisoformat(entry.get("last_active", ""))
            if (now - last).total_seconds() <= hours * 3600:
                active[sid] = entry
        except ValueError:
            continue
    return active


def cleanup(hours: int = 72) -> int:
    """Remove sessions older than the given window. Returns count removed."""
    with _lock:
        data = _load()
        now = datetime.datetime.now()
        to_remove = []
        for sid, entry in data["sessions"].items():
            try:
                last = datetime.datetime.fromisoformat(entry.get("last_active", ""))
                if (now - last).total_seconds() > hours * 3600:
                    to_remove.append(sid)
            except ValueError:
                log.warning("Session %s has unparseable last_active %r — removing", sid[:8], entry.get("last_active"))
                to_remove.append(sid)
        for sid in to_remove:
            del data["sessions"][sid]
        if to_remove:
            _save(data)
    return len(to_remove)
