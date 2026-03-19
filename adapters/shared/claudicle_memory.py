"""
Claudicle Memory Adapter — soul-aware channel memory routing.

If ~/.claudicle/soul/soul.md exists (soul is active), routes all memory
operations through the canonical Claudicle daemon module at
~/.claudicle/daemon/memory/. Otherwise returns None so callers fall back
to their local per-skill databases.

This module is imported by both SMS and Slack skills as their unified
memory gateway. It never owns a database — it delegates to whichever
backend is appropriate.

Thread-safe: delegates to thread-safe canonical modules.
"""

import json
import logging
import os
import sys
import threading
import time
import types
from typing import Any, Optional

log = logging.getLogger(__name__)

SOUL_PATH = os.path.expanduser("~/.claudicle/soul/soul.md")
DAEMON_DIR = os.path.expanduser("~/.claudicle/daemon")

# Cache the daemon modules after first successful import
_daemon: Optional[types.SimpleNamespace] = None
_daemon_checked = False
_init_lock = threading.Lock()
_last_import_attempt: float = 0.0
_IMPORT_RETRY_COOLDOWN = 60.0  # seconds between retry attempts after failure


def is_soul_active() -> bool:
    """Check if the Claudicle soul is active (soul.md exists)."""
    return os.path.isfile(SOUL_PATH)


def get_daemon_modules() -> Optional[types.SimpleNamespace]:
    """Import and return canonical memory modules if soul is active.

    Returns a namespace with: working_memory, soul_memory, soul_state, user_models, snapshot.
    Returns None if soul is not active or import fails.
    """
    global _daemon, _daemon_checked, _last_import_attempt

    if not is_soul_active():
        return None

    if _daemon_checked:
        return _daemon

    # After a failed import, wait before retrying (prevents hammering)
    now = time.time()
    if _last_import_attempt and (now - _last_import_attempt) < _IMPORT_RETRY_COOLDOWN:
        return None

    with _init_lock:
        if _daemon_checked:
            return _daemon
        # Re-check cooldown inside lock
        now = time.time()
        if _last_import_attempt and (now - _last_import_attempt) < _IMPORT_RETRY_COOLDOWN:
            return None
        _last_import_attempt = now
        try:
            if DAEMON_DIR not in sys.path:
                sys.path.insert(0, DAEMON_DIR)
            from memory import working_memory, soul_memory, soul_state, user_models
            from memory.snapshot import (
                WorkingMemorySnapshot,
                CognitiveOutput,
                load_snapshot,
                apply_output,
            )
            _daemon = types.SimpleNamespace(
                working_memory=working_memory,
                soul_memory=soul_memory,
                soul_state=soul_state,
                user_models=user_models,
                load_snapshot=load_snapshot,
                apply_output=apply_output,
                WorkingMemorySnapshot=WorkingMemorySnapshot,
                CognitiveOutput=CognitiveOutput,
            )
            _daemon_checked = True  # Only cache success, not failure
            log.info("Claudicle daemon memory loaded from %s", DAEMON_DIR)
            return _daemon
        except Exception as e:
            log.warning("Failed to load Claudicle daemon memory (will retry in %ds): %s",
                        int(_IMPORT_RETRY_COOLDOWN), e)
            _daemon = None
            return None


# ── Working Memory ──────────────────────────────────────────────────────


def log_memory(
    channel: str,
    thread_ts: str,
    user_id: str,
    entry_type: str,
    content: str,
    verb: Optional[str] = None,
    metadata: Optional[dict] = None,
    display_name: Optional[str] = None,
    region: str = "default",
) -> bool:
    """Route a working memory entry to canonical DB if soul active.

    Returns True if written to canonical, False if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return False
    try:
        dm.working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id=user_id,
            entry_type=entry_type,
            content=content,
            verb=verb,
            metadata=metadata,
            display_name=display_name,
            region=region,
        )
        return True
    except Exception as e:
        log.error("Canonical working_memory.add failed for channel=%s: %s", channel, e)
        return False


def get_recent(
    channel: str,
    thread_ts: str,
    limit: int = 20,
) -> Optional[list[dict]]:
    """Get recent working memory entries from canonical DB.

    Returns list of dicts if soul active, None if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.working_memory.get_recent(channel, thread_ts, limit=limit)


# ── Soul Memory ─────────────────────────────────────────────────────────


def get_soul(key: str) -> Optional[str]:
    """Get a soul state value from canonical DB via unified soul_state.

    Returns the value if soul active, None if caller should use local DB.
    Note: None is ambiguous (could mean 'key not found' or 'soul not active').
    Use is_soul_active() to disambiguate.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.soul_state.get_state_key(key)


def set_soul(key: str, value: str, channel: str = "sms") -> bool:
    """Set a soul state value in canonical DB via unified soul_state.

    Routes through soul_state.set_state_key() which handles topic stack,
    emotional state transitions, and narrative working memory entries.

    Returns True if written to canonical, False if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return False
    try:
        dm.soul_state.set_state_key(key, value, channel=channel)
        return True
    except Exception as e:
        log.error("Canonical soul_state.set_state_key failed for key=%s: %s", key, e)
        return False


def get_all_soul() -> Optional[dict[str, str]]:
    """Get all soul state values from canonical DB.

    Returns dict if soul active, None if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.soul_memory.get_all()


def format_soul_state() -> Optional[str]:
    """Format soul state for prompt injection via unified soul_state.

    Returns formatted string if soul active, None if caller should use local.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.soul_state.format_for_prompt()


def prune_working_memory(
    phone_number: str,
    entry_types: Optional[list[str]] = None,
    content_pattern: Optional[str] = None,
    date: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """Prune working memory entries from canonical DB using delete_by_filter.

    Returns count of entries deleted (or would be deleted). Returns 0 if soul not active.

    Note: content_pattern is only applied in dry_run mode (Python-side substring
    match). The canonical delete_by_filter() API does not support content filtering,
    so live deletes ignore content_pattern and delete all matching entries by
    channel/type/date. Always dry_run first to verify scope.
    """
    dm = get_daemon_modules()
    if dm is None:
        return 0

    channel = f"sms:{phone_number}"
    total = 0

    # Convert date to epoch range
    since = None
    until = None
    if date:
        import datetime as _dt
        day_start = _dt.datetime.strptime(date, "%Y-%m-%d").timestamp()
        since = day_start
        until = day_start + 86400

    types_to_prune = entry_types or [None]
    for etype in types_to_prune:
        if dry_run:
            # Query count manually since delete_by_filter doesn't have dry_run
            try:
                entries = dm.working_memory.get_recent(channel, "", limit=10000)
                for e in (entries or []):
                    match = True
                    if etype and e.get("entry_type") != etype:
                        match = False
                    if content_pattern:
                        pattern = content_pattern.replace("%", "")
                        if pattern.lower() not in e.get("content", "").lower():
                            match = False
                    if since and e.get("created_at", 0) < since:
                        match = False
                    if until and e.get("created_at", 0) >= until:
                        match = False
                    if match:
                        total += 1
            except Exception as e:
                log.error("Canonical prune dry_run failed: %s", e)
        else:
            try:
                count = dm.working_memory.delete_by_filter(
                    channel=channel,
                    thread_ts="",
                    entry_type=etype,
                    since=since,
                    until=until,
                )
                total += count
            except Exception as e:
                log.error("Canonical prune failed: %s", e)

    return total


# ── User Models ─────────────────────────────────────────────────────────


def get_user_model(user_id: str) -> Optional[str]:
    """Get a user model from canonical DB.

    Returns model markdown if found and soul active, None otherwise.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.user_models.get(user_id)


def save_user_model(
    user_id: str,
    model_md: str,
    display_name: Optional[str] = None,
    change_note: str = "",
) -> bool:
    """Save a user model to canonical DB.

    Returns True if written to canonical, False if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return False
    try:
        dm.user_models.save(user_id, model_md, display_name, change_note)
        return True
    except Exception as e:
        log.error("Canonical user_models.save failed for %s: %s", user_id, e)
        return False


def increment_interaction(user_id: str) -> bool:
    """Increment interaction count in canonical DB.

    Returns True if done in canonical, False if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return False
    try:
        dm.user_models.increment_interaction(user_id)
        return True
    except Exception as e:
        log.error("Canonical increment_interaction failed for %s: %s", user_id, e)
        return False


def should_check_user_model(user_id: str) -> Optional[bool]:
    """Check if user model should be updated based on interaction count.

    Returns True/False if soul active, None if caller should use local DB.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    try:
        return dm.user_models.should_check_update(user_id)
    except Exception as e:
        log.error("Canonical should_check_update failed for %s: %s", user_id, e)
        return None


# ── Snapshot API (Open Souls pattern) ───────────────────────────────────


def load_snapshot(
    channel: str,
    thread_ts: str,
    limit: int = 40,
) -> Optional[Any]:
    """Load an immutable WorkingMemorySnapshot from canonical DB.

    Returns WorkingMemorySnapshot if soul active, None otherwise.
    """
    dm = get_daemon_modules()
    if dm is None:
        return None
    return dm.load_snapshot(channel, thread_ts, limit=limit)


def apply_cognitive_output(
    output: Any,
    channel: str,
    thread_ts: str,
    internal: bool = False,
) -> bool:
    """Apply a CognitiveOutput atomically to canonical DB.

    Returns True if applied to canonical, False if caller should handle locally.
    """
    dm = get_daemon_modules()
    if dm is None:
        return False
    dm.apply_output(output, channel, thread_ts, internal=internal)
    return True


# ── Helpers ─────────────────────────────────────────────────────────────


def sms_channel(phone: str) -> str:
    """Format an SMS phone number as a canonical channel ID."""
    return f"sms:{phone}"


def slack_channel(channel_id: str) -> str:
    """Format a Slack channel ID as a canonical channel ID."""
    return f"slack:{channel_id}"


def invalidate_cache():
    """Force re-check of soul status on next call. Useful for testing."""
    global _daemon, _daemon_checked, _last_import_attempt
    _daemon = None
    _daemon_checked = False
    _last_import_attempt = 0.0
