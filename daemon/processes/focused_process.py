"""Focused process — deep work mode.

Activated when emotionalState=focused. Runs a streamlined cognitive
pipeline: skips user model check, uses shorter monologue. Transitions
back to main_process when the topic changes or emotional state shifts.
"""

import logging
from typing import Optional

from engine import context, soul_engine
from engine.process_base import ProcessResult, ProcessTransition
from memory import user_models, working_memory
from memory.snapshot import CognitiveOutput, WorkingMemorySnapshot
import config as _config

log = logging.getLogger("claudicle.processes.focused")

# Focused mode uses a subset of steps — no user model check, no dossier
_FOCUSED_STEPS = [
    ("stimulus_verb", "0. Stimulus Narration"),
    ("internal_monologue", "1. Internal Monologue"),
    ("external_dialogue", "2. External Dialogue"),
    ("soul_state_check", "3. Soul State Check"),
    ("soul_state_update", "3a. Soul State Update (only if check was true)"),
]


async def run(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    snapshot: WorkingMemorySnapshot,
    display_name: Optional[str] = None,
    params: dict | None = None,
) -> ProcessResult:
    """Run focused cognitive pipeline with reduced steps."""
    trace_id = working_memory.new_trace_id()

    # Build focused instruction set (subset of normal steps)
    instructions = _build_focused_instructions(user_id, display_name)
    prompt = context.build_context(
        text, user_id, channel, thread_ts, display_name,
        instructions=instructions,
        trace_id=trace_id,
    )

    from providers import get_provider
    provider = get_provider(_config.DEFAULT_PROVIDER)
    raw = await provider.agenerate(prompt, model=_config.DEFAULT_MODEL or None)

    dialogue, output = soul_engine.parse_cognitive_response(raw, user_id, trace_id)

    # Shared side effects
    user_models.increment_interaction(user_id)
    import daimonic
    daimonic.consume_all_whispers()

    transition = _check_transition(output)

    return ProcessResult(dialogue=dialogue, output=output, transition=transition)


def _build_focused_instructions(
    user_id: str = "",
    display_name: Optional[str] = None,
) -> str:
    """Build a reduced instruction set for focused mode."""
    from processes._shared import build_step_instructions
    return build_step_instructions(
        steps=list(_FOCUSED_STEPS),
        mode_name="Focused Mode",
        intro_lines=[
            "You are in deep focus mode. Keep internal monologue concise (1-2 sentences).",
            "Skip user model updates — focus on the task at hand.",
        ],
        user_id=user_id,
        display_name=display_name,
        filter_stimulus_verb=True,
    )


def _check_transition(output: CognitiveOutput) -> ProcessTransition | None:
    """Transition back to main on topic change or emotional state shift."""
    state_updates = dict(output.soul_state_updates)
    emotional_state = state_updates.get("emotionalState", "")

    # Leave focused mode on non-focused emotional states
    if emotional_state and emotional_state not in ("focused", "engaged"):
        if emotional_state == "frustrated":
            return ProcessTransition(target="frustrated_process")
        return ProcessTransition(target="main_process")

    return None
