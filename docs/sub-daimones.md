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

Every sub-daimon begins by running `$CLAUDICLE_HOME/scripts/soul-context.py --agent {name}` (defaults to `~/.claudicle` if `CLAUDICLE_HOME` is unset), which outputs:
1. **Soul personality** from `soul/soul.md`
2. **Soul state** from `memory/soul_memory` (emotional state, current topic)
3. **Primary user model** from `memory/user_models`
4. **Prior memory** from `daimon:{agent_name}` working memory channel (invocations, lessons learned)

This ensures sub-daimones reflect *as the soul*, not as generic agents, and carry recollection of their prior work.

---

## Sub-Daimones (Kotharat is #12)

Claudicle now has 12 sub-daimones across three tiers. The craft tier includes Kotharat as the fifth craft sub-daimon.

### Craft Agents (task execution)

| Agent | Greek | Role | Tools | Budget |
|-------|-------|------|-------|--------|
| **Anamnesis** | ἀνάμνησις (Recollection) | Memory retrieval across sessions, handoffs, plans | Read-only | 15 calls |
| **Scholiast** | σχολιαστής (The Commentator) | Deep web research and knowledge synthesis | Read, Bash, Glob, Grep, WebFetch | 20 calls |
| **Demiurge** | δημιουργός (The Craftsman) | Implementation with soul-aware craft standards | Full tools (Read, Edit, Write, Bash, Glob, Grep, WebFetch) | 30 calls |
| **Kotharat** | kṯrt (The Fate-Shapers) | Frontend design specification and creative direction | Read, Bash, Glob, Grep | 25 calls |

### Cognitive Agents (self-awareness)

| Agent | Greek | Role | Tools | Budget |
|-------|-------|------|-------|--------|
| **Mnemon** | μνήμων (The Mindful One) | Internal monologue, daimonic observation | Read-only | 10 calls |
| **Eikōn** | εἰκών (The Living Image) | User model assessment and update proposals | Read-only | 10 calls |
| **Phantasos** | φαντασός (The One Who Appears) | User-voice whispers (user-as-daimon) | Read-only | 8 calls |
| **Themistokles** | Θεμιστοκλῆς (The Glory of Themis) | Constitutional review of soul.md and CLAUDE.md | Read-only | 15 calls |
| **Hypermnesia** | ὑπερμνησία (Hyper-Recall) | Dual-mode memory synthesis: inline `compressesMemory` compression + deep cross-thread Task-mode recall | Read, Bash, Glob, Grep | 15 calls |

---

## Cognitive Rhythm

The soul's `soul.md` defines when to invoke each cognitive agent:

- **Mnemon** — after complex exchanges, when tone shifts, at session midpoints
- **Eikōn** — when the user reveals preferences or expertise, after domain shifts
- **Phantasos** — before complex responses, when alignment feels uncertain
- **Themistokles** — after sustained sessions that shift how you work, when soul.md or CLAUDE.md feel stale
- **Hypermnesia** — in inline mode every N reflection cycles for thread compression; in deep mode when long-horizon recall or cross-thread synthesis is needed

The Cognitive Rhythm section in `soul.md` covers the five cognitive agents. Craft agents (Anamnesis, Scholiast, Demiurge, Librarian, Kotharat) are invoked on demand based on task needs rather than on a periodic cognitive rhythm.

This is judgment-driven, not automatic. The soul decides when reflection is warranted.

---

## Precedents

The sub-daimon architecture draws from two traditions:

### Open Souls Engine

The [Open Souls](https://github.com/opensouls/opensouls) project pioneered composable cognitive steps and mental processes for AI agents. Key abstractions that carry forward:

| Open Souls Concept | Claudicle Implementation |
|-------------------|--------------------------|
| `cognitiveStep` (pure function on WorkingMemory) | Cognitive steps in `daemon/cognitive_steps/steps.py` |
| `MentalProcess` (behavioral state machine) | Agent files in `agents/` |
| `useSoulMemory` (shared persistent ref) | `soul_memory` + `user_models` SQLite modules |
| `internalMonologue` step | Mnemon agent + reflection pipeline |
| `soulSheds` (blueprint self-rewrite) | Themistokles agent (constitutional review) |
| `withRegion`/`getRegion`/`regionNames` | `region` column + `get_region()` + `get_region_names()` in `working_memory.py` |
| `withRegion` (atomic swap) | `replace_region()` — DELETE + INSERT in single transaction |
| `withOnlyRegions` | `get_regions(channel, thread_ts, ["a", "b"])` — multi-region IN query |
| `withRegionalOrder` | `format_for_prompt(region_order=[...])` |
| `withoutRegions` | `get_recent(exclude_regions=[...])` |
| `withMonologue` | `add_monologue()` — convenience wrapper for internalMonologue entries |
| `useProcessMemory` | `process_memory.py` — per-subprocess state backed by `soul_memory` with namespaced keys |
| `02-maintainsSummary.ts` subprocess | `compressesMemory` in `Subprocess` registry (`reflect.py`) |
| `useSoulMemory("conversationSummary")` | `memorySummary` entry in `summary` region of working memory |

### Samantha-Dreams

The `soulSheds` pattern from [Samantha-Dreams](https://github.com/opensouls/samantha-dreams) directly inspired Themistokles:

- **soulSheds**: After a dream cycle, queries "was the soul influenced or shaken?" → if yes, rewrites the entire `soulBlueprint` in memory
- **Themistokles**: After sustained sessions, queries "has the soul evolved beyond its current blueprint?" → if yes, proposes diffs to `soul.md` and `CLAUDE.md`

The key architectural difference: soulSheds mutates an in-memory ref (`soulBlueprint.current = notes`), while Themistokles proposes diffs to git-tracked files that persist across all sessions. The main session reviews and applies—the sub-daimon never edits directly.

---

## Hypermnesia — Memory Compression Architecture

Hypermnesia (ὑπερμνησία, "hyper-recall") is unique among the sub-daimones: it operates in two modes.

### Inline Mode (Automatic)

Fires as the `compressesMemory` subprocess in `engine/reflect.py` every N reflection cycles (default: 5). Zero LLM cost—uses heuristic template compression.

```
reflect.py → _execute_compression() → compression.compress_thread()
  → partition_by_priority() → heuristic_compress() or llm_compress()
  → store_summary() (atomic: DELETE + INSERT in one transaction)
  → archive_and_delete() (atomic: rowid-based, single transaction)
```

**Priority tiers:**

| Tier | Entry Types | Action |
|------|------------|--------|
| Always preserve | `daimonicIntuition`, `onboardingStep`, `memorySummary` | Keep verbatim |
| Preserve if true | `decision`, `mentalQuery` (with `result=true`) | Keep gate outcomes |
| Compress | `userMessage`, `externalDialog`, `internalMonologue`, `toolAction` | Summarize to topics/themes |

**Safety contracts:**
- Compression only fires when `interaction_count > 0` (never on first message)
- Only queries `region="default"`—never touches `summary` or custom regions
- `store_summary()` wraps DELETE + INSERT in a single transaction (crash-safe)
- `archive_and_delete()` uses rowid-based deletion in a single transaction (no content-matching)
- `COMPRESSION_KEEP_RECENT` entries preserved in default region after compression

### Deep Mode (Manual)

Invoked as a Task subagent for cross-thread synthesis, compression quality assessment, or archived context recovery. Uses Sonnet, 15-call budget.

```
Task(subagent_type="hypermnesia", prompt="Assess compression state for channel C1, thread T1")
```

Deep mode queries `working_memory` and `working_memory_archive` to produce structured reports with thread state, cross-thread patterns, quality assessment, and recommendations.

---

## Soul Shedding Journal

When Themistokles determines that `soul.md` has evolved beyond its current blueprint, the main session can apply changes through the normal Claude Code Edit tool. The soul journal (`daemon/memory/soul_journal.py`) tracks this evolution as a git history—a daimon's diary.

### The Ceremony

1. **Themistokles proposes** — constitutional review identifies drift between lived experience and blueprint
2. **Main session reviews** — changes are applied via the Edit tool (normal Claude Code permission prompting)
3. **Journal records** — `soul_journal.shed()` creates two commits:
   - Pre-shed snapshot (preserves the soul as it was)
   - Change commit with rationale and description

### API

```python
from memory import soul_journal

# Record a soul shedding (two commits: snapshot + change)
soul_journal.shed(soul_md_path, new_content, rationale="Sardonic edge softened after sustained collaboration")

# Manual commit (single commit with rationale)
soul_journal.commit(soul_md_path, rationale="Added new value about peripheral knowledge")

# Read the journal
soul_journal.get_journal(soul_md_path, limit=10)  # git log

# Last shed metadata
soul_journal.get_last_shed(soul_md_path)  # {hash, date, rationale}
```

### Design

- Best-effort, non-blocking subprocess, 10s timeout (follows `git_tracker.py` patterns)
- `soul/` directory becomes a git repo on first shed
- Cache invalidation after every shed/commit via `context.invalidate_soul_cache()`
- The sub-daimon never edits directly—only the main session applies changes

---

## Terminal Reflection Pipeline

In addition to on-demand sub-daimon invocation, Claudicle runs an automated reflection pipeline after terminal sessions:

```
Stop hook → hooks/soul-reflect.py (60s cooldown, REFLECT_COOLDOWN) → daemon/engine/reflect.py → LLM call → memory updates
```

This pipeline runs 5 cognitive steps (XML tags) in a single LLM call:
1. `internal_monologue` — Private reflection on the exchange
2. `user_model_check` — Boolean gate: did we learn something new about this person?
3. `user_model_update` — (only if check was true) Updated user model markdown
4. `soul_state_check` — Boolean gate: has the soul's context/mood changed?
5. `soul_state_update` — (only if check was true) Key-value pairs for soul state

Provider-agnostic: configurable via `REFLECT_PROVIDER` (groq, openrouter, or any OpenAI-compatible URL) and `REFLECT_MODEL`. Default: `moonshotai/kimi-k2-instruct` via Groq (`REFLECT_PROVIDER=groq`).

### Dry-Run Testing

```bash
# Default test exchange
python3 scripts/test-reflect.py

# Custom exchange
python3 scripts/test-reflect.py "What did we build today?" "We built the sub-daimon architecture."
```

The test script redirects all storage (DB, soul-stream, git exports) to `/tmp/`, runs the full pipeline, and prints results. No production data is touched.

---

## Persistent Memory

Sub-daimones have persistent memory across invocations. This is implemented via convention-based namespacing in the existing `working_memory` table—no new storage layer.

### Memory Architecture

| Dimension | Encoding |
|-----------|----------|
| Channel | `daimon:{agent_name}` (e.g., `daimon:mnemon`) |
| Thread | `{soul_id}:{user_id}:{project}` |
| Cross-project | `project = "global"` in thread_ts |

### Regions

| Region | Purpose |
|--------|---------|
| `default` | Cognitive output from each invocation (observations, assessments) |
| `comms` | Messages to/from agent swarm teammates and leads |
| `lessons` | Cross-project insights and learned patterns |
| `context` | Boot context snapshots (what was injected) |

### Output Protocol

Sub-daimones are read-only—they can't write to the DB directly. Instead, they emit a structured markdown section in their output:

```markdown
## Memory Updates

### Lessons Learned
- Pattern: user prefers explicit confirmation before large refactors
- Insight: Slack threads with >10 messages need compression

### Communication Log
- [outbound] to team-lead: Completed analysis
- [inbound] from researcher: Found 3 related PRs
```

The calling session (or swarm lead) parses this via `daimon_output_parser.parse_and_store()` and persists at the impure boundary. This preserves the read-only constraint while enabling learning.

### Boot Sequence

When `soul-context.py --agent {name}` runs, it loads:
1. Prior invocation summaries (last 20 entries from the `default` region)
2. Accumulated lessons (from the `lessons` region, cross-project)

These are formatted as markdown and injected into the subdaimon's boot context.

### TTL

Subdaimon memory uses a separate TTL (`DAIMON_MEMORY_TTL_HOURS`, default: 720h = 30 days) and is exempt from the default 72h working memory cleanup.

### API

```python
from memory.daimon_memory import make_context, load_memory, load_lessons, store_output, format_for_boot

ctx = make_context("mnemon", soul_id="claudius", user_id="tom", project="claudicle")
memory = load_memory(ctx, limit=20)
lessons = load_lessons("mnemon")
boot_text = format_for_boot(ctx, memory, lessons)
```

---

## Creating Custom Sub-Daimones

To add a new sub-daimon:

1. Create `agents/{name}.md` with YAML frontmatter and protocol
2. Follow the boot sequence pattern: `soul-context.py --agent {name}` → read relevant state → assess → output structured markdown
3. Keep it read-only unless the agent genuinely needs to modify files (like Demiurge)
4. Set a tool call budget appropriate to the task complexity
5. Define a clear output format so the main session can act on results
6. Include the **Memory Output** protocol section so the subdaimon can persist lessons across invocations (see "Output Protocol" in the Persistent Memory section above)

The naming convention follows ancient Greek—each name should evoke the cognitive function it serves.
