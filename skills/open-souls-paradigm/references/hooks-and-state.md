# Hooks and State — Extension Pattern

## Open Souls Pattern

The Open Souls Engine provides a set of hooks for accessing capabilities and persistent state within mental processes and subprocesses. Each hook provides a specific interface for the soul to interact with its environment.

### useActions — External Interactions

```typescript
const { speak, log, dispatch, scheduleEvent, expire } = useActions();
```

| Action | Purpose |
|--------|---------|
| `speak(content, verb?)` | Dispatch speech to frontend (supports streaming) |
| `log(...args)` | Debug logging to Soul Engine debugger |
| `dispatch(event)` | Generalized interaction request to frontend |
| `scheduleEvent(opts)` | Schedule a future perception (see `scheduled-events.md`) |
| `expire()` | Terminate the soul |

**Critical pattern:** `speak(stream)` and `dispatch({ content: stream })` forward `AsyncIterable` streams directly to the frontend — the backend never consumes the stream.

### useSoulMemory — Global Persistent State

Persists across all mental process transitions. Available to all processes and subprocesses.

```typescript
const userName = useSoulMemory("userName", "");  // key, initialValue
const mood = useSoulMemory("mood", "neutral");

// Read
console.log(userName.current);

// Write (persists immediately)
userName.current = "Alice";
mood.current = "engaged";
```

**Scope:** Soul-wide. Survives process transitions. Available everywhere.

### useProcessMemory — Per-Process State

Persists while the process continues to be invoked. Resets on process transition.

```typescript
const counter = useProcessMemory(0);  // initialValue
const wasProvoked = useProcessMemory(false);

counter.current++;
wasProvoked.current = true;
// Resets to initial values when soul transitions to a different process
```

**Scope:** Per-process. Resets on transition. Useful for invocation counting, conversation state.

### useProcessManager — Process Lifecycle

```typescript
const {
  invocationCount,           // Number of times this process has been invoked
  previousMentalProcess,     // Reference to the prior process
  setNextProcess,            // Set transition without returning
  wait,                      // Pause execution (ms)
  pendingScheduledEvents,    // Array of scheduled events
  cancelScheduledEvent,      // Cancel by ID
} = useProcessManager();
```

### usePerceptions — Perception Queue

```typescript
const { invokingPerception, pendingPerceptions } = usePerceptions();

// Current perception being processed
invokingPerception.action;   // "says", "poked", "followUpDue"
invokingPerception.content;  // Message text
invokingPerception.name;     // User name

// Queue monitoring (for interrupt detection)
if (pendingPerceptions.current.length > 5) {
  // User is sending many messages quickly
}
```

### useSoulStore / useBlueprintStore / useOrganizationStore — Vector Search

Three scopes of key-value storage with automatic embedding and vector similarity search:

```typescript
const { set, fetch, search, remove } = useSoulStore();      // Per-soul
const blueprintStore = useBlueprintStore();                   // Per-blueprint
const orgStore = useOrganizationStore();                      // Organization-wide

// Store
set("user-preference", "prefers formal communication");

// Retrieve
const pref = await fetch("user-preference");

// Vector search
const results = await search("communication style");
// [{ key, content, similarity, metadata }]
```

### useSharedContext — Cross-Soul Communication

Multi-soul coordination with persistent data and ephemeral presence:

```typescript
const { data, ready, update, awareness } = useSharedContext<GameState>('game-lobby');

await ready;
console.log(data.players);

await update(current => ({ ...current, players: [...current.players, 'New'] }));

// Ephemeral presence
awareness.setLocalStateField('status', 'typing');
const allStates = awareness.getStates();
```

### useTool — Client-Side Tool Invocation

Blocking tool calls from blueprint code to client-side code:

```typescript
const visit = useTool<{ url: string }, { markdown: string }>("visit");
const result = await visit({ url: "https://example.com" });
```

30-second timeout. Client registers tools via `soul.registerTool()`.

### useRag — RAG Pipeline Integration

```typescript
const { search, withRagContext } = useRag('knowledge-bucket');
const results = await search('query');
const enhancedMemory = await withRagContext(workingMemory);
```

---

## Claudius Mapping

| Open Souls Hook | Claudius Equivalent | Status |
|-----------------|---------------------|--------|
| `useActions.speak()` | `slack_post.py` / terminal output | Implemented |
| `useActions.log()` | Python `logging` module | Implemented |
| `useActions.dispatch()` | Not implemented | Extension (event bus) |
| `useActions.scheduleEvent()` | Not implemented | Extension (see `scheduled-events.md`) |
| `useActions.expire()` | Not implemented | Extension (session cleanup) |
| `useSoulMemory` | `soul_memory.py` | Implemented |
| `useProcessMemory` | Not implemented | Extension (per-process SQLite) |
| `useProcessManager` | Not implemented | Extension (see `mental-processes.md`) |
| `usePerceptions` | `slack_listen.py` inbox | Partially implemented |
| `useSoulStore` | Not implemented | Extension (rlama or SQLite FTS) |
| `useBlueprintStore` | Not implemented | Extension (see `rag-and-tools.md`) |
| `useSharedContext` | Not implemented | Extension (see `cross-soul-communication.md`) |
| `useTool` | Claude Code tools (Read, Bash, etc.) | Different model |
| `useRag` | Not implemented | Extension (rlama integration) |

### What's Implemented

**`soul_memory.py`** (120 LOC) — Maps to `useSoulMemory`:
- `soul_memory.get(key)` → read value
- `soul_memory.set(key, value)` → write value
- `soul_memory.format_for_prompt()` → render as markdown for prompt injection
- Persists to SQLite `soul_memory` table. Available across all threads and sessions.

**`working_memory.py`** (179 LOC) — Partial map to `useProcessMemory`:
- Per-thread metadata store (not per-process)
- 72h TTL (not process-transition reset)
- Stores all cognitive step outputs for analytics
- NOT injected into prompts (conversation continuity via `--resume`)

**Perception queue:** `slack_listen.py` writes to `inbox.jsonl`, `slack_check.py` reads. This is a simplified perception queue — no `action` field classification, no `pendingPerceptions` monitoring.

### What's Not Implemented

1. **`useProcessMemory`** — Would need per-process SQLite table with reset-on-transition logic
2. **`useProcessManager`** — Depends on mental processes extension
3. **`dispatch()`** — Would need an event bus for custom action routing
4. **Vector stores** — Would integrate with `rlama` (local RAG) or SQLite FTS5
5. **`useSharedContext`** — Would use shared `memory.db` with file locking
6. **`useTool`** — Claude Code already has tools; the soul engine would need to expose them to cognitive steps
7. **`useRag`** — Would wrap rlama search into a cognitive function

---

## Extension Blueprint

### Priority 1: useProcessMemory

Requires the mental processes extension. Add per-process storage that resets on transition:

```python
# daemon/process_memory.py
import sqlite3

def get(process_name: str, key: str, default=None):
    """Get process-scoped value."""
    # Query from process_memory table
    pass

def set(process_name: str, key: str, value):
    """Set process-scoped value."""
    pass

def reset(process_name: str):
    """Clear all state for a process (called on transition)."""
    pass
```

### Priority 2: Event Dispatch

Add a simple event bus for `dispatch()`:

```python
# daemon/event_bus.py
_handlers: dict[str, list[Callable]] = {}

def on(event: str, handler: Callable):
    _handlers.setdefault(event, []).append(handler)

def dispatch(event: str, data: dict):
    for handler in _handlers.get(event, []):
        handler(data)
```

### Priority 3: Vector Store Integration

Wrap rlama for `useSoulStore`/`useBlueprintStore`:

```python
# daemon/soul_store.py
import subprocess

def search(query: str, collection: str = "default", limit: int = 5):
    """Semantic search via rlama."""
    result = subprocess.run(
        ["rlama", "search", collection, query, "--top", str(limit)],
        capture_output=True, text=True
    )
    return _parse_results(result.stdout)

def set(key: str, content: str, collection: str = "default"):
    """Store content for vector search."""
    # Would need rlama API for document ingestion
    pass
```

### Estimated Effort

- `process_memory.py`: ~60 LOC + schema migration
- `event_bus.py`: ~30 LOC
- `soul_store.py`: ~80 LOC (rlama wrapper)
- Modified: `soul_engine.py` — expose hooks to cognitive pipeline
- Tests: ~100 LOC across all three modules
