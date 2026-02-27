"""Main process — default cognitive pipeline.

Wraps the existing soul_engine build_prompt/parse_cognitive_response
into the mental process interface. Handles all standard cognitive steps.
Transitions to focused_process on emotionalState=focused, to
frustrated_process on emotionalState=frustrated.
"""

import logging
from typing import Optional

from engine import context, soul_engine
from engine.process_base import ProcessResult, ProcessTransition
from memory import user_models, working_memory
from memory.snapshot import CognitiveOutput, WorkingMemorySnapshot
import config as _config

log = logging.getLogger("claudicle.processes.main")


async def run(
    text: str,
    user_id: str,
    channel: str,
    thread_ts: str,
    snapshot: WorkingMemorySnapshot,
    display_name: Optional[str] = None,
    params: dict | None = None,
) -> ProcessResult:
    """Run the default cognitive pipeline.

    Delegates to soul_engine for prompt building and pure parsing,
    then wraps the result in a ProcessResult with optional transition.
    """
    trace_id = working_memory.new_trace_id()

    # Build prompt via shared context + cognitive instructions
    instructions = soul_engine._assemble_instructions(user_id, display_name)
    prompt = context.build_context(
        text, user_id, channel, thread_ts, display_name,
        instructions=instructions,
        trace_id=trace_id,
    )

    # Call LLM
    from providers import get_provider
    provider = get_provider(_config.DEFAULT_PROVIDER)
    raw = await provider.agenerate(prompt, model=_config.DEFAULT_MODEL or None)

    # Pure parse
    dialogue, output = soul_engine.parse_cognitive_response(raw, user_id, trace_id)

    # Stimulus verb — side effect (updates existing row, not a new entry)
    if _config.STIMULUS_VERB_ENABLED:
        from engine.helpers import extract_tag
        stimulus_verb_raw, _ = extract_tag(raw, "stimulus_verb")
        if stimulus_verb_raw:
            sv = stimulus_verb_raw.strip().lower()
            if sv and " " not in sv:
                working_memory.update_latest_verb(channel, thread_ts, user_id, sv)

    # Emit soul_log events for observability
    soul_engine._emit_soul_log(raw, trace_id, channel, thread_ts, user_id, output)

    # Shared side effects — match soul_engine.parse_response() tail
    user_models.increment_interaction(user_id)
    import daimonic
    daimonic.consume_all_whispers()

    # Check for process transition based on emotional state
    transition = _check_transition(output)

    return ProcessResult(dialogue=dialogue, output=output, transition=transition)


def _check_transition(output: CognitiveOutput) -> ProcessTransition | None:
    """Check if emotional state warrants a process transition."""
    state_updates = dict(output.soul_state_updates)
    emotional_state = state_updates.get("emotionalState", "")

    if emotional_state == "focused":
        return ProcessTransition(target="focused_process")
    elif emotional_state == "frustrated":
        return ProcessTransition(target="frustrated_process")

    return None
