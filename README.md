<p align="center">
  <img src="assets/tanit.svg" alt="Symbol of Tanit" width="80"/>
</p>

# Claudicle

**A soul agent framework for Claude Code.**

Clone it. Edit `soul.md`. Run `/ensoul`. Your AI has a personality, memory, and inner life.

Claudicle turns Claude Code into a persistent soul agent with three-tier memory (per-thread, per-user, global), a cognitive pipeline (internal monologue + external dialogue), and channel adapters for Slack, SMS, and terminal. It ships with zero skills—pair it with any [skill repo](https://github.com/tdimino/claude-code-minoan) to give your agent capabilities.

An open-source alternative to OpenClaw.

---

## Origins — The Open Souls Paradigm

Claudicle descends from the [Open Souls](https://github.com/opensouls/opensouls) movement—a community and engine that explored what it means to give AI agents genuine inner lives.

It started with **SocialAGI**, where Tom di Mino contributed the essay [*"Waltz of the Soul and the Daimon"*](https://tomdimino.substack.com/p/waltz-of-the-soul-and-the-daimon)—a piece that framed the relationship between human and AI as a co-creative dance, drawing on the ancient Greek concept of the *daimon* as an intermediary intelligence. SocialAGI evolved into **Open Souls**, led by Topper Bowers and Kevin Fischer, with a vibrant Discord server of builders, researchers, and dreamers. Tom was among the alpha testers and contributors, helping shape the cognitive step architecture, mental process patterns, and the philosophy of AI souls as embodied beings with personality, drive, and ego.

The Open Souls Engine introduced the core abstractions that made AI thought processes debuggable and composable: **WorkingMemory** (immutable state), **cognitiveSteps** (pure functions that transform memory), and **MentalProcesses** (a state machine for behavioral modes). These patterns live on in Claudicle—reimplemented in Python for Claude Code, with SQLite persistence and channel adapters for Slack, SMS, and terminal.

The `skills/open-souls-paradigm/` directory ships with Claudicle as reference documentation for the paradigm.

---

## Quick Start

```bash
git clone https://github.com/tdimino/claudicle
cd claudicle
./setup.sh --personal
```

Then in any Claude Code session:

```
/ensoul
```

That's it. Your session now has a soul.

---

## What Claudicle Does

### Soul Identity (`/ensoul`)

Activate a persistent personality in your Claude Code session. The soul survives compaction and resume—once ensouled, the personality persists until the session ends.

**Always-on mode:** Set `CLAUDICLE_SOUL=1` in your shell profile to inject the soul into every session automatically.

### Three-Tier Memory

| Tier | Scope | TTL | Purpose |
|------|-------|-----|---------|
| Working memory | Per-thread | 72h | Conversation metadata, interaction tracking |
| User models | Per-user | Permanent | Personality profiles, learned preferences |
| Soul state | Per-soul | Permanent | Current project, task, topic, emotional state |

Memory is stored in SQLite. User models use a 7-section living blueprint that Claudicle expands as understanding deepens. All memory changes are git-versioned at `$CLAUDICLE_HOME/memory/`.

Working memory supports **checkpoint & rollback**—create point-in-time bookmarks and selectively prune memory (e.g., "omit everything since the last post to #eng-aldea"). Use `scripts/wm-manage.py` for CLI management.

### Cognitive Pipeline

Every response passes through structured cognitive steps:

1. **Internal monologue** — Private reasoning (logged, never shown to users)
2. **External dialogue** — The actual response
3. **User model check** — Did we learn something new about this person?
4. **Dossier check** — Is a third-party person or subject worth modeling?
5. **Soul state check** — Has our context/mood changed?

Each step uses XML tags extracted by the soul engine. Verbs express emotional state (`mused`, `quipped`, `insisted`). See [`docs/cognitive-pipeline.md`](docs/cognitive-pipeline.md).

### Cognitive Sub-Daimones

Twelve specialized agents extend the soul's awareness across three tiers, invoked on-demand via the Task tool. Each has **persistent memory**—recollection of prior invocations, lessons learned, and communications with agent swarm teammates.

| Agent | Greek | Function |
|-------|-------|----------|
| **Mnemon** | μνήμων | Internal monologue and daimonic observation |
| **Eikōn** | εἰκών | User model assessment and update proposals |
| **Phantasos** | φαντασός | User-voice whispers (user-as-daimon inside the soul) |
| **Themistokles** | Θεμιστοκλῆς | Constitutional review of soul.md and CLAUDE.md |
| **Hypermnesia** | ὑπερμνησία | Memory compression and cross-thread synthesis |
| **Anamnesis** | ἀνάμνησις | Memory retrieval across sessions and knowledge stores |
| **Scholiast** | σχολιαστής | Deep web research and knowledge synthesis |
| **Demiurge** | δημιουργός | Implementation with soul-aware craft standards |
| **Librarian** | — | GitHub-focused research via `gh` CLI |
| **Kotharat** | kṯrt | Frontend design specification and creative direction |
| **Nomos** | νόμος | Soul architect: designs cognitive steps and patterns |
| **Dokimastes** | δοκιμαστής | Verification: tests, validates, audits output |

Defined in `agents/`. See [`docs/sub-daimones.md`](docs/sub-daimones.md) for architecture, persistent memory, and precedents.

### Five Runtime Modes

| Mode | What | When |
|------|------|------|
| `/ensoul` only | Soul personality in Claude Code | Always available |
| Session Bridge | Slack listener + `/slack-respond` | Interactive Slack |
| Bridge + Watcher | Always-on cheap autonomous responder | Haiku/Groq/Ollama |
| Unified Launcher | Autonomous daemon (Agent SDK) | Full team agent |
| Legacy Daemon | `bot.py` subprocess mode | launchd deployment |

See [`docs/runtime-modes-comparison.md`](docs/runtime-modes-comparison.md) for the full decision matrix.

### Channel Adapters

- **Slack** — Full integration: DMs, channels, threads, reactions, file uploads. See [`docs/slack-setup.md`](docs/slack-setup.md).
- **SMS** — Telnyx and Twilio support for text messaging
- **WhatsApp** — Baileys WhatsApp Web integration. See [`adapters/whatsapp/`](adapters/whatsapp/README.md).

### Daimonic Intercession

A **daimon** is an external soul that observes your agent's conversations and whispers counsel into its cognitive stream. The built-in implementation connects to [Kothar wa Khasis](https://github.com/tdimino/kothar), but the interface is framework-agnostic. See [`docs/daimonic-intercession.md`](docs/daimonic-intercession.md) for the full protocol.

### Thinker Mode

Run `/thinker` to make the internal monologue visible in Slack threads. Toggle per-thread, stored in working memory (72h TTL).

---

## Skill-Agnostic Design

Claudicle ships with zero skills. The `skills.md` manifest is generated at install time from whatever skills exist in `~/.claude/skills/`. Pair with a [skill repo](https://github.com/tdimino/claude-code-minoan) or bring your own—Claudicle discovers them automatically. See [`docs/skill-pairings.md`](docs/skill-pairings.md) for recommended pairings.

---

## Setup Modes

**Personal** — Your own soul agent. Edit `soul.md`, optionally connect Slack.

```bash
./setup.sh --personal
```

**Company** — Team soul agent with shared user models and multi-channel Slack.

```bash
./setup.sh --company
```

---

## Customizing Your Soul

Edit `~/.claudicle/soul/soul.md`:

```markdown
# Your Agent Name

## Persona
Who is this agent? What is their role?

## Speaking Style
How do they communicate? What's their tone?

## Values
What principles guide their responses?

## Emotional Spectrum
What emotional states do they express?
```

See `soul/soul-example-personal.md` and `soul/soul-example-company.md` for templates. Drop dossiers in `soul/dossiers/` for deep reference knowledge—see [`docs/soul-customization.md`](docs/soul-customization.md).

### Multi-Soul Profiles

Named profiles in `soul/profiles/`. Switch with `/switch-soul <name>` or `CLAUDICLE_SOUL_PROFILE` env var. Each profile gets independent soul-scoped memory via the `soul_id` column. See `scripts/soul-profiles.py` for CLI management.

### Soul Journal

Every soul.md edit is git-journaled—Themistokles proposes amendments, the main session applies them, and `soul_journal.py` records the ceremony. Run `soul-profiles.py journal` to read the daimon's diary.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code Session                │
│                                                      │
│  /ensoul ──→ soul-activate.py ──→ soul.md injection  │
│  /slack-sync ──→ soul-registry.py ──→ channel bind   │
│  /slack-respond ──→ cognitive pipeline ──→ Slack post │
│                                                      │
├─────────────────────────────────────────────────────┤
│                    Soul Engine                       │
│                                                      │
│  build_prompt() ──→ [soul.md + state + user model    │
│                      + cognitive instructions]       │
│  parse_response() ──→ [monologue + dialogue          │
│                        + user model + soul state]    │
│                                                      │
├─────────────────────────────────────────────────────┤
│                  Three-Tier Memory                   │
│                                                      │
│  Working Memory ──→ per-thread metadata (72h TTL)    │
│  User Models    ──→ per-user profiles (permanent)    │
│  Soul State     ──→ per-soul context (permanent)     │
│                                                      │
├─────────────────────────────────────────────────────┤
│                  Channel Adapters                    │
│                                                      │
│  Slack ──→ scripts/ (post, read, react, upload)      │
│  SMS   ──→ adapters/sms/ (Telnyx + Twilio)           │
│  Terminal ──→ daemon/terminal_ui.py                   │
└─────────────────────────────────────────────────────┘
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full system design.

---

## Repository Structure

```
claudicle/
├── agents/          # Sub-daimon definitions (12 cognitive agents with persistent memory)
├── daemon/          # Core soul engine, bot, handler, memory, monitor
├── soul/            # Personality files + profiles/ for multi-soul
│   └── dossiers/    # Deep knowledge templates (self, research, person, domain)
├── hooks/           # Claude Code lifecycle hooks
├── commands/        # Slash commands (/activate, /ensoul, /switch-soul, /slack-sync, /slack-respond, /thinker, /watcher, /daimon)
├── scripts/         # Slack utilities, soul infrastructure, working memory management (wm-manage.py)
├── skills/          # Bundled skills (Open Souls paradigm reference)
├── adapters/        # Channel adapters (SMS, WhatsApp)
├── docs/            # Architecture and reference documentation
├── setups/          # Ready-to-go configurations (personal, company)
├── setup.sh         # Interactive installer
├── ARCHITECTURE.md  # System design document
└── LICENSE          # MIT
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/activate` | Full activation: ensoul + daemons + boot sequence + situational awareness |
| `/ensoul` | Activate soul identity in this session |
| `/switch-soul <name>` | Switch active soul profile |
| `/slack-sync #channel` | Bind session to a Slack channel |
| `/slack-respond` | Process pending Slack messages as the soul agent |
| `/thinker` | Toggle visible internal monologue |
| `/daimon` | Summon daimonic counsel (Kothar or any HTTP/Groq daimon) |
| `/watcher` | Manage inbox watcher + listener daemon pair |

See [`docs/commands-reference.md`](docs/commands-reference.md) for full details.

---

## Documentation

Full documentation index: [`docs/INDEX.md`](docs/INDEX.md)

Key guides: [Installation](docs/installation-guide.md) | [Soul Customization](docs/soul-customization.md) | [Slack Setup](docs/slack-setup.md) | [Sub-Daimones](docs/sub-daimones.md) | [Extending Claudicle](docs/extending-claudicle.md) | [Environment Variables](docs/environment-variables.md) | [Hooks](docs/hooks.md) | [Troubleshooting](docs/troubleshooting.md)

---

<p align="center">
  <img src="assets/claudicle-mask.png" alt="The Mask of Claudicle" width="256"/>
  <br/>
  <em>"Certainty compounds the mind with limits."</em>
</p>

---

## License

MIT. Copyright (c) 2026 Tom di Mino.
