# Open Souls Functional Programming Principles in Claudicle

> "Side effects are described as data, applied at the boundary."

This document maps the Open Souls Paradigm's functional programming principles to their Claudicle Python implementations. It serves as the constitutional reference for all code in this repository.

---

## 1. Immutability: Frozen Dataclasses & Copy-on-Write

**Open Souls (TypeScript):** `WorkingMemory` is an immutable class. Every operation (`withMemory()`, `slice()`, `filter()`, `concat()`) returns a new instance. The original is never mutated.

**Claudicle (Python):** `@dataclass(frozen=True)` enforces immutability at the language level. Any attempt to mutate a frozen field raises `FrozenInstanceError`. New instances are created via `dataclasses.replace()`.

### Three Frozen Types

| Type | File | Purpose |
|------|------|---------|
| `MemoryEntry` | `daemon/memory/snapshot.py:33-71` | Single working memory record (entry_type, content, verb, metadata, region, trace_id) |
| `WorkingMemorySnapshot` | `daemon/memory/snapshot.py:74-116` | Immutable thread state: entries tuple + soul_state dict |
| `CognitiveOutput` | `daemon/memory/snapshot.py:123-233` | Immutable effect description from a cognitive cycle |

### Copy-on-Write Pattern

```python
# TypeScript (Open Souls)
memory = memory.withMemory({ role: "assistant", content: "hello" })

# Python (Claudicle)
snapshot = snapshot.with_entry(MemoryEntry(entry_type="externalDialog", content="hello"))
# snapshot is unchanged — with_entry returns a NEW WorkingMemorySnapshot

# Under the hood:
def with_entry(self, entry: MemoryEntry) -> WorkingMemorySnapshot:
    return replace(self, entries=self.entries + (entry,))
```

### Why Tuples, Not Lists

Collections use `tuple`, not `list`:
- `entries: tuple[MemoryEntry, ...]` — immutable sequence
- `soul_state_updates: tuple[tuple[str, str], ...]` — immutable key-value pairs

Tuple concatenation (`self.entries + (new_entry,)`) creates a new tuple. Lists would allow in-place mutation via `.append()`, breaking the immutability contract.

---

## 2. Pure/Impure Boundary

**Open Souls:** Cognitive steps are pure functions: `(memory, input) → [newMemory, output]`. The runtime applies side effects.

**Claudicle:** The cognitive pipeline has exactly one pure function and one impure boundary.

### The Pure Function

`parse_cognitive_response()` in `daemon/engine/soul_engine.py:179-309`

- **Input:** Raw LLM response string + config flags
- **Output:** `(dialogue_text: str, output: CognitiveOutput)`
- **Guarantee:** Zero DB reads. Zero DB writes. Zero imports of mutable modules.
- **What it does:** Parses XML tags (`<internal_monologue>`, `<external_dialogue>`, etc.), extracts content, builds a `CognitiveOutput` via copy-on-write chaining.

```python
output = (CognitiveOutput()
    .with_entry("internalMonologue", monologue, verb=verb, trace_id=trace_id)
    .with_entry("externalDialog", dialogue, verb=verb, trace_id=trace_id)
    .with_soul_state("emotionalState", "engaged"))
```

### The Impure Boundary

`apply_output()` in `daemon/memory/snapshot.py:266-312`

- **Input:** Immutable `CognitiveOutput` + channel + thread_ts
- **Effect:** Atomically commits to 4 tables: working_memory, soul_memory, user_models, dossiers
- **This is the ONLY place where cognitive cycle side effects hit the DB.**

### The Thin Wrapper

`parse_response()` in `daemon/engine/soul_engine.py:312-383`

Bridges pure and impure: resolves trace_id, calls the pure parser, then calls `apply_output()` + observability logging at the boundary.

### The Rule

**Never import DB modules inside pure functions.** If a function imports `working_memory`, `soul_memory`, or `user_models`, it is impure and belongs at the boundary. The pure core (`parse_cognitive_response`, `build_context`, `build_reflection_prompt`) must remain free of storage dependencies.

---

## 3. CognitiveOutput as Effect Description

**Open Souls:** Cognitive steps return `[newMemory, output]`. The return value *describes* what should happen; the runtime *applies* it.

**Claudicle:** `CognitiveOutput` is not a mutation—it is a **description of intended effects**, reified as an immutable data structure.

```python
# CognitiveOutput describes 4 categories of effects:
output = CognitiveOutput(
    entries=(...),              # Working memory entries to add
    soul_state_updates=(...),   # Soul state key-value pairs to set
    user_model_update="...",    # User model content to save
    dossier_updates=(...),      # Dossier entries to create/update
)

# Nothing has happened yet. The output is pure data.
# apply_output() is the impure boundary that makes it real:
apply_output(output, channel="slack:C04ABC", thread_ts="1234567890.123456")
```

### Composing Effects

Two `CognitiveOutput` instances can be merged immutably:

```python
combined = output_a.merge(output_b)
# entries: concatenated (all entries from both)
# soul_state_updates: concatenated
# user_model_update: last-write-wins (output_b's value if present)
# dossier_updates: concatenated
```

### Checking for No-Ops

```python
if output.is_empty:
    # No side effects to apply — skip the boundary call
    pass
```

---

## 4. Region Semantics

**Open Souls (TypeScript):**
- `memory.withRegion("analysis", ...memories)` — add memories to a named region
- `memory.withoutRegions("analysis")` — remove all memories in a region
- `memory.withOnlyRegions("core", "summary")` — keep only specified regions

**Claudicle (Python):** Regions are implemented as a `region` column in the `working_memory` SQLite table (`daemon/memory/working_memory.py:53`).

### Region Operations

| Operation | Open Souls | Claudicle | File |
|-----------|-----------|-----------|------|
| Add to region | `withRegion(name, ...memories)` | `add(..., region="name")` | `working_memory.py:96-134` |
| Read region | `withOnlyRegions(name)` | `get_region(channel, thread_ts, region)` | `working_memory.py:220-231` |
| Read multiple regions | `withOnlyRegions(a, b)` | `get_regions(channel, thread_ts, [a, b])` | `working_memory.py:348-366` |
| List regions | — | `get_region_names(channel, thread_ts)` | `working_memory.py:234-243` |
| Replace region | `withoutRegions(name).withRegion(name, ...)` | `replace_region(channel, thread_ts, region, entries)` | `working_memory.py:246-276` |
| Exclude on read | `filter(m => m.region !== name)` | `get_recent(..., exclude_regions=[name])` | `working_memory.py:189-217` |

### Snapshot-Level Regions

`WorkingMemorySnapshot` also supports region filtering:

```python
snapshot = load_snapshot(channel, thread_ts)
default_entries = snapshot.get_region("default")    # tuple of MemoryEntry
all_regions = snapshot.get_regions()                 # set of region names
```

### When to Use Regions

- `"default"` — conversation flow (messages, monologue, dialogue)
- `"summary"` — compressed memory from Hypermnesia (excluded from `get_recent()` by default)
- `"lessons"` — subdaimon cross-project insights
- `"comms"` — subdaimon communication logs
- Custom — temporary analysis context, injected and removed within a cycle

---

## 5. Composition Patterns

### Copy-on-Write Chaining

```python
# Build up effects step by step (each returns a new CognitiveOutput)
output = (CognitiveOutput()
    .with_entry("internalMonologue", "The user is frustrated", verb="sensed")
    .with_entry("externalDialog", "I understand. Let me help.", verb="said")
    .with_soul_state("emotionalState", "empathetic")
    .with_user_model("Prefers direct solutions", target_id="tom"))
```

### Snapshot → Pipeline → Output → Apply

The canonical data flow:

```
load_snapshot(channel, thread_ts)     # Impure: reads DB → returns frozen snapshot
    ↓
build_prompt(snapshot, ...)           # Pure: assembles context string
    ↓
LLM call → raw_response              # External: API call
    ↓
parse_cognitive_response(raw, ...)    # Pure: parses → returns (dialogue, CognitiveOutput)
    ↓
apply_output(output, channel, ...)    # Impure: commits to DB
```

### Process Memory (useProcessMemory Analog)

`daemon/memory/process_memory.py` maps to Open Souls' `useProcessMemory` hook:

```python
# Open Souls
const counter = useProcessMemory(sessionId, "processName", "counter", 0);

# Claudicle
count = process_memory.get("hypermnesia", "compression_count", default=0)
process_memory.set("hypermnesia", "compression_count", count + 1)
```

Backed by `soul_memory` with namespaced keys: `proc:{subprocess}:{key}` or `proc:{subprocess}:{channel}:{thread_ts}:{key}`.

### Subdaimon Memory Protocol

Subdaimones are read-only (no DB access). They interact with memory through an output protocol:

1. **Boot:** `soul-context.py --agent {name}` injects prior memory as formatted text
2. **Work:** Subdaimon reasons over the injected context (pure computation)
3. **Output:** Subdaimon emits structured markdown with `## Memory Updates`
4. **Persist:** Calling session parses output and calls boundary functions (`store_lesson()`, `store_communication()`)

This preserves the pure/impure boundary: subdaimones are pure observers; the calling session handles persistence.

---

## Anti-Patterns

### Never Do This

```python
# ❌ Importing DB modules in a pure function
def parse_cognitive_response(raw, user_id, trace_id):
    from memory import working_memory  # VIOLATION: pure function now has DB dependency
    working_memory.add(...)            # VIOLATION: side effect in pure code

# ❌ Mutating a frozen dataclass
snapshot.entries.append(new_entry)     # TypeError: tuples don't support append
snapshot.soul_state["key"] = "value"   # FrozenInstanceError

# ❌ Using lists instead of tuples for immutable collections
@dataclass(frozen=True)
class Bad:
    entries: list[MemoryEntry] = field(default_factory=list)  # list is mutable!

# ❌ Side effects scattered across the pipeline
def step_one(snapshot):
    working_memory.add(...)  # Side effect here
    return modified_snapshot
def step_two(snapshot):
    soul_memory.set(...)     # Side effect here too
    return modified_snapshot
# Effects should be collected in CognitiveOutput and applied ONCE at the boundary
```

### Always Do This

```python
# ✅ Keep pure functions free of imports
def parse_cognitive_response(raw, user_id, trace_id):
    # Only uses: dataclasses.replace(), string parsing, CognitiveOutput
    output = CognitiveOutput().with_entry(...)
    return (dialogue, output)

# ✅ Collect effects, apply at boundary
output = CognitiveOutput()
for step in cognitive_steps:
    output = output.with_entry(step.entry_type, step.content)
apply_output(output, channel, thread_ts)  # ONE boundary call

# ✅ Use tuples for immutable collections
entries: tuple[MemoryEntry, ...] = ()

# ✅ Create new instances via replace
new_snapshot = replace(snapshot, entries=snapshot.entries + (new_entry,))
```

---

## Summary

| Principle | Open Souls | Claudicle |
|-----------|-----------|-----------|
| Immutability | `WorkingMemory` class | `@dataclass(frozen=True)` + `tuple` |
| Copy-on-write | `withMemory()`, spread ops | `with_*()` methods via `dataclasses.replace()` |
| Pure/impure | CognitiveStep returns `[memory, output]` | `parse_cognitive_response()` → `apply_output()` |
| Effect description | Return values describe effects | `CognitiveOutput` as immutable data |
| Regions | `withRegion()` / `withoutRegions()` | `region` column + `get_region()` / `replace_region()` |
| Process memory | `useProcessMemory()` hook | `process_memory.get()` / `.set()` |
| Composition | Chain cognitive steps | Copy-on-write chaining + `merge()` |
