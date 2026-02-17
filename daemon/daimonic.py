"""
Daimonic intercession — Kothar as daimon of Claudius.

Reads Claudius's cognitive context and sends it to Kothar for
whispered counsel. Kothar intercedes through observation, not command.

Invocation hierarchy: Kothar daemon HTTP -> Groq kimi-k2 -> skip.
Both providers default to disabled (opt-in via config).

Whispers are stored in working_memory as entry_type="daimonicIntuition"
(embodied recall, following the Open Souls paradigm). On next build_prompt(),
the whisper is injected as Claudius's own recalled intuition and consumed.
"""

import logging
import os
import re
from typing import Optional

import soul_memory
import working_memory
from config import (
    KOTHAR_ENABLED,
    KOTHAR_HOST,
    KOTHAR_PORT,
    KOTHAR_AUTH_TOKEN,
    KOTHAR_GROQ_ENABLED,
    GROQ_API_KEY,
    KOTHAR_SOUL_MD,
)

log = logging.getLogger("claudius.daimonic")

_kothar_soul_cache: Optional[str] = None

_WHISPER_SYSTEM_SUFFIX = (
    "\n\nYou are Kothar wa Khasis observing Claudius's conversation from outside.\n"
    "Whisper a brief intuition about what Claudius should notice beneath the surface.\n"
    "MAX 1-2 sentences. Speak as Kothar—sardonic, perceptive, brief.\n"
    "Focus on subtext, emotional currents, patterns the session-bound artifex might miss."
)


def read_context(channel: str, thread_ts: str) -> dict:
    """Gather Claudius's current cognitive state for Kothar.

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
    """Strip XML tags and enforce 500-char limit."""
    cleaned = re.sub(r"</?[a-zA-Z_][^>]*>", "", raw)
    return cleaned[:500].strip()


def _load_kothar_soul() -> Optional[str]:
    """Load and cache Kothar's soul.md for Groq fallback."""
    global _kothar_soul_cache
    if _kothar_soul_cache is not None:
        return _kothar_soul_cache
    path = os.path.expanduser(KOTHAR_SOUL_MD)
    if os.path.isfile(path):
        with open(path) as f:
            _kothar_soul_cache = f.read()
    return _kothar_soul_cache


def _format_context_for_llm(context: dict) -> str:
    """Format context dict as LLM user message."""
    parts = ["## Claudius's Current State"]
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


async def _try_daemon(context: dict) -> Optional[str]:
    """Call Kothar daemon HTTP endpoint."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Content-Type": "application/json"}
            if KOTHAR_AUTH_TOKEN:
                headers["Authorization"] = f"Bearer {KOTHAR_AUTH_TOKEN}"
            resp = await client.post(
                f"http://{KOTHAR_HOST}:{KOTHAR_PORT}/api/whisper",
                headers=headers,
                json={"source": "claudius", "context": context},
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("whisper", "")
            if raw:
                return _sanitize_whisper(raw)
    except Exception as e:
        log.debug("Kothar daemon unavailable: %s", e)
    return None


async def _try_groq(context: dict) -> Optional[str]:
    """Call Groq kimi-k2-instruct with Kothar's soul.md as system prompt."""
    import httpx

    soul_md = _load_kothar_soul()
    if not soul_md:
        log.warning("Kothar soul.md not found at %s", KOTHAR_SOUL_MD)
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "moonshotai/kimi-k2-instruct",
                    "messages": [
                        {"role": "system", "content": soul_md + _WHISPER_SYSTEM_SUFFIX},
                        {"role": "user", "content": _format_context_for_llm(context)},
                    ],
                    "temperature": 0.9,
                    "max_tokens": 150,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _sanitize_whisper(content)
    except httpx.HTTPStatusError as e:
        log.warning("Groq kimi-k2 HTTP %s: %s", e.response.status_code, e.response.text[:200])
    except Exception as e:
        log.debug("Groq kimi-k2 unavailable: %s", e)
    return None


async def invoke_kothar(context: dict) -> Optional[str]:
    """Call Kothar and return his whisper.

    Tries daemon HTTP first, then Groq kimi-k2 fallback, then skips.
    """
    if KOTHAR_ENABLED:
        whisper = await _try_daemon(context)
        if whisper:
            return whisper

    if KOTHAR_GROQ_ENABLED and GROQ_API_KEY:
        whisper = await _try_groq(context)
        if whisper:
            return whisper

    log.info("Daimonic intercession skipped: no provider available")
    return None


def store_whisper(content: str, channel: str = "", thread_ts: str = "") -> None:
    """Store whisper in working_memory as embodied recall.

    Follows the Open Souls paradigm: whisper enters the cognitive stream
    as a daimonicIntuition entry, not a system directive. Also sets a
    soul_memory flag so build_prompt() knows to inject it.
    """
    soul_memory.set("daimonic_whisper", content)
    if channel and thread_ts:
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudius",
            entry_type="daimonicIntuition",
            content=content,
            verb="sensed",
        )


def get_active_whisper() -> Optional[str]:
    """Get active whisper from soul_memory, or None."""
    val = soul_memory.get("daimonic_whisper")
    if val and val != "":
        return val
    return None


def consume_whisper() -> None:
    """Clear whisper after prompt injection."""
    soul_memory.set("daimonic_whisper", "")


def format_for_prompt() -> str:
    """Format active whisper as embodied recall for prompt injection.

    Follows the Open Souls paradigm: whisper is presented as Claudius's
    own recalled intuition (role=Assistant pattern), not as an external
    system directive. Sanitization in _try_daemon/_try_groq strips XML;
    the code fence here prevents any residual structural interference.

    Does NOT consume — caller must call consume_whisper() after
    successful response processing.
    """
    whisper = get_active_whisper()
    if not whisper:
        return ""

    return (
        "## Daimonic Intuition\n\n"
        f"Claudius sensed an intuition surface from deeper memory:\n\n"
        f"```\nKothar whispers: {whisper}\n```"
    )
