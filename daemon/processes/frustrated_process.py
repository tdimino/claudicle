"""Frustrated process — sardonic/terse response mode.

Activated when emotionalState=frustrated. Uses shorter monologue,
1-2 sentence responses, and faster soul state checks. Transitions
back to main_process when emotional state returns to neutral/engaged.
"""

import logging
from typing import Optional

from engine import context, soul_engine
from engine.process_base import ProcessResult, ProcessTransition
from memory import user_models, working_memory
from memory.snapshot import CognitiveOutput, WorkingMemorySnapshot
import config as _config

log = logging.getLogger("claudicle.processes.frustrated")

_FRUSTRATED_STEPS = [
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
    """Run frustrated cognitive pipeline with terse output."""
    trace_id = working_memory.new_trace_id()

    instructions = _build_frustrated_instructions(user_id, display_name)
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


def _build_frustrated_instructions(
    user_id: str = "",
    display_name: Optional[str] = None,
) -> str:
    """Build terse instruction set for frustrated mode."""
    from processes._shared import build_step_instructions
    return build_step_instructions(
        steps=list(_FRUSTRATED_STEPS),
        mode_name="Frustrated Mode",
        intro_lines=[
            "You are frustrated. Keep monologue to 1 sentence.",
            "Keep dialogue to 1-2 sentences. Be direct, sardonic if warranted.",
            "Check soul state every turn — you want to know when to calm down.",
        ],
        user_id=user_id,
        display_name=display_name,
        filter_stimulus_verb=False,
    )


def _check_transition(output: CognitiveOutput) -> ProcessTransition | None:
    """Transition back to main when frustration subsides."""
    state_updates = dict(output.soul_state_updates)
    emotional_state = state_updates.get("emotionalState", "")

    if emotional_state in ("neutral", "engaged"):
        return ProcessTransition(target="main_process")
    elif emotional_state == "focused":
        return ProcessTransition(target="focused_process")

    return None
