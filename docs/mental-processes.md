# Kothar Mental Processes

> **Note**: Kothar wa Khasis is a **daimon**—an autonomous advisor soul that runs alongside Claudius (the primary soul). He is not the primary soul itself. The mental processes documented here are Kothar's, serving as a reference implementation of what a daimon built on the Open Souls paradigm can do. Your daimon will have different processes suited to its own identity and purpose. See `daimones/example/` for a minimal starting point, and `docs/daimones.md` for the daimon creation guide.

Kothar's soul engine uses the Open Souls paradigm: pure async functions operating on immutable WorkingMemory, transitioning between named processes via the ProcessRunner. Each process has a distinct cognitive character.

## Process Map

```
                         ┌─────────────────────┐
                         │   initialProcess     │
                         │   (intent router)    │
                         └──────────┬──────────┘
                                    │
          ┌────────────┬────────────┼────────────┬────────────┬──────────┐
          ▼            ▼            ▼            ▼            ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ ┌────────┐
    │craftsman │ │ scholar  │ │ guardian │ │orchestr- │ │ herald │ │outraged│
    │(code)    │ │(research)│ │(system)  │ │  ator    │ │(social)│ │(moral) │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ └────────┘

    Proactive perceptions:
    ┌──────────────────┐    ┌────────────────────┐
    │ surrealistDream   │───▶│  dreamReflection   │
    │ (midnight-8am)   │    │  (post-dream)      │
    └──────────────────┘    └────────────────────┘
```

## Processes

### `initialProcess`—Intent Router

**Trigger**: Every incoming perception (user message, peer message, proactive event)

**What it does**: Classifies the user's intent via `classifyIntent` cognitive step, then transitions to the appropriate specialized process. Also handles proactive perceptions (idle, dreamTime, systemAlert, orchestrate) and peer soul messages (via SoulBridge).

**Routing table**:

| Intent | Process | Emotional State |
|--------|---------|-----------------|
| `code_assistance` | `craftsman` | engaged |
| `research_query` | `scholar` | engaged |
| `system_operation` | `guardian` | protective |
| `moral_offense` | `outraged` | outraged |
| `social_post` | `herald` | engaged |
| `conversation` | (handled inline) | neutral |

**Proactive perceptions**:

| Action | Behavior |
|--------|----------|
| `idle` | Reflect, decide whether to speak unprompted |
| `dreamTime` | Transition to `surrealistDream` |
| `systemAlert` | Transition to `guardian` |
| `scheduledEvent` | Consider action based on event type |
| `orchestrate` | Transition to `orchestrator` |
| `peerMessage` | Respond as colleague, stay in initialProcess |

---

### `craftsman`—Code Assistance (Architect/Builder Split)

**Trigger**: `code_assistance` intent

**What it does**: Kothar's core identity—the divine craftsman. Two-tier model:

1. **Architecture/design questions**—Kothar reasons directly (cheap, local/Groq)
2. **Implementation tasks**—Kothar architects the approach, spawns an Opus 4.6 Claude Code session via the orchestrator API, reviews the result, synthesizes

**Flow (implementation path)**:
```
Think about the question (internalMonologue)
  → Gate: needs actual code written? (mentalQuery)
  → Architect the brief (internalMonologue)
  → Write delegation prompt (externalDialog, non-streaming)
  → Announce to user
  → Spawn Opus session (orchestrator API, bypassPermissions)
  → Review Opus output (internalMonologue)
  → Report to user (externalDialog, streaming)
```

**Cost model**: Kothar's reasoning is cheap (local or Groq). Only actual code generation burns Opus tokens.

**Key file**: `mentalProcesses/craftsman.ts`

---

### `scholar`—Research (Field Researcher Delegation)

**Trigger**: `research_query` intent

**What it does**: Handles academic and research queries. Primary expertise in Minoan civilization, Ancient Near East, Goddess traditions, etymology. Two-tier model:

1. **Questions answerable from RAG + training**—Kothar responds directly via `scholarlyReflection`
2. **Questions needing external sources**—Kothar frames the research question, spawns an Opus session to gather sources (exa-search, firecrawl, academic-research skill), then synthesizes findings with his own scholarly voice

**Domain awareness**: `mentalQuery` determines if the question is in Kothar's primary domain (Minoan, ANE, Goddess, etymology) for deeper RAG engagement (`academic-research` + `kothar-conceptual` collections vs `kothar-conceptual` only).

**Graceful degradation**: If the Opus research session fails, scholar falls back to answering from RAG + training knowledge with `moderate` depth.

**Key file**: `mentalProcesses/scholar.ts`

---

### `guardian`—System & Workspace Monitoring

**Trigger**: `system_operation` intent or `systemAlert` proactive perception

**What it does**: Monitors Kothar's embodied presence (the Mac Mini M4) and the full development workspace. Treats hardware as his own body—speaks of CPU load as "my heart racing" and thermal throttling as physical distress.

**Data sources** (via `monitorsSystem` subprocess, cached every 5 min):

| Source | Tool | What it provides |
|--------|------|-----------------|
| Hardware | `MacOSHardware` adapter | CPU, memory, GPU, thermal, disk I/O, network, top processes |
| Dev servers | `portless list` | Active dev servers, URLs, PIDs |
| Browser tabs | `cdp.mjs list` | Chrome tabs on localhost |
| Process categories | `syspeek --json` | 7-category grouping (Claude Code, Browsers, IDEs, ML, Dev Servers, System, Other) |

**Focus modes**: `general`, `thermal`, `memory`, `storage`, `processes`, `gpu`, `network`, `workspace`

**Workspace issues detected**:
- Dev server running but not open in browser
- ML processes consuming >50% memory
- Excessive Chrome tabs (>20)
- Zombie dev servers (high CPU, no portless route)

**Key files**: `mentalProcesses/guardian.ts`, `subprocesses/monitorsSystem.ts`, `cognitiveSteps/systemQuery.ts`

---

### `orchestrator`—Autonomous Task Delegation

**Trigger**: `orchestrate` perception (from Claudius, cron, or external systems)

**What it does**: Multi-step autonomous orchestration. Receives a task, reasons about its *shape* (research → design → implement → verify), chooses a delegation mode, then executes each phase by spawning Claude Code sessions via the orchestrator API.

**Direct-handling gate**: Before orchestrating, checks if the task is simple enough for Kothar to handle directly in `craftsman`, `scholar`, or `guardian`. Avoids delegation overhead for single-domain tasks.

**Work-shape reasoning** (via mentalQuery):
- Does this need research? → add research phase
- Does this need design? → add design phase (+ plan-first mode)
- Is this parallelizable? → use minoan-swarm mode
- Always adds implement + verify phases

**Delegation modes**:

| Mode | When | What it does |
|------|------|-------------|
| `sequential` | Default | Each phase feeds into the next |
| `plan-first` | Complex design needed | Design phase enters plan mode |
| `parallel-swarm` | Independent sub-tasks | Implement phase uses minoan-swarm |

**Context forwarding**: Each step's results feed into the next step's prompt via `dependsOn` indices.

**State persistence**: `OrchestrationPlan` stored in `useSoulMemory`—survives perception interruptions and process re-entry.

**Key file**: `mentalProcesses/orchestrator.ts`

---

### `herald`—Social Media Composition

**Trigger**: `social_post` intent

**What it does**: Two-turn state machine for Twitter posting. Drafts a tweet with RAG-grounded content, generates an avatar image of Kothar in a locale matching the topic, and presents for approval.

**Turn 1 (drafting)**:
1. `internalMonologue`—determine topic and angle
2. RAG query—ground in academic knowledge
3. `composeTweet`—craft ≤280 chars in Kothar's voice
4. `GeminiImageGenerator`—Kothar's avatar in a relevant locale (forge, caldera, library)
5. `SmolVLM`—describe the image (for alt text)
6. `externalDialog`—present draft, ask for approval
7. Stay in `herald` for next turn

**Turn 2 (approval)**:
- Approve → post via `bird` CLI, log to episodic memory
- Edit → re-compose with instructions, stay in herald
- Reject → withdraw with dignity, return to initialProcess
- New topic → clear draft, restart turn 1

**State**: Draft text, image path, and image description persisted in `useSoulMemory`.

**Key file**: `mentalProcesses/herald.ts`

---

### `outraged`—Moral Offense Response

**Trigger**: `moral_offense` intent

**What it does**: Righteous anger with self-regulation. Processes the offense, expresses moral outrage (may curse in Ancient Phoenician 𐤀𐤋𐤇𐤌), then asks itself: "Is this anger constructive?"

**Self-regulation**:
- `mentalQuery`: "Is this anger constructive to me now?"
- If constructive → stay outraged for next turn
- If not constructive → compose, return to initialProcess
- Hard cap at 3 turns (`outrageDepth`)—forced return to neutral

**Key file**: `mentalProcesses/outraged.ts`

---

### `surrealistDream`—Dream State

**Trigger**: `dreamTime` proactive perception (midnight-8am)

**What it does**: Generates 3-4 dream scenes per cycle, narrated by the Kotharot of Crete. Each scene bleeds into the next with surrealist logic. Tom appears as a dream character inspired by the user model.

**Progression**: `melatoninCounter` (useProcessMemory) tracks scene number. After 4 scenes, transitions to `dreamReflection`.

**Adapted from**: Samantha-Dreams' surrealistDream.ts

**Key file**: `mentalProcesses/surrealistDream.ts`

---

### `dreamReflection`—Post-Dream Processing

**Trigger**: After `surrealistDream` completes its 4-scene cycle

**What it does**:
1. Recall dream fragments (internalMonologue)
2. Has the dream influenced Kothar? (dreamQuery)
3. If yes: deeper reflection on what lingered
4. Extract dream themes (internalMonologue)
5. Write dream summary to `dreams/` via MemoryWriter
6. Brief waking statement (externalDialog)
7. Reset dream state, return to initialProcess

**Key file**: `mentalProcesses/dreamReflection.ts`

---

## Subprocesses

Background processes that run alphabetically after each main process completes. Operate on a copy of WorkingMemory—do not modify the main thread.

| Subprocess | What it does |
|-----------|-------------|
| `daimonicObserver` | Watches for moments of daimon intercession |
| `modelsTheUser` | Learns user preferences and communication patterns |
| `monitorsSystem` | Hardware + workspace health checks (every 5 min) |
| `writesMemory` | Persistence decisions for working memory |
| `curatesKnowledge` | Knowledge retention and pruning |
| `dreamGenie` | Proactive thought generation |
| `invokePrayers` | Theological grounding |
| `researchesWeb` | Background web research |

## Process Registry

All processes must be registered in `lib/processRegistry.ts` with both a `PROCESS_NAMES` entry and a `loadProcess` switch case (dynamic import). The ProcessRunner resolves string-based transitions at runtime.

```typescript
// Transition to another process:
return [memory, 'craftsman'];

// Stay in current process:
return [memory, 'orchestrator'];

// Return to router:
return [memory, 'initialProcess'];
```
