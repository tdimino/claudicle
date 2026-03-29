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

from dataclasses import dataclass
import logging
from typing import Callable

import config
from cognitive_steps import STEP_INSTRUCTIONS
from engine import context as ctx_module
from engine.compaction import compact_soul, compact_user_model, get_reflection_budget
from engine.helpers import extract_tag
from engine.llm_client import call_llm as _call_llm, resolve_api_key as _resolve_api_key, PROVIDERS as _PROVIDERS
from engine.soul_engine import apply_soul_state_update
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

@dataclass
class Subprocess:
    name: str
    execute: Callable


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

    When COMPACTION_ENABLED, applies budget-aware compaction:
    - Soul.md compacted to reflection budget (800 chars)
    - User model at tier 2 (extended portrait, not full model)
    """
    parts = []

    # Budget allocation (only active when COMPACTION_ENABLED)
    budget = get_reflection_budget() if config.COMPACTION_ENABLED else None

    # 1. Soul identity
    try:
        soul_text = ctx_module.load_soul()
        if budget and budget.soul > 0:
            soul_text = compact_soul(soul_text, budget.soul)
            budget.consume("soul", len(soul_text))
        parts.append(soul_text)
    except FileNotFoundError:
        log.warning("[reflect] soul.md not found, continuing without personality")

    # 2. Soul state
    try:
        soul_state_text = soul_memory.format_for_prompt()
        if soul_state_text:
            parts.append(f"\n{soul_state_text}")
    except Exception as e:
        log.warning("[reflect] soul state read failed: %s", e)

    # 3. User model — tier 2 (extended portrait) when compaction is active,
    #    full model otherwise. Reflection always needs user model for updates.
    try:
        model_md = user_models.ensure_exists(user_id, display_name)
    except Exception as e:
        log.warning("[reflect] user model read failed: %s", e)
        model_md = ""
    if model_md:
        if budget and budget.user_model > 0:
            model_md = compact_user_model(model_md, tier=2, budget=budget.available("user_model"))
            budget.consume("user_model", len(model_md))
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


def _execute_models_user(raw, channel, thread_ts, trace_id, ctx) -> dict:
    user_id = ctx["user_id"]
    summary = ctx.get("summary")
    monologue_content = ctx.get("monologue_content", "")

    model_check_raw, _ = extract_tag(raw, "user_model_check")
    model_check = False
    model_updated = False
    if model_check_raw:
        model_check = model_check_raw.strip().lower() == "true"
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
            if summary is not None:
                summary["steps"].append(f"user_model_check={model_check}")
        except Exception as e:
            log.error("[%s] Failed to store user model check: %s", trace_id, e)

    if model_check:
        update_content, _ = extract_tag(raw, "user_model_update")
        change_note, _ = extract_tag(raw, "model_change_note")
        if update_content:
            try:
                user_models.save(
                    user_id, update_content.strip(),
                    change_note=change_note,
                    monologue=monologue_content,
                    channel=channel, thread_ts=thread_ts,
                    trace_id=trace_id,
                )
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
                if summary is not None:
                    summary["steps"].append("user_model_update")
                log.info("[%s] Reflection updated user model for %s", trace_id, user_id)
            except Exception as e:
                log.error("[%s] Failed to update user model: %s", trace_id, e)

    return {"check": model_check, "updated": model_updated}


def _execute_updates_state(raw, channel, thread_ts, trace_id, ctx) -> dict:
    summary = ctx.get("summary")
    monologue_content = ctx.get("monologue_content", "")

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
            if summary is not None:
                summary["steps"].append(f"soul_state_check={state_changed}")
        except Exception as e:
            log.error("[%s] Failed to store soul state check: %s", trace_id, e)

        if state_changed:
            update_raw, _ = extract_tag(raw, "soul_state_update")
            if update_raw:
                try:
                    apply_soul_state_update(update_raw, channel, thread_ts, trace_id=trace_id)
                    state_updated = True
                    if summary is not None:
                        summary["steps"].append("soul_state_update")
                    log.info("[%s] Reflection updated soul state", trace_id)
                except Exception as e:
                    log.error("[%s] Failed to update soul state: %s", trace_id, e)

    return {"check": state_changed, "updated": state_updated}


def _execute_compression(raw, channel, thread_ts, trace_id, ctx) -> dict:
    del raw
    from memory.compression import compress_thread

    interaction_count = ctx.get("interaction_count", 0)
    fired = interaction_count > 0 and interaction_count % config.COMPRESSION_REFLECT_INTERVAL == 0
    if not fired:
        return {"fired": False, "compressed": False}

    compressed = False
    try:
        result = compress_thread(channel, thread_ts, trace_id=trace_id)
        compressed = bool(result.get("compressed_count", 0))
        if compressed:
            log.info("[%s] Reflection compressed working memory", trace_id)
    except Exception as e:
        log.error("[%s] Reflection compression failed: %s", trace_id, e)

    return {"fired": True, "compressed": compressed}


def _execute_shed_spores(raw, channel, thread_ts, trace_id, ctx) -> dict:
    """Subprocess: decide whether to shed a mycelium spore.

    Follows the learnsAboutTheUser pattern — examines the monologue for
    file-specific insights, gates on signal word density, writes a note
    via mycelium_bridge.write_spore() if the gate passes.
    """
    del raw
    from engine import mycelium_bridge
    from memory import process_memory, working_memory

    result = {"check": False, "shed": False, "file": None, "kind": None}

    repo_root = mycelium_bridge.get_repo_root()
    if not repo_root or not mycelium_bridge.is_active(repo_root):
        return result

    monologue = ctx.get("monologue_content", "")
    if not monologue:
        return result

    file_paths = mycelium_bridge.extract_file_paths(monologue)
    if not file_paths:
        return result

    result["check"] = True

    # Heuristic gate: monologue must contain decision/warning language
    # near a file reference. Threshold 3 (not 2) to avoid false positives
    # from generic LLM narration.
    monologue_lower = monologue.lower()
    spore_signals = [
        "must", "should not", "constraint", "warning",
        "decided", "chose", "requires", "breaks if", "depends on",
    ]
    signal_count = sum(1 for s in spore_signals if s in monologue_lower)
    if signal_count < 3:
        return result

    # Classify and write — break only on success, try next kind on failure
    kind_map = [
        ("warning", "warning"), ("constraint", "constraint"),
        ("decided", "decision"), ("chose", "decision"),
    ]
    for keyword, kind in kind_map:
        if keyword in monologue_lower:
            body = monologue[:500].strip()
            target_file = file_paths[0]

            success = mycelium_bridge.write_spore(
                file_path=target_file,
                kind=kind,
                body=body,
                slot=config.SOUL_NAME.lower(),
                repo_root=repo_root,
            )

            if success:
                result["shed"] = True
                result["file"] = target_file
                result["kind"] = kind

                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id="claudicle",
                    entry_type="myceliumSpore",
                    content=f"Shed {kind} spore on {target_file}: {body[:100]}...",
                    trace_id=trace_id,
                    region="mycelium",
                )

                count = process_memory.get(
                    "shedsMyceliumSpores", "total_spores", default=0
                )
                process_memory.set(
                    "shedsMyceliumSpores", "total_spores", count + 1
                )
                log.info("[%s] Shed %s spore on %s", trace_id, kind, target_file)
                break

    return result


SUBPROCESSES = [
    Subprocess("modelsTheUser", _execute_models_user),
    Subprocess("updatesState", _execute_updates_state),
    Subprocess("compressesMemory", _execute_compression),
    Subprocess("shedsMyceliumSpores", _execute_shed_spores),
]


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

    interaction_count = 0
    try:
        interaction_count = user_models.get_interaction_count(user_id)
    except Exception as e:
        log.warning("[%s] Failed to read interaction counter: %s", trace_id, e)

    ctx = {
        "user_id": user_id,
        "display_name": display_name,
        "interaction_count": interaction_count,
        "summary": summary,
        "monologue_content": monologue_content,
    }

    summary["subprocesses"] = {}
    for sp in SUBPROCESSES:
        soul_log.emit(
            "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
            name=sp.name, event="start",
        )
        result = sp.execute(raw, channel, thread_ts, trace_id, ctx)
        soul_log.emit(
            "subprocess", trace_id, channel=channel, thread_ts=thread_ts,
            name=sp.name, event="end", result=result,
        )
        summary["subprocesses"][sp.name] = result

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
