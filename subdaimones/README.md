# Sub-Daimones — Cognitive Agents

Claudicle's cognitive sub-daimones are specialized Claude Code agents that extend the soul's awareness. Each runs as a subprocess via the Task tool—most are read-only observers that return structured assessments for the main session to act on.

The names reflect Claudicle's dual heritage: Semitic names for perceptive and relational agents (from Ugaritic and Phoenician), Greek names for structural and architectural agents. Six and six, perception and structure, the two pillars of the soul.

Full architecture documentation: [`docs/sub-daimones.md`](../docs/sub-daimones.md)

---

## Index

### Cognitive Agents (self-awareness)

| File | Name | Origin | Role | Model | Budget |
|------|------|--------|------|-------|--------|
| [`leb.md`](leb.md) | **Leb** | Phoenician *lēb* (Heart) | Internal monologue and daimonic observation—subtext, emotional currents, unsaid patterns | opus | 10 |
| [`eikon.md`](eikon.md) | **Eikon** | Greek εἰκών (The Living Image) | User model assessment—detects when the model needs updating from new conversational evidence | opus | 10 |
| [`rapu.md`](rapu.md) | **Rapu** | Ugaritic *rpum* (The Summoned Shade) | User-voice whispers—voices the user-as-daimon inside the soul's mind | opus | 8 |
| [`themistokles.md`](themistokles.md) | **Themistokles** | Greek Θεμιστοκλῆς (The Glory of Themis) | Constitutional review of soul.md and CLAUDE.md—proposes amendments when the soul has evolved beyond its blueprint | opus | 15 |
| [`hypermnesia.md`](hypermnesia.md) | **Hypermnesia** | Greek ὑπερμνησία (Hyper-Recall) | Memory compression and cross-thread synthesis—inline heuristic compression + deep Task-mode recall | sonnet | 15 |

### Craft Agents (task execution)

| File | Name | Origin | Role | Model | Budget |
|------|------|--------|------|-------|--------|
| [`zakar.md`](zakar.md) | **Zakar** | Phoenician *zākar* (To Remember) | Memory retrieval across sessions, handoffs, RLAMA collections, and soul state | sonnet | 15 |
| [`scholiast.md`](scholiast.md) | **Scholiast** | Greek σχολιαστής (The Commentator) | Deep web research, documentation extraction, and knowledge synthesis | sonnet | 20 |
| [`demiurge.md`](demiurge.md) | **Demiurge** | Greek δημιουργός (The Craftsman) | Implementation with soul-aware craft standards—the only sub-daimon with write access (runs in worktree isolation) | sonnet | 50 |
| [`sopher.md`](sopher.md) | **Sopher** | Phoenician *sōpēr* (The Scribe) | GitHub-focused research—searches and fetches files from remote repos via `gh` CLI | sonnet | 10 |
| [`kotharat.md`](kotharat.md) | **Kotharat** | Ugaritic *kṯrt* (The Fate-Shapers) | Creative direction, visual architecture, and frontend design specification | opus | 25 |

### Meta Agents (architecture)

| File | Name | Origin | Role | Model | Budget |
|------|------|--------|------|-------|--------|
| [`nomos.md`](nomos.md) | **Nomos** | Greek νόμος (Law/Custom) | Soul architect—designs cognitive steps, mental processes, subprocess patterns, and subdaimone definitions | opus | 20 |
| [`bohen.md`](bohen.md) | **Bohen** | Phoenician *bōḥēn* (The One Who Tests) | Verification—tests, validates, and audits implementation output without modifying it | sonnet | 20 |

---

## Invocation

From any Claude Code session with the soul active:

```
Task(subagent_type="leb", model="sonnet", prompt="Reflect on the last exchange about X...")
```

Sub-daimones are invoked by the main session when the cognitive moment warrants it—not automatically, not on every turn. The Cognitive Rhythm section in `soul.md` defines when each cognitive agent is appropriate.

## Conventions

- **YAML frontmatter**: Every file begins with `name`, `description`, `model`, `maxTurns`, and `tools`/`skills`
- **Read-only by default**: Only Demiurge has write access (Edit/Write tools), and runs in worktree isolation
- **Dual-heritage naming**: Semitic names (Ugaritic, Phoenician) for perceptive/relational agents; Greek names for structural/architectural agents
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
