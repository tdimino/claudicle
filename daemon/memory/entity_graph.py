"""Frozen entity graph for Obsidian-inspired entity awareness.

Builds an in-memory graph of all entities (dossiers + user models) from
their frontmatter tags and wiki links. Provides multi-signal relevance
scoring that replaces simple substring matching in get_relevant_dossiers().

Open Souls Paradigm alignment:
- EntityNode and EntityGraph are frozen dataclasses (like WorkingMemorySnapshot)
- All query functions are pure: (graph, query) → results
- Graph is built by impure read (load_entity_graph), cached per-process
- Cache invalidation at the apply_output() boundary only

No external dependencies. Uses frontmatter.py for parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from memory.db import memory_pool
from memory.frontmatter import extract_rag_tags, parse_frontmatter, parse_wiki_links

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frozen data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntityNode:
    """A single entity in the dossier graph. Immutable."""

    entity_id: str                             # "dossier:knossos"
    name: str                                  # "Knossos"
    entity_type: str                           # "person" | "subject"
    tags: dict = field(default_factory=dict)    # {"concepts": ["minoan"], ...}
    outgoing_links: tuple[str, ...] = ()       # Wiki link target names
    aliases: tuple[str, ...] = ()              # From frontmatter aliases field
    rag_keywords: tuple[str, ...] = ()         # From RAG: line


@dataclass(frozen=True)
class EntityGraph:
    """Immutable entity graph snapshot.

    Follows the WorkingMemorySnapshot pattern: frozen dataclass with dict
    fields built once at construction and never mutated afterward.
    """

    nodes: dict[str, EntityNode] = field(default_factory=dict)
    _name_index: dict[str, str] = field(default_factory=dict)
    _tag_index: dict[str, frozenset[str]] = field(default_factory=dict)
    _backlinks: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def get_node(self, entity_id: str) -> Optional[EntityNode]:
        """Get a node by entity_id, or None."""
        return self.nodes.get(entity_id)

    def resolve_name(self, name: str) -> Optional[str]:
        """Resolve a name or alias to an entity_id, or None."""
        return self._name_index.get(name.lower().strip())

    def get_backlinks(self, entity_name: str) -> list[str]:
        """Get display names of entities that wiki-link TO this entity."""
        entity_id = self.resolve_name(entity_name)
        if not entity_id or entity_id not in self._backlinks:
            return []
        return [
            self.nodes[eid].name
            for eid in self._backlinks[entity_id]
            if eid in self.nodes
        ]


# ---------------------------------------------------------------------------
# Graph builder (impure read, pure construction)
# ---------------------------------------------------------------------------

def _build_node(entity_id: str, display_name: str, entity_type: str, model_md: str) -> EntityNode:
    """Build an EntityNode from a dossier's markdown. Pure function."""
    meta = parse_frontmatter(model_md)
    links = parse_wiki_links(model_md)
    rag = extract_rag_tags(model_md)

    # Extract nested tags dict (e.g. {"concepts": [...], "people": [...]})
    tags_raw = meta.get("tags", {})
    tags = tags_raw if isinstance(tags_raw, dict) else {}

    # Extract aliases — may be a list or a single string
    aliases_raw = meta.get("aliases", [])
    if isinstance(aliases_raw, str):
        aliases = (aliases_raw,) if aliases_raw else ()
    elif isinstance(aliases_raw, list):
        aliases = tuple(aliases_raw)
    else:
        aliases = ()

    return EntityNode(
        entity_id=entity_id,
        name=display_name or entity_id,
        entity_type=entity_type or "subject",
        tags=tags,
        outgoing_links=tuple(links),
        aliases=aliases,
        rag_keywords=tuple(rag),
    )


def build_entity_graph() -> EntityGraph:
    """Build the entity graph from all entities in the database.

    Includes both dossiers (entity_type: person/subject) and user models
    (entity_type: user). User models are indexed for wiki link resolution
    and cross-referencing but scored differently in relevance queries.

    Impure: reads from SQLite. Returns a frozen EntityGraph.

    Steps:
    1. Query all rows from user_models (dossiers + users)
    2. Build EntityNode for each
    3. Build name index (display_name + aliases → entity_id)
    4. Build tag index ("dimension:value" → {entity_ids})
    5. Compute backlinks (invert wiki link edges)
    """
    conn = memory_pool.get_conn()
    rows = conn.execute(
        "SELECT user_id, display_name, entity_type, model_md "
        "FROM user_models"
    ).fetchall()

    nodes: dict[str, EntityNode] = {}
    name_index: dict[str, str] = {}
    tag_index: dict[str, set[str]] = {}

    # Phase 1: Build nodes and indexes
    for row in rows:
        entity_id = row["user_id"]
        display_name = row["display_name"] or ""
        model_md = row["model_md"] or ""

        # Determine entity type: dossiers have explicit types,
        # non-dossier rows are user models
        if entity_id.startswith("dossier:"):
            entity_type = row["entity_type"] or "subject"
        else:
            entity_type = "user"

        node = _build_node(entity_id, display_name, entity_type, model_md)
        nodes[entity_id] = node

        # Name index: display_name + aliases → entity_id
        if node.name:
            name_index[node.name.lower().strip()] = entity_id
        for alias in node.aliases:
            if alias:
                name_index[alias.lower().strip()] = entity_id

        # Tag index: "dimension:value" → {entity_ids}
        for dimension, values in node.tags.items():
            if isinstance(values, list):
                for val in values:
                    key = f"{dimension}:{val.lower().strip()}"
                    tag_index.setdefault(key, set()).add(entity_id)
            elif isinstance(values, str):
                key = f"{dimension}:{values.lower().strip()}"
                tag_index.setdefault(key, set()).add(entity_id)

    # Phase 2: Compute backlinks by resolving wiki links
    backlinks_map: dict[str, set[str]] = {}
    for entity_id, node in nodes.items():
        for target_name in node.outgoing_links:
            target_id = name_index.get(target_name.lower().strip())
            if target_id and target_id != entity_id:
                backlinks_map.setdefault(target_id, set()).add(entity_id)

    backlinks = {eid: tuple(sources) for eid, sources in backlinks_map.items()}
    tag_index_frozen = {k: frozenset(v) for k, v in tag_index.items()}

    return EntityGraph(
        nodes=nodes,
        _name_index=name_index,
        _tag_index=tag_index_frozen,
        _backlinks=backlinks,
    )


# ---------------------------------------------------------------------------
# Cache (same pattern as usermodel_resolver._phone_index)
# ---------------------------------------------------------------------------

_graph_cache: Optional[EntityGraph] = None


def get_entity_graph() -> EntityGraph:
    """Get or build the entity graph. Cached per-process."""
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = build_entity_graph()
    return _graph_cache


def invalidate_graph() -> None:
    """Clear the cached graph. Call after dossier writes."""
    global _graph_cache
    _graph_cache = None


# ---------------------------------------------------------------------------
# Pure query functions
# ---------------------------------------------------------------------------

def _score_entity(node: EntityNode, text_lower: str, text_words: set[str]) -> float:
    """Score an entity's relevance to the given text. Pure function."""
    score = 0.0

    # Signal 1: Name match (weight 10.0)
    if node.name and node.name.lower() in text_lower:
        score += 10.0

    # Signal 1b: Alias match (weight 8.0)
    for alias in node.aliases:
        if alias and alias.lower() in text_lower:
            score += 8.0
            break  # One alias match is enough

    # Signal 2: Tag match (weight 2.0 per hit)
    # Split hyphenated values (e.g. "minoan-crete" → check "minoan" and "crete")
    for values in node.tags.values():
        tag_values = [values] if isinstance(values, str) else values
        if not isinstance(tag_values, list):
            continue
        for val in tag_values:
            val_lower = val.lower().strip()
            if val_lower in text_lower or val_lower in text_words:
                score += 2.0
            elif "-" in val_lower:
                # Check individual words of hyphenated compound
                parts = val_lower.split("-")
                matches = sum(1 for p in parts if p in text_words)
                if matches > 0:
                    score += 1.0 * matches  # Partial match, lower weight

    # Signal 3: RAG keyword match (weight 1.0 per hit)
    for kw in node.rag_keywords:
        if kw.lower().strip() in text_lower:
            score += 1.0

    return score


def get_relevant_entities(
    graph: EntityGraph,
    text: str,
    limit: int = 3,
    entity_types: tuple[str, ...] | None = None,
) -> list[str]:
    """Find entities relevant to the given text using multi-signal scoring.

    Pure function: (graph, text) → entity display names.

    Signals:
    1. Name/alias substring match (weight 10.0 / 8.0)
    2. Tag value match (weight 2.0 per hit)
    3. RAG keyword match (weight 1.0 per hit)
    4. Backlink boost: if entity A links to matched entity B,
       A gets +0.3 × B's score (graph adjacency)

    Args:
        graph: The entity graph to search.
        text: Message text to match against.
        limit: Maximum number of results.
        entity_types: Filter results to these types (e.g. ("person", "subject")
            for dossiers only, or ("user",) for user models only).
            None returns all types. All types participate in scoring
            and backlink boosting regardless of this filter — it only
            controls which types appear in the final results.

    Returns entity display names sorted by score, capped at limit.
    """
    if not graph.nodes or not text:
        return []

    text_lower = text.lower()
    text_words = set(text_lower.split())

    # Phase 1: Score ALL entities (regardless of type filter —
    # user models contribute to backlink boosting even if filtered out)
    scores: dict[str, float] = {}
    for entity_id, node in graph.nodes.items():
        s = _score_entity(node, text_lower, text_words)
        if s > 0:
            scores[entity_id] = s

    # Phase 2: Backlink boost — if matched entity B has a backlink from A,
    # boost A's score by a fraction of B's score
    boost: dict[str, float] = {}
    for entity_id, score in scores.items():
        backlink_sources = graph._backlinks.get(entity_id, ())
        for source_id in backlink_sources:
            if source_id not in scores:
                # Source wasn't directly matched — give it a boost
                boost[source_id] = boost.get(source_id, 0.0) + 0.3 * score

    # Merge boosts into scores
    for entity_id, b in boost.items():
        if entity_id in graph.nodes:
            scores[entity_id] = scores.get(entity_id, 0.0) + b

    # Sort by score descending, apply type filter to results only
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results: list[str] = []
    for eid, _score in ranked:
        node = graph.nodes[eid]
        if entity_types is not None and node.entity_type not in entity_types:
            continue
        results.append(node.name)
        if len(results) >= limit:
            break
    return results
