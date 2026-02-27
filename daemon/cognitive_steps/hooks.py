"""Post-process hooks for cognitive steps.

Each hook has the signature: (raw_text: str, output: CognitiveOutput) → CognitiveOutput.
Pure functions — they transform the output via copy-on-write, never touch the DB.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.snapshot import CognitiveOutput


def cap_brainstorm(raw: str, output: CognitiveOutput) -> CognitiveOutput:
    """Truncate brainstorm JSON array to the count attribute's value.

    If <brainstorm count="3"> produces 5 ideas, truncate to 3.
    """
    match = re.search(r'<brainstorm[^>]*count="(\d+)"[^>]*>(.*?)</brainstorm>', raw, re.DOTALL)
    if not match:
        return output
    max_count = int(match.group(1))
    content = match.group(2).strip()
    try:
        ideas = json.loads(content)
        if isinstance(ideas, list) and len(ideas) > max_count:
            ideas = ideas[:max_count]
            entries = list(output.entries)
            for i in range(len(entries) - 1, -1, -1):
                if entries[i].entry_type == "brainstorm":
                    entries[i] = replace(entries[i], content=json.dumps(ideas))
                    break
            return replace(output, entries=tuple(entries))
    except (json.JSONDecodeError, ValueError):
        pass
    return output


def validate_decision(raw: str, output: CognitiveOutput) -> CognitiveOutput:
    """Validate that the chosen decision is in the options list.

    If the chosen option isn't in the options attribute, correct to the first option.
    """
    match = re.search(
        r'<decision[^>]*options="([^"]+)"[^>]*>(.*?)</decision>',
        raw, re.DOTALL,
    )
    if not match:
        return output
    options = [o.strip() for o in match.group(1).split(",")]
    chosen = match.group(2).strip()
    if chosen not in options:
        corrected = options[0]
        entries = list(output.entries)
        for i in range(len(entries) - 1, -1, -1):
            if entries[i].entry_type == "decision":
                entries[i] = replace(
                    entries[i],
                    content=corrected,
                    metadata={**entries[i].metadata, "corrected_from": chosen},
                )
                break
        return replace(output, entries=tuple(entries))
    return output
