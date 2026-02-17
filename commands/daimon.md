---
name: daimon
description: "Summons Kothar's daimonic counsel by gathering Claudius's cognitive context and sending it for a whispered intuition."
disable-model-invocation: true
---

# Daimonic Intercession

Summon Kothar wa Khasis to observe and whisper about the current conversation.

## Instructions

1. Gather Claudius's current cognitive state
2. Call Kothar (daemon HTTP or Groq kimi-k2 fallback)
3. Present the whisper and store it for next prompt injection

### Gather context and invoke

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDIUS_HOME:-$HOME/.claudius}/daemon"
python3 -c "
import sys
import asyncio
import daimonic
from config import KOTHAR_ENABLED, KOTHAR_GROQ_ENABLED

if not KOTHAR_ENABLED and not KOTHAR_GROQ_ENABLED:
    print('ERROR: No daimonic provider enabled. Set CLAUDIUS_KOTHAR_ENABLED=true or CLAUDIUS_KOTHAR_GROQ_ENABLED=true')
    sys.exit(1)

context = daimonic.read_context('_direct', '_direct')
whisper = asyncio.run(daimonic.invoke_kothar(context))

if whisper:
    daimonic.store_whisper(whisper)
    print(f'WHISPER:{whisper}')
else:
    print('SILENT')
"
```

When running via `/daimon`, use `_direct` as channel and thread_ts placeholders since this is a direct invocation outside a thread context.

### Present result

If output starts with `WHISPER:`:
> _Kothar whispers: "{whisper text}"_

The whisper is now stored and will be injected into the next `build_prompt()` cycle as recalled intuition for Claudius to process in his internal monologue.

If output is `SILENT`:
> _Kothar is silent. The daemon may be offline, or no Groq key is set._

If output starts with `ERROR:`:
> Report the error message to the user.

## Provider Configuration

| Env Var | Default | Effect |
|---------|---------|--------|
| `CLAUDIUS_KOTHAR_ENABLED` | `false` | Enable Kothar daemon HTTP |
| `CLAUDIUS_KOTHAR_HOST` | `localhost` | Kothar daemon hostname |
| `CLAUDIUS_KOTHAR_PORT` | `3033` | Kothar daemon port |
| `CLAUDIUS_KOTHAR_GROQ_ENABLED` | `false` | Enable Groq kimi-k2-instruct fallback |
| `GROQ_API_KEY` | (none) | Required for Groq fallback |
| `CLAUDIUS_KOTHAR_AUTH_TOKEN` | (none) | Shared secret for daemon auth |
| `CLAUDIUS_KOTHAR_SOUL_MD` | `~/souls/kothar/soul.md` | Path to Kothar's soul.md (Groq system prompt) |
