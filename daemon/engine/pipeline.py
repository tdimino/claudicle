"""
Per-step cognitive routing pipeline for Claudicle.

When PIPELINE_MODE=split, each cognitive step is a separate LLM call
routable to a different provider/model. When PIPELINE_MODE=unified
(default), this module is not used — the existing single-call path
in claude_handler.py handles everything.

Architecture:
    Step 1: monologue  → [context + user_msg + monologue_instructions] → Provider A
    Step 2: dialogue   → [context + monologue_output + dialogue_instructions] → Provider B
    Step 3: model_check → [context + monologue + dialogue + check_instructions] → Provider C
    Step 4: model_update (if check=true) → Provider C
    Step 5: state_check (every Nth turn) → Provider C
    Step 6: state_update (if check=true) → Provider C

Each step receives accumulated outputs from prior steps as a
## Prior Cognitive Steps section with XML tags intact.

Context assembly (soul.md, skills, soul state, whispers, user model, dossiers)
is handled by the shared context module — same as unified mode.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from engine import context, soul_engine
from memory import user_models, working_memory
from monitoring import soul_log
from config import (
    DEFAULT_PROVIDER,
    DEFAULT_MODEL,
    PIPELINE_MODE,
    SOUL_NAME,
    SOUL_STATE_UPDATE_INTERVAL,
    STEP_MODEL,
    STEP_PROVIDER,
)

log = logging.getLogger("claudicle.pipeline")


@dataclass
class PipelineResult:
    """Result from a split-mode pipeline run."""
    dialogue: str = ""
    monologue: str = ""
    monologue_verb: str = ""
    dialogue_verb: str = ""
    model_check: bool = False
    model_reflection: str = ""
    model_update: str = ""
    user_whispers: str = ""
    state_check: bool = False
    state_update: str = ""
    step_outputs: dict = field(default_factory=dict)


def is_split_mode() -> bool:
    """Check if pipeline is in split mode."""
    return PIPELINE_MODE == "split"


def _resolve_provider(step_name: str):
    """Resolve provider for a cognitive step. Falls back to DEFAULT_PROVIDER."""
    from providers import get_provider
    name = STEP_PROVIDER.get(step_name, "") or DEFAULT_PROVIDER
    return get_provider(name)


def _resolve_model(step_name: str) -> str:
    """Resolve model for a cognitive step. Falls back to DEFAULT_MODEL."""
    return STEP_MODEL.get(step_name, "") or DEFAULT_MODEL


def _build_step_prompt(
    ctx: str,
    step_name: str,
    instruction: str,
    prior_outputs: str = "",
    template_vars: dict | None = None,
) -> str:
    """Assemble prompt for a single cognitive step."""
    parts = [ctx]

    if prior_outputs:
        parts.append(f"\n## Prior Cognitive Steps\n\n{prior_outputs}")

    # Apply template variables — always includes soul_name, callers can add more
    vars_ = {"soul_name": SOUL_NAME}
    if template_vars:
        vars_.update(template_vars)
    try:
        instruction = instruction.format(**vars_)
    except KeyError:
        # Graceful fallback if a template var is missing — leave unreplaced
        for k, v in vars_.items():
            instruction = instruction.replace(f"{{{k}}}", str(v))
    parts.append(f"\n## Instructions\n\n{instruction}")

    return "\n".join(parts)


# Per-step instructions — shared with unified mode via soul_engine.STEP_INSTRUCTIONS
_STEP = soul_engine.STEP_INSTRUCTIONS


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_pipeline(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: Optional[str] = None,
) -> PipelineResult:
    """Run the full cognitive pipeline with per-step provider routing.

    Generates a trace_id grouping all working_memory entries from this cycle.
    Each step:
      1. Resolve provider + model for this step
      2. Build step prompt (shared context + prior outputs + step instruction)
      3. Call provider.agenerate()
      4. Extract XML tag from response
      5. Store in working_memory (with trace_id)
      6. Chain output to next step
    """
    count = context.increment_interaction()
    trace_id = working_memory.new_trace_id()

    result = PipelineResult()
    ctx = context.build_context(text, user_id, channel, thread_ts, display_name, trace_id=trace_id)
    prior = ""

    # Step 1: Internal Monologue
    try:
        provider = _resolve_provider("internal_monologue")
        model = _resolve_model("internal_monologue")
        prompt = _build_step_prompt(ctx, "internal_monologue", _STEP["internal_monologue"])
        raw = await provider.agenerate(prompt, model=model)

        content, verb = soul_engine.extract_tag(raw, "internal_monologue")
        if content:
            result.monologue = content
            result.monologue_verb = verb or "thought"
            result.step_outputs["internal_monologue"] = raw
            prior += f"<internal_monologue verb=\"{result.monologue_verb}\">{content}</internal_monologue>\n\n"

            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="internalMonologue",
                content=content, verb=result.monologue_verb,
                trace_id=trace_id,
            )
            soul_log.emit(
                "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                step="internalMonologue", verb=result.monologue_verb,
                content=content, content_length=len(content),
                provider=provider.name, model=model or "default",
            )
            log.info("[%s] Pipeline monologue (%s/%s): %s", trace_id, provider.name, model or "default", content[:80])
    except Exception as e:
        log.error("[%s] Pipeline monologue failed: %s", trace_id, e)

    # Step 2: External Dialogue
    try:
        provider = _resolve_provider("external_dialogue")
        model = _resolve_model("external_dialogue")
        prompt = _build_step_prompt(ctx, "external_dialogue", _STEP["external_dialogue"], prior)
        raw = await provider.agenerate(prompt, model=model)

        content, verb = soul_engine.extract_tag(raw, "external_dialogue")
        if content:
            result.dialogue = content
            result.dialogue_verb = verb or "said"
            result.step_outputs["external_dialogue"] = raw
            prior += f"<external_dialogue verb=\"{result.dialogue_verb}\">{content}</external_dialogue>\n\n"

            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="externalDialog",
                content=content, verb=result.dialogue_verb,
                trace_id=trace_id,
            )
            soul_log.emit(
                "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                step="externalDialog", verb=result.dialogue_verb,
                content=content, content_length=len(content),
                provider=provider.name, model=model or "default",
            )
            log.info("[%s] Pipeline dialogue (%s/%s): %s", trace_id, provider.name, model or "default", content[:80])
    except Exception as e:
        log.error("[%s] Pipeline dialogue failed: %s", trace_id, e)

    # Step 3: User Model Check
    try:
        provider = _resolve_provider("user_model_check")
        model = _resolve_model("user_model_check")
        prompt = _build_step_prompt(ctx, "user_model_check", _STEP["user_model_check"], prior)
        raw = await provider.agenerate(prompt, model=model)

        content, _ = soul_engine.extract_tag(raw, "user_model_check")
        if content:
            result.model_check = content.strip().lower() == "true"
            result.step_outputs["user_model_check"] = raw

            working_memory.add(
                channel=channel, thread_ts=thread_ts,
                user_id="claudicle", entry_type="mentalQuery",
                content="Should the user model be updated?",
                verb="evaluated",
                metadata={"result": result.model_check},
                trace_id=trace_id,
            )
            soul_log.emit(
                "decision", trace_id, channel=channel, thread_ts=thread_ts,
                gate="user_model_check", result=result.model_check,
                content="Should the user model be updated?",
                provider=provider.name, model=model or "default",
            )
    except Exception as e:
        log.error("[%s] Pipeline model_check failed: %s", trace_id, e)

    # Step 3b: User Model Reflection (conditional — articulate what was learned)
    if result.model_check:
        try:
            provider = _resolve_provider("user_model_reflection")
            model = _resolve_model("user_model_reflection")
            prompt = _build_step_prompt(ctx, "user_model_reflection", _STEP["user_model_reflection"], prior)
            raw = await provider.agenerate(prompt, model=model)

            content, _ = soul_engine.extract_tag(raw, "user_model_reflection")
            if content:
                result.model_reflection = content
                result.step_outputs["user_model_reflection"] = raw
                prior += f"<user_model_reflection>{content}</user_model_reflection>\n\n"

                working_memory.add(
                    channel=channel, thread_ts=thread_ts,
                    user_id="claudicle", entry_type="internalMonologue",
                    content=content, verb="reflected",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="user_model_reflection",
                    content=content, content_length=len(content),
                    provider=provider.name, model=model or "default",
                )
                log.info("[%s] Pipeline model reflection (%s/%s): %s", trace_id, provider.name, model or "default", content[:80])
        except Exception as e:
            log.error("[%s] Pipeline model_reflection failed: %s", trace_id, e)

    # Step 4: User Model Update (conditional)
    if result.model_check:
        try:
            provider = _resolve_provider("user_model_update")
            model = _resolve_model("user_model_update")
            prompt = _build_step_prompt(ctx, "user_model_update", _STEP["user_model_update"], prior)
            raw = await provider.agenerate(prompt, model=model)

            content, _ = soul_engine.extract_tag(raw, "user_model_update")
            if content:
                result.model_update = content
                result.step_outputs["user_model_update"] = raw
                user_models.save(user_id, content.strip())
                log.info("[%s] Pipeline updated user model for %s", trace_id, user_id)

                working_memory.add(
                    channel=channel, thread_ts=thread_ts,
                    user_id="claudicle", entry_type="toolAction",
                    content=f"updated user model for {user_id}",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="user_model_update", target=user_id,
                    change_note=content.strip()[:200],
                    provider=provider.name, model=model or "default",
                )
        except Exception as e:
            log.error("[%s] Pipeline model_update failed: %s", trace_id, e)

    # Step 4a: User Whispers — sense the user's inner daimon
    if result.model_check and result.model_update:
        try:
            provider = _resolve_provider("user_whispers")
            model = _resolve_model("user_whispers")
            current_model = user_models.get(user_id) or ""
            whisper_name = display_name or user_id
            prompt = _build_step_prompt(ctx, "user_whispers", _STEP["user_whispers"], prior,
                                        template_vars={"user": whisper_name, "user_model": current_model})
            raw = await provider.agenerate(prompt, model=model)

            content, _ = soul_engine.extract_tag(raw, "user_whispers")
            if content:
                result.user_whispers = content
                result.step_outputs["user_whispers"] = raw

                working_memory.add(
                    channel=channel, thread_ts=thread_ts,
                    user_id="claudicle", entry_type="daimonicIntuition",
                    content=content, verb="sensed",
                    metadata={"source": "user_inner_daimon", "target": user_id},
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="user_whispers",
                    content=content, content_length=len(content),
                    provider=provider.name, model=model or "default",
                )
                log.info("[%s] Pipeline user whispers (%s/%s): %s", trace_id, provider.name, model or "default", content[:80])
        except Exception as e:
            log.error("[%s] Pipeline user_whispers failed: %s", trace_id, e)

    # Step 5: Soul State Check (periodic)
    if count % SOUL_STATE_UPDATE_INTERVAL == 0:
        try:
            provider = _resolve_provider("soul_state_check")
            model = _resolve_model("soul_state_check")
            prompt = _build_step_prompt(ctx, "soul_state_check", _STEP["soul_state_check"], prior)
            raw = await provider.agenerate(prompt, model=model)

            content, _ = soul_engine.extract_tag(raw, "soul_state_check")
            if content:
                result.state_check = content.strip().lower() == "true"
                result.step_outputs["soul_state_check"] = raw

                working_memory.add(
                    channel=channel, thread_ts=thread_ts,
                    user_id="claudicle", entry_type="mentalQuery",
                    content="Has the soul state changed?",
                    verb="evaluated",
                    metadata={"result": result.state_check},
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "decision", trace_id, channel=channel, thread_ts=thread_ts,
                    gate="soul_state_check", result=result.state_check,
                    content="Has the soul state changed?",
                    provider=provider.name, model=model or "default",
                )
        except Exception as e:
            log.error("[%s] Pipeline state_check failed: %s", trace_id, e)

        # Step 6: Soul State Update (conditional)
        if result.state_check:
            try:
                provider = _resolve_provider("soul_state_update")
                model = _resolve_model("soul_state_update")
                prompt = _build_step_prompt(ctx, "soul_state_update", _STEP["soul_state_update"], prior)
                raw = await provider.agenerate(prompt, model=model)

                content, _ = soul_engine.extract_tag(raw, "soul_state_update")
                if content:
                    result.state_update = content
                    result.step_outputs["soul_state_update"] = raw
                    soul_engine.apply_soul_state_update(content, channel, thread_ts, trace_id=trace_id)
                    log.info("[%s] Pipeline updated soul state", trace_id)
            except Exception as e:
                log.error("[%s] Pipeline state_update failed: %s", trace_id, e)

    # Increment user interaction count
    user_models.increment_interaction(user_id)

    # Fallback if dialogue extraction failed
    if not result.dialogue:
        result.dialogue = "I had a thought but couldn't form a response."

    return result
