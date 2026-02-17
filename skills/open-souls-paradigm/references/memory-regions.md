# Memory Regions — Extension Pattern

## Open Souls Pattern

Regions are named, lightweight containers that organize a WorkingMemory's memories. They solve the problem of context accumulation—as conversations grow, the LLM loses track of earlier details. Regions let you selectively include, exclude, and reorder context for each cognitive step.

### Default Regions

Every new soul starts with three regions:

```
WorkingMemory regions
+--------------------+
|      core          |  ← soul.ts personality (always present)
+--------------------+
|     summary        |  ← rolling conversation summary (subprocess)
+--------------------+
|     default        |  ← all other memories
+--------------------+
```

New memories without an explicit region go to `default`. Developer-defined regions are placed before `default` unless ordering is specified.

### Core API

**`withRegion(name, memory)`** — Add or replace a named region:

```typescript
workingMemory = workingMemory.withRegion("userNotes", {
  role: ChatMessageRoleEnum.System,
  content: "User prefers concise answers, is expert in Python.",
});
```

**`withRegionalOrder(regions[])`** — Explicit ordering (LLMs attend more to beginning/end of context):

```typescript
workingMemory = workingMemory.withRegionalOrder([
  "core", "userNotes", "default", "summary"
]);
```

**`withoutRegions(names[])`** — Remove regions before a cognitive step:

```typescript
// Remove verbose context for a quick decision
const slim = workingMemory.withoutRegions(["summary", "userNotes"]);
const [, choice] = await decision(slim, { description: "...", choices: [...] });
```

**`withOnlyRegions(names[])`** — Keep only specified regions:

```typescript
// Focus on goals for a targeted evaluation
const goals = workingMemory.withOnlyRegions(["goals"]);
const [, achieved] = await mentalQuery(goals, "Did the soul achieve the goal?");
```

### Memory Integrator

The `MemoryIntegrator` runs on every incoming perception, setting up regions before the mental process executes. It controls which regions are available per-process:

```typescript
const memoryIntegrator: MemoryIntegrator = async ({
  perception, workingMemory, currentProcess, soul
}) => {
  // Always load core personality
  workingMemory = workingMemory
    .withRegion("core", {
      role: ChatMessageRoleEnum.System,
      content: soul.staticMemories.core,
    })
    .withRegionalOrder("core", "summary", "default");

  // Per-process region configuration
  if (currentProcess === "researchProcess") {
    workingMemory = workingMemory.withRegionalOrder([
      "core", "rag-context", "userNotes", "default"
    ]);
  } else if (currentProcess === "casualChat") {
    workingMemory = workingMemory.withRegionalOrder([
      "core", "summary", "default"
    ]);
  }

  return workingMemory;
};
```

---

## Current Claudius Implementation

Claudius assembles a **flat prompt** in `soul_engine.py:build_prompt()`. The sections are logically distinct but not managed as named regions:

```python
# soul_engine.py — current prompt assembly (simplified)
sections = []
sections.append(soul_md)                    # personality (≈ "core" region)
sections.append(skills_md)                  # capabilities (first message only)
sections.append(soul_state_section)         # global state
sections.append(user_model_section)         # conditional (Samantha-Dreams gate)
sections.append(cognitive_instructions)     # XML output format
sections.append(fenced_user_message)        # untrusted input
prompt = "\n\n".join(sections)
```

The prompt is assembled once per message and sent as a single string. There is no mechanism to reorder sections, exclude sections for specific cognitive steps, or compose sections dynamically.

---

## Extension Blueprint

### Goal

Refactor `build_prompt()` to use named regions with ordering control. This enables:

1. Per-step context optimization (slim context for `mentalQuery`, full context for `externalDialog`)
2. RAG injection as a named region (see `rag-and-tools.md`)
3. Per-process region configuration (see `mental-processes.md`)
4. Conversation summarization as a managed region (see `subprocesses.md`)

### Schema Changes

Add a `region` column to `working_memory` table:

```sql
ALTER TABLE working_memory ADD COLUMN region TEXT DEFAULT 'default';
```

### New Module: `daemon/regions.py`

```python
# Region registry and ordering
class RegionManager:
    def __init__(self):
        self.regions: dict[str, list[str]] = {}  # name -> content sections
        self.order: list[str] = ["core", "summary", "context", "default"]

    def set_region(self, name: str, content: str) -> None:
        self.regions[name] = [content]

    def with_order(self, order: list[str]) -> 'RegionManager':
        new = RegionManager()
        new.regions = dict(self.regions)
        new.order = order
        return new

    def without(self, names: list[str]) -> 'RegionManager':
        new = RegionManager()
        new.regions = {k: v for k, v in self.regions.items() if k not in names}
        new.order = [r for r in self.order if r not in names]
        return new

    def assemble(self) -> str:
        sections = []
        for name in self.order:
            if name in self.regions:
                sections.extend(self.regions[name])
        # Include unordered regions at end
        for name, content in self.regions.items():
            if name not in self.order:
                sections.extend(content)
        return "\n\n".join(sections)
```

### Modified `build_prompt()`

```python
# soul_engine.py — refactored with regions
def build_prompt(text, user_id, channel, thread_ts, is_first=False):
    rm = RegionManager()
    rm.set_region("core", _load_soul())
    if is_first:
        rm.set_region("skills", _load_skills())
    state_section = soul_memory.format_for_prompt()
    if state_section:
        rm.set_region("context", state_section)
    if _should_inject_user_model(user_id, channel, thread_ts):
        model = user_models.load(user_id)
        if model:
            rm.set_region("user-model", f"## User Model\n\n{model}")
    rm.set_region("instructions", _COGNITIVE_INSTRUCTIONS)
    rm.set_region("default", _fence_message(text, user_id))
    return rm.assemble()
```

### Region Names for Claudius

| Region | Content | Always Present |
|--------|---------|----------------|
| `core` | soul.md personality | Yes |
| `skills` | skills.md capabilities | First message only |
| `context` | Soul state (project, mood, topic) | When non-default |
| `user-model` | Per-user personality profile | Conditional (Samantha-Dreams) |
| `summary` | Rolling conversation summary | When subprocess enabled |
| `rag-context` | Retrieved knowledge | When RAG enabled |
| `instructions` | Cognitive XML format spec | Yes |
| `default` | Fenced user message | Yes |

### Estimated Effort

- New file: `daemon/regions.py` (~80 LOC)
- Modified: `soul_engine.py` build_prompt() (~30 lines changed)
- Schema migration: 1 ALTER TABLE statement
- Tests: ~50 LOC for region ordering and assembly
