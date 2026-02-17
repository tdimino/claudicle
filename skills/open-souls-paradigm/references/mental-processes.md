# Mental Processes — Extension Pattern

## Open Souls Pattern

A `MentalProcess` is a stateful behavior mode triggered by incoming perceptions. The soul is a state machine: it has one active mental process at a time, and each process can transition to another. This enables distinct behavioral modes (greeting, problem-solving, frustrated, proactive) that respond differently to the same input.

### Core API

```typescript
const exampleProcess: MentalProcess = async ({ workingMemory, params }) => {
  // Operations on working memory...
  return workingMemory;
};
```

**Parameters:**
- `workingMemory` — current memory state, containing the latest perception
- `params` — static props passed during transition (e.g. `{ wasProvoked: true }`)

### Return Types

A mental process controls both memory state and process transitions:

1. **`WorkingMemory`** — Updated memory, same process continues
2. **`[WorkingMemory, MentalProcess]`** — Updated memory + transition to new process (next perception)
3. **`[WorkingMemory, MentalProcess, { ...params, executeNow }]`** — Transition with params, optionally execute immediately

### State Transitions

```typescript
// introduction.ts — greet, then hand off
const introduction: MentalProcess = async ({ workingMemory }) => {
  const { speak } = useActions();
  const [output, greeting] = await externalDialog(workingMemory, "Say hello");
  speak(greeting);
  return [output, conversationProcess];  // Next perception goes to conversationProcess
};

// conversationProcess.ts — normal chat, can escalate
const conversationProcess: MentalProcess = async ({ workingMemory }) => {
  const { speak } = useActions();
  const [mem, isAngry] = await mentalQuery(workingMemory, "Is the user angry?");
  if (isAngry) {
    return [mem, deescalationProcess, { executeNow: true }];
  }
  const [output, response] = await externalDialog(mem, "Respond normally");
  speak(response);
  return output;
};
```

### `executeNow`

When a process returns `{ executeNow: true }`, the next process runs immediately using the same perception — no new user input required. This enables chained transitions within a single turn.

### Process Lifecycle

Each process is defined in its own file under `mentalProcesses/`. The `initialProcess` (exported from `soul.ts`) is the entry point. The `useProcessManager` hook provides lifecycle control:

```typescript
const { invocationCount, previousMentalProcess, setNextProcess } = useProcessManager();

if (invocationCount === 0) {
  // First time this process runs
}

if (previousMentalProcess === greetingProcess) {
  // We came from the greeting
}
```

---

## Current Claudius Implementation

Claudius runs the **same cognitive pipeline** for every message. There is no process state machine — `soul_engine.py` always executes the same sequence:

```
build_prompt() → LLM → parse_response()
  → internal_monologue (always)
  → external_dialogue (always)
  → user_model_check (always)
  → user_model_update (conditional)
  → soul_state_check (periodic, every Nth turn)
  → soul_state_update (conditional)
```

The `emotionalState` field in `soul_memory` (`neutral → engaged → focused → frustrated → sardonic`) is a lightweight substitute — it modulates verb selection and tone, but doesn't change the cognitive step sequence.

---

## Extension Blueprint

### Goal

Add a process state machine so different behavioral modes run different cognitive step sequences. This enables:

1. A `greeting` process with personality introduction and no soul state check
2. A `deepWork` process that skips user model updates and focuses on tool use
3. A `frustrated` process with shorter responses and sardonic verbs
4. A `proactive` process that initiates contact when idle

### New Directory: `daemon/processes/`

Each process is a Python module exporting a `run()` function:

```python
# daemon/processes/main_process.py
"""Default conversational process — the standard cognitive pipeline."""

COGNITIVE_STEPS = [
    "internal_monologue",
    "external_dialogue",
    "user_model_check",
    "user_model_update",    # conditional
    "soul_state_check",     # periodic
    "soul_state_update",    # conditional
]

def should_transition(parse_result: dict) -> str | None:
    """Check if we should transition to a different process.
    Returns process name or None to stay."""
    emotional_state = parse_result.get("soul_state", {}).get("emotionalState")
    if emotional_state == "frustrated":
        return "frustrated"
    return None
```

```python
# daemon/processes/frustrated.py
"""Frustrated process — shorter responses, sardonic tone, faster resolution."""

COGNITIVE_STEPS = [
    "internal_monologue",
    "external_dialogue",
    # Skip user model updates when frustrated
    "soul_state_check",
    "soul_state_update",
]

# Override cognitive instructions for this process
INSTRUCTION_OVERRIDES = {
    "external_dialogue": "Keep responses to 1-2 sentences. Use verbs: pointed out, corrected, insisted.",
}

def should_transition(parse_result: dict) -> str | None:
    emotional_state = parse_result.get("soul_state", {}).get("emotionalState")
    if emotional_state in ("neutral", "engaged"):
        return "main_process"
    return None
```

### Soul Memory Key: `currentProcess`

```python
# New key in SOUL_MEMORY_DEFAULTS
SOUL_MEMORY_DEFAULTS = {
    "currentProject": "",
    "currentTask": "",
    "currentTopic": "",
    "emotionalState": "neutral",
    "conversationSummary": "",
    "currentProcess": "main_process",  # NEW
}
```

### Process Router in `soul_engine.py`

```python
# soul_engine.py — new process routing logic
import importlib

def _load_process(name: str):
    """Load a process module from daemon/processes/."""
    try:
        return importlib.import_module(f"processes.{name}")
    except ImportError:
        log.warning(f"Process {name} not found, falling back to main_process")
        return importlib.import_module("processes.main_process")

def build_prompt(text, user_id, channel, thread_ts, is_first=False):
    current_process = soul_memory.get("currentProcess") or "main_process"
    process = _load_process(current_process)

    # Use process-specific cognitive step list
    instructions = _build_cognitive_instructions(process.COGNITIVE_STEPS)

    # Apply any instruction overrides
    if hasattr(process, 'INSTRUCTION_OVERRIDES'):
        for step, override in process.INSTRUCTION_OVERRIDES.items():
            instructions = instructions.replace(
                _DEFAULT_INSTRUCTIONS[step], override
            )
    # ... rest of prompt assembly
```

### Transition Logic in `parse_response()`

```python
def parse_response(raw, user_id, channel, thread_ts):
    result = _extract_all_tags(raw)

    # Check for process transition
    current_process = soul_memory.get("currentProcess") or "main_process"
    process = _load_process(current_process)
    next_process = process.should_transition(result)

    if next_process and next_process != current_process:
        log.info(f"Process transition: {current_process} → {next_process}")
        soul_memory.set("currentProcess", next_process)

    return result.get("external_dialogue", raw)
```

### Example Process Graph

```
                    ┌──────────────┐
        ┌──────────│  greeting    │───────────┐
        │          └──────────────┘           │
        │ (first message)           (after greeting)
        │                                      │
        ▼                                      ▼
┌──────────────┐                      ┌──────────────┐
│  main_process│◄────────────────────│  deepWork    │
└──────┬───────┘  (task complete)     └──────────────┘
       │                                      ▲
       │ (emotionalState=frustrated)          │
       ▼                                      │
┌──────────────┐  (emotionalState=focused)    │
│  frustrated  │──────────────────────────────┘
└──────────────┘
```

### Estimated Effort

- New directory: `daemon/processes/` with 3 initial process files (~60 LOC each)
- Modified: `soul_engine.py` — add process router (~40 lines)
- Modified: `soul_memory.py` — add `currentProcess` default
- Modified: `config.py` — add `PROCESS_DIR` config
- Tests: ~80 LOC for process loading and transitions
