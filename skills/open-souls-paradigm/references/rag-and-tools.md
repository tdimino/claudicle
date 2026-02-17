# RAG & Tool Integration — Extension Pattern

## Open Souls Pattern

The Open Souls Engine integrates external knowledge (RAG) and tools through two complementary patterns:

1. **RAG as a Cognitive Function** — orchestrates brainstorm → parallel vector search → inject context
2. **Tools via Dispatch-Perception Cycle** — soul requests action, application executes, results return as perceptions

### RAG Implementation

RAG is implemented as a **cognitive function** (not a cognitive step)—a pure TypeScript function that orchestrates multiple cognitive steps and vector searches.

```typescript
const withRagContext = async (workingMemory: WorkingMemory) => {
  const { log } = useActions();
  const { search } = useBlueprintStore("default");

  // Step 1: Brainstorm search queries from conversation context
  const [, questions] = await brainstorm(
    workingMemory,
    `Given the conversation, what three questions would ${workingMemory.soulName}
     look to answer from memory?`
  );

  // Step 2: Parallel vector search
  const results = await Promise.all(questions.map(async (question) => {
    const vectorResults = await search(question, {
      minSimilarity: 0.6,
      limit: 10
    });

    if (vectorResults.length === 0) {
      return { question, answer: "No relevant memory found." };
    }

    // Step 3: Use retrieved content to answer each question
    const memoriesToUse = [];
    for (const r of vectorResults) {
      memoriesToUse.push(r.content.toString());
      if (memoriesToUse.join("\n").split(/\s/).length > 700) break;  // Token budget
    }

    const [, answer] = await instruction(
      workingMemory.slice(0, 1),  // Blank slate (personality only)
      `Considering these memories about "${question}":
       ${memoriesToUse.map(m => `<Memory>${m}</Memory>`).join("\n")}
       Answer: ${question}`
    );

    return { question, answer };
  }));

  // Step 4: Inject RAG context into memory at position 1 (after personality)
  const ragMemory = {
    role: ChatMessageRoleEnum.Assistant,
    content: `## Relevant Memory\n\n${results.map(
      r => `### ${r.question}\n${r.answer}`
    ).join("\n\n")}`
  };

  return workingMemory.slice(0, 1)
    .withMemory(ragMemory)
    .concat(workingMemory.slice(1));
};
```

**Key pattern**: Brainstorm generates diverse search queries → parallel vector search casts a wide net → instruction step synthesizes retrieved content → inject as memory at position 1.

### Three Vector Store Scopes

```typescript
const { search, set } = useSoulStore();           // Per-soul instance
const { search } = useBlueprintStore("default");   // Per-blueprint (shared)
const { search } = useOrganizationStore();          // Organization-wide

// Store
await set("user-preference", "prefers formal communication");

// Retrieve
const pref = await fetch("user-preference");

// Vector search
const results = await search("communication style", {
  minSimilarity: 0.6,
  limit: 10
});
// → [{ key, content, similarity, metadata }]
```

### useRag Hook

Simplified RAG integration when brainstorm is not needed:

```typescript
const { search, withRagContext } = useRag('knowledge-bucket');

// Simple search
const results = await search('query');

// Auto-inject context into memory
const enhancedMemory = await withRagContext(workingMemory);
```

### Tool Integration via Dispatch-Perception Cycle

Tools use a **dispatch-perception cycle**: the soul dispatches a tool request, the application layer executes it, and results return as perceptions in the next processing cycle.

```typescript
// Soul dispatches tool request
dispatch({
  action: "browseTo",
  content: url,
  _metadata: { waitForLoad: true, timeout: 30000 }
});

// Application executes tool, returns result as perception:
// { action: "browserResult", content: pageMarkdown, metadata: { url, title } }

// Soul receives result in next invocation
if (invokingPerception?.action === "browserResult") {
  const { url, title } = invokingPerception.metadata;
  // Process tool result...
}
```

### useTool Hook (Blocking)

For synchronous tool calls (30-second timeout):

```typescript
const visit = useTool<{ url: string }, { markdown: string }>("visit");
const result = await visit({ url: "https://example.com" });
// Blocks until client-side tool handler responds
```

### Tool Design Principles

1. **Souls orchestrate, applications execute** — soul says "I need X", app does X
2. **Use dispatch for all tool requests** — maintains functional purity
3. **Receive results as perceptions** — results flow through normal processing
4. **Subprocesses for tool awareness** — background processes inject tool context
5. **Type-safe parameters** — Zod schemas validate tool inputs

---

## Current Claudius Implementation

Claudius has **no RAG integration** and a **different tool model** than Open Souls.

### Tool Model

Claude Code already has rich tool access (Read, Glob, Grep, Bash, WebFetch, Edit, Write). These are not mediated through a dispatch-perception cycle—they're invoked directly by Claude during `query()` execution.

- **Slack messages**: Tools restricted to read-heavy set (`Read,Glob,Grep,Bash,WebFetch`) via `config.CLAUDE_ALLOWED_TOOLS`
- **Terminal**: Full tool access (`Read,Glob,Grep,Bash,WebFetch,Edit,Write`) via `config.TERMINAL_SESSION_TOOLS`
- Tool results are part of Claude's internal processing, not visible to the soul engine

### No Vector Store

Claudius has no vector search capability. The `soul_memory.py` module stores key-value pairs in SQLite, but there's no embedding or similarity search.

The closest existing tool is `rlama`, which provides local RAG via Ollama embeddings. But it's a standalone CLI, not integrated into the cognitive pipeline.

### No Dispatch System

There's no `dispatch()` equivalent. The soul engine doesn't route action requests to external handlers—it processes everything in one LLM call and returns the dialogue.

---

## Extension Blueprint

### Priority 1: rlama Integration for RAG

Wrap the existing `rlama` CLI tool as a cognitive function:

```python
# daemon/rag.py
"""RAG integration via rlama for vector search."""

import subprocess
import json
import logging

log = logging.getLogger("claudius.rag")

def search(query: str, collection: str = "default", limit: int = 5) -> list[dict]:
    """Semantic search via rlama."""
    try:
        result = subprocess.run(
            ["rlama", "search", collection, query, "--top", str(limit), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning(f"rlama search failed: {result.stderr[:200]}")
            return []
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        log.error(f"RAG search error: {e}")
        return []

def inject_context(prompt: str, query: str, collection: str = "default") -> str:
    """Search and inject RAG context into prompt."""
    results = search(query, collection)
    if not results:
        return prompt

    context = "\n".join(
        f"- {r.get('content', '')[:300]}" for r in results[:5]
    )

    return f"""## Relevant Context (from {collection})
{context}

{prompt}"""
```

### Priority 2: SQLite FTS5 for Soul Store

Add full-text search to `soul_memory.py` for lightweight vector-free search:

```python
# daemon/soul_store.py
"""Key-value store with full-text search (SQLite FTS5)."""

import sqlite3

def _init_fts(conn):
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS soul_store_fts
        USING fts5(key, content, metadata)
    """)

def store(key: str, content: str, metadata: str = ""):
    # Insert into FTS table
    pass

def search(query: str, limit: int = 5) -> list[dict]:
    # FTS5 MATCH query
    pass
```

### Priority 3: Cognitive RAG Function

A Python equivalent of the Open Souls RAG pattern, integrated into `soul_engine.py`:

```python
# daemon/cognitive_rag.py
"""Cognitive RAG: brainstorm → search → inject."""

import rag

def build_rag_context(text: str, user_id: str, collections: list[str]) -> str:
    """Generate RAG context for prompt injection.

    Unlike Open Souls' multi-step RAG (brainstorm → parallel search → instruction),
    Claudius uses a simpler pattern: extract key terms from the message → search
    → format results. The brainstorm step would require an additional LLM call.
    """
    # Simple keyword extraction (no LLM needed)
    keywords = _extract_keywords(text)

    all_results = []
    for collection in collections:
        for keyword in keywords[:3]:
            results = rag.search(keyword, collection, limit=3)
            all_results.extend(results)

    if not all_results:
        return ""

    # Deduplicate and format
    seen = set()
    unique = []
    for r in all_results:
        key = r.get("content", "")[:100]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    context = "\n".join(
        f"- {r.get('content', '')[:300]}" for r in unique[:5]
    )

    return f"## Relevant Knowledge\n{context}"
```

### Integration Point in `soul_engine.py`

```python
# soul_engine.py:build_prompt() — add RAG context injection
def build_prompt(text, user_id, channel, thread_ts, is_first=False):
    # ... existing prompt assembly ...

    # RAG context (if enabled and collections configured)
    if config.RAG_ENABLED:
        rag_context = cognitive_rag.build_rag_context(
            text, user_id, config.RAG_COLLECTIONS
        )
        if rag_context:
            prompt_parts.append(rag_context)

    # ... rest of prompt ...
```

### Configuration

```python
# config.py additions
RAG_ENABLED = _env("RAG_ENABLED", "false").lower() == "true"
RAG_COLLECTIONS = _env("RAG_COLLECTIONS", "default").split(",")
RAG_MIN_SIMILARITY = float(_env("RAG_MIN_SIMILARITY", "0.6"))
RAG_MAX_RESULTS = int(_env("RAG_MAX_RESULTS", "5"))
```

### Estimated Effort

- `daemon/rag.py`: ~60 LOC (rlama wrapper)
- `daemon/soul_store.py`: ~80 LOC (SQLite FTS5)
- `daemon/cognitive_rag.py`: ~100 LOC (cognitive RAG function)
- Modified `soul_engine.py`: ~15 lines (RAG injection point)
- Modified `config.py`: ~5 lines (RAG settings)
- Tests: ~80 LOC
