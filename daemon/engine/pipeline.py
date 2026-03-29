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

Gate steps (user_model_check, soul_state_check, dossier_check) receive minimal
context via _build_gate_context() — only the exchange and the specific memory
they check. This reduces gate prompt tokens ~60-70% vs full context, enabling
cost-effective routing to cheap models (e.g. Kimi-K2 on Groq).

Memory discard (Open Souls pattern): when a gate returns false, the raw LLM
reasoning is discarded from step_outputs. Only the boolean result is stored.

Side effects are collected in frozen CognitiveOutput and committed at the boundary
via apply_output() — same pattern as unified mode's parse_cognitive_response().
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from engine import context, soul_engine
from engine.helpers import extract_tag
from memory import soul_memory, user_models, working_memory
from memory.snapshot import CognitiveOutput, apply_output
from monitoring import soul_log
from providers import ToolCapableProvider
import config

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
    return config.PIPELINE_MODE == "split"


def _resolve_provider(step_name: str, step_provider: str = ""):
    """Resolve provider for a cognitive step.

    Fallback chain: CognitiveStep.provider → config.STEP_PROVIDER[name] → DEFAULT_PROVIDER.
    """
    from providers import get_provider
    name = step_provider or config.STEP_PROVIDER.get(step_name, "") or config.DEFAULT_PROVIDER
    return get_provider(name)


def _resolve_model(step_name: str, step_model: str = "") -> str:
    """Resolve model for a cognitive step.

    Fallback chain: CognitiveStep.model → config.STEP_MODEL[name] → DEFAULT_MODEL.
    """
    return step_model or config.STEP_MODEL.get(step_name, "") or config.DEFAULT_MODEL


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
    vars_ = {"soul_name": config.SOUL_NAME}
    if template_vars:
        vars_.update(template_vars)
    try:
        instruction = instruction.format(**vars_)
    except KeyError as missing:
        log.warning("Template var %s missing in step %s; using partial replacement", missing, step_name)
        for k, v in vars_.items():
            instruction = instruction.replace(f"{{{k}}}", str(v))
    parts.append(f"\n## Instructions\n\n{instruction}")

    return "\n".join(parts)


# Per-step instructions — shared with unified mode via STEP_INSTRUCTIONS
_STEP = soul_engine.STEP_INSTRUCTIONS

# Step registry — CognitiveStep dataclass instances (for tool lookup)
from cognitive_steps import STEP_REGISTRY as _STEP_REGISTRY

# Gate steps — boolean checks that benefit from stripped context
_GATE_STEPS = {"user_model_check", "soul_state_check", "dossier_check"}


def _build_gate_context(
    user_message: str,
    display_name: str,
    prior_outputs: str,
    step_name: str,
    user_id: str = "",
) -> str:
    """Build minimal context for gate steps (boolean checks).

    Gate steps only evaluate a boolean — they don't need full soul.md,
    skills, dossiers, or whispers. Stripping irrelevant context reduces
    tokens ~60-70% per gate call when routed to a cheap model.

    Maps to Open Souls pattern: mentalQuery receives only the regions
    relevant to its evaluation, not the full WorkingMemory.
    """
    parts = []

    # Step-specific context — only the memory this gate checks
    if step_name == "user_model_check":
        model_md = user_models.get(user_id) or ""
        if model_md:
            parts.append(f"## Current User Model\n\n{model_md}")
    elif step_name == "soul_state_check":
        state_text = soul_memory.format_for_prompt()
        if state_text:
            parts.append(state_text)

    # The exchange — user message + prior cognitive outputs
    name_label = display_name or user_id
    parts.append(f"## Exchange\n\n**{name_label}**: {user_message}")
    if prior_outputs:
        parts.append(f"\n## Cognitive Outputs\n\n{prior_outputs}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Generic step runner — DRYs the repetitive per-step boilerplate
# ---------------------------------------------------------------------------

async def _run_step(
    step_name: str,
    xml_tag: str,
    ctx: str,
    prior: str,
    trace_id: str,
    template_vars: dict | None = None,
    step_model: str = "",
    step_provider: str = "",
) -> tuple[str, Optional[str], str]:
    """Run a single cognitive step: resolve provider, call LLM, extract tag.

    Returns (content, verb, raw_output). All empty strings on failure.
    Pure w.r.t. memory — no DB writes here.

    step_model/step_provider: per-step overrides from CognitiveStep dataclass.
    Fallback: step override → config dict → global default.
    """
    try:
        provider = _resolve_provider(step_name, step_provider)
        model = _resolve_model(step_name, step_model)

        # Check for tool-augmented step
        step_def = _STEP_REGISTRY.get(step_name)
        if (
            step_def
            and step_def.tools
            and config.TOOL_AUGMENTED_STEPS_ENABLED
            and isinstance(provider, ToolCapableProvider)
        ):
            return await _run_step_with_tools(
                step_name, xml_tag, ctx, prior, trace_id,
                step_def, provider, model, template_vars,
            )

        prompt = _build_step_prompt(ctx, step_name, _STEP[step_name], prior, template_vars)
        raw = await provider.agenerate(prompt, model=model)
        content, verb = extract_tag(raw, xml_tag)
        if content:
            log.info("[%s] Pipeline %s (%s/%s): %s", trace_id, step_name, provider.name, model or "default", content[:80])
        return content, verb, raw
    except Exception as e:
        log.error("[%s] Pipeline %s failed: %s", trace_id, step_name, e, exc_info=True)
        return "", None, ""


async def _run_step_with_tools(
    step_name: str,
    xml_tag: str,
    ctx: str,
    prior: str,
    trace_id: str,
    step_def,
    provider: ToolCapableProvider,
    model: str,
    template_vars: dict | None = None,
) -> tuple[str, Optional[str], str]:
    """Run a cognitive step with tool-call support (multi-turn loop).

    The LLM can call tools mid-reasoning. Tool results are injected as
    transient context — they never enter WorkingMemory or CognitiveOutput.
    After max_tool_rounds or when the LLM produces end_turn, the final
    text is extracted via the standard XML tag parser.
    """
    prompt = _build_step_prompt(ctx, step_name, _STEP[step_name], prior, template_vars)

    # Build tool definitions from step's ToolSpec list
    tool_defs = [t.to_anthropic_tool() for t in step_def.tools]
    tool_handlers = {t.name: t.handler for t in step_def.tools}

    # Initial message
    messages = [{"role": "user", "content": prompt}]
    max_rounds = step_def.max_tool_rounds or config.TOOL_MAX_ROUNDS
    accumulated_text = ""
    round_num = 0

    for round_num in range(max_rounds + 1):
        # On final round, strip tools to force text-only response
        active_tools = tool_defs if round_num < max_rounds else []

        try:
            response = await asyncio.wait_for(
                provider.agenerate_with_tools(
                    messages=messages,
                    tools=active_tools,
                    model=model,
                ),
                timeout=config.TOOL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.warning("[%s] Tool step %s timed out after %ds", trace_id, step_name, config.TOOL_TIMEOUT_SECONDS)
            break

        stop_reason = response.get("stop_reason", "end_turn")
        content_blocks = response.get("content", [])

        # Collect text from this response
        for block in content_blocks:
            if block.get("type") == "text":
                accumulated_text += block.get("text", "")

        # If no tool calls, we're done
        if stop_reason != "tool_use":
            break

        # Execute tool calls and build result messages
        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
        if not tool_use_blocks:
            break

        # Append assistant message with tool_use blocks
        messages.append({"role": "assistant", "content": content_blocks})

        # Execute each tool and build results
        tool_results = []
        for tool_block in tool_use_blocks:
            tool_name = tool_block.get("name", "")
            tool_input = tool_block.get("input", {})
            tool_id = tool_block.get("id", str(uuid.uuid4()))

            handler = tool_handlers.get(tool_name)
            if handler:
                try:
                    result = await asyncio.to_thread(handler, **tool_input)
                    log.info(
                        "[%s] Tool %s called in %s: %s",
                        trace_id, tool_name, step_name, result[:80],
                    )
                except Exception as e:
                    log.error(
                        "[%s] Tool handler %s raised in %s: %s",
                        trace_id, tool_name, step_name, e, exc_info=True,
                    )
                    result = f"Tool error: {tool_name} is temporarily unavailable."
            else:
                result = f"Unknown tool: {tool_name}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    # Extract XML tag from accumulated text
    content, verb = extract_tag(accumulated_text, xml_tag)
    if content:
        log.info(
            "[%s] Pipeline %s (tools, %s/%s, %d rounds): %s",
            trace_id, step_name, provider.name, model or "default",
            round_num + 1, content[:80],
        )
    return content, verb, accumulated_text


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
    Side effects are collected in frozen CognitiveOutput via copy-on-write
    and committed at the boundary via apply_output().
    """
    count = context.increment_interaction()
    trace_id = working_memory.new_trace_id()

    result = PipelineResult()
    output = CognitiveOutput()
    ctx = context.build_context(text, user_id, channel, thread_ts, display_name, trace_id=trace_id)
    prior = ""

    # Step 1: Internal Monologue
    content, verb, raw = await _run_step("internal_monologue", "internal_monologue", ctx, prior, trace_id)
    if content:
        result.monologue = content
        result.monologue_verb = verb or "thought"
        result.step_outputs["internal_monologue"] = raw
        prior += f'<internal_monologue verb="{result.monologue_verb}">{content}</internal_monologue>\n\n'
        output = output.with_entry("internalMonologue", content, verb=result.monologue_verb, trace_id=trace_id)

    # Step 1b: Mycelium Context (conditional — only if file notes in context)
    from engine.mycelium_bridge import MYCELIUM_HEADER
    if MYCELIUM_HEADER in ctx:
        content, verb, raw = await _run_step("mycelium_context", "mycelium_context", ctx, prior, trace_id)
        if content and len(content) > 50 and not re.search(r'\bno\b.*\bappl', content.lower()):
            result.step_outputs["mycelium_context"] = raw
            prior += f"<mycelium_context>{content}</mycelium_context>\n\n"
            output = output.with_entry("myceliumContext", content, verb=verb or "considered", trace_id=trace_id)

    # Step 2: External Dialogue
    content, verb, raw = await _run_step("external_dialogue", "external_dialogue", ctx, prior, trace_id)
    if content:
        result.dialogue = content
        result.dialogue_verb = verb or "said"
        result.step_outputs["external_dialogue"] = raw
        prior += f'<external_dialogue verb="{result.dialogue_verb}">{content}</external_dialogue>\n\n'
        output = output.with_entry("externalDialog", content, verb=result.dialogue_verb, trace_id=trace_id)

    # Step 3: User Model Check — minimal context for gate step
    gate_ctx = _build_gate_context(text, display_name or user_id, prior, "user_model_check", user_id)
    content, _, raw = await _run_step("user_model_check", "user_model_check", gate_ctx, "", trace_id)
    if content:
        result.model_check = content.strip().lower() == "true"
        # Memory discard: only retain raw LLM output when gate passes (Open Souls pattern)
        if result.model_check:
            result.step_outputs["user_model_check"] = raw
        output = output.with_entry("mentalQuery", "Should the user model be updated?",
                                   verb="evaluated", metadata={"result": result.model_check}, trace_id=trace_id)

    # Step 3b: User Model Reflection (conditional)
    if result.model_check:
        content, _, raw = await _run_step("user_model_reflection", "user_model_reflection", ctx, prior, trace_id)
        if content:
            result.model_reflection = content
            result.step_outputs["user_model_reflection"] = raw
            prior += f"<user_model_reflection>{content}</user_model_reflection>\n\n"
            output = output.with_entry("internalMonologue", content, verb="reflected", trace_id=trace_id)

    # Step 4: User Model Update (conditional)
    if result.model_check:
        content, _, raw = await _run_step("user_model_update", "user_model_update", ctx, prior, trace_id)
        if content:
            result.model_update = content
            result.step_outputs["user_model_update"] = raw
            output = (output
                .with_user_model(content.strip(), user_id)
                .with_entry("toolAction", f"updated user model for {user_id}", trace_id=trace_id))

    # Step 4a: User Whispers (conditional — after model update)
    if result.model_check and result.model_update:
        current_model = user_models.get(user_id) or ""
        whisper_name = display_name or user_id
        content, _, raw = await _run_step(
            "user_whispers", "user_whispers", ctx, prior, trace_id,
            template_vars={"user": whisper_name, "user_model": current_model},
        )
        if content:
            result.user_whispers = content
            result.step_outputs["user_whispers"] = raw
            output = output.with_entry("daimonicIntuition", content, verb="sensed",
                                       metadata={"source": "user_inner_daimon", "target": user_id}, trace_id=trace_id)

    # Step 5: Soul State Check (periodic) — minimal context for gate step
    if count % config.SOUL_STATE_UPDATE_INTERVAL == 0:
        gate_ctx = _build_gate_context(text, display_name or user_id, prior, "soul_state_check")
        content, _, raw = await _run_step("soul_state_check", "soul_state_check", gate_ctx, "", trace_id)
        if content:
            result.state_check = content.strip().lower() == "true"
            # Memory discard: only retain raw LLM output when gate passes
            if result.state_check:
                result.step_outputs["soul_state_check"] = raw
            output = output.with_entry("mentalQuery", "Has the soul state changed?",
                                       verb="evaluated", metadata={"result": result.state_check}, trace_id=trace_id)

        # Step 6: Soul State Update (conditional)
        if result.state_check:
            content, _, raw = await _run_step("soul_state_update", "soul_state_update", ctx, prior, trace_id)
            if content:
                result.state_update = content
                result.step_outputs["soul_state_update"] = raw
                output = output.with_soul_state_updates(soul_engine._parse_soul_state_keys(content))

    # --- Boundary: commit frozen output to DB ---
    apply_output(output, channel, thread_ts)

    # Increment user interaction count
    user_models.increment_interaction(user_id)

    # Fallback if dialogue extraction failed
    if not result.dialogue:
        result.dialogue = "I had a thought but couldn't form a response."

    return result
