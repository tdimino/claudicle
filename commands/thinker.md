---
name: thinker
description: "This command toggles visible internal monologue for the current Slack thread. When active, the soul agent posts its private reasoning as italic follow-up messages."
argument-hint: [on|off]
disable-model-invocation: true
---

# Thinker Mode

Toggle visible internal monologue per-thread. When enabled, the soul agent posts its private reasoning as italic follow-up messages after each response.

## Instructions

Target: $ARGUMENTS. If empty, toggle (check current state and flip it).

### Check current state

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 -c "
import working_memory
entries = working_memory.get_recent('CHANNEL', 'THREAD_TS', limit=50)
thinker = any(e['entry_type'] == 'toolAction' and 'thinker=on' in e.get('content','') for e in entries)
print('on' if thinker else 'off')
working_memory.close()
"
```

Replace CHANNEL and THREAD_TS with the current thread's values.

### Turn on

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 -c "
import working_memory
working_memory.add('CHANNEL', 'THREAD_TS', 'system', entry_type='toolAction', content='thinker=on')
working_memory.close()
"
```

Respond: _"You want to see inside the workshop. Very well."_

### Turn off

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 -c "
import working_memory
working_memory.add('CHANNEL', 'THREAD_TS', 'system', entry_type='toolAction', content='thinker=off')
working_memory.close()
"
```

Respond: _"Back behind the curtain."_

### When Active

After posting the external dialogue to a thread, also:

1. Post the internal monologue as a separate italic message:
```bash
source ~/.zshrc 2>/dev/null
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_post.py" "CHANNEL" "_MONOLOGUE_TEXT_" --thread "THREAD_TS"
```

2. Add a thought balloon reaction to the dialogue message:
```bash
source ~/.zshrc 2>/dev/null
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/scripts/slack_react.py" "CHANNEL" "DIALOGUE_TS" "thought_balloon"
```

## Storage

Thinker mode is stored in working memory (per-thread, 72h TTL). Each thread has its own toggle. When the thread goes stale, thinker mode dies with it.

Natural language triggers also work:
- "think out loud", "show me your thoughts" → turn on
- "stop thinking out loud", "quiet", "hide your thoughts" → turn off
