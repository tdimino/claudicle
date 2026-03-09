"""
Per-user model and entity dossier management for the pseudo soul engine.

Each Slack user gets a markdown profile (modeled after tom/tomModel.md) stored in
~/.claude/userModels/{name}/. Claudicle uses these to personalize interactions.
Claudicle can also autonomously create dossiers for third-party people and subjects
encountered in conversation.

Models are stored in the same SQLite DB as working memory and updated periodically
via a mentalQuery boolean check.

Thread-safe: shares the same threading.local() DB connection pattern as working_memory.
"""

import json
import logging
import os
import re
import sqlite3
import time
from datetime import date
from typing import Optional

from config import USER_MODEL_UPDATE_INTERVAL
from memory.db import memory_pool

log = logging.getLogger(__name__)

_USER_MODEL_TEMPLATE = """---
title: "{display_name}"
type: user-model
userName: "{display_name}"
userId: "{user_id}"
created: "{date}"
updated: "{date}"
status: active
onboardingComplete: {onboarding_complete}
role: "{role}"
---

# {display_name}

## Persona
Unknown — first interaction.

## Speaking Style
Not yet observed.

## Conversational Context
Not yet observed.

## Worldview
Not yet observed.

## Interests & Domains
Not yet observed.

## Working Patterns
Not yet observed.

## Most Potent Memories
No shared memories yet.
"""

_CREATE_USER_MODELS = """
    CREATE TABLE IF NOT EXISTS user_models (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        model_md TEXT NOT NULL,
        interaction_count INTEGER DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
"""

_CREATE_USER_MODEL_MODULES = """
    CREATE TABLE IF NOT EXISTS user_model_modules (
        user_id TEXT NOT NULL,
        module_name TEXT NOT NULL,
        module_md TEXT NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (user_id, module_name)
    )
"""

# Register schema + migrations with the shared pool
memory_pool.add_migrations(
    [
        _CREATE_USER_MODELS,
        "ALTER TABLE user_models ADD COLUMN entity_type TEXT DEFAULT 'user'",
        _CREATE_USER_MODEL_MODULES,
    ]
)

# Backward compat — tests monkeypatch these
DB_PATH = memory_pool.db_path


def _get_conn() -> sqlite3.Connection:
    return memory_pool.get_conn()


def get(user_id: str) -> Optional[str]:
    """Get the markdown user model for a Slack user, or None if not yet created."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT model_md FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return row["model_md"]


def get_display_name(user_id: str) -> Optional[str]:
    """Get the cached display name for a user."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT display_name FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None
    return row["display_name"]


def save(
    user_id: str,
    model_md: str,
    display_name: Optional[str] = None,
    change_note: str = "",
    monologue: str = "",
    channel: str = "",
    thread_ts: str = "",
    trace_id: str = "",
) -> None:
    """Save or update a user model. Increments interaction count on update."""
    # Read old version before overwrite (for shedding archaeology)
    old_md = get(user_id)

    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_models (user_id, display_name, model_md, interaction_count, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?)
           ON CONFLICT(user_id)
           DO UPDATE SET
               model_md = excluded.model_md,
               display_name = COALESCE(excluded.display_name, user_models.display_name),
               updated_at = excluded.updated_at""",
        (user_id, display_name, model_md, now, now),
    )
    conn.commit()

    # Invalidate entity graph cache — user model content changed
    from memory.entity_graph import invalidate_graph
    invalidate_graph()

    # Record shed event if content changed
    if old_md is not None and old_md != model_md:
        try:
            from memory.model_journal import shed_model
            name = display_name or get_display_name(user_id) or user_id
            shed_model(
                user_id=user_id, old_md=old_md, new_md=model_md,
                monologue=monologue, change_note=change_note,
                channel=channel, thread_ts=thread_ts, trace_id=trace_id,
                display_name=name,
            )
        except Exception as e:
            log.warning("Model shedding failed (best-effort): %s", e)

    # Git-track the change
    try:
        from config import MEMORY_GIT_ENABLED
        if MEMORY_GIT_ENABLED:
            from memory import git_tracker as memory_git
            name = display_name or get_display_name(user_id) or user_id
            memory_git.export_user_model(user_id, name, model_md, change_note)
    except Exception as e:
        log.warning("Git memory tracking failed (best-effort): %s", e)


def ensure_exists(user_id: str, display_name: Optional[str] = None) -> str:
    """Ensure a user model exists, creating a blank template if needed. Returns the model."""
    model = get(user_id)
    if model is not None:
        return model
    name = display_name or user_id
    today = date.today().isoformat()
    # Skip onboarding for users with known real names (e.g. from Slack API).
    # Needs onboarding when: no display_name given, or display_name is the default.
    from config import DEFAULT_USER_NAME, PRIMARY_USER_ID
    onboarding_complete = "true" if (display_name and display_name != DEFAULT_USER_NAME) else "false"
    role = "primary" if user_id == PRIMARY_USER_ID else "standard"
    model = (
        _USER_MODEL_TEMPLATE
        .replace("{display_name}", name)
        .replace("{user_id}", user_id)
        .replace("{date}", today)
        .replace("{onboarding_complete}", onboarding_complete)
        .replace("{role}", role)
    )
    save(user_id, model, display_name)
    return model


def parse_frontmatter(model_md: str) -> dict:
    """Extract YAML frontmatter from a user model or dossier markdown string.

    .. deprecated::
        Import from ``memory.frontmatter.parse_frontmatter`` directly.
        This wrapper exists for backward compatibility and will be removed
        in a future release.

    Returns an empty dict if no frontmatter is found.
    """
    from memory.frontmatter import parse_frontmatter as _parse
    return _parse(model_md)


def get_user_name(user_id: str) -> Optional[str]:
    """Get the authoritative display name from the user model's frontmatter.

    Returns userName from YAML frontmatter if present, otherwise None.
    This is the canonical source for how to address a user — takes precedence
    over Slack display_name or user_id.
    """
    model = get(user_id)
    if not model:
        return None
    meta = parse_frontmatter(model)
    return meta.get("userName")


def should_check_update(user_id: str) -> bool:
    """Return True if it's time to check whether the user model needs updating.

    Triggers every USER_MODEL_UPDATE_INTERVAL interactions.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT interaction_count FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return False
    return row["interaction_count"] % USER_MODEL_UPDATE_INTERVAL == 0


def increment_interaction(user_id: str) -> None:
    """Bump the interaction counter for a user."""
    conn = _get_conn()
    conn.execute(
        "UPDATE user_models SET interaction_count = interaction_count + 1, updated_at = ? WHERE user_id = ?",
        (time.time(), user_id),
    )
    conn.commit()


def get_interaction_count(user_id: str) -> int:
    """Get the current interaction count for a user."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT interaction_count FROM user_models WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return 0
    return row["interaction_count"]


def close() -> None:
    """Close the thread-local connection if open."""
    memory_pool.close()


# ---------------------------------------------------------------------------
# Modular user models — Tier 3 of the Open Souls token optimization
#
# Core model (Persona, Speaking Style, Conversational Context, Worldview)
# is always injected — these are identity sections. Optional reference
# modules (expertise, history, preferences) are loaded on demand based
# on channel and message content.
#
# Backward compatible: if no modules exist, the monolithic model_md
# column is used as-is.
# ---------------------------------------------------------------------------

# Valid module names — only the optional reference modules.
# Identity sections (persona, style, context, worldview) live in core model_md.
VALID_MODULES = frozenset({
    "expertise", "history", "preferences",
})

# Keyword → module activation map (case-insensitive substring matching)
# Only maps to optional modules — identity sections are always in core.
_KEYWORD_MODULES: dict[str, str] = {
    "coding": "expertise",
    "programming": "expertise",
    "language": "expertise",
    "technical": "expertise",
    "domain": "expertise",
    "remember": "history",
    "last time": "history",
    "before": "history",
    "memory": "history",
    "prefer": "preferences",
    "workflow": "preferences",
    "tool": "preferences",
}

# Channel → default modules loaded (in addition to core)
_CHANNEL_DEFAULTS: dict[str, list[str]] = {
    "sms": [],                          # SMS: core only by default
    "slack": ["expertise"],             # Slack: core + expertise
    "terminal": ["expertise", "preferences"],  # Terminal: core + expertise + preferences
    "discord": [],
    "telegram": [],
}


def save_module(user_id: str, module_name: str, module_md: str) -> None:
    """Save or update a reference module for a user."""
    if module_name not in VALID_MODULES:
        raise ValueError(f"Invalid module name: {module_name}. Must be one of {sorted(VALID_MODULES)}")
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_model_modules (user_id, module_name, module_md, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, module_name)
           DO UPDATE SET module_md = excluded.module_md, updated_at = excluded.updated_at""",
        (user_id, module_name, module_md, now, now),
    )
    conn.commit()


def get_module(user_id: str, module_name: str) -> Optional[str]:
    """Get a specific reference module for a user, or None if not found."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT module_md FROM user_model_modules WHERE user_id = ? AND module_name = ?",
        (user_id, module_name),
    ).fetchone()
    return row["module_md"] if row else None


def get_modules(user_id: str, module_names: list[str] | None = None) -> dict[str, str]:
    """Get reference modules for a user.

    Args:
        user_id: User identifier.
        module_names: Optional list of specific modules to fetch.
            If None, returns all modules for this user.

    Returns:
        Dict mapping module_name → module_md.
    """
    conn = _get_conn()
    if module_names:
        placeholders = ",".join("?" for _ in module_names)
        rows = conn.execute(
            f"SELECT module_name, module_md FROM user_model_modules "
            f"WHERE user_id = ? AND module_name IN ({placeholders})",
            [user_id] + list(module_names),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT module_name, module_md FROM user_model_modules WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {row["module_name"]: row["module_md"] for row in rows}


def list_modules(user_id: str) -> list[str]:
    """List available module names for a user."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT module_name FROM user_model_modules WHERE user_id = ? ORDER BY module_name",
        (user_id,),
    ).fetchall()
    return [row["module_name"] for row in rows]


def has_modules(user_id: str) -> bool:
    """Check if a user has any reference modules stored."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM user_model_modules WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return row["cnt"] > 0


def delete_module(user_id: str, module_name: str) -> bool:
    """Delete a specific module. Returns True if a row was deleted."""
    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM user_model_modules WHERE user_id = ? AND module_name = ?",
        (user_id, module_name),
    )
    conn.commit()
    return cursor.rowcount > 0


def select_modules(channel: str, message_text: str = "") -> list[str]:
    """Select which reference modules to load based on channel and message content.

    Module selection algorithm (from the plan):
    1. Channel defaults: SMS loads core only; Slack loads core + context; etc.
    2. Keyword activation: message mentions "project" → load `context`; etc.
    3. Deduplication: no module listed twice.

    Returns list of module names to load (may be empty = core only).
    """
    selected: set[str] = set()

    # 1. Channel defaults
    ch_lower = channel.lower()
    for prefix, modules in _CHANNEL_DEFAULTS.items():
        if ch_lower.startswith(prefix + ":") or ch_lower.startswith(prefix):
            selected.update(modules)
            break
    else:
        # Slack channel IDs start with C (public) or D (DM)
        if channel.startswith("C") or channel.startswith("D"):
            selected.update(_CHANNEL_DEFAULTS.get("slack", []))

    # 2. Keyword activation
    if message_text:
        text_lower = message_text.lower()
        for keyword, module in _KEYWORD_MODULES.items():
            if keyword in text_lower:
                selected.add(module)

    return sorted(selected)


def get_with_modules(
    user_id: str,
    channel: str = "",
    message_text: str = "",
    module_names: list[str] | None = None,
) -> str:
    """Get the core user model with relevant reference modules appended.

    When the user has reference modules, this returns:
    - The core model (model_md from user_models table)
    - Selected reference modules appended as ## sections

    When the user has no modules, returns model_md unchanged (backward compatible).

    Args:
        user_id: User identifier.
        channel: Channel for module selection defaults.
        message_text: Current message for keyword-based module activation.
        module_names: Explicit module list (overrides channel/keyword selection).

    Returns:
        Assembled user model text (core + selected modules).
    """
    core = get(user_id)
    if core is None:
        return ""

    if not has_modules(user_id):
        return core

    # Determine which modules to load
    names = module_names or select_modules(channel, message_text)
    if not names:
        return core

    modules = get_modules(user_id, names)
    if not modules:
        return core

    # Assemble: core + module sections
    parts = [core]
    for name in names:
        if name in modules:
            parts.append(f"\n## Module: {name.title()}\n\n{modules[name]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Dossier API — autonomous entity modeling (people, subjects, topics)
# ---------------------------------------------------------------------------

def _dossier_id(entity_name: str) -> str:
    """Create a stable ID for a dossier entity."""
    return f"dossier:{entity_name.lower().strip()}"


def save_dossier(
    entity_name: str,
    model_md: str,
    entity_type: str = "subject",
    change_note: str = "",
    monologue: str = "",
    channel: str = "",
    thread_ts: str = "",
    trace_id: str = "",
) -> None:
    """Save or update a dossier for a person or subject."""
    # Read old version before overwrite (for shedding archaeology)
    old_md = get_dossier(entity_name)

    entity_id = _dossier_id(entity_name)
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO user_models
               (user_id, display_name, model_md, entity_type, interaction_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)
           ON CONFLICT(user_id)
           DO UPDATE SET
               model_md = excluded.model_md,
               display_name = excluded.display_name,
               entity_type = excluded.entity_type,
               updated_at = excluded.updated_at""",
        (entity_id, entity_name, model_md, entity_type, now, now),
    )
    conn.commit()
    log.info("Saved dossier for %s (%s): %s", entity_name, entity_type, change_note or "no note")

    # Invalidate entity graph cache — dossier content changed
    from memory.entity_graph import invalidate_graph
    invalidate_graph()

    # Record shed event if content changed
    if old_md is not None and old_md != model_md:
        try:
            from memory.model_journal import shed_dossier
            shed_dossier(
                entity_name=entity_name, old_md=old_md, new_md=model_md,
                monologue=monologue, change_note=change_note,
                entity_type=entity_type, channel=channel,
                thread_ts=thread_ts, trace_id=trace_id,
            )
        except Exception as e:
            log.warning("Dossier shedding failed (best-effort): %s", e)

    # Git-track the change
    try:
        from config import MEMORY_GIT_ENABLED
        if MEMORY_GIT_ENABLED:
            from memory import git_tracker as memory_git
            memory_git.export_dossier(entity_name, model_md, entity_type, change_note)
    except Exception as e:
        log.warning("Git memory tracking failed (best-effort): %s", e)


def get_dossier(entity_name: str) -> Optional[str]:
    """Get a dossier by entity name, or None if not found."""
    entity_id = _dossier_id(entity_name)
    conn = _get_conn()
    row = conn.execute(
        "SELECT model_md FROM user_models WHERE user_id = ?", (entity_id,)
    ).fetchone()
    return row["model_md"] if row else None


def list_dossiers(entity_type: Optional[str] = None) -> list[dict]:
    """List all dossiers, optionally filtered by type ('person' or 'subject')."""
    conn = _get_conn()
    if entity_type:
        rows = conn.execute(
            "SELECT user_id, display_name, entity_type, updated_at FROM user_models "
            "WHERE user_id LIKE 'dossier:%' AND entity_type = ? ORDER BY updated_at DESC",
            (entity_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT user_id, display_name, entity_type, updated_at FROM user_models "
            "WHERE user_id LIKE 'dossier:%' ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {
            "entity_id": row["user_id"],
            "name": row["display_name"],
            "type": row["entity_type"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def get_relevant_dossiers(text: str, limit: int = 3) -> list[str]:
    """Find dossier entity names relevant to the given text.

    Uses multi-signal graph scoring (name, alias, tags, RAG keywords,
    backlink boost) when the entity graph is available. Falls back to
    simple substring matching if the graph is empty or on DB errors.
    """
    from memory.entity_graph import get_entity_graph, get_relevant_entities

    try:
        graph = get_entity_graph()
    except Exception:
        log.warning("Failed to build entity graph — falling back to substring matching")
        graph = None

    if graph and graph.nodes:
        return get_relevant_entities(
            graph, text, limit=limit,
            entity_types=("person", "subject"),
        )

    # Fallback: simple substring matching (cold start or graph error)
    log.debug("Entity graph empty — using substring fallback for dossier matching")
    conn = _get_conn()
    rows = conn.execute(
        "SELECT display_name FROM user_models WHERE user_id LIKE 'dossier:%'"
    ).fetchall()
    text_lower = text.lower()
    matches = [
        row["display_name"]
        for row in rows
        if row["display_name"] and row["display_name"].lower() in text_lower
    ]
    return matches[:limit]
