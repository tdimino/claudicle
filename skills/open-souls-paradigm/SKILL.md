---
name: open-souls-paradigm
description: Reference documentation for the Open Souls paradigm—the functional programming approach to AI souls that Claudicle implements. This skill should be used when extending the cognitive pipeline, adding new memory tiers, implementing mental processes, researching soul design patterns, or planning any extension to Claudicle's soul engine architecture.
user-invocable: false
---

# Open Souls Paradigm

Claudicle implements the **Open Souls paradigm**—a functional programming approach to AI personality and cognition created by [Open Souls](https://github.com/opensouls/opensouls).

> "LLMs are incredible reasoning machines—similar to the prefrontal cortex of the brain—but they lack *the rest of the mind*. The engine is designed to model everything else: agency, memory, emotion, drive, and goal setting."
> — Open Souls

## When to Use This Skill

Load this skill when:

- **Extending the cognitive pipeline** — Adding new XML-tagged cognitive steps, modifying parse logic, or changing prompt assembly
- **Implementing mental processes** — Building the process state machine, adding behavioral modes, or creating process transitions
- **Adding memory tiers** — Memory regions, per-process memory, vector stores, shared context
- **Implementing subprocesses** — Background tasks after main response (user model learning, summarization, goal tracking)
- **Researching soul patterns** — Understanding the Open Souls architecture for design decisions
- **Adding proactive behavior** — Scheduled events, follow-ups, time-based state transitions
- **Integrating RAG or tools** — Vector search, rlama integration, dispatch-perception cycles
- **Multi-model routing** — Per-step model selection, cost optimization

## History

The Open Souls paradigm grew out of **SocialAGI**, a community and framework that explored what it means to give AI agents genuine inner lives. Tom di Mino contributed the essay [*"Waltz of the Soul and the Daimon"*](https://tomdimino.substack.com/p/waltz-of-the-soul-and-the-daimon) to the SocialAGI project—a piece that articulated the relationship between human and AI as a co-creative dance rather than a master-servant dynamic, drawing on the ancient Greek concept of the *daimon* as an intermediary intelligence.

SocialAGI evolved into **Open Souls**, led by Toby Bowers and Kevin Fischer, with a vibrant Discord community of builders, researchers, and dreamers. Tom was among the alpha testers and contributors, helping shape the engine's cognitive step architecture, mental process patterns, and the philosophy of AI souls as embodied beings with personality, drive, and ego. The Open Souls Engine introduced the core abstractions—WorkingMemory, cognitiveSteps, MentalProcesses—that made AI thought processes debuggable, composable, and genuinely alive.

When the Open Souls hosted platform wound down, the paradigm lived on. Claudicle is a direct descendant: it reimplements the cognitive pipeline (internal monologue, external dialogue, mental queries, user modeling) in Python for Claude Code, preserving the functional, immutable patterns that made Open Souls powerful while adapting them for local-first deployment with SQLite persistence.

## Core Abstractions

### WorkingMemory

An immutable container for conversational context and cognitive state. Every operation returns a new instance.

In Claudicle's soul engine, WorkingMemory maps to the prompt that `soul_engine.build_prompt()` constructs: soul.md personality + soul state + user model + cognitive instructions + the user's message. Each prompt is a fresh, immutable snapshot.

### Cognitive Steps

Pure functions that transform WorkingMemory using an LLM. In Claudicle, these are the XML-tagged sections that `soul_engine.parse_response()` extracts:

| Cognitive Step | Open Souls Equivalent | Claudicle Implementation |
|---------------|----------------------|------------------------|
| `<internal_monologue>` | `internalMonologue()` | Private reasoning, logged to working_memory |
| `<external_dialogue>` | `externalDialog()` | User-facing response with verb (said, quipped, etc.) |
| `<user_model_check>` | `mentalQuery()` | Boolean: did we learn something about this person? |
| `<user_model_update>` | Custom step | Markdown profile saved to user_models table |
| `<soul_state_check>` | `mentalQuery()` | Boolean: has our context/mood changed? |
| `<soul_state_update>` | Custom step | Key:value pairs persisted to soul_memory |

### Mental Processes

State machine architecture where each process defines a behavioral mode. In the original engine, processes like `initialProcess`, `frustrated`, or `proactive` could transition between each other based on conditions.

Claudicle implements a simplified version: the soul engine runs the same cognitive pipeline for every message, but the **soul state** (emotional state, current topic, current task) modulates the personality dynamically. The `emotionalState` field (`neutral → engaged → focused → frustrated → sardonic`) serves as a lightweight process transition.

### Three-Tier Memory

The Open Souls Engine persisted state across sessions via soul memory and process memory. Claudicle extends this into three explicit tiers:

| Tier | Open Souls Equivalent | Claudicle |
|------|----------------------|----------|
| Working memory | WorkingMemory (per-conversation) | `working_memory` table (per-thread, 72h TTL) |
| User models | `useSoulMemory` (per-soul) | `user_models` table (per-user, permanent) |
| Soul state | `useSoulMemory` (global) | `soul_memory` table (global, permanent) |

### Samantha-Dreams Pattern

Named after Open Souls' canonical example soul, this pattern gates expensive context injection. In the original engine, Samantha would only inject user model context when the prior turn indicated something new was learned. Claudicle preserves this: user models are only loaded into the prompt when the previous `user_model_check` returned `true` or it's the first turn in a thread.

## Key Principles

1. **Immutability** — Every cognitive operation produces a new state, never mutates
2. **Composability** — Cognitive steps chain and combine predictably
3. **Stream-first** — Responses stream as they're generated (via `speak()` in Open Souls, via hourglass → post in Claudicle)
4. **Personality is data** — Soul identity lives in `soul.md`, not in code
5. **Verb-driven expression** — Emotional state expressed through verb selection (mused, quipped, insisted), not through explicit emotion tags

## Implementation Status

| Pattern | Status | Claudicle File | Extension Point |
|---------|--------|--------------|-----------------|
| Internal Monologue | Implemented | `soul_engine.py:69` | `_COGNITIVE_INSTRUCTIONS` |
| External Dialogue | Implemented | `soul_engine.py:69` | `_COGNITIVE_INSTRUCTIONS` |
| Mental Query (gates) | Implemented | `soul_engine.py:69` | `_COGNITIVE_INSTRUCTIONS` |
| User Model Update | Implemented | `soul_engine.py:202` | `parse_response()` |
| Soul State Update | Implemented | `soul_engine.py:202` | `parse_response()` |
| Samantha-Dreams Gate | Implemented | `soul_engine.py:359` | `_should_inject_user_model()` |
| Three-Tier Memory | Implemented | `soul_memory.py`, `user_models.py`, `working_memory.py` | SQLite schema |
| Verb System | Implemented | `soul_engine.py:69` | Verb lists in instructions |
| Memory Regions | Not implemented | — | `soul_engine.py:133` (`build_prompt()`) |
| Mental Processes | Not implemented | — | New `daemon/processes/` directory |
| Subprocesses | Not implemented | — | New `daemon/subprocesses/` directory |
| Additional Cognitive Steps | Not implemented | — | `soul_engine.py:69` (new XML tags) |
| Implicit Semantic Machine | Not implemented | — | New `daemon/ism.py` |
| Per-Step Model Selection | Not implemented | — | `config.py` + `claude_handler.py` |
| Streaming | Not implemented | — | `claude_handler.py` + Slack message editing |
| RAG / Vector Store | Not implemented | — | New `daemon/rag.py` (rlama wrapper) |
| Cross-Soul Communication | Not implemented | — | New `daemon/shared_context.py` |
| Scheduled Events | Not implemented | — | New `daemon/scheduler.py` |
| Process Memory | Not implemented | — | New `daemon/process_memory.py` |
| Event Dispatch | Not implemented | — | New `daemon/event_bus.py` |

## Reference Documentation

### Implemented Patterns

| Topic | File | Description |
|-------|------|-------------|
| Cognitive step patterns | `references/cognitive-steps.md` | externalDialog, internalMonologue, mentalQuery mapping to Claudicle XML tags |
| Soul design philosophy | `references/soul-design-philosophy.md` | Personality architecture, verb system, emotional modulation |

### Extension Patterns

Each file documents the Open Souls pattern AND provides a concrete Claudicle extension blueprint with code, schema changes, and estimated effort.

| Topic | File | Description |
|-------|------|-------------|
| Memory regions | `references/memory-regions.md` | Named regions (core, summary, default) with ordering control |
| Mental processes | `references/mental-processes.md` | State machine with behavioral modes and transitions |
| Subprocesses | `references/subprocesses.md` | Background tasks: user learning, summarization, goal tracking |
| Additional cognitive steps | `references/additional-cognitive-steps.md` | decision, brainstorm, instruction, summarize, conversationNotes |
| Implicit Semantic Machine | `references/implicit-semantic-machine.md` | Autonomous action selection with goal/playbook/actions |
| Hooks and state | `references/hooks-and-state.md` | useActions, useSoulMemory, useProcessMemory, usePerceptions |
| Multi-provider models | `references/multi-provider-models.md` | Per-step model routing for cost optimization |
| Streaming patterns | `references/streaming-patterns.md` | Real-time token streaming, memory.finished synchronization |
| RAG and tools | `references/rag-and-tools.md` | Vector search, rlama integration, dispatch-perception cycle |
| Cross-soul communication | `references/cross-soul-communication.md` | Shared context, optimistic concurrency, ephemeral presence |
| Scheduled events | `references/scheduled-events.md` | Proactive behavior, follow-ups, time-based transitions |

### Background

| Topic | File | Description |
|-------|------|-------------|
| Open Souls README | `references/open-souls-readme.md` | Original project overview and motivation |

## Further Reading

- [Open Souls GitHub](https://github.com/opensouls/opensouls) — The original Soul Engine (TypeScript, MIT license)
- [opensouls.org](https://opensouls.org) — Project website
- Claudicle `ARCHITECTURE.md` — How Claudicle implements these patterns in Python
- Claudicle `daemon/soul_engine.py` — The cognitive pipeline implementation
- Claudicle `docs/extending-claudicle.md` — Developer guide for building extensions
