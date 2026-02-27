---
title: "feat: Open Souls Parity Phase 2 — Mental Processes, Perception, Scheduling"
type: feat
status: active
date: 2026-02-27
repo: ~/Desktop/Programming/claudius
depends_on: splendid-growing-quilt (Phase 1 complete)
---

# Open Souls Parity Phase 2 — Mental Processes, Perception, Scheduling

## Overview

Phase 1 (complete) established the functional programming foundation: immutable snapshots, copy-on-write, checkpoint/rollback, subdaimon persistent memory, regions, general query interface. Phase 2 builds the behavioral layer on top of it — the soul becomes a state machine that classifies perceptions, routes to behavioral modes, schedules proactive events, and routes cognitive steps to cost-optimal models.

Six features, in dependency order. Each builds on the previous.

---

## Feature Dependency Graph

```
Feature 1: Mental Process State Machine     ← foundation for everything
    ↑               ↑               ↑
Feature 4:      Feature 6:      Feature 2:
Perception      Scheduled       Per-Step Model
Processor       Events          Selection
    ↑
Feature 3: Additional Cognitive Steps
    ↑
Feature 5: postProcess Hooks
```

Feature 1 must land first. Features 2, 3, 5 are independent of each other. Feature 4 benefits from Feature 1 (routes to processes). Feature 6 hard-requires Feature 1 (events target processes).

---

## Feature 1: Mental Process State Machine

**Priority:** 1 (highest). Everything else depends on this.
**Estimated LOC:** ~350

### Architecture Decision: Callables, Not Configs

The Feb 25 review is emphatic: processes should be **callables** that compose cognitive steps imperatively, not declarative dataclasses with step lists. The existing `onboarding.py` is the canonical example — it has its own `build_instructions()`, `parse_response()`, and stage-based state machine. Follow that pattern.

### Process Interface

```python
# daemon/engine/process_base.py (~40 LOC)

@dataclass(frozen=True)
class ProcessTransition:
    target: str                     # process module name
    params: dict = field(default_factory=dict)
    execute_now: bool = False       # chain immediately, same perception

@dataclass(frozen=True)
class ProcessResult:
    dialogue: str                   # external response text
    output: CognitiveOutput         # immutable effect description
    transition: ProcessTransition | None = None

class MentalProcess(Protocol):
    """Every process module exports a run() matching this signature."""
    async def run(
        self,
        text: str,
        user_id: str,
        channel: str,
        thread_ts: str,
        snapshot: WorkingMemorySnapshot,
        params: dict | None = None,
    ) -> ProcessResult: ...
```

### Process Lifecycle

```python
# daemon/engine/process_router.py (~120 LOC)

MAX_EXECUTE_NOW_DEPTH = 3

def load_process(name: str) -> ModuleType:
    """Import daemon/processes/{name}.py, fallback to main_process."""

async def route(text, user_id, channel, thread_ts, snapshot, depth=0) -> ProcessResult:
    """Route a perception through the current mental process."""
    current = soul_memory.get("currentProcess") or "main_process"
    process = load_process(current)
    result = await process.run(text, user_id, channel, thread_ts, snapshot)

    if result.transition:
        soul_memory.set("currentProcess", result.transition.target)
        soul_memory.set("previousProcess", current)
        process_memory.clear(current)  # Open Souls: reset on transition
        emit_transition(current, result.transition.target)  # observability

        if result.transition.execute_now:
            if depth >= MAX_EXECUTE_NOW_DEPTH:
                log.warning(f"executeNow depth limit reached at {depth}")
                return result
            return await route(text, user_id, channel, thread_ts,
                             snapshot, depth + 1)
    return result
```

### Initial Processes

**Create:** `daemon/processes/` directory with 3 modules:

| Process | File | Behavior |
|---------|------|----------|
| `main_process` | `daemon/processes/main_process.py` (~80 LOC) | Default cognitive pipeline. All steps. Transitions to `focused` on `emotionalState=focused`, to `frustrated` on `emotionalState=frustrated` |
| `focused_process` | `daemon/processes/focused_process.py` (~60 LOC) | Deep work. Skips user model check. Shorter monologue. Transitions back to `main` when topic changes |
| `frustrated_process` | `daemon/processes/frustrated_process.py` (~60 LOC) | Sardonic. 1-2 sentence responses. Faster soul state checks. Transitions back on `emotionalState=neutral\|engaged` |

Each process is a callable module with `run()` that calls `soul_engine.build_prompt()` and `soul_engine.parse_response()` with process-specific step lists and instruction overrides. The key difference from the declarative approach: the process body can include conditional branching, multiple LLM calls, and inline `mentalQuery` gates.

### Soul Memory Changes

**Modify:** `daemon/memory/soul_memory.py` — add defaults:

```python
"currentProcess": "main_process",
"previousProcess": "",
"processTurnCount": 0,
```

### Onboarding Integration

`onboarding.py` becomes a formal mental process. The current `_check_onboarding_intercept()` in `soul_engine.py` becomes a process transition: if onboarding is incomplete, `currentProcess = "onboarding"`. When onboarding completes, it transitions to `main_process`.

### Observability

Emit `phase="processTransition"` to `soul-stream.jsonl`:

```json
{"phase": "processTransition", "from": "main_process", "to": "frustrated_process",
 "trigger": "emotionalState=frustrated", "execute_now": false}
```

### Tests: `daemon/tests/test_process_router.py` (~120 LOC)

- Process loading (existing module, missing module → fallback)
- Transition (normal, executeNow, depth limit)
- Process memory auto-clear on transition
- Onboarding interop

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Create | `daemon/engine/process_base.py` | ~40 |
| Create | `daemon/engine/process_router.py` | ~120 |
| Create | `daemon/processes/__init__.py` | 0 |
| Create | `daemon/processes/main_process.py` | ~80 |
| Create | `daemon/processes/focused_process.py` | ~60 |
| Create | `daemon/processes/frustrated_process.py` | ~60 |
| Create | `daemon/tests/test_process_router.py` | ~120 |
| Modify | `daemon/memory/soul_memory.py` | +3 lines |
| Modify | `daemon/engine/soul_engine.py` | ~20 lines (process router integration) |
| Modify | `daemon/engine/onboarding.py` | ~15 lines (adapt to process interface) |

---

## Feature 2: Per-Step Model Selection

**Priority:** 2 (low effort, high value — fields already exist, just not wired).
**Estimated LOC:** ~80

### Current State

`CognitiveStep` in `daemon/cognitive_steps/steps.py` already has `model: str = ""` and `provider: str = ""` fields. They are never read at runtime. The unified-mode pipeline sends all steps in one LLM call with one model.

### Design

Per-step routing only works in **split/pipeline mode** (where each step gets its own LLM call). In unified mode, the whole batch uses the default model. The approach:

1. Add a `STEP_MODEL_OVERRIDES` config dict in `config.py` — env-driven routing table
2. In `pipeline.py`'s split-mode execution, read `step.model` and `step.provider` to select the LLM client
3. Fallback chain: step override → process default → global default

```python
# config.py
STEP_MODEL_OVERRIDES: dict = {}  # e.g., {"user_model_check": "haiku", "external_dialogue": "sonnet"}
```

```python
# pipeline.py — split mode step execution
for step in process.cognitive_steps:
    model = step.model or STEP_MODEL_OVERRIDES.get(step.name) or default_model
    provider = step.provider or default_provider
    response = await llm_client.call(prompt, model=model, provider=provider)
```

### Cost Optimization Table

| Step | Recommended Model | Rationale |
|------|-------------------|-----------|
| `user_model_check` | haiku/flash | Boolean gate, cheap |
| `soul_state_check` | haiku/flash | Boolean gate, cheap |
| `dossier_check` | haiku/flash | Boolean gate, cheap |
| `internal_monologue` | sonnet | Creative reasoning |
| `external_dialogue` | sonnet/opus | User-facing quality |

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Modify | `daemon/config.py` | +5 lines |
| Modify | `daemon/engine/pipeline.py` | ~30 lines (model routing in split mode) |
| Modify | `daemon/engine/llm_client.py` | ~20 lines (accept model/provider params) |
| Create | `daemon/tests/test_step_model_routing.py` | ~50 |

---

## Feature 3: Additional Cognitive Steps

**Priority:** 3.
**Estimated LOC:** ~120

### New Steps

| Step | XML Tag | Output | Use Case |
|------|---------|--------|----------|
| `brainstorm` | `<brainstorm count="N">` | JSON array of ideas | RAG query generation, creative ideation |
| `decision` | `<decision options="a,b,c">` | Single chosen option + reasoning | Process routing, tool selection, response mode |
| `instruction` | `<instruction>` | Free-form internal computation | Multi-step reasoning that isn't monologue or dialogue |

### Implementation

Add to `daemon/cognitive_steps/steps.py`:

```python
CognitiveStep(
    name="brainstorm",
    xml_tag="brainstorm",
    entry_type="brainstorm",
    instruction="""When generating ideas or search queries, brainstorm multiple options:
<brainstorm count="3">
["idea one", "idea two", "idea three"]
</brainstorm>""",
),
CognitiveStep(
    name="decision",
    xml_tag="decision",
    entry_type="decision",
    instruction="""When choosing between options, reason through and decide:
<decision options="option1,option2,option3" reasoning="why this choice">
chosen_option
</decision>""",
),
CognitiveStep(
    name="instruction",
    xml_tag="instruction",
    entry_type="instruction",
    instruction="""For internal computation that isn't monologue or dialogue:
<instruction>
Step-by-step reasoning or computation here.
</instruction>""",
),
```

Add extraction logic in `soul_engine.py:parse_cognitive_response()` for each new tag. Store in working memory with appropriate `entry_type`.

### Distinction: instruction vs internalMonologue

- `internalMonologue` — emotional, reflective, verb-narrated ("pondered", "bristled"). The soul's inner voice.
- `instruction` — mechanical, computational, step-by-step. No verb narration. Used by processes that need multi-step reasoning before generating dialogue.

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Modify | `daemon/cognitive_steps/steps.py` | +30 lines |
| Modify | `daemon/engine/soul_engine.py` | +40 lines (extraction) |
| Create | `daemon/tests/test_cognitive_steps_new.py` | ~50 |

---

## Feature 4: Perception Processor

**Priority:** 4. Benefits from Feature 1 (routes to processes).
**Estimated LOC:** ~200

### Architecture Decision: Separate Classification from Memory Assembly

The Feb 25 review is clear: classification (which process handles this) and memory assembly (which regions to inject) are separate concerns. `context.py` already handles memory assembly. The new module handles classification.

### Design

```python
# daemon/engine/perception.py (~120 LOC)

@dataclass(frozen=True)
class Perception:
    action: str          # "userMessage", "scheduledEvent", "systemNotification", "inactivityTimeout"
    content: str         # message text or event content
    user_id: str
    channel: str
    thread_ts: str
    display_name: str = ""
    internal: bool = False    # True for scheduled/system perceptions
    metadata: dict = field(default_factory=dict)

class PerceptionProcessor:
    """Classify incoming messages and construct typed Perceptions."""

    def classify(self, text: str, user_id: str, channel: str,
                 thread_ts: str, queue_depth: int = 0) -> Perception:
        """Fast-path heuristics for obvious cases, LLM for ambiguous ones."""
        # Skip/noise: empty, duplicate within 2s, bot echo
        # Obvious: commands (starts with /), reactions, file-only
        # Ambiguous: everything else → return userMessage (LLM classification deferred to process)
```

**Key design choice**: The perception processor does NOT do LLM-based classification in Phase 2. It provides the typed `Perception` dataclass and fast-path filtering. LLM-based routing (mentalQuery for "is this a crisis?") happens *inside* the mental process, which is the Open Souls-native pattern — the MemoryIntegrator can call cognitive steps, but Claudicle's current single-LLM-call architecture makes this expensive. Phase 3 (with per-step model routing to cheap models) makes LLM classification practical.

### Process Routing via Perception

Mental processes can declare which perception actions they handle:

```python
# daemon/processes/proactive_process.py
HANDLES_ACTIONS = {"scheduledEvent", "inactivityTimeout"}
```

The process router checks `perception.action` against the current process's `HANDLES_ACTIONS`. If the current process doesn't handle the action, route to the process that does.

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Create | `daemon/engine/perception.py` | ~120 |
| Modify | `daemon/engine/process_router.py` | +30 lines (perception-aware routing) |
| Modify | `daemon/engine/soul_engine.py` | +20 lines (use Perception in build_prompt) |
| Create | `daemon/tests/test_perception.py` | ~80 |

---

## Feature 5: postProcess Hooks

**Priority:** 5. Pairs with Feature 3 (validates brainstorm/decision output).
**Estimated LOC:** ~80

### Design

Add `post_process` as an optional callable on `CognitiveStep`. Runs **before** `apply_output()` — transforms the `CognitiveOutput` copy-on-write, then the final output is committed atomically.

```python
# daemon/cognitive_steps/steps.py
@dataclass
class CognitiveStep:
    name: str
    xml_tag: str
    entry_type: str
    instruction: str
    model: str = ""
    provider: str = ""
    post_process: Callable[[str, CognitiveOutput], CognitiveOutput] | None = None
```

### Example Hooks

```python
# Validate decision against allowed options
def validate_decision(raw_content: str, output: CognitiveOutput) -> CognitiveOutput:
    match = re.search(r'<decision options="([^"]+)">(.*?)</decision>', raw_content, re.DOTALL)
    if match:
        options = match.group(1).split(",")
        chosen = match.group(2).strip()
        if chosen not in options:
            chosen = options[0]  # fallback to first option
            return output.with_entry(entry_type="decision",
                                     content=f"options={options}, chose={chosen} (corrected)")
    return output

# Truncate brainstorm to max N ideas
def cap_brainstorm(raw_content: str, output: CognitiveOutput) -> CognitiveOutput:
    # Parse JSON array, truncate to count attribute, return modified output
    ...
```

### Execution Point

In `soul_engine.parse_cognitive_response()`, after extracting each step's output but before building the final `CognitiveOutput`:

```python
for step in active_steps:
    extracted = _extract_tag(raw, step.xml_tag)
    if extracted and step.post_process:
        output = step.post_process(raw, output)
```

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Modify | `daemon/cognitive_steps/steps.py` | +5 lines (field) |
| Create | `daemon/cognitive_steps/hooks.py` | ~40 (hook implementations) |
| Modify | `daemon/engine/soul_engine.py` | +15 lines (invoke hooks) |
| Create | `daemon/tests/test_postprocess.py` | ~50 |

---

## Feature 6: Scheduled Events

**Priority:** 6 (last). Hard-requires Feature 1 (mental processes).
**Estimated LOC:** ~300

### Design

```python
# daemon/scheduler.py (~120 LOC)

# Schema (new table via memory_pool.add_migrations())
"""
CREATE TABLE IF NOT EXISTS scheduled_events (
    id TEXT PRIMARY KEY,
    fire_at REAL NOT NULL,
    perception_action TEXT NOT NULL,
    perception_content TEXT DEFAULT '',
    target_process TEXT DEFAULT '',     -- which mental process handles this
    channel TEXT,
    thread_ts TEXT,
    metadata TEXT DEFAULT '{}',
    internal BOOLEAN DEFAULT 1,         -- always True for scheduled events
    created_at REAL DEFAULT (strftime('%s', 'now')),
    fired INTEGER DEFAULT 0
);
"""

def schedule(action, content, delay_seconds, target_process="",
             channel=None, thread_ts=None, metadata=None) -> str
def schedule_at(action, content, fire_at, **kwargs) -> str
def cancel(event_id) -> bool
def get_due_events(max_batch=5) -> list[dict]     # cap for restart safety
def mark_fired(event_id) -> None
def pending(channel=None) -> list[dict]
def cleanup(max_age_days=30) -> int
```

### Scheduler Loop

```python
# daemon/scheduler_loop.py (~60 LOC)

async def run_scheduler(interval: int = 30):
    """Background loop in unified launcher. Polls for due events."""
    while True:
        due = scheduler.get_due_events(max_batch=5)  # cap for restart safety
        for event in due:
            perception = Perception(
                action=event["action"],
                content=event["content"],
                user_id="system",
                channel=event.get("channel", "scheduler"),
                thread_ts=event.get("thread_ts", "scheduled"),
                internal=True,          # prevents infinite re-scheduling
                metadata=event.get("metadata", {}),
            )
            try:
                result = await process_router.route_perception(perception)
                if event.get("channel"):
                    await post_to_channel(event["channel"], result.dialogue)
                scheduler.mark_fired(event["id"])
            except Exception as e:
                log.error(f"Scheduled event {event['id']} failed: {e}")
        await asyncio.sleep(interval)
```

### Cognitive Step for Scheduling

New XML tag so the soul can schedule events from within a response:

```xml
<schedule_event action="followUpDue" delay="3600" process="follow_up_process">
Check in about the deployment.
</schedule_event>
```

Extraction in `parse_cognitive_response()`. Only fires if `SCHEDULER_ENABLED=true`.

### Infinite Loop Guard

Scheduled events always have `internal=True`. Processes check `perception.internal` before scheduling:

```python
if not perception.internal:
    scheduler.schedule("checkIn", "Daily check", 86400, target_process="check_in_process")
```

### Restart Safety

`get_due_events(max_batch=5)` caps how many overdue events fire per cycle. Events overdue by more than 2x their intended delay are auto-expired:

```python
def get_due_events(max_batch=5) -> list[dict]:
    # ... query WHERE fire_at <= now AND fired = 0 ...
    # Filter: skip events where (now - fire_at) > 2 * (fire_at - created_at)
```

### Daemon Lifecycle

Scheduler runs in the unified launcher (`claudicle.py`) and the inbox watcher. Session Bridge mode (`slack_listen.py`) can optionally start the scheduler loop. Terminal-only mode has no scheduler (sessions are ephemeral).

### Config

```python
SCHEDULER_ENABLED: bool = False
SCHEDULER_INTERVAL: int = 30         # seconds between polls
SCHEDULER_MAX_EVENTS: int = 100      # cap total pending events
SCHEDULER_MAX_OVERDUE_RATIO: float = 2.0  # auto-expire ratio
```

### Files Summary

| Action | File | LOC |
|--------|------|-----|
| Create | `daemon/scheduler.py` | ~120 |
| Create | `daemon/scheduler_loop.py` | ~60 |
| Modify | `daemon/engine/soul_engine.py` | +20 lines (schedule_event tag) |
| Modify | `daemon/config.py` | +5 lines |
| Modify | `daemon/claudicle.py` | +5 lines (start scheduler task) |
| Create | `daemon/tests/test_scheduler.py` | ~100 |

---

## Implementation Order

```
Week 1: Feature 1 (Mental Process State Machine)
  → Process base types, router, 3 initial processes, onboarding migration, tests
  → Gate: all 564 existing tests + new process tests pass

Week 2: Features 2 + 3 + 5 (parallel, independent)
  → Per-step model selection (pipeline.py split mode)
  → brainstorm/decision/instruction cognitive steps
  → postProcess hooks with decision validation
  → Gate: new steps extractable, hooks transforming output

Week 3: Feature 4 (Perception Processor)
  → Perception dataclass, classifier, process-routing integration
  → Gate: typed perceptions flowing through the system

Week 4: Feature 6 (Scheduled Events)
  → Scheduler, loop, XML tag, restart safety, infinite loop guard
  → Gate: events fire on schedule, crisis routing works end-to-end
```

---

## Totals

| Category | Files Created | Files Modified | Estimated LOC |
|----------|--------------|----------------|---------------|
| Feature 1 | 6 | 3 | ~350 |
| Feature 2 | 1 | 3 | ~80 |
| Feature 3 | 1 | 2 | ~120 |
| Feature 4 | 2 | 2 | ~200 |
| Feature 5 | 2 | 2 | ~80 |
| Feature 6 | 3 | 3 | ~300 |
| **Total** | **15** | **15** | **~1,130** |

---

## Verification

1. **Tests:** `python3 -m pytest daemon/tests/ -v` — all existing + new tests pass, <10s
2. **Process transition:** Manually set `emotionalState=frustrated` → verify `currentProcess` transitions to `frustrated_process` → set back to `neutral` → verify return to `main_process`
3. **executeNow:** Trigger crisis → verify immediate chaining to crisis process, depth limit at 3
4. **Per-step routing:** Set `STEP_MODEL_OVERRIDES={"user_model_check": "haiku"}` → verify split-mode pipeline routes that step to haiku
5. **New steps:** Generate response with `<decision>` tag → verify extraction, working memory storage, postProcess validation
6. **Perception:** Send message → verify typed `Perception` object, `action="userMessage"`, routed correctly
7. **Scheduler:** Schedule event 5s out → verify fires, posts response, `fired=1`. Test restart with overdue events → verify max_batch cap
8. **Infinite loop guard:** Schedule event from within scheduled event handler → verify `internal=True` blocks re-scheduling

---

## What This Does NOT Include (Phase 3+)

These are acknowledged gaps deferred to future phases:

| Concept | Status | Phase |
|---------|--------|-------|
| Streaming responses | Not started | Phase 3 |
| RAG integration (rlama in pipeline) | Not started | Phase 3 |
| Cross-soul communication | Not started | Phase 3 |
| ISM (autonomous goals) | Not started | Phase 4 |
| Multi-texting | Not started | Phase 3 |
| Event dispatch bus | Not started | Phase 3 |
| Zod-style structured output validation | Not started | Phase 3 |
| LLM-based perception classification | Deferred (needs cheap per-step routing first) | Phase 3 |
| Session self-termination (`expire()`) | Not started | Phase 4 |

---

## References

### Internal

- Prior review: `~/.claude/plans/2026-02-25-review-open-souls-parity-plan-agent-a5e21482691f7b5c1.md`
- Phase 1 plan: `~/.claude/plans/splendid-growing-quilt.md`
- Alignment doc: `docs/open-souls-alignment.md`
- Extension guide: `docs/extending-claudicle.md` (Extension Priority Guide, lines 523-539)
- FP principles: `agent_docs/open-souls-functional-principles.md`
- Onboarding (callable process reference): `daemon/engine/onboarding.py`

### Open Souls Skill References

- Mental processes: `skills/open-souls-paradigm/references/mental-processes.md`
- Scheduled events: `skills/open-souls-paradigm/references/scheduled-events.md`
- Subprocesses: `skills/open-souls-paradigm/references/subprocesses.md`
- Cross-soul: `skills/open-souls-paradigm/references/cross-soul-communication.md`
- Hooks & state: `skills/open-souls-paradigm/references/hooks-and-state.md`
- Advanced patterns: `~/.claude/skills/open-souls-paradigm/references/advanced-patterns.md`
- Daimonic Samantha: `~/.claude/skills/open-souls-paradigm/references/soul-examples/daimonic-samantha-android/`
