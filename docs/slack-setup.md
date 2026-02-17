# Slack Setup Guide

Connect Claudius to your Slack workspace. This covers creating the Slack app, choosing a runtime mode, and getting everything running.

---

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From Scratch**
2. Name it (e.g. "Claudius" or your soul's name) → select your workspace

### Bot Token Scopes

**OAuth & Permissions** → **Bot Token Scopes** → add all:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Receive @mentions in channels |
| `channels:history` | Read channel messages |
| `channels:read` | List and get channel info |
| `groups:history` | Read private channel messages |
| `im:history` | Read DM messages |
| `im:read` | List DM conversations |
| `im:write` | Open DM conversations |
| `mpim:history` | Read group DM messages |
| `chat:write` | Post messages and replies |
| `files:write` | Upload files |
| `files:read` | Access file info |
| `reactions:write` | Add emoji reactions |
| `reactions:read` | Read emoji reactions |
| `search:read` | Search messages and files |
| `users:read` | Look up users |
| `users:read.email` | Look up users by email |
| `users:write` | *(optional)* Show green presence dot |

### Enable Socket Mode

**Settings → Socket Mode** → toggle **ON** → generate an App-Level Token:
- Name: `socket-mode`
- Scope: `connections:write`
- Copy the `xapp-...` token

### Event Subscriptions

**Event Subscriptions** → toggle **ON** (no Request URL needed with Socket Mode) → **Subscribe to Bot Events**:

| Event | Purpose |
|-------|---------|
| `app_mention` | Channel @mentions |
| `message.im` | Direct messages |
| `app_home_opened` | App Home tab rendering |

### App Home

**App Home** → Show Tabs → enable **"Allow users to send Slash commands and messages from the messages tab"**

This lets users DM the bot directly.

### Install to Workspace

**Install App** → **Install to Workspace** → approve permissions → copy the **Bot User OAuth Token** (`xoxb-...`)

---

## Step 2: Set Environment Variables

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export SLACK_BOT_TOKEN="xoxb-..."   # Bot User OAuth Token
export SLACK_APP_TOKEN="xapp-..."   # App-Level Token (Socket Mode)
```

Reload: `source ~/.zshrc`

Verify:

```bash
echo $SLACK_BOT_TOKEN   # should start with xoxb-
echo $SLACK_APP_TOKEN   # should start with xapp-
```

> **Note:** `setup.sh` will prompt for these tokens during installation and add them to your shell profile automatically.

---

## Step 3: Invite the Bot

In Slack, invite the bot to any channel where you want it active:

```
/invite @Claudius
```

---

## Step 4: Choose a Runtime Mode

Claudius offers four ways to use Slack, from simplest to most autonomous.

**Quickest path:** Run `/activate` in any Claude Code session. It ensouls the session, starts both daemons, and narrates situational awareness in-character. One command, zero to running.

### Option A: Session Bridge (Recommended for Getting Started)

**Requires only a Claude Code session.** A background listener catches @mentions and DMs, queues them in an inbox file. You process messages from your Claude Code session with `/slack-respond`. Whatever model or provider you've configured Claude Code to use is what processes messages. **You control when the agent responds.**

**Advantages:**
- Requires ONLY a running Claude Code session—no SDK, no extra dependencies
- Zero additional API costs (messages processed in your current session)
- Works with whatever model/provider your Claude Code is configured to use
- Full tool access (Read, Grep, Bash, Edit—whatever your session has)
- Full session context (your current project, your CLAUDE.md, your skills)

**Quick start (recommended):**

```
/activate
```

This ensouls the session, starts the listener + watcher, and displays a situational awareness readout. To stop: `/activate stop`.

**Manual start (if you prefer granular control):**

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 slack_listen.py --bg       # Start in background
python3 slack_listen.py --status   # Check if running
python3 slack_listen.py --stop     # Stop
```

**Process messages from Claude Code:**

```
/slack-respond
```

This reads the inbox, processes each message through the cognitive pipeline, posts responses back to the correct threads, and marks messages as handled.

**Manual workflow (without /slack-respond):**

```bash
# Check for unhandled messages
python3 ${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_check.py

# Post a response to a thread
python3 ${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_post.py "C12345" "Here's the answer..." --thread "1234567890.123456"

# Mark as handled
python3 ${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_check.py --ack 1
```

For full Session Bridge details, see `docs/session-bridge.md`.

### Option B: Inbox Watcher (Always-On Cheap Responder)

Same listener as the Session Bridge, plus an always-on watcher daemon that auto-responds using a configurable LLM provider. The watcher handles simple messages autonomously; you handle complex ones with `/slack-respond`.

**Advantages:**
- Always-on autonomous responses (no manual `/slack-respond` needed)
- Provider choice: Haiku ($0.90/mo), Groq (~$0.30/mo), Ollama ($0), or any OpenAI-compatible endpoint
- Per-step routing: monologue on Ollama (free), dialogue on Sonnet (quality)
- Coexists with `/slack-respond`—first to process wins

**Start both daemons:**

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 slack_listen.py --bg       # catches events (free)
python3 inbox_watcher.py --bg      # responds to events (configurable cost)
```

**Configure provider:**

```bash
# Haiku (recommended — cheap + high quality)
export CLAUDIUS_WATCHER_PROVIDER=anthropic
export CLAUDIUS_WATCHER_MODEL=claude-haiku-4-5-20251001

# Or local Ollama (zero cost)
export CLAUDIUS_WATCHER_PROVIDER=ollama
export CLAUDIUS_WATCHER_MODEL=hermes3:8b
```

**Manage:**

```bash
python3 inbox_watcher.py --status  # Check if running
python3 inbox_watcher.py --stop    # Stop
```

For full details, see `docs/inbox-watcher.md`.

### Option C: Unified Launcher (Autonomous Agent)

A standalone daemon handles terminal and Slack input in one process via the Claude Agent SDK. Per-channel session continuity, full soul engine, three-tier memory. **No manual intervention needed.**

**Additional requirements:**
- `claude` CLI in PATH (`which claude`)
- `claude-agent-sdk` Python package

**Install SDK:**

```bash
uv pip install --system claude-agent-sdk
```

**Launch:**

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon

# Interactive terminal + Slack
python3 claudius.py

# Verbose logging
python3 claudius.py --verbose

# Slack only (no terminal input)
python3 claudius.py --slack-only

# Terminal only (no Slack)
python3 claudius.py --no-slack
```

For full Unified Launcher details, see `docs/unified-launcher-architecture.md`.

### Option D: Legacy Daemon (bot.py)

The standalone `bot.py` uses `claude -p` subprocesses instead of the Agent SDK. Preserved as a fallback and for launchd deployment.

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 bot.py --verbose
```

**Production (macOS launchd):**

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/launchd
./install.sh install    # Load LaunchAgent
./install.sh status     # Check if running
./install.sh logs       # Tail logs
./install.sh restart    # Reload
./install.sh uninstall  # Stop and remove
```

---

## Comparison: Which Mode?

| | Session Bridge | Inbox Watcher | Unified Launcher | Legacy Daemon |
|---|---|---|---|---|
| **Complexity** | Lowest | Low | Medium | Low |
| **Autonomy** | Manual (`/slack-respond`) | Auto (configurable) | Fully autonomous | Fully autonomous |
| **Extra costs** | None (uses current session) | Per-message (cheap) | SDK API calls | Subprocess API calls |
| **Terminal access** | No (separate session) | No | Yes (shared process) | No |
| **Provider choice** | Claude only | Any (Haiku, Groq, Ollama...) | Claude SDK only | Claude CLI only |
| **Session continuity** | Via Claude Code `--resume` | Shared (one brain) | SDK `resume=` parameter | CLI `--resume` flag |
| **Soul engine** | Yes (via `/slack-respond`) | Yes (built-in) | Yes (built-in) | Yes (built-in) |
| **Required packages** | `slack_bolt` | `slack_bolt`, `httpx` | `slack_bolt`, `claude-agent-sdk` | `slack_bolt` |
| **Best for** | Getting started, cost-conscious | Always-on + cheap | Always-on team agent | launchd deployment |

For a comprehensive comparison of all five modes (including `/ensoul`), see [`docs/runtime-modes-comparison.md`](runtime-modes-comparison.md).

---

## Monitoring

### Soul Monitor TUI

Live dashboard showing active sessions, memory stats, cognitive stream, and message flow. Run in a separate terminal:

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
uv run python monitor.py
```

### Inspecting Memory

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon

# Soul state (global)
sqlite3 memory.db "SELECT key, value FROM soul_memory"

# User models
sqlite3 memory.db "SELECT user_id, display_name, interaction_count FROM user_models"

# Recent working memory
sqlite3 memory.db "SELECT entry_type, verb, content FROM working_memory ORDER BY created_at DESC LIMIT 20"

# Session mappings
sqlite3 sessions.db "SELECT channel, thread_ts, session_id FROM sessions"
```

---

## Auto-Notification Hook (Optional)

Surface unhandled Slack messages at the start of every Claude Code turn. Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python3 ${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_inbox_hook.py"
      }
    ]
  }
}
```

When there are unhandled messages, you'll see:
```
[Slack: 2 unhandled messages -- run /slack-check to view]
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot not responding to @mentions | Verify Socket Mode is ON and `SLACK_APP_TOKEN` (xapp-) is exported |
| "missing_scope" error | Add the scope in OAuth & Permissions → **reinstall** the app |
| No DMs | Subscribe to `message.im` event → reinstall |
| No search results | Invite bot to channels with `/invite @Claudius` |
| "Sending messages turned off" | App Home → enable "Allow users to send Slash commands and messages" |
| Bot can't post to channel | Invite with `/invite @Claudius` and verify `chat:write` scope |
| Listener exits immediately | Check `SLACK_APP_TOKEN` is set; run foreground first: `python3 slack_listen.py` |
| Launcher exits immediately | Verify `which claude` returns a path |
| "Credit balance is too low" | Check Anthropic billing |
| No green presence dot | Add `users:write` scope → reinstall |
| App Home tab blank | Subscribe to `app_home_opened` event → reinstall |
| Monitor TUI won't start | `uv pip install --system textual psutil` |
| SDK import error | `uv pip install --system claude-agent-sdk` |
| Rate limited (429) | Scripts auto-retry; reduce message frequency |

**After any scope or event subscription change:** reinstall the app (Install App → Reinstall to Workspace) and restart the listener/launcher.

---

## Slack Utility Scripts

Once connected, you have full programmatic access to Slack:

| Task | Command |
|------|---------|
| Post message | `slack_post.py "#general" "Hello"` |
| Reply to thread | `slack_post.py "#ch" "reply" --thread TS` |
| Read channel | `slack_read.py "#general" -n 20` |
| Read thread | `slack_read.py "#ch" --thread TS` |
| Search messages | `slack_search.py "query"` |
| Search files | `slack_search.py "query" --files` |
| Add reaction | `slack_react.py "#ch" TS emoji` |
| Upload file | `slack_upload.py "#ch" ./file.pdf` |
| List channels | `slack_channels.py` |
| Find user | `slack_users.py --email user@example.com` |
| Delete message | `slack_delete.py "#ch" TS` |

All scripts are in `${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/`. See `docs/scripts-reference.md` for full documentation.
