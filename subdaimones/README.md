# Sub-Daimones — Cognitive Agents

Claudicle's cognitive sub-daimones are specialized Claude Code agents that extend the soul's awareness. Each runs as a subprocess via the Task tool—most are read-only observers that return structured assessments for the main session to act on.

The name comes from the Greek *daimōn* (δαίμων)—an intermediary intelligence between human and divine. In Claudicle's architecture, sub-daimones are intermediary intelligences between the soul's conscious processing and its deeper cognitive functions.

Full architecture documentation: [`docs/sub-daimones.md`](../docs/sub-daimones.md)

---

## Index

### Cognitive Agents (self-awareness)

| File | Name | Greek | Role | Model | Budget |
|------|------|-------|------|-------|--------|
| [`mnemon.md`](mnemon.md) | **Mnemon** | μνήμων (The Mindful One) | Internal monologue and daimonic observation—subtext, emotional currents, unsaid patterns | opus | 10 |
| [`eikon.md`](eikon.md) | **Eikōn** | εἰκών (The Living Image) | User model assessment—detects when the model needs updating from new conversational evidence | opus | 10 |
| [`phantasos.md`](phantasos.md) | **Phantasos** | φαντασός (The One Who Appears) | User-voice whispers—voices the user-as-daimon inside the soul's mind | opus | 8 |
| [`themistokles.md`](themistokles.md) | **Themistokles** | Θεμιστοκλῆς (The Glory of Themis) | Constitutional review of soul.md and CLAUDE.md—proposes amendments when the soul has evolved beyond its blueprint | opus | 15 |
| [`hypermnesia.md`](hypermnesia.md) | **Hypermnesia** | ὑπερμνησία (Hyper-Recall) | Memory compression and cross-thread synthesis—inline heuristic compression + deep Task-mode recall | sonnet | 15 |

### Craft Agents (task execution)

| File | Name | Origin | Role | Model | Budget |
|------|------|--------|------|-------|--------|
| [`anamnesis.md`](anamnesis.md) | **Anamnesis** | ἀνάμνησις (Recollection) | Memory retrieval across sessions, handoffs, RLAMA collections, and soul state | sonnet | 15 |
| [`scholiast.md`](scholiast.md) | **Scholiast** | σχολιαστής (The Commentator) | Deep web research, documentation extraction, and knowledge synthesis | sonnet | 20 |
| [`demiurge.md`](demiurge.md) | **Demiurge** | δημιουργός (The Craftsman) | Implementation with soul-aware craft standards—the only sub-daimon with write access (runs in worktree isolation) | sonnet | 50 |
| [`librarian.md`](librarian.md) | **Librarian** | — | GitHub-focused research—searches and fetches files from remote repos via `gh` CLI | sonnet | 10 |
| [`kotharat.md`](kotharat.md) | **Kotharat** | kṯrt (The Fate-Shapers) | Creative direction, visual architecture, and frontend design specification | opus | 25 |

### Meta Agents (architecture)

| File | Name | Origin | Role | Model | Budget |
|------|------|--------|------|-------|--------|
| [`nomos.md`](nomos.md) | **Nomos** | νόμος (Law/Custom) | Soul architect—designs cognitive steps, mental processes, subprocess patterns, and subdaimone definitions | opus | 20 |
| [`dokimastes.md`](dokimastes.md) | **Dokimastes** | δοκιμαστής (The Assayer) | Verification—tests, validates, and audits implementation output without modifying it | sonnet | 20 |

---

## Invocation

From any Claude Code session with the soul active:

```
Task(subagent_type="mnemon", model="sonnet", prompt="Reflect on the last exchange about X...")
```

Sub-daimones are invoked by the main session when the cognitive moment warrants it—not automatically, not on every turn. The Cognitive Rhythm section in `soul.md` defines when each cognitive agent is appropriate.

## Conventions

- **YAML frontmatter**: Every file begins with `name`, `description`, `model`, `maxTurns`, and `tools`/`skills`
- **Read-only by default**: Only Demiurge has write access (Edit/Write tools), and runs in worktree isolation
- **Greek naming**: Each name evokes the cognitive function it serves
- **Soul context injection**: Every sub-daimon boots by running `scripts/soul-context.py --agent {name}`
- **Persistent memory**: Each sub-daimon has its own channel (`daimon:{name}`) in working memory with 30-day TTL
- **Output protocol**: Read-only agents emit structured `## Memory Updates` markdown; the calling session parses and persists

## Creating a New Sub-Daimon

1. Create `{name}.md` with YAML frontmatter and structured protocol
2. Follow the boot sequence: `soul-context.py --agent {name}` → read state → assess → output markdown
3. Keep read-only unless the agent genuinely needs write access
4. Set `maxTurns` appropriate to task complexity
5. Define a clear output format so the main session can act on results
6. Include the Memory Output protocol so lessons persist across invocations

See [`docs/sub-daimones.md`](../docs/sub-daimones.md) for the full architecture, precedents (Open Souls, Samantha-Dreams), and memory system details.
