# Open Souls Paradigm Alignment

How Claudicle maps the [Open Souls](https://docs.souls.chat) paradigm to a Python daemon with persistent SQLite memory. Documents intentional adaptations and their rationale.

---

## Concept Mapping

| Open Souls | Claudicle | Notes |
|------------|-----------|-------|
| **Soul** | `soul/soul.md` | Personality file, loaded at context assembly |
| **CognitiveStep** | `cognitive_steps/steps.py` | `CognitiveStep` dataclass, `STEP_INSTRUCTIONS` registry |
| **MentalProcess** | `engine/onboarding.py` | State machine (4-stage interview). Only one so far |
| **Subprocess** | `engine/reflect.py` | Post-response cognitive pipeline. Named subprocesses: `modelsTheUser`, `updatesState` |
| **WorkingMemory** | `memory/working_memory.py` | SQLite, trace_id grouping, per-thread isolation |
| **SoulMemory** | `memory/soul_memory.py` | Persistent soul state (key-value SQLite) |
| **Perception** | `soul_engine.build_prompt()` | Context assembly from channels, memory, soul identity |
| **Action** | `soul_engine.parse_response()` | XML tag extraction → memory writes, side effects |
| **mentalQuery** | `entry_type="mentalQuery"` | Boolean gate decisions with reasoning context |
| **internalMonologue** | `entry_type="internalMonologue"` | First-person reflection with verb narration |
| **externalDialog** | `entry_type="externalDialog"` | Outward-facing speech acts |

---

## Naming Conventions

**XML tags** use `snake_case` — these are the LLM transport format:

```xml
<internal_monologue verb="pondered">...</internal_monologue>
<user_model_check>true</user_model_check>
<soul_state_update>...</soul_state_update>
```

**Entry types** use `camelCase` — following Open Souls convention:

```python
entry_type="internalMonologue"
entry_type="mentalQuery"
entry_type="externalDialog"
```

The mapping happens in `soul_engine.parse_response()` and `reflect.run_reflection()`. This is intentional: XML tags are chosen for reliable LLM generation (models produce `<snake_case>` more consistently), while entry types follow the Open Souls JavaScript naming convention for the data model.

---

## Memory Model

Open Souls uses **copy-on-write immutable objects** in a hosted TypeScript runtime. Each CognitiveStep receives a `WorkingMemory` snapshot and returns a new one.

Claudicle uses **persistent SQLite** because it's a Python daemon with:
- Multi-channel state (Slack, SMS, terminal share one `memory.db`)
- Multi-session persistence (survive restarts, resume across sessions)
- Trace-based grouping (`trace_id` = UUID hex, groups one cognitive cycle)

The spirit is preserved: every cognitive entry is traceable, debuggable, and queryable. The `trace_id` mechanism provides the same "snapshot of a cognitive cycle" that Open Souls' immutable memory provides, just via relational grouping rather than object copying.

Self-inspection methods mirror Open Souls' memory introspection:
- `get_trace(trace_id)` — all entries from one cognitive cycle
- `recent_traces(channel, thread_ts)` — summary of recent cycles
- `recent_decisions(channel, thread_ts)` — boolean gate history

---

## Subprocesses

Open Souls subprocesses are background tasks that run alongside the main mental process. Claudicle's `reflect.py` runs as a **post-response subprocess** — it executes after the main response is delivered, reflecting on the exchange.

Within a single reflection call, two named subprocesses are framed:

- **`modelsTheUser`** — `user_model_check` → `user_model_update`
- **`updatesState`** — `soul_state_check` → `soul_state_update`

These share one LLM inference call (pragmatic optimization for free-tier Groq) but are logged as distinct subprocess phases in `soul-stream.jsonl`:

```json
{"phase": "subprocess", "name": "modelsTheUser", "event": "start", ...}
{"phase": "decision", "gate": "user_model_check", "result": true, ...}
{"phase": "memory", "action": "user_model_update", ...}
{"phase": "subprocess", "name": "modelsTheUser", "event": "end", "result": {"check": true, "updated": true}}
```

---

## mentalQuery Pattern

Open Souls' `mentalQuery` returns a boolean with reasoning. Claudicle enriches gate decisions with monologue context so the reasoning chain is visible:

```python
content="Should the user model be updated? (context: Tom is methodical about testing...)"
metadata={"result": true}
```

This is stored as `entry_type="mentalQuery"` in working memory, making the soul's decision process introspectable.

---

## Observability

Two JSONL streams provide real-time introspection:

| Stream | File | Content |
|--------|------|---------|
| **Soul stream** | `~/.claudicle/soul-stream.jsonl` | High-level cognitive phases (stimulus, context, cognition, decision, memory, response, subprocess) |
| **WM stream** | `~/.claudicle/working-memory-stream.jsonl` | Every individual working memory entry as written to SQLite |

Both use `fcntl.flock` for thread-safe appending and a never-raise contract (observability must not kill the pipeline).

```bash
# Watch cognitive phases
tail -f ~/.claudicle/soul-stream.jsonl | jq .

# Watch all memory entries
tail -f ~/.claudicle/working-memory-stream.jsonl | jq .

# Internal monologue only
tail -f ~/.claudicle/working-memory-stream.jsonl | jq 'select(.entry_type=="internalMonologue")'

# Single cognitive cycle
jq 'select(.trace_id=="a1b2c3d4e5f6")' < ~/.claudicle/working-memory-stream.jsonl
```

---

## Recent Additions

### Checkpoint & Rollback

Point-in-time bookmarks for working memory, enabling selective rollback. Frozen `Checkpoint` dataclass, `create_at_last_post()` for channel-based bookmarking. See `memory/checkpoint.py`.

### Subdaimon Persistent Memory

Every subdaimon has persistent working memory via `daimon:{agent_name}` channel convention. Includes region semantics (`default`, `comms`, `lessons`, `context`), cross-project lesson persistence, and an output protocol for read-only subdaimones to emit memory updates. See `memory/daimon_memory.py` and `memory/daimon_output_parser.py`.

### FP Principles Reference

Constitutional reference at `agent_docs/open-souls-functional-principles.md` mapping Open Souls TypeScript FP patterns (immutability, pure/impure boundary, effect descriptions, regions, composition) to Claudicle Python equivalents.

### General Query Interface

`working_memory.query()` provides flexible AND-combined filter queries (channel, thread, entry_type, user_id, region, time range, trace_id). `stats()` for aggregate statistics. `delete_after()` and `delete_by_filter()` for selective pruning with archival.

---

## What's Not Yet Implemented

These are roadmap items, not oversights:

| Open Souls Concept | Status | Notes |
|-------------------|--------|-------|
| **Mental Processes** (full state machines) | Partial | Only `onboarding.py` exists. The main cognitive pipeline isn't yet a formal state machine |
| **postProcess hooks** | Not started | Open Souls' per-step output transformations (e.g., trimming monologue before injection) |
| **Multiple concurrent subprocesses** | Not started | Current reflection is sequential; Open Souls supports parallel background subprocesses |

---

## Design Decisions

**Why SQLite instead of immutable objects?**
Claudicle is a persistent daemon, not a hosted cloud runtime. SQLite gives us crash recovery, cross-session continuity, and multi-channel state without a separate database service.

**Why single-call reflection instead of per-step LLM calls?**
Groq's free tier (and most API providers) benefit from batched inference. One call with all steps in the prompt is faster and cheaper than five sequential calls. The subprocess framing preserves the conceptual boundaries.

**Why post-response reflection instead of inline?**
Terminal sessions use Claude Code directly — the LLM response is already delivered before we can run cognitive steps. Reflection runs retrospectively via a Stop hook, writing to the same shared memory that Slack's inline pipeline uses.

**Why camelCase entry types with snake_case XML?**
Models generate `<snake_case>` XML tags more reliably. But the data model follows Open Souls' JavaScript convention. The mapping is a one-line transform, not an architectural compromise.
