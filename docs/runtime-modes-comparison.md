# Runtime Modes Comparison

How should you run Claudicle? This guide compares all five runtime modes to help you choose.

---

## Mode Summary

### `/ensoul` — Soul-in-Session

Inject soul personality into a standard Claude Code session. No Slack, no daemon, no extra processes. The lightest integration — you get Claudicle's personality and memory in your current session.

### Session Bridge — Interactive Slack (Requires Only Claude Code)

**The only mode that requires nothing beyond a running Claude Code session.** A background listener catches Slack events and writes them to an inbox file. You process messages from your session with `/slack-respond`. Whatever model or provider you've configured Claude Code to use is what processes messages. No SDK, no extra API calls, no additional LLM costs. You control when the agent responds.

### Bridge + Watcher — Autonomous Cheap Responder

Same as Session Bridge, plus an always-on watcher daemon that auto-responds using a configurable LLM provider (Haiku, Groq, Ollama). The watcher handles simple messages autonomously; you handle complex ones with `/slack-respond`.

### Unified Launcher — Full Autonomous Agent

Standalone daemon handling terminal and Slack in one process via the Claude Agent SDK. Per-channel session isolation, shared soul engine, three-tier memory. No manual intervention needed.

### Legacy Daemon — Subprocess Bot

Standalone Slack bot using `claude -p` subprocesses. Preserved for launchd deployment and as a fallback.

---

## Decision Matrix

| | `/ensoul` | Session Bridge | Bridge + Watcher | Unified Launcher | Legacy Daemon |
|---|---|---|---|---|---|
| **Autonomy** | Manual | Manual (`/slack-respond`) | Auto (configurable) | Fully autonomous | Fully autonomous |
| **API cost** | Zero | Zero | Per-message (cheap) | Per-message (full) | Per-message (full) |
| **Tool access** | Full session tools | Full session tools | Provider only | Configured per-origin | Configured |
| **Session isolation** | N/A | Shared (one brain) | Shared (one brain) | Per-channel/thread | Per-channel/thread |
| **Requires Claude Code** | Yes (is a session) | Yes (is the brain) | No | No | No |
| **Provider choice** | Whatever Claude Code uses | Whatever Claude Code uses | Any (Haiku, Groq, Ollama...) | Claude SDK only | Claude CLI only |
| **Slack integration** | No | Yes | Yes | Yes | Yes |
| **Terminal access** | Yes (is a session) | Separate session | No | Yes (shared process) | No |
| **Per-step routing** | No | No | Yes (split mode) | Yes (split mode) | No |
| **launchd deployable** | No | Listener only | Both daemons | Not yet | Yes |
| **Dependencies** | None | `slack_bolt` | `slack_bolt`, `httpx` | `slack_bolt`, `claude-agent-sdk` | `slack_bolt` |
| **Best for** | Solo dev, cost-conscious | Getting started with Slack | Always-on + cheap | Team agent, full autonomy | launchd on Mac Mini |

---

## Choose This Mode When...

### `/ensoul`

- You want Claudicle's personality in your own coding session
- You don't need Slack integration
- You want zero additional API costs
- You're a solo developer

### Session Bridge

- You want Slack integration with zero extra API costs
- You want to use ONLY your existing Claude Code session—no SDK, no extra dependencies
- You've configured Claude Code with your preferred model/provider and want that to drive responses
- You need full tool access for responses (Read, Edit, Bash, etc.)
- You want the full project context of your current session

### Bridge + Watcher

- You want always-on Slack responses without running a full Claude session
- You want to minimize API costs (use Haiku, Groq, or local Ollama)
- You want a cheap autonomous responder for simple questions
- You still want the option to handle complex messages manually
- You want per-step routing (monologue on Ollama, dialogue on Sonnet)

### Unified Launcher

- You need a full team-facing autonomous agent
- You want per-channel session isolation
- You want terminal + Slack in one process
- API cost is not a concern

### Legacy Daemon

- You need a launchd-managed service on a Mac Mini
- You want the simplest autonomous option
- You don't need terminal access

---

## Migration Paths

### `/ensoul` → Session Bridge

Add Slack. Start `slack_listen.py --bg`, use `/slack-respond` to process messages.

### Session Bridge → Bridge + Watcher

Add autonomy. Start `inbox_watcher.py --bg` alongside the listener. Configure a cheap provider (Haiku recommended). Messages get auto-responded; you still have `/slack-respond` for anything the watcher doesn't handle.

### Bridge + Watcher → Unified Launcher

Switch to full autonomy. Install `claude-agent-sdk`, launch `claudicle.py`. You get per-channel session isolation and terminal access. The listener and watcher are no longer needed.

### Unified Launcher → Bridge + Watcher

Reduce costs. Stop the unified launcher, start the listener + watcher pair. You trade per-channel isolation for provider flexibility and lower costs.

---

## Per-Step Routing

Available in Bridge + Watcher and Unified Launcher modes. Route each cognitive step to a different provider/model:

```bash
export CLAUDICLE_PIPELINE_MODE=split

# Monologue: local model (free, for private reasoning)
export CLAUDICLE_PROVIDER_MONOLOGUE=ollama
export CLAUDICLE_MODEL_MONOLOGUE=hermes3:8b

# Dialogue: high-quality model (user-facing)
export CLAUDICLE_PROVIDER_DIALOGUE=anthropic
export CLAUDICLE_MODEL_DIALOGUE=claude-sonnet-4-20250514

# Gates: cheap model (boolean true/false checks)
export CLAUDICLE_PROVIDER_GATE=anthropic
export CLAUDICLE_MODEL_GATE=claude-haiku-4-5-20251001

# Updates: same as gates
export CLAUDICLE_PROVIDER_UPDATE=anthropic
export CLAUDICLE_MODEL_UPDATE=claude-haiku-4-5-20251001
```

When `PIPELINE_MODE=unified` (default), all steps go through a single LLM call — the existing behavior. No configuration needed.

---

## Cost Comparison

Approximate per-message costs (assuming ~500 input tokens, ~200 output tokens):

| Mode | Provider | Per-Message Cost | Monthly (100 msgs/day) |
|------|----------|-----------------|----------------------|
| `/ensoul` | — | $0 (current session) | $0 |
| Session Bridge | — | $0 (current session) | $0 |
| Bridge + Watcher | Ollama (local) | $0 | $0 |
| Bridge + Watcher | Groq (Llama 3.3) | ~$0.0001 | ~$0.30 |
| Bridge + Watcher | Haiku | ~$0.0003 | ~$0.90 |
| Bridge + Watcher | Sonnet | ~$0.005 | ~$15 |
| Unified Launcher | Sonnet (SDK) | ~$0.005+ | ~$15+ |
| Legacy Daemon | Sonnet (CLI) | ~$0.005+ | ~$15+ |

Split mode can reduce costs further by routing cheap steps (boolean gates) to Haiku while keeping dialogue on Sonnet.

---

## Quick Start Commands

```bash
# /activate — one command to go from zero to running (ensouls + starts daemons + situational awareness)
/activate

# /ensoul — soul personality only, no Slack
/ensoul

# Session Bridge (requires only a Claude Code session — no SDK, no extra API costs)
cd ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon
python3 slack_listen.py --bg
# then use /slack-respond in your session

# Bridge + Watcher (Haiku)
export CLAUDICLE_WATCHER_PROVIDER=anthropic
export CLAUDICLE_WATCHER_MODEL=claude-haiku-4-5-20251001
python3 slack_listen.py --bg
python3 inbox_watcher.py --bg

# Bridge + Watcher (local Ollama)
export CLAUDICLE_WATCHER_PROVIDER=ollama
export CLAUDICLE_WATCHER_MODEL=hermes3:8b
python3 slack_listen.py --bg
python3 inbox_watcher.py --bg

# Unified Launcher
python3 claudicle.py

# Legacy Daemon
python3 bot.py --verbose
```

---

## Further Reading

| Document | Description |
|----------|-------------|
| `docs/session-bridge.md` | Session Bridge installation and usage |
| `docs/inbox-watcher.md` | Inbox watcher setup, providers, deployment |
| `docs/unified-launcher-architecture.md` | Unified launcher deep dive |
| `docs/cognitive-pipeline.md` | How the cognitive pipeline works |
| `docs/slack-setup.md` | Slack app creation and configuration |
