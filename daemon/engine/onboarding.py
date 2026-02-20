"""
First ensoulment onboarding—mental process (Open Souls pattern).

When Claudicle encounters a user whose model has onboardingComplete: false,
this module intercepts the normal cognitive pipeline and conducts a multi-turn
interview to learn the user's name, build their model, define Claudicle's
persona for them, and select which skills to activate.

State machine:
  Stage 0 (greeting)  → Learn name
  Stage 1 (primary)   → Ask if primary user → set role
  Stage 2 (persona)   → Define Claudicle's personality
  Stage 3 (skills)    → Select tools/skills
  Complete            → Transition to normal pipeline
"""

import json
import logging
from typing import Optional

from memory import user_models, working_memory
from config import DEFAULT_USER_NAME, SOUL_NAME
from monitoring import soul_log

log = logging.getLogger("claudicle.onboarding")


def needs_onboarding(user_id: str) -> bool:
    """Check if user needs onboarding (onboardingComplete: false in frontmatter)."""
    model = user_models.get(user_id)
    if not model:
        return False
    meta = user_models.parse_frontmatter(model)
    return meta.get("onboardingComplete", "true").lower() == "false"


def get_stage(channel: str, thread_ts: str, user_id: str) -> int:
    """Determine current onboarding stage from working memory entries."""
    entries = working_memory.get_recent(channel, thread_ts, limit=50)
    completed_stages = set()
    for entry in entries:
        if entry.get("entry_type") == "onboardingStep":
            try:
                meta = json.loads(entry["metadata"]) if entry.get("metadata") else {}
                stage = meta.get("stage")
                if stage is not None and isinstance(stage, int):
                    completed_stages.add(stage)
            except (json.JSONDecodeError, TypeError):
                pass
    # Return the next incomplete stage
    for stage in range(4):
        if stage not in completed_stages:
            return stage
    return 4  # all done


def build_instructions(stage: int, user_id: str, soul_name: str = "") -> str:
    """Build onboarding prompt instructions for the current stage."""
    soul_name = soul_name or SOUL_NAME
    from skills.interview import prompts

    if stage == 0:
        return prompts.greeting(soul_name)
    elif stage == 1:
        user_name = user_models.get_user_name(user_id) or "friend"
        return prompts.primary_check(soul_name, user_name)
    elif stage == 2:
        user_name = user_models.get_user_name(user_id) or "friend"
        return prompts.persona(soul_name, user_name)
    elif stage == 3:
        user_name = user_models.get_user_name(user_id) or "friend"
        from skills.interview import catalog
        skills_text = catalog.format_available_skills()
        return prompts.skills_selection(soul_name, user_name, skills_text)
    return ""


def parse_response(
    raw: str,
    stage: int,
    user_id: str,
    channel: str,
    thread_ts: str,
    trace_id: str,
) -> str:
    """Parse onboarding response, update model, advance stage, return dialogue.

    Handles the same side effects as soul_engine.parse_response():
    interaction counting and daimonic whisper consumption.
    """
    from engine.soul_engine import extract_tag, strip_all_tags

    dialogue = ""

    if stage == 0:
        # Extract user's name
        name_raw, _ = extract_tag(raw, "user_name")
        greeting, _ = extract_tag(raw, "onboarding_greeting")
        dialogue = greeting or ""

        if name_raw:
            name = name_raw.strip()
            if name:
                _update_user_name(user_id, name)
                _record_stage(channel, thread_ts, 0, {"name": name}, trace_id)
                soul_log.emit(
                    "memory", trace_id, channel=channel, thread_ts=thread_ts,
                    action="onboarding_name", target=user_id, change_note=name,
                )

    elif stage == 1:
        # Extract primary user designation
        is_primary_raw, _ = extract_tag(raw, "is_primary")
        dialogue_raw, _ = extract_tag(raw, "onboarding_dialogue")
        dialogue = dialogue_raw or ""

        if is_primary_raw:
            is_primary = is_primary_raw.strip().lower() == "yes"
            role = "primary" if is_primary else "standard"
            _set_role(user_id, role)
            _record_stage(channel, thread_ts, 1, {"role": role}, trace_id)
            soul_log.emit(
                "memory", trace_id, channel=channel, thread_ts=thread_ts,
                action="onboarding_primary", target=user_id, change_note=role,
            )

    elif stage == 2:
        # Extract persona preferences
        persona_raw, _ = extract_tag(raw, "persona_notes")
        dialogue_raw, _ = extract_tag(raw, "onboarding_dialogue")
        dialogue = dialogue_raw or ""

        if persona_raw:
            _apply_persona_notes(user_id, persona_raw.strip())
            _record_stage(channel, thread_ts, 2, {"persona": persona_raw.strip()}, trace_id)
            soul_log.emit(
                "memory", trace_id, channel=channel, thread_ts=thread_ts,
                action="onboarding_persona", target=user_id,
            )

    elif stage == 3:
        # Extract skill selections
        skills_raw, _ = extract_tag(raw, "selected_skills")
        dialogue_raw, _ = extract_tag(raw, "onboarding_dialogue")
        dialogue = dialogue_raw or ""

        if skills_raw:
            _record_stage(channel, thread_ts, 3, {"skills": skills_raw.strip()}, trace_id)
            _complete_onboarding(user_id, channel, thread_ts, trace_id)
            soul_log.emit(
                "memory", trace_id, channel=channel, thread_ts=thread_ts,
                action="onboarding_complete", target=user_id,
                change_note=skills_raw.strip(),
            )

    # Fallback: strip tags, return text
    if not dialogue:
        dialogue = strip_all_tags(raw).strip()

    # Shared side effects — must match soul_engine.parse_response() tail
    user_models.increment_interaction(user_id)
    import daimonic
    daimonic.consume_all_whispers()

    return dialogue


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_role(user_id: str, role: str) -> None:
    """Update user model frontmatter with the role."""
    import re as _re
    model = user_models.get(user_id)
    if not model:
        return
    updated = _re.sub(r'role: ".*?"', f'role: "{role}"', model)
    user_models.save(user_id, updated)
    log.info("Onboarding: set role '%s' for %s", role, user_id)


def _update_user_name(user_id: str, name: str) -> None:
    """Update user model frontmatter with the real name."""
    model = user_models.get(user_id)
    if not model:
        return
    updated = model.replace(f'userName: "{DEFAULT_USER_NAME}"', f'userName: "{name}"')
    updated = updated.replace(f'title: "{DEFAULT_USER_NAME}"', f'title: "{name}"')
    updated = updated.replace(f"# {DEFAULT_USER_NAME}", f"# {name}")
    user_models.save(user_id, updated, display_name=name)
    log.info("Onboarding: learned user name '%s' for %s", name, user_id)


def _apply_persona_notes(user_id: str, notes: str) -> None:
    """Append persona notes to the user model's Persona section."""
    model = user_models.get(user_id)
    if not model:
        return
    updated = model.replace(
        "## Persona\nUnknown \u2014 first interaction.",
        f"## Persona\n{notes}",
    )
    user_models.save(user_id, updated)
    log.info("Onboarding: applied persona notes for %s", user_id)


def _record_stage(
    channel: str,
    thread_ts: str,
    stage: int,
    data: dict,
    trace_id: str,
) -> None:
    """Record a completed onboarding stage in working memory."""
    working_memory.add(
        channel=channel,
        thread_ts=thread_ts,
        user_id="claudicle",
        entry_type="onboardingStep",
        content=f"Completed onboarding stage {stage}",
        metadata={"stage": stage, **data},
        trace_id=trace_id,
    )


def _complete_onboarding(
    user_id: str,
    channel: str,
    thread_ts: str,
    trace_id: str,
) -> None:
    """Mark onboarding complete in user model frontmatter."""
    model = user_models.get(user_id)
    if model:
        updated = model.replace("onboardingComplete: false", "onboardingComplete: true")
        user_models.save(user_id, updated)
        log.info("Onboarding complete for %s", user_id)
