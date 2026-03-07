"""Tests for daemon/memory/frontmatter.py and daemon/memory/entity_graph.py.

Covers:
- Frontmatter parser (flat, nested, inline lists, backward compat, edge cases)
- Wiki link parser
- RAG tag extractor
- Entity graph building from DB (dossiers + user models)
- Multi-signal relevance scoring (name, alias, tags, RAG, backlinks)
- Type filtering
- Cache lifecycle
"""

from memory import user_models
from memory.frontmatter import extract_rag_tags, parse_frontmatter, parse_wiki_links
from memory.entity_graph import (
    EntityGraph,
    EntityNode,
    _build_node,
    _score_entity,
    build_entity_graph,
    get_entity_graph,
    get_relevant_entities,
    invalidate_graph,
)


# ---------------------------------------------------------------------------
# Frontmatter parser tests
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    """Tests for the enhanced frontmatter parser."""

    def test_flat_values(self):
        md = '---\ntitle: "Knossos"\ntype: subject\nstatus: active\n---\n'
        result = parse_frontmatter(md)
        assert result == {"title": "Knossos", "type": "subject", "status": "active"}

    def test_flat_values_single_quotes(self):
        md = "---\ntitle: 'Knossos'\n---\n"
        result = parse_frontmatter(md)
        assert result["title"] == "Knossos"

    def test_flat_values_no_quotes(self):
        md = "---\nstatus: active\n---\n"
        result = parse_frontmatter(md)
        assert result["status"] == "active"

    def test_nested_tags(self):
        md = (
            "---\n"
            "title: \"Knossos\"\n"
            "tags:\n"
            "  concepts: [minoan-crete, trade-routes]\n"
            "  people: [cyrus-gordon]\n"
            "  domains: [archaeology, linguistics]\n"
            "---\n"
        )
        result = parse_frontmatter(md)
        assert result["title"] == "Knossos"
        assert result["tags"]["concepts"] == ["minoan-crete", "trade-routes"]
        assert result["tags"]["people"] == ["cyrus-gordon"]
        assert result["tags"]["domains"] == ["archaeology", "linguistics"]

    def test_nested_with_quoted_items(self):
        md = '---\ntags:\n  concepts: ["minoan crete", \'trade routes\']\n---\n'
        result = parse_frontmatter(md)
        assert result["tags"]["concepts"] == ["minoan crete", "trade routes"]

    def test_nested_empty_list(self):
        md = "---\ntags:\n  concepts: []\n---\n"
        result = parse_frontmatter(md)
        assert result["tags"]["concepts"] == []

    def test_nested_string_value(self):
        md = "---\ntags:\n  primary: archaeology\n---\n"
        result = parse_frontmatter(md)
        assert result["tags"]["primary"] == "archaeology"

    def test_top_level_inline_list(self):
        md = "---\naliases: [Cnossus, Knosós]\n---\n"
        result = parse_frontmatter(md)
        assert result["aliases"] == ["Cnossus", "Knosós"]

    def test_mixed_flat_and_nested(self):
        md = (
            "---\n"
            "title: \"Test\"\n"
            "tags:\n"
            "  concepts: [a, b]\n"
            "status: active\n"
            "---\n"
        )
        result = parse_frontmatter(md)
        assert result["title"] == "Test"
        assert result["tags"]["concepts"] == ["a", "b"]
        assert result["status"] == "active"

    def test_empty_string(self):
        assert parse_frontmatter("") == {}

    def test_none_input(self):
        assert parse_frontmatter(None) == {}

    def test_no_frontmatter(self):
        assert parse_frontmatter("# Just a heading\nSome content") == {}

    def test_no_closing_delimiter(self):
        assert parse_frontmatter("---\ntitle: Test\nNo closing") == {}

    def test_empty_frontmatter(self):
        assert parse_frontmatter("---\n---\n") == {}

    def test_backward_compat_with_user_model_template(self):
        """Verify the new parser produces identical output to the old one
        for the standard user model template format."""
        md = (
            '---\n'
            'title: "Alice"\n'
            'type: user-model\n'
            'userName: "Alice"\n'
            'userId: "U123"\n'
            'created: "2026-01-01"\n'
            'updated: "2026-01-01"\n'
            'status: active\n'
            'onboardingComplete: true\n'
            'role: "primary"\n'
            '---\n'
        )
        result = parse_frontmatter(md)
        assert result["title"] == "Alice"
        assert result["userName"] == "Alice"
        assert result["userId"] == "U123"
        assert result["onboardingComplete"] == "true"
        assert result["role"] == "primary"

    def test_multiple_nested_sections(self):
        md = (
            "---\n"
            "tags:\n"
            "  concepts: [a]\n"
            "metadata:\n"
            "  source: manual\n"
            "  verified: true\n"
            "---\n"
        )
        result = parse_frontmatter(md)
        assert result["tags"]["concepts"] == ["a"]
        assert result["metadata"]["source"] == "manual"
        assert result["metadata"]["verified"] == "true"


# ---------------------------------------------------------------------------
# Wiki link parser tests
# ---------------------------------------------------------------------------

class TestParseWikiLinks:
    """Tests for the wiki link extractor."""

    def test_basic_links(self):
        content = "See [[Knossos]] and [[Ugarit]] for more."
        assert parse_wiki_links(content) == ["Knossos", "Ugarit"]

    def test_display_text(self):
        content = "See [[Knossos|the palace]] for details."
        assert parse_wiki_links(content) == ["Knossos"]

    def test_deduplication(self):
        content = "Both [[Knossos]] and [[Knossos]] reference the same."
        assert parse_wiki_links(content) == ["Knossos"]

    def test_case_insensitive_dedup(self):
        content = "[[Knossos]] and [[knossos]] are the same."
        assert parse_wiki_links(content) == ["Knossos"]

    def test_in_cross_references_section(self):
        content = (
            "## Cross-References\n"
            "- [[Cyrus Gordon]] (etymology research)\n"
            "- [[Minoan Trade]] (shared evidence)\n"
        )
        links = parse_wiki_links(content)
        assert "Cyrus Gordon" in links
        assert "Minoan Trade" in links

    def test_empty_content(self):
        assert parse_wiki_links("") == []

    def test_no_links(self):
        assert parse_wiki_links("Just plain text.") == []

    def test_nested_in_markdown(self):
        content = "**bold [[Entity]]** and `code [[Other]]`"
        links = parse_wiki_links(content)
        assert "Entity" in links
        assert "Other" in links


# ---------------------------------------------------------------------------
# RAG tag extractor tests
# ---------------------------------------------------------------------------

class TestExtractRagTags:
    """Tests for RAG tag line extraction."""

    def test_basic_extraction(self):
        content = "Some content\nRAG: knossos, minoan, crete, trade\n"
        tags = extract_rag_tags(content)
        assert tags == ["knossos", "minoan", "crete", "trade"]

    def test_whitespace_handling(self):
        content = "RAG:  knossos ,  minoan , crete \n"
        tags = extract_rag_tags(content)
        assert tags == ["knossos", "minoan", "crete"]

    def test_no_rag_line(self):
        assert extract_rag_tags("No RAG here") == []

    def test_empty_content(self):
        assert extract_rag_tags("") == []

    def test_rag_line_in_section(self):
        content = (
            "## RAG Tags\n"
            "RAG: alpha, beta, gamma\n"
            "\n"
            "## Other Section\n"
        )
        assert extract_rag_tags(content) == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# EntityNode building tests
# ---------------------------------------------------------------------------

class TestBuildNode:
    """Tests for _build_node() pure function."""

    def test_full_dossier(self):
        md = (
            '---\n'
            'title: "Knossos"\n'
            'aliases: [Cnossus, Knosós]\n'
            'tags:\n'
            '  concepts: [minoan, trade]\n'
            '  domains: [archaeology]\n'
            '---\n'
            '# Knossos\n'
            '## Cross-References\n'
            '- [[Cyrus Gordon]] (research)\n'
            'RAG: knossos, palace, crete\n'
        )
        node = _build_node("dossier:knossos", "Knossos", "subject", md)
        assert node.entity_id == "dossier:knossos"
        assert node.name == "Knossos"
        assert node.entity_type == "subject"
        assert node.tags == {"concepts": ["minoan", "trade"], "domains": ["archaeology"]}
        assert node.outgoing_links == ("Cyrus Gordon",)
        assert node.aliases == ("Cnossus", "Knosós")
        assert node.rag_keywords == ("knossos", "palace", "crete")

    def test_minimal_dossier(self):
        md = "---\ntitle: \"Test\"\n---\n# Test\n"
        node = _build_node("dossier:test", "Test", "subject", md)
        assert node.tags == {}
        assert node.outgoing_links == ()
        assert node.aliases == ()
        assert node.rag_keywords == ()

    def test_user_model(self):
        md = '---\ntitle: "Alice"\ntype: user-model\nuserName: "Alice"\n---\n# Alice\n'
        node = _build_node("U123", "Alice", "user", md)
        assert node.entity_type == "user"
        assert node.name == "Alice"

    def test_no_frontmatter(self):
        node = _build_node("dossier:x", "X", "subject", "# No frontmatter")
        assert node.tags == {}
        assert node.aliases == ()


# ---------------------------------------------------------------------------
# Entity graph building from DB
# ---------------------------------------------------------------------------

class TestBuildEntityGraph:
    """Tests for build_entity_graph() with real DB fixtures."""

    def test_empty_db(self):
        graph = build_entity_graph()
        assert graph.nodes == {}

    def test_single_dossier(self):
        md = (
            '---\ntitle: "Knossos"\ntags:\n  concepts: [minoan]\n---\n'
            '# Knossos\nRAG: knossos, crete\n'
        )
        user_models.save_dossier("Knossos", md, entity_type="subject")
        graph = build_entity_graph()

        assert "dossier:knossos" in graph.nodes
        node = graph.nodes["dossier:knossos"]
        assert node.entity_type == "subject"
        assert node.tags == {"concepts": ["minoan"]}
        assert node.rag_keywords == ("knossos", "crete")

    def test_user_model_included(self):
        user_models.ensure_exists("U42", display_name="Alice")
        graph = build_entity_graph()

        assert "U42" in graph.nodes
        node = graph.nodes["U42"]
        assert node.entity_type == "user"
        assert node.name == "Alice"

    def test_name_index(self):
        user_models.save_dossier("Knossos", "---\naliases: [Cnossus]\n---\n")
        graph = build_entity_graph()

        assert graph.resolve_name("Knossos") == "dossier:knossos"
        assert graph.resolve_name("knossos") == "dossier:knossos"
        assert graph.resolve_name("Cnossus") == "dossier:knossos"
        assert graph.resolve_name("nonexistent") is None

    def test_tag_index(self):
        user_models.save_dossier(
            "Knossos",
            "---\ntags:\n  concepts: [minoan, trade]\n---\n",
        )
        graph = build_entity_graph()

        assert "dossier:knossos" in graph._tag_index.get("concepts:minoan", frozenset())
        assert "dossier:knossos" in graph._tag_index.get("concepts:trade", frozenset())

    def test_backlinks(self):
        user_models.save_dossier(
            "Knossos",
            "---\ntitle: \"Knossos\"\n---\n## Cross-References\n- [[Gordon]]\n",
        )
        user_models.save_dossier("Gordon", "---\ntitle: \"Gordon\"\n---\n# Gordon\n")
        graph = build_entity_graph()

        backlinks = graph.get_backlinks("Gordon")
        assert "Knossos" in backlinks

    def test_backlinks_empty(self):
        user_models.save_dossier("Isolated", "---\ntitle: \"Isolated\"\n---\n")
        graph = build_entity_graph()
        assert graph.get_backlinks("Isolated") == []

    def test_mixed_entities(self):
        """Both dossiers and user models appear in the graph."""
        user_models.save_dossier("Knossos", "---\ntitle: \"Knossos\"\n---\n")
        user_models.ensure_exists("U1", display_name="Tom")
        graph = build_entity_graph()

        assert "dossier:knossos" in graph.nodes
        assert "U1" in graph.nodes
        assert graph.nodes["dossier:knossos"].entity_type == "subject"
        assert graph.nodes["U1"].entity_type == "user"


# ---------------------------------------------------------------------------
# Relevance scoring tests
# ---------------------------------------------------------------------------

class TestScoreEntity:
    """Tests for the pure _score_entity() function."""

    def _node(self, **kwargs):
        defaults = dict(
            entity_id="dossier:test", name="Test", entity_type="subject",
            tags={}, outgoing_links=(), aliases=(), rag_keywords=(),
        )
        defaults.update(kwargs)
        return EntityNode(**defaults)

    def test_name_match(self):
        node = self._node(name="Knossos")
        score = _score_entity(node, "tell me about knossos", {"tell", "me", "about", "knossos"})
        assert score >= 10.0

    def test_alias_match(self):
        node = self._node(name="Knossos", aliases=("Cnossus",))
        score = _score_entity(node, "the site at cnossus", {"the", "site", "at", "cnossus"})
        assert score >= 8.0

    def test_tag_match(self):
        node = self._node(tags={"concepts": ["minoan", "trade"]})
        score = _score_entity(node, "minoan trade routes", {"minoan", "trade", "routes"})
        assert score >= 4.0  # 2.0 per tag hit

    def test_hyphenated_tag_partial_match(self):
        node = self._node(tags={"concepts": ["minoan-crete"]})
        score = _score_entity(node, "tell me about minoan", {"tell", "me", "about", "minoan"})
        assert score >= 1.0  # partial match on hyphenated component

    def test_rag_keyword_match(self):
        node = self._node(rag_keywords=("knossos", "crete", "palace"))
        score = _score_entity(node, "the palace at crete", {"the", "palace", "at", "crete"})
        assert score >= 2.0  # 1.0 per RAG hit

    def test_no_match(self):
        node = self._node(name="Knossos", tags={"concepts": ["minoan"]})
        score = _score_entity(node, "quantum computing", {"quantum", "computing"})
        assert score == 0.0

    def test_combined_signals(self):
        node = self._node(
            name="Knossos",
            tags={"concepts": ["minoan"]},
            rag_keywords=("crete",),
        )
        score = _score_entity(
            node, "knossos and minoan crete",
            {"knossos", "and", "minoan", "crete"},
        )
        # Name (10) + tag (2) + RAG (1) = 13
        assert score >= 13.0


class TestGetRelevantEntities:
    """Tests for get_relevant_entities() with graph fixtures."""

    def _graph(self):
        """Build a small test graph with interconnected entities."""
        return EntityGraph(
            nodes={
                "dossier:knossos": EntityNode(
                    entity_id="dossier:knossos", name="Knossos", entity_type="subject",
                    tags={"concepts": ["minoan-crete", "trade-routes"]},
                    outgoing_links=("Gordon",),
                    rag_keywords=("knossos", "minoan", "crete"),
                ),
                "dossier:gordon": EntityNode(
                    entity_id="dossier:gordon", name="Gordon", entity_type="person",
                    tags={"domains": ["linguistics", "archaeology"]},
                    outgoing_links=("Knossos",),
                    rag_keywords=("gordon", "semitic"),
                ),
                "U1": EntityNode(
                    entity_id="U1", name="Tom", entity_type="user",
                    tags={}, outgoing_links=(), aliases=(), rag_keywords=(),
                ),
            },
            _name_index={
                "knossos": "dossier:knossos",
                "gordon": "dossier:gordon",
                "tom": "U1",
            },
            _tag_index={
                "concepts:minoan-crete": {"dossier:knossos"},
                "concepts:trade-routes": {"dossier:knossos"},
                "domains:linguistics": {"dossier:gordon"},
                "domains:archaeology": {"dossier:gordon"},
            },
            _backlinks={
                "dossier:gordon": ("dossier:knossos",),
                "dossier:knossos": ("dossier:gordon",),
            },
        )

    def test_name_match(self):
        result = get_relevant_entities(self._graph(), "Tell me about Knossos")
        assert "Knossos" in result

    def test_tag_match_finds_entity(self):
        result = get_relevant_entities(self._graph(), "Minoan archaeology", limit=5)
        assert len(result) > 0

    def test_backlink_boost(self):
        """Mentioning Gordon should boost Knossos via backlinks."""
        result = get_relevant_entities(self._graph(), "Gordon", limit=5)
        assert "Gordon" in result
        # Knossos should appear via backlink boost (Gordon links to Knossos)
        assert "Knossos" in result

    def test_type_filter_dossiers_only(self):
        result = get_relevant_entities(
            self._graph(), "Tell me about Knossos and Tom",
            entity_types=("person", "subject"),
        )
        assert "Tom" not in result
        assert "Knossos" in result

    def test_type_filter_users_only(self):
        result = get_relevant_entities(
            self._graph(), "Tom", entity_types=("user",),
        )
        assert result == ["Tom"]

    def test_empty_text(self):
        assert get_relevant_entities(self._graph(), "") == []

    def test_empty_graph(self):
        empty = EntityGraph()
        assert get_relevant_entities(empty, "anything") == []

    def test_limit(self):
        result = get_relevant_entities(self._graph(), "Knossos Gordon", limit=1)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Cache lifecycle tests
# ---------------------------------------------------------------------------

class TestGraphCache:
    """Tests for get_entity_graph() and invalidate_graph()."""

    def test_cache_returns_same_instance(self):
        invalidate_graph()
        g1 = get_entity_graph()
        g2 = get_entity_graph()
        assert g1 is g2

    def test_invalidate_clears_cache(self):
        invalidate_graph()
        g1 = get_entity_graph()
        invalidate_graph()
        g2 = get_entity_graph()
        assert g1 is not g2

    def test_cache_reflects_new_dossier(self):
        invalidate_graph()
        g1 = get_entity_graph()
        assert "dossier:new-entity" not in g1.nodes

        user_models.save_dossier("New Entity", "---\ntitle: \"New Entity\"\n---\n")
        invalidate_graph()
        g2 = get_entity_graph()
        assert "dossier:new entity" in g2.nodes
