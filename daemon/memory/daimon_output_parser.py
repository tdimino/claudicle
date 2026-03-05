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
import time
from typing import Optional

from memory.daimon_memory import DaimonContext
from memory.snapshot import CognitiveOutput, MemoryEntry, apply_output


_LESSON_RE = re.compile(r"^[-*]\s+(.+)$")
_COMM_RE = re.compile(r"^[-*]\s+\[(\w+)\]\s+(?:to|from)\s+(\S+?):\s+(.+)$")


def parse_output(
    raw_output: str,
    ctx: DaimonContext,
) -> CognitiveOutput:
    """Parse subdaimon output into a pure CognitiveOutput (no DB writes).

    Scans for a '## Memory Updates' section, then processes:
    - '### Lessons Learned' — each bullet → MemoryEntry routed to global lessons thread
    - '### Communication Log' — each bullet → MemoryEntry routed to project-scoped thread

    Returns an immutable CognitiveOutput ready for apply_output() at the boundary.
    """
    output = CognitiveOutput()

    # Find the Memory Updates section
    mem_match = re.search(r"##\s+Memory Updates\b", raw_output)
    if mem_match is None:
        return output

    section = raw_output[mem_match.end():]

    # Stop at the next top-level heading (## or #) that isn't a subsection
    next_section = re.search(r"\n##?\s+(?!#)", section)
    if next_section:
        section = section[:next_section.start()]

    current_subsection: Optional[str] = None
    channel = f"daimon:{ctx.agent_name}"

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
                meta = {}
                if ctx.project:
                    meta["source_project"] = ctx.project
                entry = MemoryEntry(
                    entry_type="daimonicIntuition",
                    content=m.group(1),
                    verb="learned",
                    user_id=ctx.agent_name,
                    metadata=meta,
                    region="lessons",
                    target_channel=channel,
                    target_thread_ts=f"{ctx.soul_id}::global",
                    created_at=time.time(),
                )
                output = output.with_raw_entry(entry)

        elif current_subsection == "comms":
            m = _COMM_RE.match(stripped)
            if m:
                direction = m.group(1)
                counterpart = m.group(2)
                content = m.group(3)
                meta = {"direction": direction, "counterpart": counterpart}
                user_id = counterpart if direction == "inbound" else ctx.agent_name
                entry = MemoryEntry(
                    entry_type="toolAction",
                    content=f"[{direction}] {counterpart}: {content}",
                    user_id=user_id,
                    metadata=meta,
                    region="comms",
                    target_channel=channel,
                    target_thread_ts=ctx.thread_ts,
                    created_at=time.time(),
                )
                output = output.with_raw_entry(entry)

    return output


# Deprecated — use parse_output() + apply_output(). Will be removed in a future release.
def parse_and_store(
    raw_output: str,
    ctx: DaimonContext,
) -> dict:
    """Parse subdaimon output and persist memory updates.

    Deprecated: prefer parse_output() for the pure path, then
    apply_output() at the pipeline boundary.
    """
    output = parse_output(raw_output, ctx)
    lessons = sum(1 for e in output.entries if e.region == "lessons")
    comms = sum(1 for e in output.entries if e.region == "comms")

    if not output.is_empty:
        apply_output(output, ctx.channel, ctx.thread_ts)

    return {"lessons_stored": lessons, "comms_stored": comms}
