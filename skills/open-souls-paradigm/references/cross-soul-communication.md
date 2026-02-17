# Cross-Soul Communication — Extension Pattern

## Open Souls Pattern

The `useSharedContext` hook enables multiple souls to share persistent state and ephemeral presence through a common data store. Each soul can read, write, and observe changes made by others—enabling multi-soul coordination, collaborative behaviors, and real-time awareness.

### Shared Context API

```typescript
type GameState = {
  players: string[];
  gamePhase: 'lobby' | 'playing' | 'finished';
};

const { data, ready, update, awareness } = useSharedContext<GameState>('game-lobby');

// Wait for initial data load
await ready;

// Read shared state
console.log(data.players);

// Update with optimistic concurrency (auto-retries on conflict)
await update(current => ({
  ...current,
  players: [...current.players, 'NewPlayer']
}));

// Direct set (overwrites entirely)
await set({ players: [], gamePhase: 'lobby' });
```

### Ephemeral Presence (Awareness)

Track real-time presence without persisting to database:

```typescript
const { awareness } = useSharedContext('collaborative-session');

// Set local presence (visible to other souls)
awareness.setLocalStateField('status', 'typing');
awareness.setLocalStateField('cursor', { x: 100, y: 200 });

// Get all connected souls' presence
const allStates = awareness.getStates();
for (const [soulKey, state] of allStates) {
  console.log(`${soulKey}: ${state.status}`);
}
```

### Cross-Soul State Pattern

```typescript
// Soul A — updates shared state
const processA: MentalProcess = async ({ workingMemory }) => {
  const { update } = useSharedContext<GameState>('shared-game');
  await update(current => ({
    ...current,
    players: [...current.players, 'SoulA']
  }));
  return workingMemory;
};

// Soul B — reads Soul A's updates
const processB: MentalProcess = async ({ workingMemory }) => {
  const { data, ready } = useSharedContext<GameState>('shared-game');
  await ready;
  console.log("Players so far:", data.players);  // Includes SoulA
  return workingMemory;
};
```

### SharedContext Interface

```typescript
interface SharedContextFacade<T> {
  data: T;                                        // Current shared data
  ready: Promise<void>;                           // Resolves when loaded
  update: (updater: (current: T) => T) => Promise<void>;  // Optimistic update
  set: (data: T) => Promise<void>;                // Direct overwrite
  awareness: {
    localState: Record<string, Json>;
    setLocalState: (data: Record<string, Json>) => void;
    setLocalStateField: (field: string, value: Json) => void;
    getStates: () => Map<string, Record<string, Json>>;
  };
}
```

### Use Cases

- **Multi-soul games**: Shared game state, turn coordination
- **Collaborative assistants**: Multiple souls working on the same task
- **Real-time awareness**: Show which souls are active, thinking, speaking
- **Handoff coordination**: One soul transfers context to another

---

## Current Claudius Implementation

Claudius has **partial cross-session awareness** but no formal shared context system.

### What Exists

**Soul Registry** (`hooks/soul-registry.py`): Tracks all active Claude Code sessions with CWD, PID, model, channel binding, and last_active timestamp. Sessions can see sibling sessions via the registry.

```json
{
  "sessions": {
    "abc123": {
      "cwd": "~/Desktop/Programming",
      "pid": 12345,
      "model": "opus-4.6",
      "channel": "C0123",
      "last_active": "2026-02-16T10:30:00"
    }
  }
}
```

**Shared SQLite databases**: All sessions (terminal + all Slack threads) read/write the same `memory.db`. This means:
- Soul state updates from one session are visible in others
- User model updates from a DM carry over to channel mentions
- Working memory entries are per-thread but queryable across threads

### What's Missing

- No structured shared context with typed state
- No optimistic concurrency (multiple writers could conflict)
- No ephemeral presence (no real-time awareness of what other sessions are doing)
- No explicit cross-session messaging

---

## Extension Blueprint

### Goal

Enable multiple Claudius instances to share typed state and coordinate, building on the existing SQLite infrastructure.

### New Table: `shared_context`

```python
# daemon/shared_context.py
"""Cross-soul shared context with optimistic concurrency."""

import json
import sqlite3
import logging

log = logging.getLogger("claudius.shared_context")

_DB_PATH = "memory.db"

def _init():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_context (
            context_key TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get(context_key: str) -> dict:
    """Read shared context."""
    conn = sqlite3.connect(_DB_PATH)
    row = conn.execute(
        "SELECT data, version FROM shared_context WHERE context_key = ?",
        (context_key,)
    ).fetchone()
    conn.close()
    if row:
        return {"data": json.loads(row[0]), "version": row[1]}
    return {"data": {}, "version": 0}

def update(context_key: str, updater_fn, max_retries: int = 3) -> dict:
    """Update with optimistic concurrency control."""
    for attempt in range(max_retries):
        current = get(context_key)
        new_data = updater_fn(current["data"])

        conn = sqlite3.connect(_DB_PATH)
        cursor = conn.execute(
            """INSERT INTO shared_context (context_key, data, version)
               VALUES (?, ?, 1)
               ON CONFLICT(context_key) DO UPDATE
               SET data = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
               WHERE version = ?""",
            (context_key, json.dumps(new_data), json.dumps(new_data), current["version"])
        )

        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return {"data": new_data, "version": current["version"] + 1}

        conn.close()
        log.warning(f"Concurrency conflict on {context_key}, retry {attempt + 1}")

    raise RuntimeError(f"Failed to update {context_key} after {max_retries} retries")
```

### Integration with Soul Engine

```python
# soul_engine.py — inject shared context into prompt
def build_prompt(text, user_id, channel, thread_ts, is_first=False):
    # ... existing prompt assembly ...

    # Shared context (if any relevant contexts are configured)
    if config.SHARED_CONTEXTS:
        for ctx_key in config.SHARED_CONTEXTS:
            ctx = shared_context.get(ctx_key)
            if ctx["data"]:
                prompt_parts.append(
                    f"## Shared Context: {ctx_key}\n{json.dumps(ctx['data'], indent=2)}"
                )
```

### Estimated Effort

- `daemon/shared_context.py`: ~80 LOC
- Modified `soul_engine.py`: ~10 lines (context injection)
- Modified `config.py`: ~3 lines (`SHARED_CONTEXTS` list)
- Tests: ~50 LOC (concurrency, read/write, conflict resolution)
