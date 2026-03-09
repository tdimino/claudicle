"""
Daimon summoning — awaken any entity as an ephemeral speaking daimon.

Any entity (user model, person dossier, subject dossier) can be "summoned"
as a temporary daimon. A soul.md is synthesized from the entity's content,
cached in whispers._soul_md_cache, and registered in the daimon registry.

Summoned daimons use the same Groq whisper infrastructure as Kothar —
no new transport or API needed. The cache trick means zero filesystem writes.

Three interfaces:
- Cognitive step (autonomous): soul_engine detects summon_check → summon_daimon
- Slash command: /daimon summon <entity>
- Programmatic API: summon_entity() / dismiss_entity() / list_summoned()
"""

import logging
from typing import Optional

import config
from daimonic import registry as daimon_registry
from daimonic.registry import DaimonConfig
from daimonic import whispers
from memory import user_models
from memory.entity_graph import get_entity_graph

log = logging.getLogger("claudicle.summoning")

_SUMMONED_PREFIX = "summoned:"
_CACHE_PREFIX = f"__summoned__{_SUMMONED_PREFIX}"


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------

def _resolve_entity(
    entity_name: str,
) -> Optional[tuple[str, str, str, str]]:
    """Resolve an entity name to (entity_id, display_name, entity_type, model_md).

    Uses the entity graph name index for alias-aware lookup, then falls back
    to direct user_models queries. Returns None if not found.
    """
    graph = get_entity_graph()
    entity_id = graph.resolve_name(entity_name)

    if entity_id:
        node = graph.get_node(entity_id)
        if node:
            # Fetch the full model content
            if entity_id.startswith("dossier:"):
                model_md = user_models.get_dossier(node.name)
            else:
                model_md = user_models.get(entity_id)
            if model_md:
                return (entity_id, node.name, node.entity_type, model_md)

    # Fallback: try direct dossier lookup
    model_md = user_models.get_dossier(entity_name)
    if model_md:
        entity_id = f"dossier:{entity_name.lower().strip()}"
        return (entity_id, entity_name, "subject", model_md)

    # Fallback: try direct user model lookup (e.g. user_id passed directly)
    model_md = user_models.get(entity_name)
    if model_md:
        display = user_models.get_display_name(entity_name) or entity_name
        return (entity_name, display, "user", model_md)

    return None


# ---------------------------------------------------------------------------
# Soul.md synthesis
# ---------------------------------------------------------------------------

_SOUL_TEMPLATES = {
    "user": (
        "# {display_name}\n\n"
        "## Origin\n"
        "I am {display_name}, as modeled by {soul_name}. I speak from "
        "the accumulated observations {soul_name} has gathered about me.\n\n"
        "## Speaking Style\n"
        "{speaking_style}\n\n"
        "## Constraints\n"
        "- Speak in first person as {display_name}\n"
        "- Draw only from the source material below — do not invent\n"
        "- 1-3 sentences, concise and characteristic\n\n"
        "## Source Material\n\n{entity_content}\n"
    ),
    "person": (
        "# {display_name}\n\n"
        "## Origin\n"
        "I am {display_name}, as understood through {soul_name}'s observations. "
        "My voice is reconstructed from what is known about me.\n\n"
        "## Speaking Style\n"
        "Speak as {display_name} would, based on what is known. "
        "Scholarly but personal — this is a mind speaking, not a biography being read.\n\n"
        "## Constraints\n"
        "- Speak in first person as {display_name}\n"
        "- Draw only from the source material below — do not invent\n"
        "- 1-3 sentences, concise and authoritative\n\n"
        "## Source Material\n\n{entity_content}\n"
    ),
    "subject": (
        "# {display_name}\n\n"
        "## Origin\n"
        "I am the voice of {display_name} — the domain itself speaking through "
        "{soul_name}'s accumulated knowledge.\n\n"
        "## Speaking Style\n"
        "Precise, authoritative domain expert. Speak as the subject matter "
        "itself — not narrating about it, but from within it.\n\n"
        "## Constraints\n"
        "- Speak as the domain expert, not about the domain\n"
        "- Draw only from the source material below — do not invent\n"
        "- 1-3 sentences, weighted and precise\n\n"
        "## Source Material\n\n{entity_content}\n"
    ),
}


def _extract_speaking_style(model_md: str) -> str:
    """Extract a ## Speaking Style section from model markdown, if present."""
    lines = model_md.splitlines()
    in_section = False
    style_lines = []
    for line in lines:
        if line.strip().lower().startswith("## speaking style"):
            in_section = True
            continue
        if in_section:
            if line.strip().startswith("## "):
                break
            style_lines.append(line)
    if style_lines:
        return "\n".join(style_lines).strip()
    return "Speak naturally as this person would, based on what is known."


def synthesize_soul_md(
    entity_id: str,
    entity_content: str,
    entity_type: str,
    display_name: str,
) -> str:
    """Synthesize a soul.md from entity content.

    Template selection based on entity_type:
    - user: first-person, extracts Speaking Style section
    - person: scholarly but personal reconstruction
    - subject: domain-expert voice

    Pure function: inputs → soul.md text.
    """
    template = _SOUL_TEMPLATES.get(entity_type, _SOUL_TEMPLATES["subject"])
    speaking_style = _extract_speaking_style(entity_content) if entity_type == "user" else ""

    return template.format(
        display_name=display_name,
        soul_name=config.SOUL_NAME,
        entity_content=entity_content[:3000],  # Cap at 3K chars for LLM context
        speaking_style=speaking_style,
    )


# ---------------------------------------------------------------------------
# Summon / dismiss / list
# ---------------------------------------------------------------------------

def _registry_name(entity_id: str) -> str:
    """Build the registry name for a summoned entity."""
    return f"{_SUMMONED_PREFIX}{entity_id}"


def _cache_key(registry_name: str) -> str:
    """Build the whisper cache key for a summoned entity."""
    return f"__summoned__{registry_name}"


def summon_entity(
    entity_name: str,
    channel: str = "",
    thread_ts: str = "",
    mode: str = "whisper",
    invoke_immediately: bool = True,
) -> Optional[str]:
    """Summon an entity as an ephemeral daimon.

    1. Resolve entity via entity graph / user_models
    2. Synthesize soul.md from entity content
    3. Cache soul.md in whispers._soul_md_cache (no filesystem)
    4. Register DaimonConfig in registry
    5. If invoke_immediately: invoke via Groq and store whisper

    Returns the whisper text if invoked, or None.
    """
    # Check max active limit
    active = list_summoned()
    max_active = getattr(config, "SUMMONING_MAX_ACTIVE", 3)
    if len(active) >= max_active:
        log.warning("Max active summoned daimons (%d) reached", max_active)
        return None

    resolved = _resolve_entity(entity_name)
    if not resolved:
        log.warning("Entity '%s' not found for summoning", entity_name)
        return None

    entity_id, display_name, entity_type, model_md = resolved
    reg_name = _registry_name(entity_id)

    # Already summoned?
    existing = daimon_registry.get(reg_name)
    if existing and existing.enabled:
        log.info("Entity '%s' already summoned", display_name)
        return None

    # Synthesize and cache soul.md
    soul_md = synthesize_soul_md(entity_id, model_md, entity_type, display_name)
    cache_k = _cache_key(reg_name)
    whispers._soul_md_cache[cache_k] = soul_md

    # Register in daimon registry
    daimon_config = DaimonConfig(
        name=reg_name,
        display_name=display_name,
        soul_md=cache_k,  # Points to cache, not filesystem
        enabled=True,
        mode=mode,
        groq_enabled=True,
        groq_model=getattr(config, "SUMMONING_GROQ_MODEL", "moonshotai/kimi-k2-instruct"),
        whisper_suffix=(
            f"\n\nYou are {display_name}, summoned by {config.SOUL_NAME} to offer your perspective.\n"
            f"Whisper a brief insight from your unique vantage point.\n"
            f"MAX 1-2 sentences. Speak as {display_name}. Be specific and grounded.\n"
        ),
        whisper_temperature=0.8,
        whisper_max_tokens=150,
    )
    daimon_registry.register(daimon_config)
    log.info("Summoned entity '%s' as daimon '%s'", display_name, reg_name)

    # Optional: invoke immediately for first whisper
    if invoke_immediately and channel and config.GROQ_API_KEY:
        try:
            import asyncio
            context = whispers.read_context(channel, thread_ts)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in a running loop — schedule and return None
                log.debug("Event loop running, skipping immediate invoke for %s", display_name)
                return None
            whisper_text = loop.run_until_complete(
                whispers.invoke_daimon(daimon_config, context)
            )
            if whisper_text:
                whispers.store_whisper(whisper_text, source=display_name,
                                       channel=channel, thread_ts=thread_ts)
                return whisper_text
        except Exception as e:
            log.debug("Immediate invoke failed for %s (best-effort): %s", display_name, e)

    return None


def dismiss_entity(entity_name: str) -> bool:
    """Dismiss a summoned daimon, removing it from registry and cache.

    Returns True if the entity was found and dismissed.
    """
    # Try to resolve the entity to find its registry name
    resolved = _resolve_entity(entity_name)
    if resolved:
        entity_id = resolved[0]
        reg_name = _registry_name(entity_id)
    else:
        # Maybe the name IS the entity_id or registry name
        reg_name = _registry_name(entity_name)

    daimon = daimon_registry.get(reg_name)
    if not daimon:
        # Try lowercase version
        reg_name_lower = _registry_name(entity_name.lower().strip())
        daimon = daimon_registry.get(reg_name_lower)
        if daimon:
            reg_name = reg_name_lower

    if not daimon:
        return False

    # Disable in registry
    daimon_registry.toggle(reg_name, False)

    # Remove from soul.md cache
    cache_k = _cache_key(reg_name)
    whispers._soul_md_cache.pop(cache_k, None)

    log.info("Dismissed summoned daimon '%s'", reg_name)
    return True


def list_summoned() -> list[DaimonConfig]:
    """List all currently active summoned daimons."""
    return [
        d for d in daimon_registry.get_enabled()
        if d.name.startswith(_SUMMONED_PREFIX)
    ]
