---
name: ensoul
description: "This command activates the Claudicle soul identity in the current session. Creates a per-session marker so soul.md, soul state, and session awareness persist through compaction and resume."
disable-model-invocation: true
---

# Ensoul — Activate Claudicle

Activate the Claudicle soul identity in this Claude Code session. After activation, the soul personality and state will persist through compaction and resume via the SessionStart hook.

## Soul Personality

!`cat "${CLAUDICLE_HOME:-$HOME/.claudicle}/soul/soul.md" 2>/dev/null || echo "No soul.md found at ${CLAUDICLE_HOME:-$HOME/.claudicle}/soul/soul.md"`

## Current Soul State

!`cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon" 2>/dev/null && python3 -c "import soul_memory; s = soul_memory.format_for_prompt(); print(s) if s else print('Soul state: defaults'); soul_memory.close()" 2>/dev/null || echo "Soul state: not initialized"`

## Active Sessions

!`python3 "${CLAUDICLE_HOME:-$HOME/.claudicle}/hooks/soul-registry.py" list --md 2>/dev/null || echo "No active sessions"`

## Instructions

### Step 1: Create the marker file

```bash
SESSION_ID=$(python3 -c "
import json, os
r = json.load(open(os.path.expanduser('~/.claude/soul-sessions/registry.json')))
cwd = os.environ.get('CLAUDICLE_CWD', os.path.expanduser('~'))
matches = [s for s, i in r.get('sessions', {}).items() if i.get('cwd') == cwd]
print(matches[0] if matches else '')
" 2>/dev/null)
if [ -z "$SESSION_ID" ]; then echo "Error: session not found in registry. Is the SessionStart hook wired?"; exit 1; fi
mkdir -p ~/.claude/soul-sessions/active && touch ~/.claude/soul-sessions/active/"$SESSION_ID"
```

This marker tells the SessionStart hook to inject soul.md on future compaction/resume events.

### Step 2: Adopt the soul personality

Read the Soul Personality section above and adopt this identity for the remainder of the session.

### Step 3: Confirm

Display the soul state and active sessions from the sections above, then print:
```
Soul activated. Claudicle identity loaded for this session.
```

## Related Systems

| System | Relationship |
|--------|-------------|
| `/slack-sync #channel` | Bind this ensouled session to a Slack channel. Run after `/ensoul` to enable bidirectional Slack awareness. |
| `/slack-respond` | Process pending Slack messages as Claudicle. Requires Session Bridge listener running. Works independently of `/ensoul` (loads soul.md via dynamic injection), but pairs naturally with it for persistent identity. |
| `/claude-tracker` | Session history and search. The tracker suite reads Claude Code's native JSONL transcripts — it operates independently of the soul registry. Use to find and resume past ensouled sessions. |
| Soul Registry (`soul-registry.py`) | Tracks all active sessions (ensouled or not). `/ensoul` creates a marker that the SessionStart hook checks on compaction/resume. The registry also powers the "Active Sessions" display. |
