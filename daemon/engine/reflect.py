"""
Retrospective cognitive pipeline for channel-agnostic reflection.

Runs cognitive steps (internal monologue, user model check/update,
soul state check/update) AFTER a response has been delivered, updating
persistent memory with the soul's reflection on the exchange.

In terminal sessions, Claude responds naturally (no XML tags). This module
runs as a post-response subprocess, reflecting on the exchange and updating
the same shared working_memory.db that Slack and other channels use.

Provider routing: REFLECT_PROVIDER selects the API endpoint (openrouter,
groq, or any OpenAI-compatible URL). REFLECT_MODEL selects the model.
Both configurable via environment variables.

Called by:
    ~/.claude/hooks/soul-reflect.py  (Stop hook → terminal sessions)
    daemon process directly           (for any channel, if needed)
"""

import json
import logging
import os
import pathlib
from typing import Optional

import httpx

import config
from cognitive_steps import STEP_INSTRUCTIONS
from engine import context as ctx_module
from engine.soul_engine import apply_soul_state_update, extract_tag
from memory import soul_memory, user_models, working_memory
from monitoring import soul_log

log = logging.getLogger("claudicle.reflect")

# Reflection steps — no stimulus_verb (already narrated) or external_dialogue
# (already responded). Focus: introspection and memory updates.
_REFLECTION_STEPS = [
    ("internal_monologue", "1. Internal Monologue"),
    ("user_model_check", "2. User Model Check"),
    ("user_model_update", "2a. User Model Update (only if check was true)"),
    ("soul_state_check", "3. Soul State Check"),
    ("soul_state_update", "3a. Soul State Update (only if check was true)"),
]

# Open Souls subprocess framing — names the logical subprocess boundaries
# within the single-call reflection. Each groups related cognitive steps.
_SUBPROCESSES = [
    {"name": "modelsTheUser", "steps": ["user_model_check", "user_model_update"]},
    {"name": "updatesState", "steps": ["soul_state_check", "soul_state_update"]},
]


# ---------------------------------------------------------------------------
# LLM call — provider-agnostic OpenAI-compatible HTTP
# ---------------------------------------------------------------------------

# Provider registry: name → (base_url, api_key_env_var, extra_headers)
_PROVIDERS = {
    "openrouter": (
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        {"HTTP-Referer": "https://github.com/tdimino/claudicle"},
    ),
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
        {},
    ),
}


def _resolve_api_key(env_var: str) -> str:
    """Resolve API key from env var or .env files."""
    key = os.environ.get(env_var, "")
    if key:
        return key
    # Fallback: scan .env files for the key
    for env_file in [
        pathlib.Path(config.CLAUDICLE_HOME) / ".env",
        pathlib.Path.home() / ".config/env/global.env",
    ]:
        try:
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith(f"{env_var}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def _call_llm(prompt: str, provider: str = "", model: str = "") -> str:
    """Make an LLM call via any OpenAI-compatible API.

    Provider routing: REFLECT_PROVIDER → base URL + API key.
    Supports: openrouter, groq, or any custom OpenAI-compatible URL.
    """
    provider = provider or config.REFLECT_PROVIDER
    model = model or config.REFLECT_MODEL

    if provider in _PROVIDERS:
        base_url, key_env, extra_headers = _PROVIDERS[provider]
    else:
        # Treat as a direct URL for custom OpenAI-compatible endpoints
        base_url = provider
        key_env = "REFLECT_API_KEY"
        extra_headers = {}

    api_key = _resolve_api_key(key_env)
    if not api_key:
        raise RuntimeError(f"No API key found for {provider} (env: {key_env})")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.3,
    }

    resp = httpx.post(base_url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    if "error" in result:
        raise RuntimeError(f"{provider} API error: {result['error']}")

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"{provider} returned no choices: {json.dumps(result)[:300]}")

    return choices[0]["message"]["content"]


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def build_reflection_prompt(
    user_message: str,
    assistant_response: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: str = "",
) -> str:
    """Build a prompt for retrospective cognitive reflection.

    Lighter than build_context() — includes soul.md, soul state, user model,
    the exchange, and reflection-specific cognitive step instructions.
    """
    parts = []

    # 1. Soul identity
    try:
        parts.append(ctx_module.load_soul())
    except FileNotFoundError:
        log.warning("[reflect] soul.md not found, continuing without personality")

    # 2. Soul state
    try:
        soul_state_text = soul_memory.format_for_prompt()
        if soul_state_text:
            parts.append(f"\n{soul_state_text}")
    except Exception as e:
        log.warning("[reflect] soul state read failed: %s", e)

    # 3. User model (always inject for reflection — need context for model updates)
    try:
        model_md = user_models.ensure_exists(user_id, display_name)
    except Exception as e:
        log.warning("[reflect] user model read failed: %s", e)
        model_md = ""
    if model_md:
        parts.append(f"\n## User Model\n\n{model_md}")

    # 4. The exchange to reflect on
    name_label = display_name or user_id
    parts.append(
        f"\n## Exchange to Reflect On\n\n"
        f"The following exchange just occurred. You responded naturally as Claude Code.\n"
        f"Now reflect on it through your cognitive pipeline.\n\n"
        f"**{name_label}**: {user_message}\n\n"
        f"**{config.SOUL_NAME}**: {assistant_response}"
    )

    # 5. Cognitive step instructions
    template_vars = {
        "soul_name": config.SOUL_NAME,
        "user": display_name or user_id,
        "user_model": model_md or "",
    }

    instruction_parts = [
        "\n## Cognitive Steps\n",
        "You MUST structure your response using these XML tags in this exact order.",
        "Do NOT include any text outside these tags.\n",
    ]

    for step_name, heading in _REFLECTION_STEPS:
        instruction_parts.append(f"### {heading}")
        instruction = STEP_INSTRUCTIONS[step_name]
        try:
            instruction = instruction.format(**template_vars)
        except KeyError:
            for k, v in template_vars.items():
                instruction = instruction.replace(f"{{{k}}}", str(v))
        instruction_parts.append(instruction)
        instruction_parts.append("")

    parts.append("\n".join(instruction_parts))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Reflection runner
# ---------------------------------------------------------------------------

def run_reflection(
    user_message: str,
    assistant_response: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: str = "",
) -> dict:
    """Run retrospective cognitive pipeline on a terminal exchange.

    Builds prompt, calls LLM, parses XML tags, updates memory.
    Returns a summary dict of what was processed.
    """
    if not config.TERMINAL_REFLECT_ENABLED:
        return {"skipped": True, "reason": "reflection disabled"}

    trace_id = working_memory.new_trace_id()
    summary = {"trace_id": trace_id, "steps": []}

    # Store the exchange in working memory (non-fatal — DB failure shouldn't block reflection)
    try:
        working_memory.add(
            channel=channel, thread_ts=thread_ts,
            user_id=user_id, entry_type="userMessage",
            content=user_message, display_name=display_name,
            trace_id=trace_id,
        )
        working_memory.add(
            channel=channel, thread_ts=thread_ts,
            user_id="claudicle", entry_type="externalDialog",
            content=assistant_response, verb="responded",
            trace_id=trace_id,
        )
    except Exception as e:
        log.warning("[%s] Failed to store exchange in working memory: %s", trace_id, e)

    soul_log.emit(
        "stimulus", trace_id, channel=channel, thread_ts=thread_ts,
        origin="terminal_reflection", user_id=user_id,
        display_name=display_name or user_id,
        text=user_message, text_length=len(user_message),
    )

    # Build and execute the reflection prompt
    prompt = build_reflection_prompt(
        user_message, assistant_response,
        user_id, channel, thread_ts, display_name,
    )

    try:
        raw = _call_llm(prompt)
    except Exception as e:
        log.error("[%s] Reflection LLM call failed: %s", trace_id, e)
        soul_log.emit(
            "error", trace_id, channel=channel, thread_ts=thread_ts,
            source="reflect.run_reflection", error=str(e)[:500],
            error_type=type(e).__name__,
        )
        return {"trace_id": trace_id, "error": str(e)}

    # --- Parse cognitive steps from XML response ---
    # Each step wrapped individually so a DB failure on one doesn't abort the rest.

    # Internal monologue
    monologue_content, monologue_verb = extract_tag(raw, "internal_monologue")
    if monologue_content:
        try:
            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="internalMonologue",
                content=monologue_content, verb=monologue_verb or "reflected",
                trace_id=trace_id,
            )
            soul_log.emit(
                "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                step="internalMonologue", verb=monologue_verb or "reflected",
                content=monologue_content, content_length=len(monologue_content),
            )
            summary["steps"].append("internal_monologue")
            log.info("[%s] Reflection monologue: %s", trace_id, monologue_content[:80])
        except Exception as e:
            log.error("[%s] Failed to store monologue: %s", trace_id, e)

    # --- Subprocess: modelsTheUser ---
    soul_log.emit(
        "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
        name="modelsTheUser", event="start",
    )

    model_check_raw, _ = extract_tag(raw, "user_model_check")
    model_check = False
    model_updated = False
    if model_check_raw:
        model_check = model_check_raw.strip().lower() == "true"
        # Enrich mentalQuery with monologue context for reasoning chain
        query_context = monologue_content[:120] if monologue_content else ""
        query_content = (
            f"Should the user model be updated? (context: {query_context})"
            if query_context else "Should the user model be updated?"
        )
        try:
            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="mentalQuery",
                content=query_content,
                verb="evaluated",
                metadata={"result": model_check},
                trace_id=trace_id,
            )
            soul_log.emit(
                "decision", trace_id, channel=channel, thread_ts=thread_ts,
                gate="user_model_check", result=model_check,
                content=query_content,
            )
            summary["steps"].append(f"user_model_check={model_check}")
        except Exception as e:
            log.error("[%s] Failed to store user model check: %s", trace_id, e)

    if model_check:
        update_content, _ = extract_tag(raw, "user_model_update")
        change_note, _ = extract_tag(raw, "model_change_note")
        if update_content:
            try:
                user_models.save(user_id, update_content.strip(), change_note=change_note)
                working_memory.add(
                    channel=channel, thread_ts=thread_ts,
                    user_id="claudicle", entry_type="toolAction",
                    content=f"updated user model for {user_id}",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="user_model_update", target=user_id,
                    change_note=change_note or "",
                )
                model_updated = True
                summary["steps"].append("user_model_update")
                log.info("[%s] Reflection updated user model for %s", trace_id, user_id)
            except Exception as e:
                log.error("[%s] Failed to update user model: %s", trace_id, e)

    soul_log.emit(
        "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
        name="modelsTheUser", event="end",
        result={"check": model_check, "updated": model_updated},
    )

    # --- Subprocess: updatesState ---
    soul_log.emit(
        "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
        name="updatesState", event="start",
    )

    state_check_raw, _ = extract_tag(raw, "soul_state_check")
    state_changed = False
    state_updated = False
    if state_check_raw:
        state_changed = state_check_raw.strip().lower() == "true"
        query_context = monologue_content[:120] if monologue_content else ""
        query_content = (
            f"Has the soul state changed? (context: {query_context})"
            if query_context else "Has the soul state changed?"
        )
        try:
            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="mentalQuery",
                content=query_content,
                verb="evaluated",
                metadata={"result": state_changed},
                trace_id=trace_id,
            )
            soul_log.emit(
                "decision", trace_id, channel=channel, thread_ts=thread_ts,
                gate="soul_state_check", result=state_changed,
                content=query_content,
            )
            summary["steps"].append(f"soul_state_check={state_changed}")
        except Exception as e:
            log.error("[%s] Failed to store soul state check: %s", trace_id, e)

        if state_changed:
            update_raw, _ = extract_tag(raw, "soul_state_update")
            if update_raw:
                try:
                    apply_soul_state_update(update_raw, channel, thread_ts, trace_id=trace_id)
                    state_updated = True
                    summary["steps"].append("soul_state_update")
                    log.info("[%s] Reflection updated soul state", trace_id)
                except Exception as e:
                    log.error("[%s] Failed to update soul state: %s", trace_id, e)

    soul_log.emit(
        "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
        name="updatesState", event="end",
        result={"check": state_changed, "updated": state_updated},
    )

    # Subprocess results for callers
    summary["subprocesses"] = {
        "modelsTheUser": {"check": model_check, "updated": model_updated},
        "updatesState": {"check": state_changed, "updated": state_updated},
    }

    # Increment interaction counter
    try:
        user_models.increment_interaction(user_id)
    except Exception as e:
        log.warning("[%s] Failed to increment interaction counter: %s", trace_id, e)

    soul_log.emit(
        "response", trace_id, channel=channel, thread_ts=thread_ts,
        text="[reflection complete]", text_length=0,
        reflection=True, steps=summary["steps"],
    )

    return summary
