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

import context
import soul_log
import soul_memory
import user_models
import working_memory
from config import DOSSIER_ENABLED, SOUL_NAME, SOUL_STATE_UPDATE_INTERVAL

log = logging.getLogger("slack-daemon.soul")

# Trace ID stash — build_prompt generates, parse_response consumes.
# Thread-local to prevent races if concurrent cognitive cycles overlap.
_trace_local = threading.local()


# ---------------------------------------------------------------------------
# Per-step instruction registry — single source of truth for both modes.
# Unified mode assembles these into a numbered block; split mode uses them
# individually as isolated prompts.
# ---------------------------------------------------------------------------

STEP_INSTRUCTIONS = {
    "internal_monologue": """Think before you speak. Choose a verb that fits your current mental state.

<internal_monologue verb="VERB">
Your private thoughts about this message, the user, the context.
This is never shown to the user.
</internal_monologue>

Verb options: thought, mused, pondered, wondered, considered, reflected, entertained, recalled, noticed, weighed""",

    "external_dialogue": """Your response to the user. Choose a verb that fits the tone of your reply.

<external_dialogue verb="VERB">
Your actual response to the user. 2-4 sentences unless the question demands more.
</external_dialogue>

Verb options: said, explained, offered, suggested, noted, observed, replied, interjected, declared, quipped, remarked, detailed, pointed out, corrected""",

    "user_model_check": """Has something significant been learned about this user in this exchange?
Answer with just true or false.

<user_model_check>true or false</user_model_check>""",

    "user_model_update": """You are the daimon who maintains a living model of each person {soul_name} knows.
Rewrite this person's model to reflect what you've learned.
Format your response so that it mirrors the example blueprint shown above,
but you may add new sections as the model matures — the blueprint is
a starting shape, not a cage.

<user_model_update>
The complete, rewritten user model in markdown.
</user_model_update>

<model_change_note>
One sentence: what changed and why.
</model_change_note>""",

    "dossier_check": """Has this exchange involved a person, topic, or subject worth maintaining
a separate dossier for? This is NOT about the user you're talking to
(that's handled above), but about third parties or subjects discussed.

Only answer true if:
- A person was discussed with enough detail to model (not just a passing name)
- A subject was explored with enough depth to warrant its own dossier
- An existing dossier entity has new significant information

<dossier_check>true or false</dossier_check>""",

    "dossier_update": """You are the daimon who maintains {soul_name}'s living dossiers on people and subjects.
Provide a dossier update. Use the entity's name as the title.
If this is a new entity, create a fresh dossier. If existing, rewrite it with
what you've learned. You may add sections freely.

For people: model their persona, expertise, relationship to the user, key ideas.
For subjects: model the domain, key concepts, open questions, connections to other domains.

Include YAML frontmatter with multi-dimensional tags for retrieval:
```yaml
---
title: "Entity Name"
tags:
  concepts: [relevant-concepts]
  people: [related-people]
  domains: [knowledge-domains]
---
```

End the dossier with a flat RAG tag line — comma-separated keywords spanning
all dimensions (names, concepts, places, synonyms, related terms):

```
RAG: entity name, concept1, concept2, related person, domain, ...
```

<dossier_update entity="Entity Name" type="person|subject">
The complete dossier in markdown with frontmatter and RAG tags.
</dossier_update>

<dossier_change_note>
One sentence: what changed and why.
</dossier_change_note>""",

    "soul_state_check": """Has your current project, task, topic, or emotional state changed based on this exchange?
Answer with just true or false.

<soul_state_check>true or false</soul_state_check>""",

    "soul_state_update": """If you answered true above, provide updated values. Only include keys that changed.
Use the format key: value, one per line.

<soul_state_update>
currentProject: project name
currentTask: task description
currentTopic: what we're discussing
emotionalState: neutral/engaged/focused/frustrated/sardonic
conversationSummary: brief rolling summary
</soul_state_update>""",
}

# Step ordering and numbering for unified mode assembly
_UNIFIED_STEPS = [
    ("internal_monologue", "1. Internal Monologue"),
    ("external_dialogue", "2. External Dialogue"),
    ("user_model_check", "3. User Model Check"),
    ("user_model_update", "4. User Model Update (only if check was true)"),
]

_DOSSIER_STEPS = [
    ("dossier_check", "4b. Dossier Check"),
    ("dossier_update", "4c. Dossier Update (only if dossier check was true)"),
]

_SOUL_STATE_STEPS = [
    ("soul_state_check", "5. Soul State Check"),
    ("soul_state_update", "6. Soul State Update (only if check was true)"),
]


def _assemble_instructions() -> str:
    """Assemble the cognitive instruction block for unified mode.

    Builds numbered sections from STEP_INSTRUCTIONS. Includes dossier
    instructions when enabled and soul state instructions at the configured
    interval.
    """
    steps = list(_UNIFIED_STEPS)

    if DOSSIER_ENABLED:
        steps.extend(_DOSSIER_STEPS)

    count = context.increment_interaction()
    if count % SOUL_STATE_UPDATE_INTERVAL == 0:
        steps.extend(_SOUL_STATE_STEPS)

    parts = [
        "\n## Cognitive Steps\n",
        "You MUST structure your response using these XML tags in this exact order.",
        "Do NOT include any text outside these tags.\n",
    ]

    for step_name, heading in steps:
        parts.append(f"### {heading}")
        instruction = STEP_INSTRUCTIONS[step_name]
        if "{soul_name}" in instruction:
            instruction = instruction.format(soul_name=SOUL_NAME)
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

    instructions = _assemble_instructions()
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

        # Extract and apply user model update
        if check_result:
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
                import memory_git
                memory_git.export_soul_state(soul_memory.get_all())
        except Exception as e:
            log.warning("Git memory tracking failed (best-effort): %s", e)


def store_user_message(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
) -> None:
    """Store a user message in working memory."""
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id=user_id,
        entry_type="userMessage",
        content=text,
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
