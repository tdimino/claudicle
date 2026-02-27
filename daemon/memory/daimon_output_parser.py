"""Parse subdaimon output for memory updates.

Subdaimones are read-only (no DB access). They emit structured markdown
that the calling code parses into memory operations. This keeps the
subdaimon's tool permissions minimal while enabling persistent memory.

Output protocol::

    ## Memory Updates

    ### Lessons Learned
    - Pattern: user prefers explicit confirmation before large refactors
    - Insight: Slack threads with >10 messages need compression

    ### Communication Log
    - [outbound] to team-lead: Completed analysis
    - [inbound] from researcher: Found 3 related PRs
"""

import re
from typing import Optional

from memory.daimon_memory import DaimonContext, store_lesson, store_communication


_LESSON_RE = re.compile(r"^[-*]\s+(.+)$")
_COMM_RE = re.compile(r"^[-*]\s+\[(\w+)\]\s+(?:to|from)\s+(\S+?):\s+(.+)$")


def parse_and_store(
    raw_output: str,
    ctx: DaimonContext,
) -> dict:
    """Parse subdaimon output for memory updates and persist them.

    Scans for a '## Memory Updates' section, then processes:
    - '### Lessons Learned' — each bullet stored via store_lesson()
    - '### Communication Log' — each bullet stored via store_communication()

    Returns: {"lessons_stored": int, "comms_stored": int}
    """
    lessons_stored = 0
    comms_stored = 0

    # Find the Memory Updates section
    mem_match = re.search(r"##\s+Memory Updates\b", raw_output)
    if mem_match is None:
        return {"lessons_stored": 0, "comms_stored": 0}

    section = raw_output[mem_match.end():]

    # Stop at the next top-level heading (## or #) that isn't a subsection
    next_section = re.search(r"\n##?\s+(?!#)", section)
    if next_section:
        section = section[:next_section.start()]

    current_subsection: Optional[str] = None

    for line in section.split("\n"):
        stripped = line.strip()

        # Detect subsections
        if re.match(r"###\s+Lessons\s+Learned", stripped, re.IGNORECASE):
            current_subsection = "lessons"
            continue
        elif re.match(r"###\s+Communication\s+Log", stripped, re.IGNORECASE):
            current_subsection = "comms"
            continue
        elif re.match(r"###\s+", stripped):
            current_subsection = None
            continue

        if not stripped:
            continue

        if current_subsection == "lessons":
            m = _LESSON_RE.match(stripped)
            if m:
                store_lesson(
                    ctx.agent_name,
                    m.group(1),
                    soul_id=ctx.soul_id,
                    project=ctx.project,
                )
                lessons_stored += 1

        elif current_subsection == "comms":
            m = _COMM_RE.match(stripped)
            if m:
                direction = m.group(1)
                counterpart = m.group(2)
                content = m.group(3)
                store_communication(ctx, direction, counterpart, content)
                comms_stored += 1

    return {"lessons_stored": lessons_stored, "comms_stored": comms_stored}
