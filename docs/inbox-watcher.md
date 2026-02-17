# Inbox Watcher — Always-On Autonomous Responder

An always-on daemon that auto-responds to Slack messages using any LLM provider. Pairs with `slack_listen.py` as a two-daemon architecture: one catches messages, one responds.

---

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  slack_listen.py --bg                                      │
│  (Socket Mode: @mentions + DMs → inbox.jsonl)              │
│  Cost: FREE — no LLM calls, just event capture             │
└─────────────────────────┬─────────────────────────────────┘
                          │ writes
                          ▼
                ┌──────────────────┐
                │   inbox.jsonl     │
                │   (append-only)   │
                └────────┬─────────┘
                         │ polls
                         ▼
┌───────────────────────────────────────────────────────────┐
│  inbox_watcher.py --bg                                     │
│                                                             │
│  For each unhandled message:                                │
│    1. Build cognitive prompt (soul engine)                  │
│    2. Call provider.agenerate(prompt, model)                │
│    3. Parse response (extract external_dialogue)            │
│    4. Post to Slack (thread reply)                          │
│    5. Remove ⏳, add ✅                                     │
│    6. Mark handled in inbox.jsonl                           │
│                                                             │
│  Provider: configurable (Haiku, Groq, Ollama, etc.)        │
└───────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────┐
│  Claude Code Session (optional escalation path)            │
│                                                             │
│  /slack-respond processes anything the watcher missed       │
│  or that needs full tool access                             │
│  Hook: slack_inbox_hook.py surfaces unhandled count         │
└───────────────────────────────────────────────────────────┘
```

The watcher and Session Bridge share the same inbox file and `handled` flag. If the watcher processes a message first, `/slack-respond` won't see it. If you process manually first, the watcher skips it. They coexist naturally.

---

## Installation

### 1. Prerequisites

- Python 3.10+
- `slack_listen.py` running (catches events → inbox.jsonl)
- A provider configured (see Provider Guide below)
- `httpx` for HTTP-based providers: `uv pip install --system httpx`

### 2. Install Dependencies

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
uv pip install --system -r requirements.txt
```

### 3. Choose a Provider

The watcher needs an LLM provider to generate responses. The default is `claude_cli` (uses `claude -p`), but you can use any provider:

| Provider | Env Var | Cost | Speed | Setup |
|----------|---------|------|-------|-------|
| `claude_cli` | — | Full API | Standard | `claude` in PATH (default) |
| `anthropic` | `ANTHROPIC_API_KEY` | Per-token | Standard | Cheapest Claude path |
| `groq` | `GROQ_API_KEY` | Near-free | Very fast | Sign up at groq.com |
| `ollama` | — | Free | Varies | `ollama serve` running locally |
| `openai_compat` | `OPENAI_COMPAT_BASE_URL` | Varies | Varies | vLLM, LM Studio, Together |
| `claude_sdk` | — | Per-token | Standard | `claude-agent-sdk` installed |

### 4. Configure

```bash
# Choose provider and model
export CLAUDIUS_WATCHER_PROVIDER=anthropic
export CLAUDIUS_WATCHER_MODEL=claude-haiku-4-5-20251001

# Optional: adjust poll interval (default: 3 seconds)
export CLAUDIUS_WATCHER_POLL=3
```

### 5. First Launch (Foreground)

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 inbox_watcher.py
```

Send a DM to the bot in Slack. You should see the watcher pick it up, process it, and post a response. `Ctrl+C` to stop.

---

## Usage

### Quick Start: `/activate`

The simplest way to start the watcher is `/activate` in any Claude Code session. It ensouls the session, starts both the listener and watcher daemons, runs a terminal boot sequence, and narrates situational awareness. One command, zero to running.

To stop: `/activate stop`

For daemon management only (no ensoul): `/watcher start` and `/watcher stop`.

### Start / Stop / Status

```bash
# Background mode (recommended)
python3 inbox_watcher.py --bg

# Check if running
python3 inbox_watcher.py --status

# Stop
python3 inbox_watcher.py --stop
```

PID file: `daemon/watcher.pid`. Log file: `daemon/logs/watcher.log`.

### Paired Launch

Run both daemons together for a fully autonomous Slack agent:

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 slack_listen.py --bg     # catches events
python3 inbox_watcher.py --bg    # responds to events
```

### With Session Bridge

The watcher handles messages autonomously. You can still use `/slack-respond` in a Claude Code session for messages that need full tool access or deeper context:

```
Watcher handles:  simple questions, greetings, status checks
You handle:       complex tasks, code reviews, multi-step workflows
```

Both read from the same inbox — first to process wins.

---

## Provider Guide

### Anthropic API (Recommended for Haiku)

The cheapest Claude path. Haiku is ideal for the watcher — high quality, low cost, fast.

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
export CLAUDIUS_WATCHER_PROVIDER=anthropic
export CLAUDIUS_WATCHER_MODEL=claude-haiku-4-5-20251001
```

### Groq (Fast, Near-Free)

Groq runs open models with extremely fast inference. Near-free for moderate usage.

```bash
export GROQ_API_KEY="gsk_..."
export CLAUDIUS_WATCHER_PROVIDER=groq
export CLAUDIUS_WATCHER_MODEL=llama-3.3-70b-versatile
```

Sign up at [console.groq.com](https://console.groq.com).

### Ollama (Zero Cost, Full Sovereignty)

Run a local model. Zero API costs, zero latency, fully private.

```bash
# Start Ollama (if not already running)
ollama serve

# Pull a model
ollama pull hermes3:8b

# Configure watcher
export CLAUDIUS_WATCHER_PROVIDER=ollama
export CLAUDIUS_WATCHER_MODEL=hermes3:8b
```

Override the Ollama host with `OLLAMA_HOST` (default: `http://localhost:11434`).

### OpenAI-Compatible (vLLM, LM Studio, Together)

Any endpoint that speaks the OpenAI chat completions API.

```bash
export OPENAI_COMPAT_BASE_URL="http://localhost:8000"
export OPENAI_COMPAT_API_KEY=""  # optional, for authenticated endpoints
export CLAUDIUS_WATCHER_PROVIDER=openai_compat
export CLAUDIUS_WATCHER_MODEL=your-model-name
```

### Claude CLI (Default)

Uses `claude -p` subprocess. Same as the existing Session Bridge path but automated.

```bash
# No config needed — this is the default
export CLAUDIUS_WATCHER_PROVIDER=claude_cli
```

---

## Per-Step Routing (Split Mode)

The watcher supports split mode, where each cognitive step (monologue, dialogue, model check, etc.) can use a different provider/model:

```bash
# Enable split mode
export CLAUDIUS_PIPELINE_MODE=split

# Route cheap gates to haiku, dialogue to sonnet
export CLAUDIUS_PROVIDER_GATE=anthropic
export CLAUDIUS_MODEL_GATE=claude-haiku-4-5-20251001
export CLAUDIUS_PROVIDER_DIALOGUE=anthropic
export CLAUDIUS_MODEL_DIALOGUE=claude-sonnet-4-20250514
export CLAUDIUS_PROVIDER_MONOLOGUE=ollama
export CLAUDIUS_MODEL_MONOLOGUE=hermes3:8b
```

Split mode applies to both the watcher and `claude_handler.py` (unified launcher).

---

## launchd Deployment

For always-on operation on macOS:

### Install

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/launchd

# Edit the plist to set your paths and tokens
# Then load:
launchctl load com.claudius.watcher.plist
```

### Manage

```bash
launchctl list | grep claudius.watcher     # check status
launchctl unload com.claudius.watcher.plist # stop
launchctl load com.claudius.watcher.plist   # start
```

### Paired launchd Services

Run both daemons as launchd services:

```
com.claudius.agent.plist    → bot.py (legacy Slack daemon)
com.claudius.watcher.plist  → inbox_watcher.py (autonomous watcher)
```

Or pair with the listener:

```
slack_listen.py --bg        → catches events (runs in background)
com.claudius.watcher.plist  → processes events (launchd managed)
```

---

## Monitoring

### Logs

```bash
# Watcher log
tail -f ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/logs/watcher.log

# Listener log
tail -f ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/logs/listener.log
```

### Inbox Stats

```bash
# Count unhandled messages
python3 ${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_check.py

# View all inbox entries
cat ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/inbox.jsonl | python3 -m json.tool --no-ensure-ascii
```

### Memory Inspection

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon

# Recent working memory (watcher entries appear here too)
sqlite3 memory.db "SELECT entry_type, verb, content FROM working_memory ORDER BY created_at DESC LIMIT 10"

# User model updates
sqlite3 memory.db "SELECT user_id, display_name, interaction_count FROM user_models"
```

### Soul Monitor TUI

The watcher's activity appears in the Soul Monitor TUI alongside all other sessions:

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon && uv run python monitor.py
```

---

## Configuration Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `CLAUDIUS_WATCHER_PROVIDER` | `claude_cli` | Provider name for watcher responses |
| `CLAUDIUS_WATCHER_MODEL` | (provider default) | Model override for watcher |
| `CLAUDIUS_WATCHER_POLL` | `3` | Poll interval in seconds |
| `CLAUDIUS_PROVIDER` | `claude_cli` | Default provider (fallback) |
| `CLAUDIUS_MODEL` | (empty) | Default model (fallback) |
| `CLAUDIUS_PIPELINE_MODE` | `unified` | `unified` or `split` |

Per-step overrides (split mode only):

| Env Var | Applies To |
|---------|-----------|
| `CLAUDIUS_PROVIDER_MONOLOGUE` | Internal monologue step |
| `CLAUDIUS_PROVIDER_DIALOGUE` | External dialogue step |
| `CLAUDIUS_PROVIDER_GATE` | User model check + soul state check |
| `CLAUDIUS_PROVIDER_UPDATE` | User model update + soul state update |
| `CLAUDIUS_MODEL_MONOLOGUE` | Model for monologue step |
| `CLAUDIUS_MODEL_DIALOGUE` | Model for dialogue step |
| `CLAUDIUS_MODEL_GATE` | Model for gate steps |
| `CLAUDIUS_MODEL_UPDATE` | Model for update steps |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Watcher not responding | Check `python3 inbox_watcher.py --status`; run foreground first |
| "Provider 'X' not registered" | Check API key is exported; verify with `python3 -c "from providers import list_providers; print(list_providers())"` |
| Duplicate responses | Both watcher and `/slack-respond` ran — this is safe (handled flag prevents true duplicates) |
| Watcher exits immediately | Run foreground: `python3 inbox_watcher.py` to see errors |
| httpx not found | `uv pip install --system httpx` |
| Ollama connection refused | Start Ollama: `ollama serve` |
| Groq rate limit | Reduce poll interval or message frequency |
| Messages marked handled but no response | Check `daemon/logs/watcher.log` for provider errors |
| Listener not catching events | Verify: `python3 slack_listen.py --status` |

---

## Files

| File | Purpose |
|------|---------|
| `daemon/inbox_watcher.py` | Watcher daemon (poll loop, provider routing, Slack posting) |
| `daemon/watcher.pid` | PID file for lifecycle management (gitignored) |
| `daemon/logs/watcher.log` | Watcher log output |
| `daemon/providers/` | Provider implementations (claude_cli, anthropic, groq, ollama, etc.) |
| `daemon/pipeline.py` | Per-step cognitive routing (split mode) |
| `daemon/config.py` | All watcher/provider/pipeline configuration |
| `daemon/launchd/com.claudius.watcher.plist` | macOS launchd service definition |
