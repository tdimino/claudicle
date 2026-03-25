"""Built-in tool handlers for tool-augmented cognitive steps.

Three read-only handlers that can be attached to any CognitiveStep via its
`tools` field. Tool results are transient context — they never enter
WorkingMemory or CognitiveOutput.

Usage:
    from cognitive_steps.tool_handlers import QUERY_MEMORY_SPEC, READ_DOSSIER_SPEC

    my_step = CognitiveStep(
        name="...",
        tools=[QUERY_MEMORY_SPEC, READ_DOSSIER_SPEC],
        ...
    )
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from cognitive_steps.steps import ToolSpec
from memory import user_models, working_memory

log = logging.getLogger("claudicle.tool_handlers")

# Maximum result sizes to prevent context bloat
_MAX_MEMORY_ENTRIES = 25
_MAX_MEMORY_CHARS = 500
_MAX_DOSSIER_CHARS = 3000
_MAX_RLAMA_RESULTS = 10
_MAX_RLAMA_CHARS = 3000
_RLAMA_TIMEOUT = 15


def _query_memory(
    channel: str = "",
    entry_type: str = "",
    limit: int = 10,
    user_id: str = "",
    region: str = "",
) -> str:
    """Query working memory by channel, entry type, region, or user."""
    try:
        limit = min(limit, _MAX_MEMORY_ENTRIES)
        entries = working_memory.query(
            channel=channel or None,
            entry_type=entry_type or None,
            user_id=user_id or None,
            region=region or None,
            limit=limit,
        )
        if not entries:
            return "No matching entries found."

        results = []
        for e in entries:
            content = e.get("content", "")[:_MAX_MEMORY_CHARS]
            results.append(
                f"[{e.get('entry_type', '?')}] "
                f"{e.get('created_at', '')}: {content}"
            )
        return "\n".join(results)
    except Exception as e:
        log.error("query_memory failed: %s", e, exc_info=True)
        return f"Memory query unavailable: {e}"


def _read_dossier(entity_name: str = "") -> str:
    """Read a dossier by entity name (fuzzy match via entity graph)."""
    if not entity_name:
        return "Error: entity_name is required."

    try:
        content = user_models.get_dossier(entity_name)
        if not content:
            return f"No dossier found for '{entity_name}'."
        return content[:_MAX_DOSSIER_CHARS]
    except Exception as e:
        log.error("read_dossier failed for '%s': %s", entity_name, e, exc_info=True)
        return f"Dossier lookup unavailable: {e}"


def _rlama_retrieve(
    collection: str = "",
    query: str = "",
    top_k: int = 5,
) -> str:
    """Semantic search over an RLAMA collection (subprocess, with timeout)."""
    if not collection or not query:
        return "Error: collection and query are required."

    top_k = min(top_k, _MAX_RLAMA_RESULTS)
    rlama_script = Path.home() / ".claude" / "skills" / "rlama" / "scripts" / "rlama_retrieve.py"
    if not rlama_script.exists():
        return "RLAMA not available (rlama_retrieve.py not found)."

    try:
        result = subprocess.run(
            ["python3", str(rlama_script), collection, query, "--top-k", str(top_k)],
            capture_output=True,
            text=True,
            timeout=_RLAMA_TIMEOUT,
        )
        if result.returncode != 0:
            return f"RLAMA error: {result.stderr[:200]}"
        return result.stdout[:_MAX_RLAMA_CHARS]
    except subprocess.TimeoutExpired:
        return f"RLAMA timed out after {_RLAMA_TIMEOUT}s."
    except Exception as e:
        return f"RLAMA error: {e}"


# ---------------------------------------------------------------------------
# Tool specs — attach these to CognitiveStep.tools
# ---------------------------------------------------------------------------

QUERY_MEMORY_SPEC = ToolSpec(
    name="query_memory",
    description="Search working memory for past entries by channel, entry type, region, or user. Returns recent entries matching the criteria.",
    parameters={
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Channel to search (e.g. 'daimon:mazkir', 'terminal:abc123'). Empty for all channels.",
            },
            "entry_type": {
                "type": "string",
                "description": "Entry type filter (e.g. 'externalDialog', 'decision', 'internalMonologue'). Empty for all types.",
            },
            "region": {
                "type": "string",
                "description": "Region filter (e.g. 'world-war-watcher', 'default'). Empty for all regions.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum entries to return (default 10, max 25).",
                "default": 10,
            },
            "user_id": {
                "type": "string",
                "description": "Filter by user/daimon ID. Empty for all.",
            },
        },
        "required": [],
    },
    handler=_query_memory,
)

READ_DOSSIER_SPEC = ToolSpec(
    name="read_dossier",
    description="Read a dossier (structured profile) for a named entity. Supports fuzzy matching via the entity graph.",
    parameters={
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": "Name of the entity to look up.",
            },
        },
        "required": ["entity_name"],
    },
    handler=_read_dossier,
)

RLAMA_RETRIEVE_SPEC = ToolSpec(
    name="rlama_retrieve",
    description="Semantic search over a local RLAMA knowledge base. Returns the most relevant passages for a natural language query.",
    parameters={
        "type": "object",
        "properties": {
            "collection": {
                "type": "string",
                "description": "RLAMA collection name (e.g. 'wwatcher-commentary', 'academic-research').",
            },
            "query": {
                "type": "string",
                "description": "Natural language search query.",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10).",
                "default": 5,
            },
        },
        "required": ["collection", "query"],
    },
    handler=_rlama_retrieve,
)

# Convenience list of all built-in tool specs
ALL_TOOL_SPECS = [QUERY_MEMORY_SPEC, READ_DOSSIER_SPEC, RLAMA_RETRIEVE_SPEC]
