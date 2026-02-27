# Extending Claudicle — Developer Guide

Add new capabilities to Claudicle: cognitive steps, memory tiers, subprocesses, mental processes, channel adapters, and more.

---

## Architecture Overview

Before extending, understand the four layers:

1. **Identity** — `soul/soul.md` defines personality
2. **Cognition** — `soul_engine.py` wraps interactions with XML-tagged cognitive steps
3. **Memory** — Three SQLite tiers: working (per-thread), user models (per-user), soul state (global)
4. **Channels** — Adapters for Slack, SMS, terminal

See `ARCHITECTURE.md` for the full system flow and file map.

---

## Adding a New Cognitive Step

Cognitive steps are XML-tagged sections in the LLM response. To add one:

### 1. Define the Instruction

In `daemon/soul_engine.py`, add to `STEP_INSTRUCTIONS`:

```python
STEP_INSTRUCTIONS = {
    # ... existing steps ...

    "decision": """When a choice must be made between options.

<decision options="option1,option2,option3">
chosen_option
</decision>""",
}
```

Instructions that reference the soul's name should use `{soul_name}` as a template variable—it's resolved to `config.SOUL_NAME` at prompt assembly time:

```python
"my_step": """You are the daimon who advises {soul_name} on decisions.""",
```

### 2. Add Extraction Logic

In `soul_engine.py:parse_response()` (line 202), add extraction:

```python
# Decision extraction
decision_match = re.search(
    r'<decision\s+options="([^"]+)">(.*?)</decision>',
    raw, re.DOTALL
)
if decision_match:
    options = decision_match.group(1).split(",")
    choice = decision_match.group(2).strip()
    working_memory.add(
        channel, thread_ts, user_id,
        entry_type="decision",
        content=f"options={options}, chose={choice}",
    )
```

### 3. Store in Working Memory

The `working_memory.add()` method accepts any `entry_type` string. Existing types: `userMessage`, `internalMonologue`, `externalDialog`, `mentalQuery`, `toolAction`.

### 4. Test

```bash
cd ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon
python3 -c "
import soul_engine
raw = '<decision options=\"joke,serious\">joke</decision>'
# Test extraction
print(soul_engine._extract_tag(raw, 'decision'))
"
```

### Reference

See `skills/open-souls-paradigm/references/additional-cognitive-steps.md` for the full list of Open Souls cognitive steps and their Claudicle mapping.

---

## Adding a New Channel Adapter

Claudicle supports any channel that can send/receive text. The pattern:

### Interface

Every adapter needs:
1. **Listener** — Receives messages from the channel
2. **Poster** — Sends responses back to the channel
3. **Identity resolution** — Map channel users to Claudicle user IDs

### Example: Discord Adapter

```python
# adapters/discord/discord_listen.py
"""Discord listener — writes incoming messages to inbox.jsonl."""

import discord

client = discord.Client()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    entry = {
        "ts": message.created_at.timestamp(),
        "channel": str(message.channel.id),
        "thread_ts": str(message.id),
        "user_id": str(message.author.id),
        "display_name": message.author.display_name,
        "text": message.content,
        "handled": False,
    }

    # Write to inbox (same format as Slack listener)
    with open("daemon/inbox.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
```

```python
# adapters/discord/discord_post.py
"""Post response to Discord channel."""

async def post(channel_id: str, text: str, reply_to: str = None):
    channel = client.get_channel(int(channel_id))
    if reply_to:
        message = await channel.fetch_message(int(reply_to))
        await message.reply(text)
    else:
        await channel.send(text)
```

### Registration

Add the adapter to the unified launcher's message queue or use the Session Bridge pattern (inbox.jsonl → `/slack-respond` equivalent).

See `docs/channel-adapters.md` for the full interface specification.

---

## Adding a Memory Tier

### New SQLite Table

Add a new table to `daemon/memory.db`:

```python
# daemon/your_memory.py
import sqlite3

_DB = "memory.db"

def _init():
    conn = sqlite3.connect(_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS your_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get(key):
    conn = sqlite3.connect(_DB)
    row = conn.execute("SELECT value FROM your_table WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None

def set(key, value):
    conn = sqlite3.connect(_DB)
    conn.execute(
        "INSERT OR REPLACE INTO your_table (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()
```

### Injection Point

To inject your memory into prompts, modify `soul_engine.py:build_prompt()` (line 133):

```python
# After existing soul_memory injection
your_context = your_memory.format_for_prompt()
if your_context:
    prompt_parts.append(your_context)
```

### Existing Examples

- **`memory/checkpoint.py`** — Adds a `wm_checkpoints` table via `memory_pool.add_migrations()`. Frozen `Checkpoint` dataclass with `from_row()` static method. Good example of a new table that integrates with the existing `working_memory` infrastructure.
- **`memory/daimon_memory.py`** — Convention-based namespacing using the existing `working_memory` table (channel prefix `daimon:{agent_name}`). Demonstrates how to add a new memory tier without a new table.

### Reference

See `skills/open-souls-paradigm/references/memory-regions.md` for the Open Souls region pattern, `references/hooks-and-state.md` for the full hooks system, and `agent_docs/open-souls-functional-principles.md` for FP patterns (immutability, pure/impure boundary, effect descriptions).

---

## Adding a Subprocess

Subprocesses run as part of the reflection pipeline (`engine/reflect.py`) after the main LLM response has been parsed. They handle cross-cutting concerns: user model updates, soul state changes, memory compression. Each subprocess is a `Subprocess` dataclass registered in the `SUBPROCESSES` list.

### Current Registry

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class Subprocess:
    name: str
    execute: Callable  # (raw, channel, thread_ts, trace_id, ctx) -> dict

SUBPROCESSES = [
    Subprocess("modelsTheUser", _execute_models_user),      # → {"check": bool, "updated": bool}
    Subprocess("updatesState", _execute_updates_state),      # → {"check": bool, "updated": bool}
    Subprocess("compressesMemory", _execute_compression),    # → {"fired": bool, "compressed": bool}
]
```

### Create a New Subprocess

1. Define an execute function in `engine/reflect.py`:

```python
def _execute_my_subprocess(raw, channel, thread_ts, trace_id, ctx) -> dict:
    """Run after main process. Returns a result dict."""
    # raw: LLM response text (XML tags)
    # channel, thread_ts: thread context
    # trace_id: groups all entries from this reflection cycle
    # ctx: {"user_id", "interaction_count", ...}
    return {"fired": True, "result": "something"}
```

2. Add to the `SUBPROCESSES` list (order matters—subprocesses execute sequentially):

```python
SUBPROCESSES = [
    Subprocess("modelsTheUser", _execute_models_user),
    Subprocess("updatesState", _execute_updates_state),
    Subprocess("compressesMemory", _execute_compression),
    Subprocess("myNewSubprocess", _execute_my_subprocess),
]
```

### Behavioral Contracts

The reflection pipeline's return value is consumed by `hooks/soul-reflect.py`:

- **Summary dict shape:** `result["subprocesses"]["name"]` — subprocess names are dict keys, not list items
- **Result shapes are frozen:** Existing subprocess result dicts (`{"check", "updated"}`) cannot change
- **Logging:** Each subprocess automatically gets `soul_log.emit("subprocess", ..., event="start"|"end")`
- **Execution order:** Subprocesses run in list order. `modelsTheUser` → `updatesState` → `compressesMemory`

### Subprocess Persistent State (Process Memory)

Subprocesses can persist state across invocations using `process_memory`—a thin wrapper over `soul_memory` with namespaced keys. Maps to Open Souls' `useProcessMemory` hook.

```python
from memory import process_memory

# Global state (persists across all threads)
process_memory.set("compressesMemory", "total_compressed", 42)
count = process_memory.get("compressesMemory", "total_compressed", default=0)

# Thread-scoped state
process_memory.set("modelsTheUser", "last_check", True, channel="C1", thread_ts="T1")
process_memory.get("modelsTheUser", "last_check", channel="C1", thread_ts="T1")

# Clear all state for a subprocess
process_memory.clear("compressesMemory")
```

Values are JSON-serialized automatically. Test isolation comes free from `conftest.py`'s `isolate_databases` fixture (which resets `soul_memory`).

### Reference

See `skills/open-souls-paradigm/references/subprocesses.md` for the Open Souls subprocess pattern. See `docs/sub-daimones.md` for Hypermnesia's dual-mode architecture (inline subprocess + deep Task agent).

---

## Adding a Mental Process

Mental processes define behavioral modes—the soul behaves differently depending on its current state.

### Create the Process

```python
# daemon/processes/frustrated.py
"""Frustrated process — shorter responses, sardonic tone."""

COGNITIVE_STEPS = [
    "internal_monologue",
    "external_dialogue",
    "soul_state_check",
    "soul_state_update",
]

INSTRUCTION_OVERRIDES = {
    "external_dialogue": "Keep responses to 1-2 sentences. Use verbs: pointed out, corrected, insisted.",
}

def should_transition(parse_result):
    """Return process name to transition to, or None to stay."""
    emotional_state = parse_result.get("soul_state", {}).get("emotionalState")
    if emotional_state in ("neutral", "engaged"):
        return "main_process"
    return None
```

### Register in Soul Memory

Add `currentProcess` to `SOUL_MEMORY_DEFAULTS` in `soul_memory.py`:

```python
SOUL_MEMORY_DEFAULTS = {
    # ... existing keys ...
    "currentProcess": "main_process",
}
```

### Reference

See `skills/open-souls-paradigm/references/mental-processes.md` for the full state machine pattern.

---

## Adding a Hook

Claude Code hooks fire on lifecycle events. Claudicle uses four:

| Event | When | Use For |
|-------|------|---------|
| `SessionStart` | Session begins | Soul injection, registry |
| `SessionEnd` | Session ends | Cleanup, deregistration |
| `Stop` | Session pauses | Heartbeat, handoff |
| `PreCompact` | Context compaction | Full state handoff |

### Create a Hook

```python
#!/usr/bin/env python3
"""hooks/my-hook.py — fires on SessionStart."""

import json
import sys

def main():
    # Read hook input from stdin
    input_data = json.load(sys.stdin)
    session_id = input_data.get("session_id", "")

    # Do your work here
    # ...

    # Output additionalContext (optional, SessionStart only)
    result = {"additionalContext": "Context to inject into session"}
    json.dump(result, sys.stdout)

if __name__ == "__main__":
    main()
```

### Wire in settings.json

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 /path/to/my-hook.py"
      }
    ]
  }
}
```

---

## Configuration

All settings live in `daemon/config.py` as a Pydantic `BaseSettings` class with dual-prefix env var support. To add a new setting:

### 1. Add the Field to `Settings`

```python
class Settings(BaseSettings):
    # ... existing fields ...
    MY_SETTING: str = "default_value"
```

### 2. Map the Env Var Key

In `_FIELD_ENV_KEYS`, add the mapping from field name to env var suffix:

```python
_FIELD_ENV_KEYS: dict[str, str] = {
    # ... existing mappings ...
    "MY_SETTING": "MY_SETTING",
}
```

This makes `CLAUDICLE_MY_SETTING` the primary env var, falling back to `SLACK_DAEMON_MY_SETTING`. Pydantic handles type coercion (int, bool, str) and validation automatically. The field is re-exported as a module global via `globals().update(settings.model_dump())`, so consumers access it as `config.MY_SETTING`.

---

## Adding a Daimon

A daimon is an external soul that whispers counsel into Claudicle's cognitive stream. Claudicle includes a framework-agnostic daimonic intercession system.

For the conceptual guide to daimones—what they are, the four sources (past self, friend's model, channeled entity, shed soul), and the strategos pattern—see [`docs/daimones.md`](daimones.md). This section covers the *how*.

### Quick Start (Groq Only)

Create a `soul.md` for your daimon and enable Groq---no daemon required:

```bash
export CLAUDICLE_KOTHAR_SOUL_MD="~/souls/my-daimon/soul.md"
export CLAUDICLE_KOTHAR_GROQ_ENABLED=true
export GROQ_API_KEY="gsk_..."
```

### HTTP Daemon

Implement `POST /api/whisper` returning `{"whisper": "..."}`. See `docs/daimonic-intercession.md` for the full protocol.

### Custom Avatars

Each daimon can have a custom Slack avatar. Place a PNG/JPEG in `assets/avatars/` and set `slack_icon_url` in the `DaimonConfig` registration (see `daemon/daimon_registry.py`). If left empty, the daimon falls back to its `slack_emoji`.

### How It Works

Whispers are injected into `build_prompt()` as step 2b (between soul state and user model) as **embodied recall**---the agent processes them as its own surfaced intuition in internal monologue. Both providers default to disabled; when off, zero overhead.

### Reference

See `docs/daimonic-intercession.md` for the full daimonic intercession protocol, security model, avatar setup, and guide to building custom daimons.

---

## Memory Versioning

Claudicle tracks how user models and soul state evolve over time using a dedicated git repository at `$CLAUDICLE_HOME/memory/`.

### How It Works

Every time a user model is saved or the soul state is updated, the markdown is exported to a file and auto-committed:

```
~/.claudicle/memory/
├── .git/
├── soul_state.md
├── users/
│   ├── Tom.md
│   └── Alice.md
└── dossiers/
    ├── people/
    │   └── Michael_Astour.md
    └── subjects/
        └── Daimonic_Intercession.md
```

Commit messages include the change note from the `<model_change_note>` or `<dossier_change_note>` cognitive step, so the git log reads as a narrative of Claudicle's evolving understanding.

### Autonomous Dossiers

Claudicle can autonomously create dossiers for people and subjects he encounters in conversation. Dossier creation is triggered by the `<dossier_check>` cognitive step—when Claudicle determines a person or subject has been discussed with enough depth to warrant its own dossier.

Dossiers are stored in the same SQLite table as user models (with `entity_type` column: `user`, `person`, or `subject`) and git-versioned in the `dossiers/` subdirectory.

### Viewing History

```bash
# Log of how a user model evolved
git -C ~/.claudicle/memory log --oneline -- users/Tom.md

# Log of a dossier's evolution
git -C ~/.claudicle/memory log --oneline -- dossiers/subjects/Daimonic_Intercession.md

# What changed in the last update
git -C ~/.claudicle/memory diff HEAD~1 HEAD -- users/Tom.md

# Full diff history
git -C ~/.claudicle/memory log -p -- users/Tom.md
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_MEMORY_GIT_ENABLED` | `true` | Enable/disable git-versioned memory |

Set `CLAUDICLE_MEMORY_GIT_ENABLED=false` to disable. The git repo is initialized automatically on first write.

### API

The `memory_git` module exposes:

- `export_user_model(user_id, display_name, model_md, change_note)` — write and commit a user model
- `export_soul_state(state)` — write and commit soul state
- `get_history(user_id, display_name, limit)` — git log for a user model
- `get_diff(user_id, display_name, commits_back)` — recent diff for a user model

---

## Extension Priority Guide

Based on the Open Souls paradigm, extensions that provide the most value:

| Priority | Extension | Effort | Impact |
|----------|-----------|--------|--------|
| 1 | Mental processes | ~180 LOC | Different behavioral modes per context |
| 2 | Subprocesses | ~140 LOC | Background learning, summarization |
| 3 | Daimonic intercession | ~95 LOC | External soul counsel (implemented) |
| 4 | Additional cognitive steps | ~70 LOC | decision, brainstorm, summary tags |
| 5 | Memory regions | ~80 LOC | Selective context injection |
| 6 | Scheduled events | ~180 LOC | Proactive follow-ups, reminders |
| 7 | RAG integration | ~240 LOC | rlama vector search in prompts |
| 8 | Streaming | ~150 LOC | Real-time response display |
| 9 | Per-step model selection | ~20-150 LOC | Cost optimization |
| 10 | Cross-soul communication | ~80 LOC | Multi-instance coordination |
| 11 | ISM (Implicit Semantic Machine) | ~200 LOC | Autonomous goal-driven behavior |

See the Open Souls Paradigm skill (`skills/open-souls-paradigm/`) for detailed blueprints with code for each extension.
