# Subprocesses — Extension Pattern

## Open Souls Pattern

Subprocesses are `MentalProcess` functions that run **in the background** after each main-thread process cycle. They operate on the same WorkingMemory but handle cross-cutting concerns: learning about the user, maintaining conversation summaries, tracking goals.

### Key Behaviors

1. They operate on WorkingMemory identically to the main process
2. They execute in **alphabetical order** by filename in the `subprocesses/` directory
3. Any new incoming perception **terminates all subprocess execution**
4. They run after every main process cycle, not on their own schedule

### Canonical Example: `learnsAboutTheUser`

```typescript
// subprocesses/learnsAboutTheUser.ts
const learnsAboutTheUser: MentalProcess = async ({ workingMemory }) => {
  const userModel = useProcessMemory("Unknown User");
  const { log } = useActions();

  let finalMemory = workingMemory;

  // Inject current user model into context
  workingMemory = workingMemory.withMemory({
    role: ChatMessageRoleEnum.Assistant,
    content: indentNicely`
      ${workingMemory.soulName} remembers:
      ## User model
      ${userModel.current}
    `
  });

  // Gate: did we learn something new?
  const [, learnedSomethingNew] = await mentalQuery(
    workingMemory,
    `${workingMemory.soulName} has learned something new about the user.`
  );

  log("Update model?", learnedSomethingNew);

  if (learnedSomethingNew) {
    // Reflect on what was learned
    let [withReflection, reflection] = await internalMonologue(workingMemory, {
      instructions: "What have I learned about the user from the last few messages?",
      verb: "noted"
    });
    log("User Learnings:", reflection);

    // Generate updated user notes
    const [, notes] = await userNotes(withReflection);
    userModel.current = notes;
  }

  // Return the ORIGINAL memory (not the modified working copy)
  return finalMemory;
};
```

**Critical pattern:** The subprocess saves `finalMemory = workingMemory` at the start and returns it at the end. The modified `workingMemory` used for introspection is a temporary copy — the main process's memory state is preserved.

### Other Common Subprocesses

**`summarizesConversation.ts`** — Maintains a rolling summary in the `summary` memory region:
```typescript
const summarizesConversation: MentalProcess = async ({ workingMemory }) => {
  const [, summary] = await conversationNotes(workingMemory, "Summarize key points");
  return workingMemory.withRegion("summary", {
    role: ChatMessageRoleEnum.System,
    content: summary,
  });
};
```

**`tracksGoals.ts`** — Monitors progress toward declared goals:
```typescript
const tracksGoals: MentalProcess = async ({ workingMemory }) => {
  const goals = useSoulMemory("activeGoals", []);
  const [, completed] = await mentalQuery(workingMemory, "Has a goal been achieved?");
  if (completed) {
    // Update goal state...
  }
  return workingMemory;
};
```

---

## Current Claudicle Implementation

Claudicle handles user model updates and soul state updates **inline** within the main cognitive pipeline:

```
parse_response() extracts:
  → internal_monologue     (always)
  → external_dialogue      (always)
  → user_model_check       (always — mentalQuery gate)
  → user_model_update      (conditional on check)
  → soul_state_check       (periodic — every Nth turn)
  → soul_state_update      (conditional on check)
```

This is equivalent to having the `learnsAboutTheUser` subprocess baked into the main process. There is no mechanism for additional background tasks (conversation summarization, goal tracking, proactive behavior) to run after the main response is sent.

The `claude_handler.py:process()` function (line 35-139) handles the full cycle:

```python
# claude_handler.py — current flow (simplified)
def process(text, user_id, channel, thread_ts, is_first=False):
    prompt = soul_engine.build_prompt(text, user_id, channel, thread_ts, is_first)
    raw = _invoke_claude(prompt, channel, thread_ts)
    dialogue = soul_engine.parse_response(raw, user_id, channel, thread_ts)
    return dialogue
    # No subprocess execution after this point
```

---

## Extension Blueprint

### Goal

Add a subprocess system that runs background tasks after each main response. This enables:

1. Decoupling user model updates from the main cognitive pipeline
2. Rolling conversation summarization (injected as a memory region)
3. Goal tracking and proactive behavior triggers
4. Custom background analytics (sentiment tracking, topic extraction)

### New Directory: `daemon/subprocesses/`

Each subprocess is a Python module with a `run()` function. Files execute in alphabetical order.

```python
# daemon/subprocesses/a_summarizes_conversation.py
"""Maintain a rolling conversation summary in the 'summary' region."""

import soul_memory
import working_memory

async def run(text: str, user_id: str, channel: str, thread_ts: str,
              parse_result: dict) -> None:
    """Run after main process. Modifies shared state, not the response."""
    # Get recent working memory entries for this thread
    recent = working_memory.recent(channel, thread_ts, limit=10)

    if len(recent) < 5:
        return  # Not enough context to summarize

    # Build summary from recent monologues and dialogues
    entries = [f"{e['entry_type']}: {e['content'][:200]}" for e in recent]
    summary_text = "\n".join(entries)

    # Store as soul state (available to all threads)
    soul_memory.set("conversationSummary", summary_text[:500])
```

```python
# daemon/subprocesses/b_tracks_sentiment.py
"""Track conversation sentiment over time."""

import working_memory

async def run(text: str, user_id: str, channel: str, thread_ts: str,
              parse_result: dict) -> None:
    monologue = parse_result.get("internal_monologue", "")
    # Simple sentiment heuristic from monologue content
    sentiment = _analyze_sentiment(monologue)
    working_memory.store(
        channel, thread_ts, user_id,
        entry_type="sentiment",
        content=f"sentiment={sentiment}",
    )
```

### Subprocess Runner

```python
# daemon/subprocess_runner.py
"""Execute subprocesses in alphabetical order after main process."""

import asyncio
import importlib
import logging
import os
from pathlib import Path

log = logging.getLogger("slack-daemon.subprocesses")

_SUBPROCESS_DIR = Path(__file__).parent / "subprocesses"

def _discover_subprocesses() -> list:
    """Find all subprocess modules in alphabetical order."""
    if not _SUBPROCESS_DIR.exists():
        return []
    modules = []
    for f in sorted(_SUBPROCESS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"subprocesses.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "run"):
                modules.append(mod)
        except ImportError as e:
            log.warning(f"Failed to load subprocess {module_name}: {e}")
    return modules

async def run_subprocesses(text, user_id, channel, thread_ts,
                           parse_result, check_interrupt=None):
    """Run all subprocesses in order. Stop if interrupted."""
    for mod in _discover_subprocesses():
        # Check for new incoming perception (interrupt)
        if check_interrupt and check_interrupt():
            log.info(f"Subprocess interrupted before {mod.__name__}")
            break
        try:
            await mod.run(text, user_id, channel, thread_ts, parse_result)
        except Exception as e:
            log.error(f"Subprocess {mod.__name__} failed: {e}")
```

### Integration with `claude_handler.py`

```python
# claude_handler.py — modified flow
import subprocess_runner

async def async_process(text, user_id, channel, thread_ts, is_first=False):
    prompt = soul_engine.build_prompt(text, user_id, channel, thread_ts, is_first)
    raw = await _invoke_claude_sdk(prompt, channel, thread_ts)
    dialogue = soul_engine.parse_response(raw, user_id, channel, thread_ts)

    # Run subprocesses AFTER response is sent
    # (in unified launcher, response is posted to Slack before this)
    await subprocess_runner.run_subprocesses(
        text, user_id, channel, thread_ts,
        parse_result=soul_engine.last_parse_result,
        check_interrupt=lambda: _has_pending_message(channel, thread_ts),
    )

    return dialogue
```

### Interrupt Mechanism

The Open Souls pattern terminates subprocesses when a new perception arrives. In Claudicle, the equivalent is checking for new messages in the inbox:

```python
def _has_pending_message(channel, thread_ts):
    """Check if new messages arrived for this thread during subprocess execution."""
    # For Session Bridge: check inbox.jsonl
    # For Unified Launcher: check async queue
    return False  # Default: no interruption
```

### Subprocess Naming Convention

Prefix with a letter to control execution order:

```
subprocesses/
├── a_summarizes_conversation.py   # Runs first
├── b_tracks_sentiment.py          # Runs second
├── c_checks_goals.py              # Runs third
└── z_cleanup.py                   # Runs last
```

### Estimated Effort

- New directory: `daemon/subprocesses/` with 2 initial subprocesses (~40 LOC each)
- New file: `daemon/subprocess_runner.py` (~60 LOC)
- Modified: `claude_handler.py` — add subprocess invocation (~10 lines)
- Modified: `config.py` — add `SUBPROCESS_ENABLED` toggle
- Tests: ~60 LOC for discovery, ordering, and interrupt
