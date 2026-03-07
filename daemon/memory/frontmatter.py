"""Pure parsing functions for YAML frontmatter, wiki links, and RAG tags.

Single source of truth for frontmatter parsing across the codebase.
Replaces the duplicate parsers in user_models.py and usermodel_resolver.py.

All functions are pure: string in, structured data out. No DB access,
no side effects, no external dependencies.
"""

import re
from typing import Optional


def parse_frontmatter(model_md: str) -> dict:
    """Extract YAML frontmatter from a markdown string.

    Handles both flat key:value and one-level nested structures:

        title: "Knossos"              → {"title": "Knossos"}
        tags:
          concepts: [minoan, crete]   → {"tags": {"concepts": ["minoan", "crete"]}}
          people: [gordon]            → {"tags": {"people": ["gordon"]}}

    Hand-rolled parser (no PyYAML dependency). Backward-compatible with
    all existing flat frontmatter in user models and dossiers.

    Returns an empty dict if no frontmatter is found.
    """
    if not model_md or not model_md.startswith("---"):
        return {}
    end = model_md.find("---", 3)
    if end == -1:
        return {}
    raw = model_md[3:end].strip()
    if not raw:
        return {}

    result: dict = {}
    current_parent: Optional[str] = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue

        # Determine indentation level
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            # Top-level key
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                # Flat key: value — parse inline lists or strip quotes
                result[key] = _parse_inline_value(value)
                current_parent = None
            else:
                # Parent key with no value (e.g. "tags:") — start nesting
                current_parent = key
                result[key] = {}
        elif indent >= 2 and current_parent is not None:
            # Child of current parent
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if value:
                result[current_parent][key] = _parse_inline_value(value)

    return result


def _clean_value(value: str) -> str:
    """Strip surrounding quotes from a frontmatter value."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or \
           (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value


def _parse_inline_value(value: str):
    """Parse a frontmatter value that may be a bracketed list or a plain string.

    [minoan, crete, "trade routes"]  → ["minoan", "crete", "trade routes"]
    archaeology                       → "archaeology"
    """
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = []
        for item in inner.split(","):
            item = item.strip()
            item = _clean_value(item)
            if item:
                items.append(item)
        return items
    return _clean_value(value)


# ---------------------------------------------------------------------------
# Wiki link parser
# ---------------------------------------------------------------------------

_WIKI_LINK_RE = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')


def parse_wiki_links(content: str) -> list[str]:
    """Extract [[Entity Name]] wiki links from markdown content.

    Handles:
        [[Entity Name]]           → "Entity Name"
        [[Entity Name|display]]   → "Entity Name"

    Returns deduplicated list of entity names, original casing preserved,
    ordered by first appearance.
    """
    if not content:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for match in _WIKI_LINK_RE.finditer(content):
        name = match.group(1).strip()
        key = name.lower()
        if key not in seen:
            seen.add(key)
            result.append(name)
    return result


# ---------------------------------------------------------------------------
# RAG tag extractor
# ---------------------------------------------------------------------------

_RAG_LINE_RE = re.compile(r'^RAG:\s*(.+)$', re.MULTILINE)


def extract_rag_tags(content: str) -> list[str]:
    """Extract comma-separated keywords from the RAG: line in dossier content.

    Looks for a line starting with "RAG:" and splits the remainder on commas.
    Returns an empty list if no RAG line is found.
    """
    if not content:
        return []
    match = _RAG_LINE_RE.search(content)
    if not match:
        return []
    raw = match.group(1)
    return [tag.strip() for tag in raw.split(",") if tag.strip()]
