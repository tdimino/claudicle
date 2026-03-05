"""
Context compaction for the Claudicle cognitive pipeline.

Sits between raw data and build_context(), applying token-budget-aware
compaction to every context layer. Inspired by the Open Souls paradigm's
withOnlyRegions and postProcess patterns.

Three compaction targets:
    1. Soul.md — priority-annotated sections (core/extended/full)
    2. User models — tiered extraction (core portrait / extended / full)
    3. Dynamic budget allocation — per-channel profiles with surplus reallocation

Feature-flagged via COMPACTION_ENABLED (default: False). When disabled,
all compact_* functions return their input unchanged.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("claudicle.compaction")

# ---------------------------------------------------------------------------
# Priority annotations in soul.md
#
# Each ## heading can have an HTML comment declaring its priority tier:
#   ## Persona <!-- priority: core -->
#   ## Daimons <!-- priority: extended -->
#
# Tiers: core (always included), extended (included if budget allows),
#        full (only in terminal/generous budgets). Unlabeled = extended.
# ---------------------------------------------------------------------------

_PRIORITY_RE = re.compile(
    r"^(##\s+.+?)\s*<!--\s*priority:\s*(core|extended|full)\s*-->\s*$",
    re.MULTILINE,
)


def _parse_soul_sections(text: str) -> list[dict]:
    """Parse soul.md into sections with priority annotations.

    Returns list of dicts: {heading, priority, content, char_count}.
    Content before the first heading is treated as priority "core" (the title).
    """
    lines = text.split("\n")
    sections: list[dict] = []
    current_heading = ""
    current_priority = "core"  # pre-heading content is always core
    current_lines: list[str] = []

    for line in lines:
        m = _PRIORITY_RE.match(line)
        if m:
            # Save previous section
            if current_lines or current_heading:
                content = "\n".join(current_lines)
                sections.append({
                    "heading": current_heading,
                    "priority": current_priority,
                    "content": content,
                    "char_count": len(content),
                })
            # Start new section — strip the annotation from the heading line
            current_heading = m.group(1).strip()
            current_priority = m.group(2)
            current_lines = [current_heading]
        elif line.startswith("## "):
            # Heading without annotation — default to "extended"
            if current_lines or current_heading:
                content = "\n".join(current_lines)
                sections.append({
                    "heading": current_heading,
                    "priority": current_priority,
                    "content": content,
                    "char_count": len(content),
                })
            current_heading = line.strip()
            current_priority = "extended"
            current_lines = [current_heading]
        else:
            current_lines.append(line)

    # Final section
    if current_lines or current_heading:
        content = "\n".join(current_lines)
        sections.append({
            "heading": current_heading,
            "priority": current_priority,
            "content": content,
            "char_count": len(content),
        })

    return sections


def compact_soul(text: str, budget: int, channel: str = "") -> str:
    """Compact soul.md to fit within a character budget.

    Priority order: core sections first, then extended, then full.
    Sections within each tier are kept in document order.

    Args:
        text: Full soul.md content.
        budget: Maximum character count. 0 = no limit.
        channel: Channel hint (unused for now, reserved for channel-specific overrides).

    Returns:
        Compacted soul.md text.
    """
    if budget <= 0:
        return text

    if len(text) <= budget:
        return text

    sections = _parse_soul_sections(text)
    if not sections:
        return text[:budget]

    # Add sections by priority tier, respecting budget
    result_parts: list[str] = []
    total = 0

    for tier in ("core", "extended", "full"):
        for section in sections:
            if section["priority"] != tier:
                continue
            needed = section["char_count"] + 1  # +1 for joining newline
            if total + needed <= budget:
                result_parts.append(section["content"])
                total += needed

    return "\n".join(result_parts) if result_parts else text[:budget]


# ---------------------------------------------------------------------------
# User model tiered extraction
#
# Graduates from the binary Samantha-Dreams gate (inject/don't-inject) to
# 3 tiers of user model detail:
#   Tier 1 (~350 tokens): Persona + Speaking Style + Conversational Context + Worldview
#   Tier 2 (+200-400 tokens): + Interests & Domains + Working Patterns + Most Potent Memories
#   Tier 3: Full model (for user model update steps)
#
# Section matching is case-insensitive heading detection.
# ---------------------------------------------------------------------------

# Sections to include at each tier (heading substrings, case-insensitive)
_TIER_1_SECTIONS = {
    "persona", "worldview", "speaking style", "communication style",
    "conversational context", "rapport",
}

_TIER_2_SECTIONS = _TIER_1_SECTIONS | {
    "interests", "domains", "working patterns", "expertise",
    "most potent memories", "notes",
}


def _extract_model_sections(model_md: str, allowed: set[str]) -> str:
    """Extract sections from a user model markdown whose headings match allowed set."""
    lines = model_md.split("\n")
    result_lines: list[str] = []
    include = True  # Include pre-heading content (title, etc.)

    for line in lines:
        # Check if this is a ## heading
        if line.startswith("## "):
            heading_text = line.lstrip("#").strip().lower()
            include = any(kw in heading_text for kw in allowed)

        if include:
            result_lines.append(line)

    return "\n".join(result_lines).strip()


def compact_user_model(model_md: str, tier: int = 1, budget: int = 0) -> str:
    """Compact a user model to the requested tier.

    Args:
        model_md: Full user model markdown.
        tier: 1 (core portrait), 2 (extended), 3 (full model).
        budget: Maximum character count. 0 = no budget limit within tier.

    Returns:
        Compacted user model text.
    """
    if tier >= 3 or not model_md:
        result = model_md
    elif tier == 2:
        result = _extract_model_sections(model_md, _TIER_2_SECTIONS)
    else:
        result = _extract_model_sections(model_md, _TIER_1_SECTIONS)

    # Apply character budget if set
    if budget > 0 and len(result) > budget:
        lines = result.split("\n")
        kept: list[str] = []
        total = 0
        for line in lines:
            if total + len(line) + 1 > budget:
                break
            kept.append(line)
            total += len(line) + 1
        result = "\n".join(kept)

    return result or model_md  # Fallback to full if extraction produced nothing


# ---------------------------------------------------------------------------
# Context budget — per-channel allocation with surplus reallocation
# ---------------------------------------------------------------------------

@dataclass
class ContextBudget:
    """Character budget allocation for context assembly.

    Each field represents the max characters for that context layer.
    0 means "no limit" (disabled). surplus_pool accumulates unused
    budget from underspending layers.
    """
    total: int = 0          # 0 = no limit (compaction disabled)
    soul: int = 0
    user_model: int = 0
    soul_state: int = 200
    dossiers: int = 800
    instructions: int = 0   # usually not compacted
    message: int = 0        # usually not compacted
    surplus_pool: int = 0

    def consume(self, layer: str, actual: int) -> int:
        """Record actual usage for a layer, return the surplus.

        Args:
            layer: Layer name (must match a field name).
            actual: Actual characters used.

        Returns:
            Surplus characters freed up (budget - actual), or 0 if no budget.
        """
        budget = getattr(self, layer, 0)
        if budget <= 0:
            return 0
        surplus = max(0, budget - actual)
        self.surplus_pool += surplus
        return surplus

    def available(self, layer: str) -> int:
        """Get available budget for a layer (its allocation + surplus pool).

        Returns 0 if no budget is set for this layer.
        """
        budget = getattr(self, layer, 0)
        if budget <= 0:
            return 0
        return budget + self.surplus_pool


# Channel profiles — default budgets per channel type
_CHANNEL_BUDGETS: dict[str, ContextBudget] = {
    "sms": ContextBudget(
        total=3000,
        soul=800,
        user_model=600,
        soul_state=150,
        dossiers=0,        # no dossiers in SMS
    ),
    "slack": ContextBudget(
        total=6000,
        soul=1500,
        user_model=1200,
        soul_state=200,
        dossiers=800,
    ),
    "terminal": ContextBudget(
        total=0,            # no limit for terminal
        soul=0,
        user_model=0,
    ),
    "reflection": ContextBudget(
        total=4000,
        soul=800,
        user_model=800,
        soul_state=150,
        dossiers=0,
    ),
}


def get_channel_budget(channel: str) -> ContextBudget:
    """Get the context budget for a channel type.

    Channel prefixes are matched: "sms:+1234" → "sms", "C04ABC" → "slack".
    Falls back to a zero-budget (no compaction) for unknown channels.
    """
    ch_lower = channel.lower()
    if ch_lower.startswith("sms:"):
        return ContextBudget(**{k: v for k, v in _CHANNEL_BUDGETS["sms"].__dict__.items()})
    elif ch_lower.startswith("terminal:"):
        return ContextBudget(**{k: v for k, v in _CHANNEL_BUDGETS["terminal"].__dict__.items()})
    elif ch_lower.startswith("discord:") or ch_lower.startswith("telegram:"):
        return ContextBudget(**{k: v for k, v in _CHANNEL_BUDGETS["slack"].__dict__.items()})
    elif channel.startswith("C") or channel.startswith("D"):
        # Slack channel IDs start with C (public) or D (DM)
        return ContextBudget(**{k: v for k, v in _CHANNEL_BUDGETS["slack"].__dict__.items()})
    else:
        return ContextBudget()  # No compaction


def get_reflection_budget() -> ContextBudget:
    """Get the context budget for reflection prompts."""
    return ContextBudget(**{k: v for k, v in _CHANNEL_BUDGETS["reflection"].__dict__.items()})


# ---------------------------------------------------------------------------
# User model tier selection
# ---------------------------------------------------------------------------

def select_user_model_tier(channel: str, samantha_dreams_gate: bool) -> int:
    """Select user model tier based on channel and Samantha-Dreams gate.

    Args:
        channel: Channel identifier.
        samantha_dreams_gate: Whether the Samantha-Dreams gate fired true
            (something new was learned about user last turn).

    Returns:
        1 (core portrait), 2 (extended), or 3 (full — only for update steps).
    """
    ch_lower = channel.lower()

    # SMS: always tier 1 (compact portrait)
    if ch_lower.startswith("sms:"):
        return 2 if samantha_dreams_gate else 1

    # Slack/Discord/Telegram: tier 1 normally, tier 2 when gate fires
    if samantha_dreams_gate:
        return 2

    return 1
