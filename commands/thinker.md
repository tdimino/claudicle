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
entries = working_memory.get_recent('_direct', '_direct', limit=50)
thinker = any(e['entry_type'] == 'toolAction' and 'thinker=on' in e.get('content','') for e in entries)
print('on' if thinker else 'off')
working_memory.close()
"
```

Uses `'_direct'` as a session-level placeholder. When processing Slack threads, `/slack-respond` checks this preference and applies it per-thread.

### Turn on

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 -c "
import working_memory
working_memory.add('_direct', '_direct', 'system', entry_type='toolAction', content='thinker=on')
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
working_memory.add('_direct', '_direct', 'system', entry_type='toolAction', content='thinker=off')
working_memory.close()
"
```

Respond: _"Back behind the curtain."_

### When Active (executed by `/slack-respond`, not this command)

After posting the external dialogue to a Slack thread, `/slack-respond` checks thinker state and:

1. Posts the internal monologue as a separate italic message to the thread
2. Adds a `thought_balloon` reaction to the dialogue message

The CHANNEL, THREAD_TS, and DIALOGUE_TS values come from the message being processed by `/slack-respond`.

## Storage

Thinker mode is stored in working memory (per-thread, 72h TTL). Each thread has its own toggle. When the thread goes stale, thinker mode dies with it.

Natural language triggers also work:
- "think out loud", "show me your thoughts" → turn on
- "stop thinking out loud", "quiet", "hide your thoughts" → turn off
