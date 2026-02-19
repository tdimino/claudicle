# Additional Cognitive Steps — Extension Pattern

## Open Souls Pattern

Beyond `externalDialog`, `internalMonologue`, and `mentalQuery`, the Open Souls standard library provides several more cognitive steps. Each is a pure function created with `createCognitiveStep` that takes WorkingMemory + instructions, calls an LLM, and returns `[WorkingMemory, typedResult]`.

### decision — Choice from Options

Choose between discrete alternatives using structured output.

```typescript
const [memory, choice] = await decision(workingMemory, {
  description: "How should I respond to the user?",
  choices: ["friendly", "formal", "playful"]
});
// choice: string (one of the provided options)
// memory now contains: "Samantha decided: friendly"
```

**Schema:** `{ decision: string }` — constrained to provided choices.

**Memory behavior:** Adds `"{soulName} decided: {choice}"` to WorkingMemory so the soul remembers its reasoning in subsequent steps.

### brainstorm — Idea Generation

Generate multiple ideas as a typed array.

```typescript
const [memory, ideas] = await brainstorm(
  workingMemory,
  "Think of 3 creative approaches to help the user learn programming"
);
// ideas: string[] — array of generated ideas
```

**Schema:** `{ newIdeas: string[] }`

**Use cases:** Creative problem solving, RAG query generation (brainstorm → parallel search), exploring solution approaches.

### instruction — Direct System Command

System-level instruction to the LLM. More general than `externalDialog` — used for internal computation, not user-facing output.

```typescript
const [memory, result] = await instruction(
  workingMemory,
  "Summarize the conversation in three sentences"
);
// result: string — the LLM's response to the instruction
```

Supports streaming: `{ stream: true }` returns `AsyncIterable<string>`.

### conversationNotes — Summarization

Generate structured summaries of conversations for memory compression.

```typescript
const [memory, notes] = await conversationNotes(
  workingMemory,
  "Summarize the key points discussed so far"
);
```

**Use cases:** Memory compression, rolling summaries, context window management.

### userNotes — User Model Updates

Generate updated observations about the user for persistent storage.

```typescript
const [memory, updatedProfile] = await userNotes(workingMemory);
// updatedProfile: string — bullet-point observations about the user
```

Works with `useProcessMemory` for persistent storage:
```typescript
const userModel = useProcessMemory("Unknown User");
const [, notes] = await userNotes(workingMemory);
userModel.current = notes;
```

### dreamQuery — Specialized Detection

More sophisticated than `mentalQuery` — designed for complex pattern detection and multi-factor analysis.

```typescript
const [memory, detected] = await dreamQuery(
  workingMemory,
  "Detect if the user is attempting to manipulate the conversation"
);
```

### summarize — Memory Compression

Efficient memory compression for long conversations:

```typescript
const oldMemories = workingMemory.slice(0, -10);
const [summaryMemory, summary] = await summarize(oldMemories);

memory = workingMemory.withRegion("summary", {
  role: ChatMessageRoleEnum.System,
  content: summary
}).slice(-10);  // Keep last 10 messages
```

### Per-Step Model Selection

Each cognitive step can specify its own model. Use cheap models for gates, expensive models for generation:

```typescript
// Fast gate check
const [mem1, shouldRespond] = await mentalQuery(
  workingMemory, "Should I respond?", { model: "gemini-flash" }
);

// Complex reasoning
const [mem2, analysis] = await internalMonologue(
  mem1, "Deep analysis", { model: "gpt-4o" }
);

// User-facing response
const [mem3, stream] = await externalDialog(
  mem2, "Respond", { stream: true, model: "kimi-k2" }
);
```

---

## Current Claudicle Implementation

Claudicle implements 6 cognitive steps via XML tags, all executed in a single LLM call:

| Step | XML Tag | Status |
|------|---------|--------|
| `internalMonologue` | `<internal_monologue>` | Implemented |
| `externalDialog` | `<external_dialogue>` | Implemented |
| `mentalQuery` (user) | `<user_model_check>` | Implemented |
| `userNotes` | `<user_model_update>` | Implemented |
| `mentalQuery` (soul) | `<soul_state_check>` | Implemented |
| Soul state update | `<soul_state_update>` | Implemented |
| `decision` | — | Not implemented |
| `brainstorm` | — | Not implemented |
| `instruction` | — | Not implemented |
| `summarize` | — | Not implemented |
| `conversationNotes` | — | Not implemented |
| `dreamQuery` | — | Not implemented |

The `decision` and `brainstorm` steps are noted in the existing `cognitive-steps.md` reference as "handled implicitly by soul.md personality" and "served by internal monologue," respectively.

The current implementation handles all steps in a **single LLM call** — the prompt requests all XML-tagged sections at once, and `parse_response()` extracts them. This is efficient (one API call) but inflexible (no per-step model selection, no conditional step execution).

### Extension Points

- **`soul_engine.py:69-127`** — `_COGNITIVE_INSTRUCTIONS` defines the XML format spec
- **`soul_engine.py:202-298`** — `parse_response()` extracts tagged sections
- **`soul_engine.py:387-398`** — `_extract_tag()` handles XML extraction

---

## Extension Blueprint

### Goal

Add `decision`, `brainstorm`, `instruction`, and `summarize` as new XML cognitive steps. These enable:

1. **`<decision>`** — Explicit choice-making with constrained options, useful for process transitions and tool selection
2. **`<brainstorm>`** — Multi-idea generation for RAG query generation and creative problem solving
3. **`<summary>`** — Context compression for the `summary` memory region
4. **`<instruction>`** — Internal computation for structured data extraction

### New XML Tags

Add to `_COGNITIVE_INSTRUCTIONS` in `soul_engine.py`:

```python
# New optional cognitive steps

## Decision (when a choice must be made)
_DECISION_INSTRUCTION = """
<decision options="option1,option2,option3">
chosen_option
</decision>
"""

## Brainstorm (when multiple ideas are needed)
_BRAINSTORM_INSTRUCTION = """
<brainstorm count="3">
- idea one
- idea two
- idea three
</brainstorm>
"""

## Summary (when conversation is getting long)
_SUMMARY_INSTRUCTION = """
<summary>
Compressed summary of the conversation so far.
</summary>
"""
```

### New Extraction in `parse_response()`

```python
def parse_response(raw, user_id, channel, thread_ts):
    # ... existing extractions ...

    # Decision extraction
    decision_match = re.search(
        r'<decision\s+options="([^"]+)">(.*?)</decision>',
        raw, re.DOTALL
    )
    if decision_match:
        options = decision_match.group(1).split(",")
        choice = decision_match.group(2).strip()
        working_memory.store(
            channel, thread_ts, user_id,
            entry_type="decision",
            content=f"options={options}, chose={choice}",
        )

    # Brainstorm extraction
    brainstorm_match = _extract_tag(raw, "brainstorm")
    if brainstorm_match:
        ideas = [line.lstrip("- ").strip()
                 for line in brainstorm_match.splitlines()
                 if line.strip()]
        working_memory.store(
            channel, thread_ts, user_id,
            entry_type="brainstorm",
            content=json.dumps(ideas),
        )

    # Summary extraction
    summary = _extract_tag(raw, "summary")
    if summary:
        soul_memory.set("conversationSummary", summary[:500])
        working_memory.store(
            channel, thread_ts, user_id,
            entry_type="summary",
            content=summary,
        )
```

### Conditional Step Injection

Not all steps are needed every turn. Use the process system (see `mental-processes.md`) to include/exclude steps:

```python
# Process definition controls which steps appear in the prompt
COGNITIVE_STEPS = [
    "internal_monologue",   # Always
    "external_dialogue",    # Always
    "decision",             # Only when choices needed
    "user_model_check",     # Always
    "user_model_update",    # Conditional
]
```

### Working Memory Entry Types

| Entry Type | Source | Stored Value |
|------------|--------|-------------|
| `userMessage` | User input | Raw text |
| `internalMonologue` | `<internal_monologue>` | Monologue text |
| `externalDialog` | `<external_dialogue>` | Dialogue text + verb |
| `mentalQuery` | `<user_model_check>`, `<soul_state_check>` | `true` or `false` |
| `decision` | `<decision>` | Options + chosen option |
| `brainstorm` | `<brainstorm>` | JSON array of ideas |
| `summary` | `<summary>` | Compressed conversation |
| `toolAction` | Tool invocations | Tool name + result |

### Estimated Effort

- Modified: `soul_engine.py` — add 3 new tag instructions (~30 lines) + 3 new extractions (~40 lines)
- Modified: `working_memory.py` — no changes (already supports arbitrary `entry_type`)
- New instructions: ~20 lines of XML instruction text per step
- Tests: ~60 LOC for new tag extraction
