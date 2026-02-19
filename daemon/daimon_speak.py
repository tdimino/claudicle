"""
Daimon speak mode — generate full responses from external soul daemons.

When a daimon is in speak or both mode, it generates a complete response
to the user's message (not just a whisper). Tries the soul daemon's WS
peer:message protocol first, then falls back to Groq with the daimon's
soul.md as system prompt.
"""

import asyncio
import json
import logging
import re
from typing import Optional

import daimonic
from config import GROQ_API_KEY, SOUL_NAME
from daimon_registry import DaimonConfig

log = logging.getLogger("claudicle.daimon_speak")

def _speak_system_suffix() -> str:
    return (
        "\n\nYou are responding directly to a user in a Slack thread. "
        f"Another soul ({SOUL_NAME}) has already responded. "
        "Give your own perspective. Stay in character. 2-4 sentences."
    )


async def generate_response(
    daimon: DaimonConfig,
    user_message: str,
    context: dict,
    claudicle_response: str = "",
) -> Optional[str]:
    """Generate a full response from a daimon.

    Tries WS daemon first (full cognitive pipeline), then Groq fallback.
    """
    if daimon.enabled and daimon.daemon_port:
        response = await _try_ws_daemon(daimon, user_message, context, claudicle_response)
        if response:
            return response

    if daimon.groq_enabled and GROQ_API_KEY:
        response = await _try_groq_speak(daimon, user_message, context, claudicle_response)
        if response:
            return response

    log.info("Daimon speak skipped for %s: no provider available", daimon.name)
    return None


async def _try_ws_daemon(
    daimon: DaimonConfig,
    user_message: str,
    context: dict,
    claudicle_response: str,
) -> Optional[str]:
    """Send user message to daimon's WS server via peer:message protocol.

    Opens a temporary WS connection, sends the message, waits for speak events.
    """
    try:
        import websockets
    except ImportError:
        log.debug("websockets not installed, skipping WS daemon for %s", daimon.name)
        return None

    try:
        uri = f"ws://{daimon.daemon_host}:{daimon.daemon_port}"
        async with websockets.connect(uri, open_timeout=5) as ws:
            payload = {
                "source": SOUL_NAME,
                "content": user_message,
                "kind": "speak",
            }
            if claudicle_response:
                payload["claudicle_response"] = claudicle_response[:300]
            msg = json.dumps({"type": "peer:message", "data": payload})
            await ws.send(msg)

            response_parts = []
            try:
                async with asyncio.timeout(15):
                    async for raw in ws:
                        event = json.loads(raw)
                        if event.get("type") == "speak":
                            return _sanitize_response(event["data"].get("content", ""))
                        elif event.get("type") == "speak:chunk":
                            response_parts.append(event["data"].get("chunk", ""))
                        elif event.get("type") == "speak:end":
                            break
            except asyncio.TimeoutError:
                pass

            if response_parts:
                return _sanitize_response("".join(response_parts))

    except Exception as e:
        log.debug("WS daemon %s unavailable: %s", daimon.name, e)
    return None


async def _try_groq_speak(
    daimon: DaimonConfig,
    user_message: str,
    context: dict,
    claudicle_response: str,
) -> Optional[str]:
    """Generate full response via Groq with daimon's soul.md."""
    import httpx

    soul_md = daimonic._load_soul_md(daimon.soul_md)
    if not soul_md:
        return None

    system = soul_md + _speak_system_suffix()
    user_content = _format_speak_prompt(user_message, context, claudicle_response)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": daimon.groq_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": daimon.speak_temperature,
                    "max_tokens": daimon.speak_max_tokens,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return _sanitize_response(content)
    except Exception as e:
        log.debug("Groq speak for %s failed: %s", daimon.name, e)
    return None


def _format_speak_prompt(
    user_message: str,
    context: dict,
    claudicle_response: str,
) -> str:
    """Build the user message for speak generation."""
    parts = ["## Conversation Context"]
    ss = context.get("soul_state", {})
    if ss.get("currentTopic"):
        parts.append(f"Topic: {ss['currentTopic']}")
    if claudicle_response:
        parts.append(f"\n{SOUL_NAME} already responded: \"{claudicle_response[:300]}\"")
    parts.append(f"\nUser says: \"{user_message}\"")
    parts.append(f"\nRespond in character. Do not repeat what {SOUL_NAME} said.")
    return "\n".join(parts)


def _sanitize_response(raw: str) -> str:
    """Strip XML tags and enforce length."""
    cleaned = re.sub(r"</?[a-zA-Z_][^>]*>", "", raw)
    cleaned = cleaned.replace("```", "")
    return cleaned[:1500].strip()
