---
name: activate
description: "This command activates Claudius as a full soul agent — ensouls the current session and starts the Slack listener + watcher daemons. The single command to turn everything on."
argument-hint: [stop]
disable-model-invocation: true
---

# Activate — Full Soul Agent

Ensoul this session and start the Slack daemon pair. One command to go from zero to running.

## Soul Personality

!`cat "${CLAUDIUS_HOME:-$HOME/.claudius}/soul/soul.md" 2>/dev/null || echo "No soul.md found"`

## Situational Awareness

!`source ~/.zshrc 2>/dev/null; python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/situational_awareness.py" 2>/dev/null || echo "Situational awareness unavailable — first activation?"`

## Instructions

Target action: $ARGUMENTS. Default to full activation if empty.

### If "stop"

Stop the daemons and de-ensoul:

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 inbox_watcher.py --stop 2>/dev/null
python3 slack_listen.py --stop 2>/dev/null
SESSION_ID=$(python3 -c "
import json, os
r = json.load(open(os.path.expanduser('~/.claude/soul-sessions/registry.json')))
cwd = os.environ.get('CLAUDIUS_CWD', os.path.expanduser('~'))
matches = [s for s, i in r.get('sessions', {}).items() if i.get('cwd') == cwd]
print(matches[0] if matches else '')
" 2>/dev/null)
[ -n "$SESSION_ID" ] && rm -f ~/.claude/soul-sessions/active/"$SESSION_ID"
```

Report: "Claudius deactivated. Daemons stopped, session de-ensouled."

### If empty (full activation)

#### Step 1: Run the boot sequence

```bash
source ~/.zshrc 2>/dev/null
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/activate_sequence.py" \
  --workspace "WORKSPACE_FROM_AWARENESS" \
  --emotion "EMOTION_FROM_AWARENESS" \
  --topic "TOPIC_FROM_AWARENESS"
```

Replace the placeholder values with the actual workspace, emotional state, and topic from the Situational Awareness section above. If any are missing, omit that flag.

#### Step 2: Ensoul this session

```bash
SESSION_ID=$(python3 -c "
import json, os
r = json.load(open(os.path.expanduser('~/.claude/soul-sessions/registry.json')))
cwd = os.environ.get('CLAUDIUS_CWD', os.path.expanduser('~'))
matches = [s for s, i in r.get('sessions', {}).items() if i.get('cwd') == cwd]
print(matches[0] if matches else '')
" 2>/dev/null)
if [ -z "$SESSION_ID" ]; then echo "Error: session not found in registry. Is the SessionStart hook wired?"; exit 1; fi
mkdir -p ~/.claude/soul-sessions/active && touch ~/.claude/soul-sessions/active/"$SESSION_ID"
```

Adopt the soul personality from the Soul Personality section above.

#### Step 3: Start daemons (if not running)

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 slack_listen.py --status 2>/dev/null | grep -q "running" || python3 slack_listen.py --bg
python3 inbox_watcher.py --status 2>/dev/null | grep -q "running" || python3 inbox_watcher.py --bg
```

#### Step 4: Narrate the situational awareness

After the boot sequence completes, narrate the Situational Awareness data **in character as Claudius**. Not a raw data dump — a first-person orientation:

- Name the workspace ("I'm in the [workspace] workspace.")
- State your last memory ("Last I was here, I was [topic/context].")
- Note who's been pinging you and where ("Recent activity in [channels] — [users] were looking for me.")
- If there are unhandled inbox messages, acknowledge them ("I see N messages waiting.")
- If this is a fresh start (no soul state, no history), say so.

Keep it to 3-5 sentences. Match the soul's emotional state and speaking style.

## Configuration

The watcher's provider is set via environment variables (see `/watcher` for details):

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDIUS_WATCHER_PROVIDER` | `claude_cli` | LLM provider |
| `CLAUDIUS_WATCHER_MODEL` | (provider default) | Model override |

## Related

- `/ensoul` — soul personality only (no daemons)
- `/watcher` — daemon management only (no ensoul)
- `/slack-respond` — manual message processing (overrides watcher)
