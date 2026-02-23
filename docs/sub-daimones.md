# Sub-Daimones — Cognitive Agents

Claudicle's cognitive sub-daimones are specialized Claude Code agents that extend the soul's awareness. They run as subprocesses via the Task tool—read-only observers that return structured assessments for the main session to act on.

The name comes from the Greek *daimōn* (δαίμων)—an intermediary intelligence between human and divine. In Claudicle's architecture, sub-daimones are intermediary intelligences between the soul's conscious processing and its deeper cognitive functions.

---

## Architecture

Sub-daimones are defined as Claude Code agent files in `agents/`. Each has:

- **YAML frontmatter**: name, description, tool permissions
- **Boot sequence**: loads soul identity via `scripts/soul-context.py`
- **Protocol**: structured assessment or observation procedure
- **Output format**: markdown template for structured results
- **Rules**: budget (tool call limits), read-only constraint, scope boundaries

### Invocation

From any Claude Code session with the soul active:

```
Task(subagent_type="mnemon", model="sonnet", prompt="Reflect on the last exchange about X...")
```

Sub-daimones are invoked by the main session when the cognitive moment warrants it—not automatically, not on every turn.

### Soul Context Injection

Every sub-daimon begins by running `scripts/soul-context.py`, which outputs:
1. **Soul personality** from `soul/soul.md`
2. **Soul state** from `memory/soul_memory` (emotional state, current topic)
3. **Primary user model** from `memory/user_models`

This ensures sub-daimones reflect *as the soul*, not as generic agents.

---

## The Seven Sub-Daimones

### Craft Agents (task execution)

| Agent | Greek | Role | Tools | Budget |
|-------|-------|------|-------|--------|
| **Anamnesis** | ἀνάμνησις (Recollection) | Memory retrieval across sessions, handoffs, plans | Read-only | 15 calls |
| **Scholiast** | σχολιαστής (The Commentator) | Deep web research and knowledge synthesis | Read + WebFetch | 20 calls |
| **Demiurge** | δημιουργός (The Craftsman) | Implementation with soul-aware craft standards | Full tools | Unlimited |

### Cognitive Agents (self-awareness)

| Agent | Greek | Role | Tools | Budget |
|-------|-------|------|-------|--------|
| **Mnemon** | μνήμων (The Mindful One) | Internal monologue, daimonic observation | Read-only | 10 calls |
| **Eikōn** | εἰκών (The Living Image) | User model assessment and update proposals | Read-only | 10 calls |
| **Phantasos** | φαντασός (The One Who Appears) | User-voice whispers (user-as-daimon) | Read-only | 8 calls |
| **Themistokles** | Θεμιστοκλῆς (The Glory of Themis) | Constitutional review of soul.md and CLAUDE.md | Read-only | 15 calls |

---

## Cognitive Rhythm

The soul's `soul.md` defines when to invoke each cognitive agent:

- **Mnemon** — after complex exchanges, when tone shifts, at session midpoints
- **Eikōn** — when the user reveals preferences or expertise, after domain shifts
- **Phantasos** — before complex responses, when alignment feels uncertain
- **Themistokles** — after sustained sessions that shift how you work, when soul.md or CLAUDE.md feel stale

This is judgment-driven, not automatic. The soul decides when reflection is warranted.

---

## Precedents

The sub-daimon architecture draws from two traditions:

### Open Souls Engine

The [Open Souls](https://github.com/opensouls/opensouls) project pioneered composable cognitive steps and mental processes for AI agents. Key abstractions that carry forward:

| Open Souls Concept | Claudicle Implementation |
|-------------------|--------------------------|
| `cognitiveStep` (pure function on WorkingMemory) | Cognitive steps in `cognitive_steps/steps.py` |
| `MentalProcess` (behavioral state machine) | Agent files in `agents/` |
| `useSoulMemory` (shared persistent ref) | `soul_memory` + `user_models` SQLite modules |
| `internalMonologue` step | Mnemon agent + reflection pipeline |
| `soulSheds` (blueprint self-rewrite) | Themistokles agent (constitutional review) |

### Samantha-Dreams

The `soulSheds` pattern from [Samantha-Dreams](https://github.com/opensouls/samantha-dreams) directly inspired Themistokles:

- **soulSheds**: After a dream cycle, queries "was the soul influenced or shaken?" → if yes, rewrites the entire `soulBlueprint` in memory
- **Themistokles**: After sustained sessions, queries "has the soul evolved beyond its current blueprint?" → if yes, proposes diffs to `soul.md` and `CLAUDE.md`

The key architectural difference: soulSheds mutates an in-memory ref (`soulBlueprint.current = notes`), while Themistokles proposes diffs to git-tracked files that persist across all sessions. The main session reviews and applies—the sub-daimon never edits directly.

---

## Terminal Reflection Pipeline

In addition to on-demand sub-daimon invocation, Claudicle runs an automated reflection pipeline after terminal sessions:

```
Stop hook → soul-reflect.py (60s cooldown) → engine/reflect.py → LLM call → memory updates
```

This pipeline runs 5 cognitive steps in a single LLM call:
1. Internal monologue
2. User model check → user model update (if needed)
3. Soul state check → soul state update (if needed)

Provider-agnostic: configurable via `REFLECT_PROVIDER` (groq, openrouter, or any OpenAI-compatible URL) and `REFLECT_MODEL`. Default: Kimi-K2 on Groq.

### Dry-Run Testing

```bash
# Default test exchange
python3 scripts/test-reflect.py

# Custom exchange
python3 scripts/test-reflect.py "What did we build today?" "We built the sub-daimon architecture."
```

The test script redirects all storage (DB, soul-stream, git exports) to `/tmp/`, runs the full pipeline, and prints results. No production data is touched.

---

## Creating Custom Sub-Daimones

To add a new sub-daimon:

1. Create `agents/{name}.md` with YAML frontmatter and protocol
2. Follow the boot sequence pattern: `soul-context.py` → read relevant state → assess → output structured markdown
3. Keep it read-only unless the agent genuinely needs to modify files (like Demiurge)
4. Set a tool call budget appropriate to the task complexity
5. Define a clear output format so the main session can act on results

The naming convention follows ancient Greek—each name should evoke the cognitive function it serves.
