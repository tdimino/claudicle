"""Shared instruction builder for mental processes.

Maps to Open Souls' Memory Integrator pattern: one shared core context
builder with process-specific configuration. Each mental process calls
this with its step list and intro text.
"""

from typing import Optional

import config as _config
from cognitive_steps import STEP_INSTRUCTIONS


def build_step_instructions(
    steps: list[tuple[str, str]],
    mode_name: str,
    intro_lines: list[str],
    user_id: str = "",
    display_name: Optional[str] = None,
    filter_stimulus_verb: bool = False,
) -> str:
    """Build instruction block from a step list and intro text.

    Shared logic extracted from focused_process and frustrated_process.
    Template vars, format loop, join — all DRY.
    """
    if filter_stimulus_verb and not _config.STIMULUS_VERB_ENABLED:
        steps = [(n, h) for n, h in steps if n != "stimulus_verb"]

    template_vars: dict[str, str] = {"soul_name": _config.SOUL_NAME}
    if user_id:
        template_vars["user"] = display_name or user_id

    parts = [f"\n## Cognitive Steps ({mode_name})\n"]
    parts.extend(intro_lines)
    parts.append("You MUST structure your response using these XML tags in this exact order.\n")

    for step_name, heading in steps:
        parts.append(f"### {heading}")
        instruction = STEP_INSTRUCTIONS[step_name]
        try:
            instruction = instruction.format(**template_vars)
        except KeyError:
            for k, v in template_vars.items():
                instruction = instruction.replace(f"{{{k}}}", str(v))
        parts.append(instruction)
        parts.append("")

    return "\n".join(parts)
