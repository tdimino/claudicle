"""
Daimonic intercession — multi-daimon whisper system for Claudicle.

Reads Claudicle's cognitive context and sends it to registered daimons for
whispered counsel. Daimons intercede through observation, not command.

Invocation hierarchy per daimon: daemon HTTP -> Groq fallback -> skip.
All providers default to disabled (opt-in via config).

Whispers are stored in working_memory as entry_type="daimonicIntuition"
(embodied recall, following the Open Souls paradigm). On next build_prompt(),
whispers are injected as Claudicle's own recalled intuitions and consumed.
"""

import logging
import os
import re
from typing import Optional

import soul_memory
import working_memory
from config import GROQ_API_KEY, SOUL_NAME

log = logging.getLogger("claudicle.daimonic")

_soul_md_cache: dict[str, Optional[str]] = {}


def read_context(channel: str, thread_ts: str) -> dict:
    """Gather Claudicle's current cognitive state for daimons.

    Returns minimal context: emotional state, topic, recent monologue excerpt.
    Does NOT send full user model text (data minimization).
    """
    state = soul_memory.get_all()
    recent = working_memory.get_recent(channel, thread_ts, limit=3)

    monologue = ""
    for entry in recent:
        if entry.get("entry_type") == "internalMonologue":
            monologue = entry.get("content", "")[:200]
            break

    return {
        "soul_state": {
            "emotionalState": state.get("emotionalState", "neutral"),
            "currentTopic": state.get("currentTopic", ""),
            "currentProject": state.get("currentProject", ""),
        },
        "recent_monologue": monologue,
        "interaction_count": len(recent),
    }


def _sanitize_whisper(raw: str) -> str:
    """Strip XML tags, triple backticks, and enforce 500-char limit."""
    cleaned = re.sub(r"</?[a-zA-Z_][^>]*>", "", raw)
    cleaned = cleaned.replace("```", "")
    return cleaned[:500].strip()


def _load_soul_md(path: str) -> Optional[str]:
    """Load and cache a daimon's soul.md."""
    if path in _soul_md_cache:
        return _soul_md_cache[path]
    expanded = os.path.expanduser(path)
    if os.path.isfile(expanded):
        with open(expanded) as f:
            _soul_md_cache[path] = f.read()
    else:
        _soul_md_cache[path] = None
    return _soul_md_cache[path]


def _format_context_for_llm(context: dict) -> str:
    """Format context dict as LLM user message."""
    parts = [f"## {SOUL_NAME}'s Current State"]
    ss = context.get("soul_state", {})
    if ss.get("emotionalState"):
        parts.append(f"- Emotional state: {ss['emotionalState']}")
    if ss.get("currentTopic"):
        parts.append(f"- Current topic: {ss['currentTopic']}")
    if ss.get("currentProject"):
        parts.append(f"- Current project: {ss['currentProject']}")
    if context.get("recent_monologue"):
        parts.append(f"\nRecent thought: {context['recent_monologue']}")
    return "\n".join(parts)


async def _try_daemon(daimon, context: dict) -> Optional[str]:
    """Call a daimon's HTTP endpoint."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Content-Type": "application/json"}
            if daimon.auth_token:
                headers["Authorization"] = f"Bearer {daimon.auth_token}"
            resp = await client.post(
                f"http://{daimon.daemon_host}:{daimon.daemon_port}/api/whisper",
                headers=headers,
                json={"source": "claudicle", "context": context},
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("whisper", "")
            if raw:
                return _sanitize_whisper(raw)
    except Exception as e:
        log.debug("%s daemon unavailable: %s", daimon.display_name, e)
    return None


async def _try_groq(daimon, context: dict) -> Optional[str]:
    """Call Groq with a daimon's soul.md as system prompt."""
    import httpx

    soul_md = _load_soul_md(daimon.soul_md)
    if not soul_md:
        log.warning("%s soul.md not found at %s", daimon.display_name, daimon.soul_md)
        return None

    system = soul_md + daimon.whisper_suffix

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": daimon.groq_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": _format_context_for_llm(context)},
                    ],
                    "temperature": daimon.whisper_temperature,
                    "max_tokens": daimon.whisper_max_tokens,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _sanitize_whisper(content)
    except Exception as e:
        log.debug("Groq %s unavailable: %s", daimon.name, e)
    return None


async def invoke_daimon(daimon, context: dict) -> Optional[str]:
    """Call a daimon and return its whisper.

    Tries daemon HTTP first, then Groq fallback, then skips.
    """
    if daimon.enabled and daimon.daemon_port:
        whisper = await _try_daemon(daimon, context)
        if whisper:
            return whisper

    if daimon.groq_enabled and GROQ_API_KEY:
        whisper = await _try_groq(daimon, context)
        if whisper:
            return whisper

    return None


async def invoke_all_whisperers(context: dict) -> list[tuple[str, str]]:
    """Invoke all enabled whispering daimons.

    Returns [(display_name, whisper), ...] for each daimon that produced a whisper.
    """
    import daimon_registry

    results = []
    for daimon in daimon_registry.get_whisperers():
        whisper = await invoke_daimon(daimon, context)
        if whisper:
            results.append((daimon.display_name, whisper))
    return results


async def invoke_kothar(context: dict) -> Optional[str]:
    """Backward-compat wrapper: invoke Kothar specifically."""
    import daimon_registry

    daimon = daimon_registry.get("kothar")
    if not daimon:
        return None
    return await invoke_daimon(daimon, context)


def store_whisper(content: str, source: str = "Kothar wa Khasis",
                  channel: str = "", thread_ts: str = "") -> None:
    """Store whisper in soul_memory + working_memory as embodied recall.

    Uses per-daimon soul_memory keys: daimonic_whisper_{source_key}
    """
    source_key = source.lower().split()[0]  # "Kothar wa Khasis" -> "kothar"
    soul_memory.set(f"daimonic_whisper_{source_key}", content)
    if channel and thread_ts:
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="daimonicIntuition",
            content=content,
            verb="sensed",
            metadata={"source": source},
        )


def get_active_whisper(source_key: str = "") -> Optional[str]:
    """Get active whisper from soul_memory.

    If source_key given, returns that daimon's whisper.
    If empty, returns first non-empty whisper found (legacy compat).
    """
    if source_key:
        val = soul_memory.get(f"daimonic_whisper_{source_key}")
        return val if val else None

    # Legacy: check old key first, then registry keys
    val = soul_memory.get("daimonic_whisper")
    if val:
        return val

    import daimon_registry
    for daimon in daimon_registry.get_whisperers():
        val = soul_memory.get(f"daimonic_whisper_{daimon.name}")
        if val:
            return val
    return None


def consume_whisper() -> None:
    """Clear legacy single whisper key. Use consume_all_whispers() instead."""
    soul_memory.set("daimonic_whisper", "")


def consume_all_whispers() -> None:
    """Clear all daimon whispers after prompt injection."""
    soul_memory.set("daimonic_whisper", "")  # legacy key
    import daimon_registry
    for daimon in daimon_registry.get_enabled():
        soul_memory.set(f"daimonic_whisper_{daimon.name}", "")


def format_for_prompt() -> str:
    """Format ALL active daimon whispers as embodied recall for prompt injection.

    Follows the Open Souls paradigm: whispers are presented as Claudius's
    own recalled intuitions, not as external system directives.

    Does NOT consume — caller must call consume_all_whispers() after
    successful response processing.
    """
    import daimon_registry

    sections = []

    # Check legacy key first (backward compat for existing whispers)
    legacy = soul_memory.get("daimonic_whisper")
    if legacy and legacy.strip():
        # Only use legacy if no per-daimon keys exist yet
        has_per_daimon = False
        for daimon in daimon_registry.get_whisperers():
            val = soul_memory.get(f"daimonic_whisper_{daimon.name}")
            if val and val.strip():
                has_per_daimon = True
                break
        if not has_per_daimon:
            sections.append(f"```\nKothar whispers: {legacy}\n```")

    # Per-daimon whispers
    for daimon in daimon_registry.get_whisperers():
        val = soul_memory.get(f"daimonic_whisper_{daimon.name}")
        if val and val.strip():
            sections.append(f"```\n{daimon.display_name} whispers: {val}\n```")

    if not sections:
        return ""

    header = "## Daimonic Intuitions" if len(sections) > 1 else "## Daimonic Intuition"
    return (
        f"{header}\n\n"
        f"{SOUL_NAME} sensed intuitions surface from deeper memory:\n\n"
        + "\n\n".join(sections)
    )
