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
from memory import soul_memory, user_models, working_memory
from monitoring import soul_log
import config as _config
from config import DOSSIER_ENABLED, SOUL_NAME, SOUL_STATE_UPDATE_INTERVAL, STIMULUS_VERB_ENABLED

log = logging.getLogger("slack-daemon.soul")

# Trace ID stash — build_prompt generates, parse_response consumes.
# Thread-local to prevent races if concurrent cognitive cycles overlap.
_trace_local = threading.local()


# ---------------------------------------------------------------------------
# Per-step instruction registry — single source of truth for both modes.
# Unified mode assembles these into a numbered block; split mode uses them
# individually as isolated prompts.
# ---------------------------------------------------------------------------

from cognitive_steps import STEP_INSTRUCTIONS

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
    template_vars = {"soul_name": SOUL_NAME}
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
                instructions = onboarding.build_instructions(stage, user_id, SOUL_NAME)
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


def parse_response(
    raw: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    trace_id: Optional[str] = None,
) -> str:
    """Parse XML-tagged cognitive response, store entries in working memory.

    Uses trace_id from build_prompt() if available, otherwise generates new.
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

    # Extract stimulus verb — retroactively narrate the incoming user message
    if STIMULUS_VERB_ENABLED:
        stimulus_verb_raw, _ = extract_tag(raw, "stimulus_verb")
        if stimulus_verb_raw:
            stimulus_verb = stimulus_verb_raw.strip().lower()
            # Sanitize: single word only, no whitespace
            if stimulus_verb and " " not in stimulus_verb:
                working_memory.update_latest_verb(channel, thread_ts, user_id, stimulus_verb)
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="stimulus_verb", verb=stimulus_verb,
                )

    # Extract internal monologue
    monologue_content, monologue_verb = extract_tag(raw, "internal_monologue")
    if monologue_content:
        log.info(
            "[%s] %s %s: %s",
            trace_id, SOUL_NAME, monologue_verb or "thought",
            monologue_content[:100],
        )
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="internalMonologue",
            content=monologue_content,
            verb=monologue_verb or "thought",
            trace_id=trace_id,
        )
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="internalMonologue", verb=monologue_verb or "thought",
            content=monologue_content, content_length=len(monologue_content),
        )

    # Extract external dialogue
    dialogue_content, dialogue_verb = extract_tag(raw, "external_dialogue")
    if dialogue_content:
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="externalDialog",
            content=dialogue_content,
            verb=dialogue_verb or "said",
            trace_id=trace_id,
        )
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="externalDialog", verb=dialogue_verb or "said",
            content=dialogue_content, content_length=len(dialogue_content),
        )

    # Extract user model check (always present now)
    model_check_raw, _ = extract_tag(raw, "user_model_check")
    if model_check_raw:
        check_result = model_check_raw.strip().lower() == "true"
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="mentalQuery",
            content="Should the user model be updated?",
            verb="evaluated",
            metadata={"result": check_result},
            trace_id=trace_id,
        )
        soul_log.emit(
            "decision", trace_id, channel=channel, thread_ts=thread_ts,
            gate="user_model_check", result=check_result,
            content="Should the user model be updated?",
        )

        # Extract user model reflection (pre-digested learnings)
        if check_result:
            reflection_content, _ = extract_tag(raw, "user_model_reflection")
            if reflection_content:
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id="claudicle",
                    entry_type="internalMonologue",
                    content=reflection_content,
                    verb="reflected",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "cognition", trace_id, channel=channel, thread_ts=thread_ts,
                    step="user_model_reflection",
                    content=reflection_content, content_length=len(reflection_content),
                )

            # Extract and apply user model update
            update_content, _ = extract_tag(raw, "user_model_update")
            change_note, _ = extract_tag(raw, "model_change_note")
            if update_content:
                user_models.save(user_id, update_content.strip(), change_note=change_note)
                log.info("[%s] Updated user model for %s: %s", trace_id, user_id, change_note or "no note")
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id="claudicle",
                    entry_type="toolAction",
                    content=f"updated user model for {user_id}",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="user_model_update", target=user_id,
                    change_note=change_note or "",
                )

    # Extract user whispers (sensing the user's inner daimon)
    whispers_content, _ = extract_tag(raw, "user_whispers")
    if whispers_content:
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="daimonicIntuition",
            content=whispers_content,
            verb="sensed",
            metadata={"source": "user_inner_daimon", "target": user_id},
            trace_id=trace_id,
        )
        soul_log.emit(
            "cognition", trace_id, channel=channel, thread_ts=thread_ts,
            step="user_whispers",
            content=whispers_content, content_length=len(whispers_content),
        )

    # Extract dossier check (autonomous entity modeling)
    if DOSSIER_ENABLED:
        dossier_check_raw, _ = extract_tag(raw, "dossier_check")
        if dossier_check_raw and dossier_check_raw.strip().lower() == "true":
            working_memory.add(
                channel=channel,
                thread_ts=thread_ts,
                user_id="claudicle",
                entry_type="mentalQuery",
                content="Should a dossier be created or updated?",
                verb="evaluated",
                metadata={"result": True},
                trace_id=trace_id,
            )
            soul_log.emit(
                "decision", trace_id, channel=channel, thread_ts=thread_ts,
                gate="dossier_check", result=True,
                content="Should a dossier be created or updated?",
            )
            # Extract dossier update — order-independent attribute matching
            dossier_match = re.search(
                r'<dossier_update\s+(?=.*?\bentity="([^"]+)")(?=.*?\btype="([^"]+)")[^>]*>(.*?)</dossier_update>',
                raw, re.DOTALL,
            )
            if dossier_match:
                entity_name = dossier_match.group(1).strip()
                entity_type = dossier_match.group(2).strip().lower()
                if entity_type not in ("person", "subject"):
                    log.warning("Invalid dossier type '%s' for '%s', defaulting to 'subject'", entity_type, entity_name)
                    entity_type = "subject"
                dossier_content = dossier_match.group(3).strip()
                dossier_note, _ = extract_tag(raw, "dossier_change_note")
                user_models.save_dossier(
                    entity_name, dossier_content, entity_type, dossier_note or ""
                )
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id="claudicle",
                    entry_type="toolAction",
                    content=f"created/updated dossier: {entity_name} ({entity_type})",
                    trace_id=trace_id,
                )
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="dossier_update", target=entity_name,
                    change_note=dossier_note or "",
                    detail={"entity_type": entity_type},
                )
            else:
                log.warning(
                    "Dossier check was true but <dossier_update> extraction failed. "
                    "Tag present: %s", "<dossier_update" in raw,
                )

    # Extract soul state check
    state_check_raw, _ = extract_tag(raw, "soul_state_check")
    if state_check_raw:
        state_changed = state_check_raw.strip().lower() == "true"
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="mentalQuery",
            content="Has the soul state changed?",
            verb="evaluated",
            metadata={"result": state_changed},
            trace_id=trace_id,
        )
        soul_log.emit(
            "decision", trace_id, channel=channel, thread_ts=thread_ts,
            gate="soul_state_check", result=state_changed,
            content="Has the soul state changed?",
        )

        if state_changed:
            update_raw, _ = extract_tag(raw, "soul_state_update")
            if update_raw:
                apply_soul_state_update(update_raw, channel, thread_ts, trace_id=trace_id)

    # Increment interaction counter
    user_models.increment_interaction(user_id)

    # Consume all daimonic whispers after successful response processing
    import daimonic
    daimonic.consume_all_whispers()

    # Return external dialogue, or fall back to raw text if parsing failed
    if dialogue_content:
        return dialogue_content.strip()

    # Fallback: strip any XML tags and return whatever text remains
    log.warning("[%s] No <external_dialogue> found, falling back to raw output", trace_id)
    fallback = strip_all_tags(raw).strip()
    return fallback if fallback else "I had a thought but couldn't form a response."


def apply_soul_state_update(
    raw_update: str, channel: str, thread_ts: str,
    trace_id: Optional[str] = None,
) -> None:
    """Parse key: value lines from soul_state_update and persist to soul_memory."""
    valid_keys = set(soul_memory.SOUL_MEMORY_DEFAULTS.keys())
    updated = []

    for line in raw_update.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in valid_keys and value:
            soul_memory.set(key, value)
            updated.append(f"{key}={value}")

    if updated:
        log.info("Soul state updated: %s", ", ".join(updated))
        working_memory.add(
            channel=channel,
            thread_ts=thread_ts,
            user_id="claudicle",
            entry_type="toolAction",
            content=f"updated soul state: {', '.join(updated)}",
            trace_id=trace_id,
        )
        soul_log.emit(
            "memory", trace_id or "", channel=channel, thread_ts=thread_ts,
            action="soul_state_update", target="soul",
            change_note=", ".join(updated),
        )
        # Git-track soul state evolution
        try:
            from config import MEMORY_GIT_ENABLED
            if MEMORY_GIT_ENABLED:
                from memory import git_tracker
                git_tracker.export_soul_state(soul_memory.get_all())
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


def extract_tag(text: str, tag: str) -> tuple[str, Optional[str]]:
    """Extract content and optional verb attribute from an XML tag.

    Returns (content, verb) or ("", None) if not found.
    """
    pattern = rf'<{tag}(?:\s+verb="([^"]*)")?\s*>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        verb = match.group(1) if match.group(1) else None
        content = match.group(2).strip()
        return content, verb
    return "", None


def strip_all_tags(text: str) -> str:
    """Remove all XML tags from text, keeping only content."""
    return re.sub(r"<[^>]+>", "", text)
