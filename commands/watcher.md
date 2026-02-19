---
name: watcher
description: "This command manages the inbox watcher and listener daemon pair. Start, stop, or check the always-on autonomous Slack responder."
argument-hint: [start|stop|status]
disable-model-invocation: true
---

# Watcher — Autonomous Responder Daemons

Manage the listener + watcher daemon pair. Both must run together for autonomous Slack responses.

## Current Status

!`source ~/.zshrc 2>/dev/null; cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" 2>/dev/null && echo "=== Listener ===" && python3 slack_listen.py --status 2>/dev/null && echo "" && echo "=== Watcher ===" && python3 inbox_watcher.py --status 2>/dev/null && echo "" && echo "=== Inbox ===" && python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py" --quiet 2>/dev/null || echo "Daemons not initialized"`

## Instructions

Target action: $ARGUMENTS. Default to `status` if empty.

### If "status" (or empty)

Display the Current Status section above. If additional detail is needed:

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 slack_listen.py --status
python3 inbox_watcher.py --status
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py" --quiet 2>/dev/null || echo "No inbox"
```

### If "start"

Start both daemons in order:

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"

# Start listener first (catches events)
python3 slack_listen.py --status 2>/dev/null | grep -q "running" || python3 slack_listen.py --bg

# Start watcher (responds to events)
python3 inbox_watcher.py --status 2>/dev/null | grep -q "running" || python3 inbox_watcher.py --bg
```

Report which daemons were started (or already running).

### If "stop"

Stop both daemons (watcher first, then listener — stop the consumer before the producer):

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 inbox_watcher.py --stop
python3 slack_listen.py --stop
```

Report results.

## Configuration

The watcher's provider and model are set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_WATCHER_PROVIDER` | `claude_cli` | LLM provider (anthropic, groq, ollama, openai_compat, claude_cli) |
| `CLAUDICLE_WATCHER_MODEL` | (provider default) | Model override |
| `CLAUDICLE_WATCHER_POLL` | `3` | Poll interval in seconds |

Example configurations:
```bash
# Haiku (cheap + high quality)
export CLAUDICLE_WATCHER_PROVIDER=anthropic
export CLAUDICLE_WATCHER_MODEL=claude-haiku-4-5-20251001

# Local Ollama (zero cost)
export CLAUDICLE_WATCHER_PROVIDER=ollama
export CLAUDICLE_WATCHER_MODEL=hermes3:8b
```

## Related

- `/slack-respond` — manually process messages (overrides watcher, first-to-process wins)
- `docs/inbox-watcher.md` — full watcher documentation
- `docs/runtime-modes-comparison.md` — compare all five runtime modes
