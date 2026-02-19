---
name: slack-sync
description: "This command binds the current Claude Code session to a Slack channel for bidirectional awareness. The session appears in the soul registry as bound to the channel."
argument-hint: [#channel-name or channel-id]
disable-model-invocation: true
---

# Slack Sync

Bind this session to a Slack channel. After binding, the session registry shows this session as connected to the channel, and Claudicle can post status updates there.

## Arguments

Target: $ARGUMENTS

If empty, show the current binding status and active sessions.

## Instructions

### If no arguments: Show Status

## Current Sessions

!`python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/hooks/soul-registry.py" list --md 2>/dev/null || echo "No active sessions"`

Display the sessions above and stop.

### If a channel is specified:

#### Step 1: Resolve the Channel

If the argument starts with `C` and looks like a Slack channel ID (e.g., `C12345`), use it directly. Otherwise, treat it as a channel name (strip leading `#` if present) and resolve it:

```bash
source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py" --filter "CHANNEL_NAME" --json
```

Parse the JSON output to find the matching channel ID and name.

#### Step 2: Ensure Listener Is Running

```bash
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon/slack_listen.py" --status
```

If not running, start it:
```bash
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" && python3 slack_listen.py --bg
```

#### Step 3: Bind in Registry

```bash
SESSION_ID=$(python3 -c "
import json, os
r = json.load(open(os.path.expanduser('~/.claude/soul-sessions/registry.json')))
cwd = os.environ.get('CLAUDICLE_CWD', os.path.expanduser('~'))
matches = [s for s, i in r.get('sessions', {}).items() if i.get('cwd') == cwd]
print(matches[0] if matches else '')
" 2>/dev/null)
if [ -z "$SESSION_ID" ]; then echo "Error: session not found in registry."; exit 1; fi
python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/hooks/soul-registry.py" bind "$SESSION_ID" "CHANNEL_ID" "#CHANNEL_NAME"
```

#### Step 4: Post Announcement

```bash
source ~/.zshrc 2>/dev/null; python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py" "CHANNEL_ID" "_Claudicle connected from $(basename $(pwd))_"
```

#### Step 5: Confirm

Print:
```
Session bound to #channel-name. This session is now visible in the soul registry as connected to that channel.
```

## Important

- The session must already be registered (happens automatically via the SessionStart hook).
- Binding is per-session. When the session ends, the registry entry is cleaned up.
- Multiple sessions can bind to the same channel.
- To unbind, just exit the session or start a new one without `/slack-sync`.

## Related Systems

| System | Relationship |
|--------|-------------|
| `/ensoul` | Activate Claudicle identity before binding. `/slack-sync` handles channel binding; `/ensoul` handles persona activation. Both are opt-in per session. |
| `/slack-respond` | Process pending Slack messages. After binding via `/slack-sync`, incoming messages for the bound channel appear in the inbox for `/slack-respond` to handle. |
| Soul Registry (`soul-registry.py`) | `/slack-sync` writes channel binding data to the registry. Other sessions see this binding in their "Active Sessions" display. |
