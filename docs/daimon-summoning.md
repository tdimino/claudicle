---
title: "Daimon Summoning"
category: architecture
created: 2026-03-09
related:
  - daimonic-intercession.md
  - open-souls-alignment.md
  - cognitive-pipeline.md
  - sub-daimones.md
  - daimones.md
key_files:
  - daemon/daimonic/summoning.py
  - daemon/daimonic/whispers.py
  - daemon/cognitive_steps/steps.py
  - daemon/engine/soul_engine.py
  - daemon/memory/snapshot.py
config:
  - SUMMONING_ENABLED (default: true)
  - SUMMONING_MAX_ACTIVE (default: 3)
  - SUMMONING_GROQ_MODEL (default: moonshotai/kimi-k2-instruct)
---

# Daimon Summoning

How any entity in Claudicle's knowledge base becomes a speaking voice.

---

## The Idea

Every entity Claudicle knows about — a user model (Tom, Mary), a person dossier (Michael Astour, Cyrus Gordon), a subject dossier (Knossos, Ugarit) — is a frozen portrait. Summoning turns that portrait into a *speaking voice*. The entity becomes a temporary daimon that whispers counsel through the same infrastructure Kothar wa Khasis uses, then fades when dismissed.

This is the daimonic tradition made literal: any accumulated knowledge can be awakened as an intermediary intelligence.

---

## Open Souls Terms

In the Open Souls paradigm, a soul engine has three primitives:

1. **WorkingMemory** — an immutable value threaded through cognitive steps. Each step receives it, returns a new one. Never mutated.
2. **CognitiveStep** — a pure function: `(WorkingMemory, args) → WorkingMemory`. It describes *intent*, never executes side effects.
3. **The membrane** — the boundary between pure computation and impure execution. Inside: frozen data, copy-on-write. Outside: database writes, API calls, registry mutations.

Summoning maps onto these precisely:

### The pure side (inside the membrane)

The LLM receives two cognitive steps in its instruction set:

- `SUMMON_CHECK` — a **mentalQuery** (boolean gate). The LLM asks itself: *"Does this exchange benefit from another entity's perspective?"* It answers `<summon_check>true</summon_check>` or false. This is the same gate pattern as `USER_MODEL_CHECK` and `DOSSIER_CHECK` — a binary decision that controls whether the conditional step fires.

- `SUMMON_DAIMON` — a **conditional action** (only if the gate passed). The LLM names who and why:
  ```xml
  <summon_daimon entity="Knossos" mode="whisper">
    Tom is discussing Minoan archaeology — Knossos has domain expertise
  </summon_daimon>
  ```

The parser (`parse_cognitive_response()`) extracts these tags and builds a frozen `CognitiveOutput` through copy-on-write:

```python
output = output.with_entry("mentalQuery", "Should an entity be summoned?",
                           metadata={"result": True})
output = output.with_scheduled_event(action="summon_daimon",
                                     content="Knossos",
                                     target_process="whisper")
output = output.with_entry("toolAction", "summoning entity: Knossos (mode=whisper)")
```

Each `.with_*` call returns a *new* `CognitiveOutput`. The original is untouched. The summon is encoded as **data** — a scheduled event inside the frozen output. No import of `summoning.py`. No side effects. No mutation. Pure accumulation of intent.

This is the Open Souls insight: cognitive steps describe what *should* happen. They never do it.

### The membrane (`apply_output()`)

`apply_output()` in `snapshot.py` is the single impure boundary — the equivalent of Open Souls' `memory.finished`. It receives the frozen `CognitiveOutput` and commits it atomically:

1. Memory entries → SQLite
2. Soul state updates → `soul_state.set_state_key()`
3. User model updates → `user_models.save()`
4. Dossier updates → `user_models.save_dossier()`
5. Scheduled events → scheduler (if enabled)
6. **Summon events → direct execution** (not scheduler-gated)

Section 6 is where summoning crosses the membrane. Summon events are filtered out of the scheduled events list and executed immediately:

```python
summon_events = [e for e in remaining_events if e["action"] == "summon_daimon"]
for event in summon_events:
    summon_entity(entity_name=event["content"], ...)
```

Why immediate, not scheduled? Because the whole point is that the summoned daimon should whisper on the *next* cognitive cycle. Routing through the scheduler would add a cycle of latency — the soul decided it needs another voice *now*, and the architecture respects that decision.

### The impure side (outside the membrane)

`summon_entity()` in `summoning.py` does four things, all outside the cognitive pipeline:

1. **Resolves the entity** via the frozen `EntityGraph` (alias-aware name index → node lookup → content fetch)
2. **Synthesizes a soul.md** — a pure function that templates the entity's content into a personality prompt
3. **Caches it in memory** — writes to `whispers._soul_md_cache` (a dict, not the filesystem)
4. **Registers a `DaimonConfig`** in the mutable daimon registry

After this, the summoned daimon exists. On the next cognitive cycle, `daimonic.format_for_prompt()` iterates all whisperers (including the newly registered summoned daimon), finds its whisper in soul_memory, and injects it as embodied recall — the same way Kothar's whispers surface.

---

## Claudicle Terms

In Claudicle's four-layer architecture:

### Identity layer

The summoned entity gets a synthesized `soul.md`. Three templates by entity type:
- **User** (`user`): First-person voice. Extracts the `## Speaking Style` section from their user model. "I am Alice, as modeled by Claudius."
- **Person** (`person`): Scholarly reconstruction. "I am Michael Astour, as understood through Claudius's observations. My voice is reconstructed from what is known about me."
- **Subject** (`subject`): The domain itself speaking. "I am the voice of Knossos — the domain itself speaking through Claudius's accumulated knowledge."

### Cognition layer

Two cognitive steps (`SUMMON_CHECK` + `SUMMON_DAIMON`) in the `steps.py` registry, gated by `SUMMONING_ENABLED` config. They're appended to the instruction set in `_assemble_instructions()` only when the config flag is true. The extraction in `parse_cognitive_response()` produces a `scheduled_event` on the frozen `CognitiveOutput`, and the soul log emits both the gate decision and the summon action.

### Memory layer

The cache trick. `DaimonConfig.soul_md` normally points to a filesystem path (e.g., `~/daimones/kothar/soul.md`). For summoned daimons, it points to a synthetic cache key like `__summoned__summoned:dossier:knossos`. When `_load_soul_md()` is called by the Groq transport, it checks `whispers._soul_md_cache` first — finds the synthesized soul.md there — and never touches the filesystem. Dismiss just pops the cache key and toggles the registry. Zero filesystem writes, zero cleanup.

The whisper key system (`_whisper_soul_key()`) derives soul_memory keys from `display_name.lower().split()[0]` — so "Knossos" stores at `daimonic_whisper_knossos`, and `format_for_prompt()` / `consume_all_whispers()` use the same derivation to find and clear it.

### Channel layer

Three interfaces, all converging on the same `summon_entity()` call:
1. **Cognitive step** (autonomous): The LLM decides on its own during a conversation
2. **Slash command** (`/daimon summon Knossos`): User-initiated via the daimon.md command
3. **Programmatic API**: `summon_entity("Knossos")` from any Python code

---

## The Lifecycle

```
LLM decides          Pure parser          Membrane              Impure side
─────────────       ─────────────       ──────────────       ─────────────────
<summon_check>  →   CognitiveOutput  →  apply_output()   →  summon_entity()
  true                .with_scheduled     section 6:           1. resolve entity
<summon_daimon>       _event(action=      immediate            2. synthesize soul.md
  entity="Knossos"    "summon_daimon",    execution            3. cache in memory
  mode="whisper">     content="Knossos")                       4. register daimon

                                         ┌─ next cycle ──────────────────────┐
                                         │ format_for_prompt() finds the     │
                                         │ new whisperer → Groq call with    │
                                         │ synthesized soul.md → whisper     │
                                         │ injected as embodied recall       │
                                         └───────────────────────────────────┘
```

---

## What Makes It Work

The architecture holds because of one principle: **the cognitive pipeline never touches the registry or cache directly**. The LLM produces XML tags. The pure parser converts those tags into frozen data on a frozen `CognitiveOutput`. The membrane commits that data atomically. The impure side does the actual work. Each layer only talks to its neighbor. The summoned daimon is just another `DaimonConfig` in the registry — `format_for_prompt()` doesn't know or care whether it was loaded from config at startup or synthesized from a dossier five seconds ago.

---

## API Reference

```python
from daimonic.summoning import summon_entity, dismiss_entity, list_summoned

# Summon an entity (by name, alias, or user ID)
summon_entity("Knossos", channel="C1", thread_ts="T1")
summon_entity("U123")  # User model
summon_entity("Hephaestus")  # Resolves via alias to "Kothar wa Khasis"

# List active summoned daimons
for daimon in list_summoned():
    print(f"{daimon.display_name}: mode={daimon.mode}")

# Dismiss
dismiss_entity("Knossos")
```

## Design Decisions

- **Best-effort**: All summon/dismiss operations wrapped in try/except — summoning never blocks the cognitive pipeline
- **Direct execution over scheduler**: Ensures the daimon is ready for the next cycle, not the one after
- **Cache over filesystem**: No temp files, no cleanup. Dismiss just removes from cache + toggles registry
- **Entity graph for resolution**: Alias-aware lookup means natural language names work
- **Synthetic cache keys**: `__summoned__` prefix prevents `_load_soul_md()` from treating cache keys as filesystem paths

## See Also

- [Daimonic Intercession](daimonic-intercession.md) — The whisper protocol this builds on
- [Open Souls Alignment](open-souls-alignment.md) — Full paradigm mapping
- [Cognitive Pipeline](cognitive-pipeline.md) — How cognitive steps compose
- [Daimones](daimones.md) — The privy council concept
- [Sub-Daimones](sub-daimones.md) — The 12 cognitive agents
