# Extending Claudius — Developer Guide

Add new capabilities to Claudius: cognitive steps, memory tiers, subprocesses, mental processes, channel adapters, and more.

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

In `daemon/soul_engine.py`, add to `_COGNITIVE_INSTRUCTIONS` (line 69):

```python
# After the existing soul_state_update instruction
"""
## Decision (when a choice must be made between options)

<decision options="option1,option2,option3">
chosen_option
</decision>
"""
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
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon
python3 -c "
import soul_engine
raw = '<decision options=\"joke,serious\">joke</decision>'
# Test extraction
print(soul_engine._extract_tag(raw, 'decision'))
"
```

### Reference

See `skills/open-souls-paradigm/references/additional-cognitive-steps.md` for the full list of Open Souls cognitive steps and their Claudius mapping.

---

## Adding a New Channel Adapter

Claudius supports any channel that can send/receive text. The pattern:

### Interface

Every adapter needs:
1. **Listener** — Receives messages from the channel
2. **Poster** — Sends responses back to the channel
3. **Identity resolution** — Map channel users to Claudius user IDs

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

### Reference

See `skills/open-souls-paradigm/references/memory-regions.md` for the Open Souls region pattern and `references/hooks-and-state.md` for the full hooks system.

---

## Adding a Subprocess

Subprocesses run background tasks after the main response. They handle cross-cutting concerns: user learning, summarization, analytics.

### Create the Subprocess

```python
# daemon/subprocesses/a_summarizes_conversation.py
"""Maintain a rolling conversation summary."""

import soul_memory
import working_memory

async def run(text, user_id, channel, thread_ts, parse_result):
    """Run after main process. Modifies shared state, not the response."""
    recent = working_memory.recent(channel, thread_ts, limit=10)
    if len(recent) < 5:
        return  # Not enough context

    entries = [f"{e['entry_type']}: {e['content'][:200]}" for e in recent]
    summary = "\n".join(entries)
    soul_memory.set("conversationSummary", summary[:500])
```

### Register the Runner

Add to `claude_handler.py` after `parse_response()`:

```python
await subprocess_runner.run_subprocesses(
    text, user_id, channel, thread_ts,
    parse_result=soul_engine.last_parse_result,
)
```

### Naming Convention

Prefix with a letter to control execution order:

```
subprocesses/
├── a_summarizes_conversation.py   # Runs first
├── b_tracks_sentiment.py          # Runs second
└── z_cleanup.py                   # Runs last
```

### Reference

See `skills/open-souls-paradigm/references/subprocesses.md` for the full Open Souls subprocess pattern.

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

Claude Code hooks fire on lifecycle events. Claudius uses four:

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

All settings live in `daemon/config.py`. Add new settings with the `_env()` helper:

```python
MY_SETTING = _env("MY_SETTING", "default_value")
```

This reads `CLAUDIUS_MY_SETTING` first, falls back to `SLACK_DAEMON_MY_SETTING`, then uses the default. See `config.py` for the full pattern.

---

## Adding a Daimon

A daimon is an external soul that whispers counsel into Claudius's cognitive stream. Claudius includes a framework-agnostic daimonic intercession system.

### Quick Start (Groq Only)

Create a `soul.md` for your daimon and enable Groq---no daemon required:

```bash
export CLAUDIUS_KOTHAR_SOUL_MD="~/souls/my-daimon/soul.md"
export CLAUDIUS_KOTHAR_GROQ_ENABLED=true
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
