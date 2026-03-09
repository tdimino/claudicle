---
name: daimon
description: "Multi-daimon management: invoke whispers, toggle modes, start inter-soul conversations."
disable-model-invocation: true
---

# Daimonic Intercession

Manage daimons registered with Claudicle. Invoke whispers, toggle modes, or start inter-soul conversations.

## Usage

- `/daimon` — List all daimons and their status
- `/daimon [name]` — Invoke whisper from a specific daimon (default: kothar)
- `/daimon toggle [name]` — Toggle a daimon on/off
- `/daimon mode [name] [mode]` — Set mode (whisper/speak/both/off)
- `/daimon converse [name]` — Start an inter-soul 1-1 conversation
- `/daimon summon [entity]` — Summon an entity (user model, dossier) as an ephemeral daimon
- `/daimon dismiss [entity]` — Dismiss a summoned daimon
- `/daimon summoned` — List all currently summoned daimons

## Instructions

### List daimons

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
import daimon_registry
daimon_registry.load_from_config()
for d in daimon_registry.get_enabled():
    print(f'{d.name}: mode={d.mode} daemon={d.daemon_host}:{d.daemon_port} groq={d.groq_enabled}')
if not daimon_registry.get_enabled():
    print('No daimons enabled. Set CLAUDICLE_KOTHAR_ENABLED=true or CLAUDICLE_ARTIFEX_ENABLED=true')
"
```

Present the output as a formatted table.

### Invoke whisper

To invoke a specific daimon's whisper (default: kothar):

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
import sys, asyncio
import daimon_registry, daimonic

daimon_registry.load_from_config()
name = sys.argv[1] if len(sys.argv) > 1 else 'kothar'
daimon = daimon_registry.get(name)

if not daimon:
    print(f'ERROR:Unknown daimon: {name}. Available: {[d.name for d in daimon_registry.get_enabled()]}')
    sys.exit(1)

if not daimon.enabled and not daimon.groq_enabled:
    print(f'ERROR:No provider enabled for {name}. Set CLAUDICLE_{name.upper()}_ENABLED=true or CLAUDICLE_{name.upper()}_GROQ_ENABLED=true')
    sys.exit(1)

context = daimonic.read_context('_direct', '_direct')
whisper = asyncio.run(daimonic.invoke_daimon(daimon, context))

if whisper:
    daimonic.store_whisper(whisper, source=daimon.display_name)
    print(f'WHISPER:{daimon.display_name}:{whisper}')
else:
    print(f'SILENT:{daimon.display_name}')
" DAIMON_NAME
```

Replace `DAIMON_NAME` with the target daimon name argument (or omit for kothar).

When running via `/daimon`, use `_direct` as channel and thread_ts placeholders.

### Present result

If output starts with `WHISPER:`:
> _[Daimon Name] whispers: "{whisper text}"_

The whisper is now stored and will be injected into the next `build_prompt()` cycle as recalled intuition.

If output starts with `SILENT:`:
> _[Daimon Name] is silent. The daemon may be offline, or no Groq key is set._

If output starts with `ERROR:`:
> Report the error message to the user.

### Converse (inter-soul 1-1)

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
import sys, asyncio
import daimon_registry, daimon_converse

daimon_registry.load_from_config()
name = sys.argv[1] if len(sys.argv) > 1 else 'artifex'
daimon = daimon_registry.get(name)

if not daimon:
    print(f'ERROR:Unknown daimon: {name}')
    sys.exit(1)

async def run():
    transcript = await daimon_converse.converse(
        daimon, channel='_direct', thread_ts='_direct',
        topic=' '.join(sys.argv[2:]) if len(sys.argv) > 2 else '',
        max_turns=4,
    )
    for t in transcript:
        print(f'{t[\"speaker\"]}: {t[\"content\"]}')

asyncio.run(run())
" DAIMON_NAME OPTIONAL_TOPIC
```

Present each line of the transcript as a formatted exchange.

### Summon entity

Awaken any entity (user model, person dossier, subject dossier) as an ephemeral speaking daimon:

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
import sys
from daimonic.summoning import summon_entity, list_summoned

name = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else ''
if not name:
    print('ERROR:No entity name provided. Usage: /daimon summon <entity name>')
    sys.exit(1)

result = summon_entity(name, invoke_immediately=False)
summoned = list_summoned()
match = [s for s in summoned if s.display_name.lower() == name.lower()]
if match:
    print(f'SUMMONED:{match[0].display_name}')
else:
    print(f'FAILED:{name} — entity not found or max active reached')
" ENTITY_NAME
```

Replace `ENTITY_NAME` with the entity name argument.

If output starts with `SUMMONED:`:
> _[Entity Name] has been summoned. Their whispers will surface in future exchanges._

If output starts with `FAILED:`:
> Report the failure to the user.

### Dismiss entity

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
import sys
from daimonic.summoning import dismiss_entity

name = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else ''
if not name:
    print('ERROR:No entity name provided')
    sys.exit(1)

if dismiss_entity(name):
    print(f'DISMISSED:{name}')
else:
    print(f'NOT_FOUND:{name}')
" ENTITY_NAME
```

### List summoned

```bash
source ~/.zshrc 2>/dev/null
cd "${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon"
python3 -c "
from daimonic.summoning import list_summoned
summoned = list_summoned()
if not summoned:
    print('No entities currently summoned.')
else:
    for s in summoned:
        print(f'{s.display_name}: mode={s.mode} groq={s.groq_enabled}')
"
```

Present the output as a formatted table or message.

## Provider Configuration

| Env Var | Default | Effect |
|---------|---------|--------|
| `CLAUDICLE_KOTHAR_ENABLED` | `false` | Enable Kothar daemon HTTP |
| `CLAUDICLE_KOTHAR_HOST` | `localhost` | Kothar daemon hostname |
| `CLAUDICLE_KOTHAR_PORT` | `3033` | Kothar daemon port |
| `CLAUDICLE_KOTHAR_GROQ_ENABLED` | `false` | Enable Groq fallback for Kothar |
| `CLAUDICLE_KOTHAR_MODE` | `whisper` | Kothar mode: whisper/speak/both/off |
| `CLAUDICLE_ARTIFEX_ENABLED` | `false` | Enable Artifex daemon WS |
| `CLAUDICLE_ARTIFEX_HOST` | `localhost` | Artifex daemon hostname |
| `CLAUDICLE_ARTIFEX_PORT` | `3034` | Artifex daemon port |
| `CLAUDICLE_ARTIFEX_GROQ_ENABLED` | `false` | Enable Groq fallback for Artifex |
| `CLAUDICLE_ARTIFEX_MODE` | `whisper` | Artifex mode: whisper/speak/both/off |
| `CLAUDICLE_ARTIFEX_SOUL_MD` | `~/souls/artifex/soul.md` | Artifex soul.md path |
| `GROQ_API_KEY` | (none) | Required for Groq fallback |

## Thread Mode Toggle (Slack)

In any Slack thread where Claudicle is active:

```
!artifex speak     — Artifex responds in this thread
!artifex whisper   — Artifex whispers only
!artifex both      — Whisper + speak
!artifex off       — Disable Artifex for this thread
!kothar off        — Disable Kothar whispers for this thread
```
