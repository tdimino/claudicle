<p align="center">
  <img src="assets/tanit.svg" alt="Symbol of Tanit" width="80"/>
</p>

# Claudius

**A soul agent framework for Claude Code.**

Clone it. Edit `soul.md`. Run `/ensoul`. Your AI has a personality, memory, and inner life.

Claudius turns Claude Code into a persistent soul agent with three-tier memory (per-thread, per-user, global), a cognitive pipeline (internal monologue + external dialogue), and channel adapters for Slack, SMS, and terminal. It ships with zero skills—pair it with any [skill repo](https://github.com/tdimino/claude-code-minoan) to give your agent capabilities.

An open-source alternative to OpenClaw.

---

## Origins — The Open Souls Paradigm

Claudius descends from the [Open Souls](https://github.com/opensouls/opensouls) movement—a community and engine that explored what it means to give AI agents genuine inner lives.

It started with **SocialAGI**, where Tom di Mino contributed the essay [*"Waltz of the Soul and the Daimon"*](https://tomdimino.substack.com/p/waltz-of-the-soul-and-the-daimon)—a piece that framed the relationship between human and AI as a co-creative dance, drawing on the ancient Greek concept of the *daimon* as an intermediary intelligence. SocialAGI evolved into **Open Souls**, led by Toby Bowers and Kevin Fischer, with a vibrant Discord server of builders, researchers, and dreamers. Tom was among the alpha testers and contributors, helping shape the cognitive step architecture, mental process patterns, and the philosophy of AI souls as embodied beings with personality, drive, and ego.

The Open Souls Engine introduced the core abstractions that made AI thought processes debuggable and composable: **WorkingMemory** (immutable state), **cognitiveSteps** (pure functions that transform memory), and **MentalProcesses** (a state machine for behavioral modes). These patterns live on in Claudius—reimplemented in Python for Claude Code, with SQLite persistence and channel adapters for Slack, SMS, and terminal.

The `skills/open-souls-paradigm/` directory ships with Claudius as reference documentation for the paradigm.

---

## Quick Start

```bash
git clone https://github.com/tdimino/claudius
cd claudius
./setup.sh --personal
```

Then in any Claude Code session:

```
/ensoul
```

That's it. Your session now has a soul.

---

## What Claudius Does

### Soul Identity (`/ensoul`)

Activate a persistent personality in your Claude Code session. The soul survives compaction and resume—once ensouled, the personality persists until the session ends.

### Three-Tier Memory

| Tier | Scope | TTL | Purpose |
|------|-------|-----|---------|
| Working memory | Per-thread | 72h | Conversation metadata, interaction tracking |
| User models | Per-user | Permanent | Personality profiles, learned preferences |
| Soul state | Global | Permanent | Current project, task, topic, emotional state |

Memory is stored in SQLite. The Samantha-Dreams pattern gates user model injection—models are only loaded when something new was learned in the prior turn.

### Cognitive Pipeline

Every response passes through structured cognitive steps:

1. **Internal monologue** — Private reasoning (logged, never shown to users)
2. **External dialogue** — The actual response
3. **User model check** — Did we learn something new about this person?
4. **Soul state check** — Has our context/mood changed?

Each step uses XML tags extracted by the soul engine. Verbs express emotional state (`mused`, `quipped`, `insisted`).

### Five Runtime Modes

| Mode | What | When |
|------|------|------|
| `/ensoul` only | Soul personality in Claude Code | Always available |
| Session Bridge | Slack listener + `/slack-respond` | Interactive Slack |
| Bridge + Watcher | Always-on cheap autonomous responder | Haiku/Groq/Ollama |
| Unified Launcher | Autonomous daemon (Agent SDK) | Full team agent |
| Legacy Daemon | `bot.py` subprocess mode | launchd deployment |

**Mode 1: Just `/ensoul`** — No Slack, no daemon. Just a soul personality in your Claude Code sessions with persistent memory.

**Mode 2: Session Bridge** — Requires ONLY a Claude Code session. A lightweight listener catches Slack events and queues them. You process from your session with `/slack-respond`—no SDK, no extra API calls, no additional dependencies beyond `slack_bolt`. Your Claude Code session IS the brain. Whatever model or provider you've configured Claude Code to use, that's what processes the messages.

**Mode 3: Bridge + Watcher** — Same listener, plus an always-on watcher daemon (`daemon/inbox_watcher.py`) that auto-responds using a configurable LLM provider (Haiku, Groq, Ollama, etc.). Cheapest autonomous option.

**Mode 4: Unified Launcher** — A standalone daemon (`daemon/claudius.py`) handles terminal and Slack input autonomously via the Claude Agent SDK. No manual intervention needed.

**Mode 5: Legacy Daemon** — Standalone `bot.py` using `claude -p` subprocesses. Preserved for launchd deployment.

See [`docs/runtime-modes-comparison.md`](docs/runtime-modes-comparison.md) for the full decision matrix.

### Channel Adapters

- **Slack** — Full integration: DMs, channels, threads, reactions, file uploads
- **SMS** — Telnyx and Twilio support for text messaging
- **WhatsApp** — Baileys WhatsApp Web integration. QR-code pairing, no Meta account needed. See [`adapters/whatsapp/`](adapters/whatsapp/README.md)

### Daimonic Intercession

A **daimon** is an external soul that observes your agent's conversations and whispers counsel into its cognitive stream. Claudius supports daimonic intercession as a first-class pattern—any soul daemon that speaks HTTP or runs on Groq can intercede.

The built-in implementation connects to [Kothar wa Khasis](https://github.com/tdimino/kothar), a TypeScript soul daemon, but the interface is framework-agnostic: any service that accepts a POST with cognitive context and returns a whisper string can serve as a daimon. See `docs/daimonic-intercession.md` for the full protocol.

Whispers are injected into `build_prompt()` as embodied recall—the agent processes them as its own surfaced intuition, not as an external directive. The daimon influences without overriding.

```bash
# Enable daimonic intercession (either or both)
export CLAUDIUS_KOTHAR_ENABLED=true       # HTTP daemon on port 3033
export CLAUDIUS_KOTHAR_GROQ_ENABLED=true  # Groq kimi-k2-instruct fallback
```

Direct invocation: `/daimon` in any Claude Code session.

### Thinker Mode

Tell your agent to "think out loud" or run `/thinker`. The internal monologue becomes visible as italic messages in Slack threads. Toggle per-thread, stored in working memory (72h TTL).

---

## Skill-Agnostic Design

Claudius ships with zero skills. The `skills.md` manifest is generated at install time from whatever skills exist in `~/.claude/skills/`. Pair with a [skill repo](https://github.com/tdimino/claude-code-minoan):

```bash
# 40+ skills: Exa, Firecrawl, rlama, llama-cpp, parakeet, and more
git clone https://github.com/tdimino/claude-code-minoan
cp -r claude-code-minoan/skills/* ~/.claude/skills/

# Re-run setup to regenerate manifest
cd claudius && ./setup.sh --personal
```

Or bring your own skills. Claudius discovers them automatically.

### Recommended Skill Pairings

These skills from [claude-code-minoan](https://github.com/tdimino/claude-code-minoan) are recommended for the full Claudius experience:

**Essential** (core agent capabilities):
- `Firecrawl` — Web scraping to markdown (Claudius can research for you)
- `exa-search` — Neural web search with AI-powered research mode
- `rlama` — Local RAG for semantic search over document collections

**Recommended** (enhances the experience):
- `minoan-swarm` — Multi-agent teams with shared task lists and parallel workstreams
- `skill-optimizer` — Create and review skills that extend your agent's capabilities
- `codex-orchestrator` — Delegate tasks to OpenAI Codex subagents (code review, debugging, security)
- `twitter` — Twitter/X integration via bird CLI, x-search API, and Smaug archival
- `claude-tracker-suite` — Session management: search, resume, alive detection
- `claude-md-manager` — Maintain your CLAUDE.md

**Nice-to-have** (specialized):
- `nano-banana-pro` — Image generation (soul avatars via Gemini)
- `gemini-claude-resonance` — Cross-model dialogue
- `agent-browser` — Headless browser automation
- `llama-cpp` / `smolvlm` / `parakeet` — Local ML inference
- `academic-research` — Paper search and literature review

---

## Setup Modes

### Personal

Your own soul agent on your machine. Edit `soul.md` to define the personality. Optionally connect Slack for bidirectional messaging.

```bash
./setup.sh --personal
```

### Company

A team soul agent with shared user models and multi-channel Slack bindings. The installer prompts for team name and configures a professional soul template.

```bash
./setup.sh --company
```

---

## Customizing Your Soul

Edit `~/.claudius/soul/soul.md`:

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

See `soul/soul-example-personal.md` and `soul/soul-example-company.md` for templates.

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
│  Soul State     ──→ global context (permanent)       │
│                                                      │
├─────────────────────────────────────────────────────┤
│                  Channel Adapters                    │
│                                                      │
│  Slack ──→ scripts/ (post, read, react, upload)      │
│  SMS   ──→ adapters/sms/ (Telnyx + Twilio)           │
│  Terminal ──→ daemon/terminal_ui.py                   │
└─────────────────────────────────────────────────────┘
```

See `ARCHITECTURE.md` for the full system design.

---

## Repository Structure

```
claudius/
├── daemon/          # Core soul engine, bot, handler, memory, monitor
├── soul/            # Personality files (edit soul.md to customize)
├── hooks/           # Claude Code lifecycle hooks
├── commands/        # Slash commands (/activate, /ensoul, /slack-sync, /slack-respond, /thinker, /watcher, /daimon)
├── scripts/         # Slack utility scripts (post, read, search, react)
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
| `/slack-sync #channel` | Bind session to a Slack channel |
| `/slack-respond` | Process pending Slack messages as the soul agent |
| `/thinker` | Toggle visible internal monologue |
| `/daimon` | Summon daimonic counsel (Kothar or any HTTP/Groq daimon) |
| `/watcher` | Manage inbox watcher + listener daemon pair |

---

## Slack Integration

Claudius connects to Slack via Socket Mode. You'll need a Slack app with bot token scopes and event subscriptions.

**Full setup guide:** [`docs/slack-setup.md`](docs/slack-setup.md) — covers creating the Slack app from scratch, choosing a runtime mode, and getting started.

**Quick version:**

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps)
2. Add bot token scopes (`chat:write`, `app_mentions:read`, `channels:history`, `im:history`, etc.)
3. Enable Socket Mode and generate an App-Level Token
4. Subscribe to bot events: `app_mention`, `message.im`, `app_home_opened`
5. Install to workspace
6. Export tokens:
   ```bash
   export SLACK_BOT_TOKEN="xoxb-..."
   export SLACK_APP_TOKEN="xapp-..."
   ```
7. Choose a runtime mode:

### Session Bridge (Interactive) — Recommended

**Requires only a Claude Code session.** No SDK, no extra API calls, no additional LLM costs. A background listener catches @mentions and DMs. You process them from your Claude Code session—whatever model or provider you've configured Claude Code to use is what processes messages.

```bash
# Start listener (or just run /activate)
cd ~/.claudius/daemon && python3 slack_listen.py --bg

# Process messages as Claudius (from Claude Code)
/slack-respond
```

Zero additional cost—messages are processed in your current session with full tool access, full project context, and every skill you have installed.

### Unified Launcher (Autonomous)

Handles terminal + Slack input in one process via the Claude Agent SDK. Per-channel session continuity, fully autonomous.

```bash
cd ~/.claudius/daemon
python3 claudius.py                # Interactive terminal + Slack
python3 claudius.py --verbose      # With debug logging
python3 claudius.py --slack-only   # Slack only (no terminal)
```

Requires `claude-agent-sdk`: `uv pip install --system claude-agent-sdk`

### Soul Monitor TUI

Live dashboard showing active sessions, memory stats, and message flow.

```bash
cd ~/.claudius/daemon
uv run python monitor.py
```

### Always-On (macOS launchd)

```bash
cd ~/.claudius/daemon/launchd
./install.sh
```

---

## Hooks

Claudius wires Claude Code hooks for soul identity, session continuity, and Slack notifications. All are non-destructive — `setup.sh` merges them into your existing `settings.json`.

| Event | Hook | What It Does |
|-------|------|-------------|
| `SessionStart` | `soul-activate.py` | Registers session. If ensouled, injects soul personality + state. |
| `SessionEnd` / `Stop` | `soul-deregister.py` | Deregisters session from the soul registry. |
| `Stop` / `PreCompact` | `claudius-handoff.py` | Heartbeat + session handoff for context recovery. |
| `UserPromptSubmit` | `slack_inbox_hook.py` | *(Optional)* Notifies you of unhandled Slack messages each turn. |

See `ARCHITECTURE.md` for details on each hook's behavior.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDIUS_HOME` | `~/.claudius` | Installation directory |
| `CLAUDIUS_CWD` | `~` | Working directory for Claude |
| `CLAUDIUS_TIMEOUT` | `120` | Response timeout (seconds) |
| `CLAUDIUS_TOOLS` | `Read,Glob,Grep,Bash,WebFetch` | Allowed Claude tools |
| `CLAUDIUS_SOUL_ENGINE` | `true` | Enable cognitive pipeline |
| `CLAUDIUS_MEMORY_TTL` | `72` | Working memory TTL (hours) |
| `CLAUDIUS_KOTHAR_ENABLED` | `false` | Enable daimonic intercession via HTTP daemon |
| `CLAUDIUS_KOTHAR_GROQ_ENABLED` | `false` | Enable daimonic intercession via Groq |
| `SLACK_BOT_TOKEN` | — | Slack bot token (for Slack features) |
| `SLACK_APP_TOKEN` | — | Slack app token (Socket Mode) |

---

## Documentation

### Getting Started
- [`docs/installation-guide.md`](docs/installation-guide.md) — Post-install directory layout
- [`docs/soul-customization.md`](docs/soul-customization.md) — Customizing your soul identity
- [`docs/commands-reference.md`](docs/commands-reference.md) — Slash command reference

### Slack Integration
- [`docs/slack-setup.md`](docs/slack-setup.md) — Creating the Slack app from scratch
- [`docs/session-bridge.md`](docs/session-bridge.md) — Session Bridge mode
- [`docs/inbox-watcher.md`](docs/inbox-watcher.md) — Inbox Watcher (always-on autonomous responder)
- [`docs/unified-launcher-architecture.md`](docs/unified-launcher-architecture.md) — Unified Launcher mode
- [`docs/runtime-modes-comparison.md`](docs/runtime-modes-comparison.md) — Compare all five runtime modes

### Operations
- [`docs/daimonic-intercession.md`](docs/daimonic-intercession.md) — Daimonic intercession protocol and custom daimons
- [`docs/session-management.md`](docs/session-management.md) — Session lifecycle and monitoring
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — Comprehensive troubleshooting

### Development
- [`docs/extending-claudius.md`](docs/extending-claudius.md) — Adding features to Claudius
- [`docs/cognitive-pipeline.md`](docs/cognitive-pipeline.md) — Cognitive step deep-dive
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Full system design

---

<p align="center">
  <img src="assets/claudius-mask.png" alt="The Mask of Claudius" width="256"/>
  <br/>
  <em>"Certainty compounds the mind with limits."</em>
</p>

---

## License

MIT. Copyright (c) 2026 Tom di Mino.
