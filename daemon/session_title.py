"""
Write customTitle to Claude Code's sessions-index.json for a given session.

Bypasses the CLI's lack of a --name flag by writing directly to the JSON file.
Uses the same fcntl locking pattern as ~/.claude/hooks/session-tags-infer.py.
"""

import fcntl
import json
import logging
import os
import pathlib
from typing import Optional

log = logging.getLogger("claudicle.session_title")

CLAUDE_PROJECTS_DIR = pathlib.Path.home() / ".claude" / "projects"
SUMMARY_CACHE = pathlib.Path.home() / ".claude" / "session-summaries.json"
_LOCK_DIR = pathlib.Path("/tmp") / f"claude-{os.getuid()}"
_LOCK_PATH = _LOCK_DIR / "sessions-index.lock"


def set_custom_title(
    session_id: str,
    title: str,
    force: bool = False,
) -> bool:
    """Set customTitle in the matching sessions-index.json.

    Scans all project directories under ~/.claude/projects/ to find
    the entry matching session_id. Returns True if written.
    """
    if not title or not session_id:
        return False

    if not CLAUDE_PROJECTS_DIR.exists():
        return False

    for index_path in CLAUDE_PROJECTS_DIR.glob("*/sessions-index.json"):
        if _write_title(index_path, session_id, title, force):
            _propagate_to_summary_cache(session_id, title)
            log.info("Set customTitle for %s: %s", session_id[:8], title)
            return True

    log.debug("Session %s not found in any sessions-index.json", session_id[:8])
    return False


def _write_title(
    index_path: pathlib.Path,
    session_id: str,
    title: str,
    force: bool,
) -> bool:
    """Write title to a specific sessions-index.json with file locking."""
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)

    lock_fd = None
    try:
        lock_fd = open(_LOCK_PATH, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("Lock held by another process, skipping title write for %s", session_id[:8])
        if lock_fd is not None:
            lock_fd.close()
        return False
    except OSError as e:
        log.warning("Failed to acquire sessions-index.json lock: %s", e)
        if lock_fd is not None:
            lock_fd.close()
        return False

    try:
        index_data = json.loads(index_path.read_text())

        for entry in index_data.get("entries", []):
            if entry.get("sessionId") == session_id:
                if entry.get("customTitle") and not force:
                    return False
                entry["customTitle"] = title
                break
        else:
            return False

        tmp = index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index_data, indent=2))
        tmp.rename(index_path)
        return True
    except (json.JSONDecodeError, OSError) as e:
        log.debug("Failed to write title to %s: %s", index_path, e)
        return False
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except OSError:
            pass


def _propagate_to_summary_cache(session_id: str, title: str):
    """Sync title to session-summaries.json (same pattern as propagate-rename.py)."""
    lock_fd = None
    try:
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
        lock_fd = open(_LOCK_DIR / "session-summaries.lock", "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        log.warning("Could not lock session-summaries.json for %s, skipping propagation", session_id[:8])
        if lock_fd is not None:
            lock_fd.close()
        return

    try:
        cache = {}
        if SUMMARY_CACHE.exists():
            try:
                cache = json.loads(SUMMARY_CACHE.read_text())
            except (json.JSONDecodeError, OSError):
                cache = {}

        if cache.get(session_id, {}).get("title") == title:
            return

        if session_id not in cache:
            cache[session_id] = {}
        cache[session_id]["title"] = title

        tmp = SUMMARY_CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, indent=2))
        tmp.rename(SUMMARY_CACHE)
    except OSError as e:
        log.warning("Failed to sync title to session-summaries.json for %s: %s", session_id[:8], e)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()
        except OSError:
            pass
