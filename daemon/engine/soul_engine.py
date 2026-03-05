"""
Pseudo soul engine for Claudicle.

Wraps every claude -p invocation with structured cognitive steps:
internal monologue, external dialogue, user modeling, and soul state tracking.
Modeled after Kothar's cognitive architecture in the Aldea Soul Engine,
adapted for single-shot subprocess calls.

The prompt instructs Claude to produce XML-tagged output sections.
parse_response() extracts them, stores entries in SQLite working memory
(for metadata gating and analytics), and returns only the external dialogue
to Slack.

Pure cognitive parsing:
- parse_cognitive_response() is a pure function: (raw, config) → (dialogue, CognitiveOutput)
- parse_response() is a thin wrapper that calls the pure parser + apply_output()
- All DB side effects are collected in frozen CognitiveOutput and committed at the boundary

Context assembly (soul.md, skills, soul state, whispers, user model, dossiers)
is handled by the shared context module. This module owns:
- Cognitive step instruction strings
- Unified-mode prompt assembly (context + instructions)
- XML response parsing and side effects
- Working memory storage helpers
"""

import logging
import re
import threading
from typing import Optional

from engine import context
from engine.helpers import extract_tag, extract_tag_with_attrs, strip_all_tags, store_and_emit  # noqa: F401 — re-exported for backward compat
from memory import soul_memory, user_models, working_memory
from memory.snapshot import CognitiveOutput, apply_output
from monitoring import soul_log
import config as _config
from config import DOSSIER_ENABLED, SOUL_STATE_UPDATE_INTERVAL, STIMULUS_VERB_ENABLED

log = logging.getLogger("slack-daemon.soul")

# Trace ID stash — build_prompt generates, parse_response consumes.
# Thread-local to prevent races if concurrent cognitive cycles overlap.
_trace_local = threading.local()


# ---------------------------------------------------------------------------
# Per-step instruction registry — single source of truth for both modes.
# Unified mode assembles these into a numbered block; split mode uses them
# individually as isolated prompts.
# ---------------------------------------------------------------------------

from cognitive_steps import STEP_INSTRUCTIONS, STEP_REGISTRY

# Step ordering and numbering for unified mode assembly
_UNIFIED_STEPS = [
    ("stimulus_verb", "0. Stimulus Narration"),
    ("internal_monologue", "1. Internal Monologue"),
    ("external_dialogue", "2. External Dialogue"),
    ("user_model_check", "3. User Model Check"),
    ("user_model_reflection", "3b. User Model Reflection (only if check was true)"),
    ("user_model_update", "4. User Model Update (only if check was true)"),
    ("user_whispers", "4a. User Whispers (only if model was updated)"),
]

_DOSSIER_STEPS = [
    ("dossier_check", "5. Dossier Check"),
    ("dossier_update", "5a. Dossier Update (only if dossier check was true)"),
]

_SOUL_STATE_STEPS = [
    ("soul_state_check", "6. Soul State Check"),
    ("soul_state_update", "6a. Soul State Update (only if check was true)"),
]


def _assemble_instructions(
    user_id: str = "",
    display_name: Optional[str] = None,
) -> str:
    """Assemble the cognitive instruction block for unified mode.

    Builds numbered sections from STEP_INSTRUCTIONS. Includes dossier
    instructions when enabled and soul state instructions at the configured
    interval.
    """
    steps = list(_UNIFIED_STEPS)
    if not STIMULUS_VERB_ENABLED:
        steps = [(n, h) for n, h in steps if n != "stimulus_verb"]

    if DOSSIER_ENABLED:
        steps.extend(_DOSSIER_STEPS)

    count = context.increment_interaction()
    if count % SOUL_STATE_UPDATE_INTERVAL == 0:
        steps.extend(_SOUL_STATE_STEPS)

    # Template variables available to all step instructions
    template_vars = {"soul_name": _config.SOUL_NAME}
    if user_id:
        template_vars["user"] = display_name or user_id
        model = user_models.get(user_id) or ""
        template_vars["user_model"] = model

    parts = [
        "\n## Cognitive Steps\n",
        "You MUST structure your response using these XML tags in this exact order.",
        "Do NOT include any text outside these tags.\n",
    ]

    for step_name, heading in steps:
        parts.append(f"### {heading}")
        instruction = STEP_INSTRUCTIONS[step_name]
        try:
            instruction = instruction.format(**template_vars)
        except KeyError:
            # Graceful fallback — replace what we can
            for k, v in template_vars.items():
                instruction = instruction.replace(f"{{{k}}}", str(v))
        parts.append(instruction)
        parts.append("")  # blank line between steps

    return "\n".join(parts)


def build_prompt(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> str:
    """Build a cognitive prompt for unified mode.

    Generates a trace_id at the start of the cycle (or uses one provided)
    and threads it through context assembly for decision logging. Stashes
    the trace_id so parse_response() can pick it up if not passed explicitly.
    """
    _trace_local.trace_id = trace_id or working_memory.new_trace_id()

    # Check for first ensoulment onboarding
    if _config.ONBOARDING_ENABLED:
        from engine import onboarding
        if onboarding.needs_onboarding(user_id):
            stage = onboarding.get_stage(channel, thread_ts, user_id)
            if stage < 4:
                instructions = onboarding.build_instructions(stage, user_id, _config.SOUL_NAME)
                return context.build_context(
                    text, user_id, channel, thread_ts, display_name,
                    instructions=instructions,
                    trace_id=_trace_local.trace_id,
                )

    instructions = _assemble_instructions(user_id, display_name)
    return context.build_context(
        text, user_id, channel, thread_ts, display_name,
        instructions=instructions,
        trace_id=_trace_local.trace_id,
    )


def _parse_soul_state_keys(raw_update: str) -> dict[str, str]:
    """Parse key: value lines from soul_state_update into a dict (pure)."""
    valid_keys = set(soul_memory.SOUL_MEMORY_DEFAULTS.keys())
    updates = {}
    for line in raw_update.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in valid_keys and value:
            updates[key] = value
    return updates


def _truncate_for_storage(content: str, step_name: str) -> str:
    """Truncate content to max_store_chars if the step defines a limit."""
    step = STEP_REGISTRY.get(step_name)
    if step and step.max_store_chars > 0 and len(content) > step.max_store_chars:
        return content[:step.max_store_chars] + "..."
    return content


def parse_cognitive_response(
    raw: str,
    user_id: str,
    trace_id: str,
    dossier_enabled: bool = DOSSIER_ENABLED,
    stimulus_verb_enabled: bool = STIMULUS_VERB_ENABLED,
) -> tuple[str, CognitiveOutput]:
    """Pure cognitive parser: extract XML tags → (dialogue, output).

    No DB writes, no soul_log.emit(), no imports of mutable state.
    All side effects are described in the frozen CognitiveOutput.
    Each step chains via copy-on-write with_* methods.

    Returns:
        (dialogue_text, output) — dialogue may be empty if parsing fails.
    """
    output = CognitiveOutput()
    dialogue_text = ""

    # Internal monologue
    monologue_content, monologue_verb = extract_tag(raw, "internal_monologue")
    if monologue_content:
        output = output.with_entry(
            "internalMonologue",
            _truncate_for_storage(monologue_content, "internal_monologue"),
            verb=monologue_verb or "thought",
            trace_id=trace_id,
        )

    # External dialogue
    dialogue_content, dialogue_verb = extract_tag(raw, "external_dialogue")
    if dialogue_content:
        output = output.with_entry(
            "externalDialog", dialogue_content,
            verb=dialogue_verb or "said",
            trace_id=trace_id,
        )
        dialogue_text = dialogue_content.strip()

    # User model check
    model_check_raw, _ = extract_tag(raw, "user_model_check")
    if model_check_raw:
        check_result = model_check_raw.strip().lower() == "true"
        output = output.with_entry(
            "mentalQuery", "Should the user model be updated?",
            verb="evaluated",
            metadata={"result": check_result},
            trace_id=trace_id,
        )

        if check_result:
            # User model reflection
            reflection_content, _ = extract_tag(raw, "user_model_reflection")
            if reflection_content:
                output = output.with_entry(
                    "internalMonologue",
                    _truncate_for_storage(reflection_content, "user_model_reflection"),
                    verb="reflected",
                    trace_id=trace_id,
                )

            # User model update
            update_content, _ = extract_tag(raw, "user_model_update")
            change_note, _ = extract_tag(raw, "model_change_note")
            if update_content:
                output = (output
                    .with_user_model(update_content.strip(), user_id, change_note or "")
                    .with_entry(
                        "toolAction",
                        f"updated user model for {user_id}",
                        trace_id=trace_id,
                    ))

    # User whispers
    whispers_content, _ = extract_tag(raw, "user_whispers")
    if whispers_content:
        output = output.with_entry(
            "daimonicIntuition", whispers_content,
            verb="sensed",
            metadata={"source": "user_inner_daimon", "target": user_id},
            trace_id=trace_id,
        )

    # Dossier check
    if dossier_enabled:
        dossier_check_raw, _ = extract_tag(raw, "dossier_check")
        if dossier_check_raw and dossier_check_raw.strip().lower() == "true":
            output = output.with_entry(
                "mentalQuery", "Should a dossier be created or updated?",
                verb="evaluated",
                metadata={"result": True},
                trace_id=trace_id,
            )
            dossier_match = re.search(
                r'<dossier_update\s+(?=.*?\bentity="([^"]+)")(?=.*?\btype="([^"]+)")[^>]*>(.*?)</dossier_update>',
                raw, re.DOTALL,
            )
            if dossier_match:
                entity_name = dossier_match.group(1).strip()
                entity_type = dossier_match.group(2).strip().lower()
                if entity_type not in ("person", "subject"):
                    entity_type = "subject"
                dossier_content = dossier_match.group(3).strip()
                dossier_note, _ = extract_tag(raw, "dossier_change_note")
                output = (output
                    .with_dossier(entity_name, dossier_content, entity_type, dossier_note or "")
                    .with_entry(
                        "toolAction",
                        f"created/updated dossier: {entity_name} ({entity_type})",
                        trace_id=trace_id,
                    ))

    # Utility steps — brainstorm, decision, instruction
    # These are NOT in _UNIFIED_STEPS; they appear when custom processes
    # compose them into their prompts.
    brainstorm_content, brainstorm_attrs = extract_tag_with_attrs(raw, "brainstorm")
    if brainstorm_content:
        output = output.with_entry(
            "brainstorm", brainstorm_content,
            metadata=brainstorm_attrs,
            trace_id=trace_id,
        )
        brainstorm_step = STEP_REGISTRY.get("brainstorm")
        if brainstorm_step and brainstorm_step.post_process:
            output = brainstorm_step.post_process(raw, output)

    decision_content, decision_attrs = extract_tag_with_attrs(raw, "decision")
    if decision_content:
        output = output.with_entry(
            "decision", decision_content.strip(),
            metadata=decision_attrs,
            trace_id=trace_id,
        )
        decision_step = STEP_REGISTRY.get("decision")
        if decision_step and decision_step.post_process:
            output = decision_step.post_process(raw, output)

    instruction_content, _ = extract_tag(raw, "instruction")
    if instruction_content:
        output = output.with_entry(
            "instruction", instruction_content,
            trace_id=trace_id,
        )

    # Scheduled events — <schedule_event action="..." delay="..." process="...">content</schedule_event>
    # Multiple schedule_event tags may appear in a single response.
    for sched_match in re.finditer(
        r'<schedule_event([^>]*)>(.*?)</schedule_event>', raw, re.DOTALL,
    ):
        sched_attrs = dict(re.findall(r'(\w+)="([^"]*)"', sched_match.group(1)))
        sched_content = sched_match.group(2).strip()
        sched_action = sched_attrs.get("action", "scheduledEvent")
        try:
            sched_delay = float(sched_attrs.get("delay", "0"))
        except (ValueError, TypeError):
            sched_delay = 0
        output = output.with_scheduled_event(
            action=sched_action,
            content=sched_content,
            delay_seconds=sched_delay,
            target_process=sched_attrs.get("process", ""),
        )
        output = output.with_entry(
            "toolAction",
            f"scheduled event: {sched_action} (delay={sched_delay}s)",
            trace_id=trace_id,
        )

    # Soul state check
    state_check_raw, _ = extract_tag(raw, "soul_state_check")
    if state_check_raw:
        state_changed = state_check_raw.strip().lower() == "true"
        output = output.with_entry(
            "mentalQuery", "Has the soul state changed?",
            verb="evaluated",
            metadata={"result": state_changed},
            trace_id=trace_id,
        )
        if state_changed:
            update_raw, _ = extract_tag(raw, "soul_state_update")
            if update_raw:
                output = output.with_soul_state_updates(_parse_soul_state_keys(update_raw))

    # Fallback if no dialogue extracted
    if not dialogue_text:
        fallback = strip_all_tags(raw).strip()
        dialogue_text = fallback if fallback else "I had a thought but couldn't form a response."

    return dialogue_text, output


def parse_response(
    raw: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    trace_id: Optional[str] = None,
) -> str:
    """Parse XML-tagged cognitive response, store entries in working memory.

    Thin wrapper around the pure parse_cognitive_response() — resolves trace_id,
    handles onboarding, calls the pure parser, then commits mutations + logs.
    Returns only the external dialogue text for Slack.
    """
    if trace_id is None:
        trace_id = getattr(_trace_local, 'trace_id', None) or working_memory.new_trace_id()
    _trace_local.trace_id = None

    # Check for onboarding response
    if _config.ONBOARDING_ENABLED:
        from engine import onboarding
        if onboarding.needs_onboarding(user_id):
            stage = onboarding.get_stage(channel, thread_ts, user_id)
            if stage < 4:
                return onboarding.parse_response(
                    raw, stage, user_id, channel, thread_ts, trace_id,
                )

    # --- Pure parse ---
    dialogue_text, output = parse_cognitive_response(raw, user_id, trace_id)

    # --- Side effects at the boundary ---

    # Stimulus verb — update existing row (not a new entry, so handled separately)
    if STIMULUS_VERB_ENABLED:
        stimulus_verb_raw, _ = extract_tag(raw, "stimulus_verb")
        if stimulus_verb_raw:
            sv = stimulus_verb_raw.strip().lower()
            if sv and " " not in sv:
                working_memory.update_latest_verb(channel, thread_ts, user_id, sv)
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="stimulus_verb", verb=sv,
                )

    # Commit frozen output to DB
    apply_output(output, channel, thread_ts)

    # Emit soul_log events for observability (kept outside output — logging, not state)
    _emit_soul_log(raw, trace_id, channel, thread_ts, user_id, output)

    # Increment interaction counter
    user_models.increment_interaction(user_id)

    # Consume all daimonic whispers after successful response processing
    import daimonic
    daimonic.consume_all_whispers()

    # Log monologue for debugging
    monologue_content, monologue_verb = extract_tag(raw, "internal_monologue")
    if monologue_content:
        log.info(
            "[%s] %s %s: %s",
            trace_id, _config.SOUL_NAME, monologue_verb or "thought",
            monologue_content[:100],
        )

    if not dialogue_text or dialogue_text == "I had a thought but couldn't form a response.":
        dialogue_content, _ = extract_tag(raw, "external_dialogue")
        if not dialogue_content:
            log.warning("[%s] No <external_dialogue> found, falling back to raw output", trace_id)

    return dialogue_text


def _emit_soul_log(
    raw: str,
    trace_id: str,
    channel: str,
    thread_ts: str,
    user_id: str,
    output: CognitiveOutput,
) -> None:
    """Emit soul_log events for observability. Not state — kept outside output."""
    # Monologue
    monologue_content, monologue_verb = extract_tag(raw, "internal_monologue")
    if monologue_content:
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="internalMonologue", content=monologue_content,
            content_length=len(monologue_content),
            verb=monologue_verb or "thought",
        )

    # Dialogue
    dialogue_content, dialogue_verb = extract_tag(raw, "external_dialogue")
    if dialogue_content:
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="externalDialog", content=dialogue_content,
            content_length=len(dialogue_content),
            verb=dialogue_verb or "said",
        )

    # User model check
    model_check_raw, _ = extract_tag(raw, "user_model_check")
    if model_check_raw:
        check_result = model_check_raw.strip().lower() == "true"
        soul_log.emit(
            "decision", trace_id, channel=channel, thread_ts=thread_ts,
            gate="user_model_check", result=check_result,
            content="Should the user model be updated?",
        )
        if check_result:
            reflection_content, _ = extract_tag(raw, "user_model_reflection")
            if reflection_content:
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="user_model_reflection", content=reflection_content,
                    content_length=len(reflection_content),
                )
            if output.user_model_update is not None:
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="user_model_update", target=user_id,
                    change_note=output.user_model_change_note or "",
                )

    # Whispers
    whispers_content, _ = extract_tag(raw, "user_whispers")
    if whispers_content:
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="user_whispers", content=whispers_content,
            content_length=len(whispers_content),
        )

    # Dossier
    if DOSSIER_ENABLED:
        dossier_check_raw, _ = extract_tag(raw, "dossier_check")
        if dossier_check_raw and dossier_check_raw.strip().lower() == "true":
            soul_log.emit(
                "decision", trace_id, channel=channel, thread_ts=thread_ts,
                gate="dossier_check", result=True,
                content="Should a dossier be created or updated?",
            )
            for dossier in output.dossier_updates:
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="dossier_update", target=dossier["entity_name"],
                    change_note=dossier.get("change_note", ""),
                    detail={"entity_type": dossier.get("entity_type", "subject")},
                )

    # Soul state
    state_check_raw, _ = extract_tag(raw, "soul_state_check")
    if state_check_raw:
        state_changed = state_check_raw.strip().lower() == "true"
        soul_log.emit(
            "decision", trace_id, channel=channel, thread_ts=thread_ts,
            gate="soul_state_check", result=state_changed,
            content="Has the soul state changed?",
        )
        if state_changed and output.soul_state_updates:
            updated_str = ", ".join(f"{k}={v}" for k, v in output.soul_state_updates)
            soul_log.emit(
                "memory", trace_id, channel=channel, thread_ts=thread_ts,
                action="soul_state_update", target="soul",
                change_note=updated_str,
            )


def apply_soul_state_update(
    raw_update: str, channel: str, thread_ts: str,
    trace_id: Optional[str] = None,
) -> None:
    """Parse key: value lines from soul_state_update and persist to soul_memory.

    Legacy entry point — uses _parse_soul_state_keys() for pure parsing,
    then applies the updates. New code should use parse_cognitive_response()
    which collects soul state updates in CognitiveOutput.
    """
    updates = _parse_soul_state_keys(raw_update)
    for key, value in updates.items():
        soul_memory.set(key, value)

    if updates:
        updated_str = ", ".join(f"{k}={v}" for k, v in updates.items())
        log.info("Soul state updated: %s", updated_str)
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="toolAction",
            content=f"updated soul state: {updated_str}",
            trace_id=trace_id,
        )
        soul_log.emit(
            "memory", trace_id or "", channel=channel, thread_ts=thread_ts,
            action="soul_state_update", target="soul",
            change_note=updated_str,
        )
        # Git-track soul state evolution
        try:
            from config import MEMORY_GIT_ENABLED
            if MEMORY_GIT_ENABLED:
                from memory import git_tracker
                git_tracker.export_soul_state(soul_memory.get_soul_state())
        except Exception as e:
            log.warning("Git memory tracking failed (best-effort): %s", e)


def store_user_message(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    display_name: Optional[str] = None,
) -> None:
    """Store a user message in working memory."""
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=user_id,
        entry_type="userMessage",
        content=text,
        display_name=display_name,
    )


def store_tool_action(
    action: str,
    channel: str,
    thread_ts: str,
) -> None:
    """Store a tool action in working memory (file reads, searches, etc.)."""
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudicle",
        entry_type="toolAction",
        content=action,
    )
