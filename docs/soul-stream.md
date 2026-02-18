# Soul Stream — Structured Cognitive Cycle Log

The soul stream is a `tail -f`-able JSONL log capturing the full interpreted cognitive cycle of every interaction. It sits alongside two other observability layers:

| Layer | File | Storage | Purpose |
|-------|------|---------|---------|
| Raw events | `slack_log.py` | `$CLAUDIUS_HOME/slack-events.jsonl` | Pre-processing Slack events |
| Cognitive store | `working_memory.py` | `memory.db` (SQLite) | Post-processing metadata, gate inputs |
| **Soul stream** | `soul_log.py` | `$CLAUDIUS_HOME/soul-stream.jsonl` | Full cognitive cycle, streaming |

The soul stream does NOT duplicate SQLite data. It is the streaming observability layer — designed for real-time monitoring, debugging, and downstream analytics.

## Quick Start

```bash
# Watch the soul's mental life in real time
tail -f ~/.claudius/soul-stream.jsonl | jq .

# Filter to decision gates only
tail -f ~/.claudius/soul-stream.jsonl | jq 'select(.phase=="decision")'

# Filter to a specific trace (cognitive cycle)
cat ~/.claudius/soul-stream.jsonl | jq 'select(.trace_id=="a1b2c3d4e5f6")'

# Show only cognition steps with their verbs
tail -f ~/.claudius/soul-stream.jsonl | jq 'select(.phase=="cognition") | {step, verb, content_length}'

# Latency analysis
cat ~/.claudius/soul-stream.jsonl | jq 'select(.phase=="response") | .elapsed_ms'
```

## JSONL Schema

Every line shares a common envelope:

```json
{
  "phase": "stimulus|context|cognition|decision|memory|response|error",
  "trace_id": "a1b2c3d4e5f6",
  "ts": "2026-02-18T14:23:01.123456+00:00",
  "channel": "C0123456789",
  "thread_ts": "1708000000.001000"
}
```

### Phase: `stimulus`

User message received and entering the cognitive pipeline.

```json
{
  "phase": "stimulus",
  "origin": "slack",
  "user_id": "U456",
  "display_name": "Tom",
  "text": "What's the etymology of Knossos?",
  "text_length": 35
}
```

### Phase: `context`

What was assembled into the prompt. The `gates` object records every injection decision.

```json
{
  "phase": "context",
  "gates": {
    "skills_injected": false,
    "user_model_injected": true,
    "dossier_injected": false,
    "dossier_names": [],
    "soul_state_injected": true,
    "daimonic_whispers_injected": false
  },
  "prompt_length": 4823,
  "pipeline_mode": "unified",
  "interaction_count": 7
}
```

### Phase: `cognition`

One entry per cognitive step extracted from the response. Multiple per trace.

```json
{
  "phase": "cognition",
  "step": "internalMonologue",
  "verb": "pondered",
  "content": "This user is asking about Minoan etymology...",
  "content_length": 128
}
```

In split mode, includes provider routing metadata:

```json
{
  "phase": "cognition",
  "step": "externalDialog",
  "verb": "explained",
  "content": "Knossos derives from...",
  "content_length": 245,
  "provider": "openrouter",
  "model": "anthropic/claude-sonnet-4"
}
```

### Phase: `decision`

One entry per boolean gate evaluation. Multiple per trace.

```json
{
  "phase": "decision",
  "gate": "user_model_check",
  "result": true,
  "content": "Should the user model be updated?"
}
```

Gates: `user_model_check`, `dossier_check`, `soul_state_check`.

### Phase: `memory`

One entry per state mutation.

```json
{
  "phase": "memory",
  "action": "user_model_update",
  "target": "U456",
  "change_note": "Added interest in Minoan archaeology",
  "detail": {}
}
```

Actions: `user_model_update`, `dossier_update`, `soul_state_update`.

### Phase: `response`

Final output sent to user.

```json
{
  "phase": "response",
  "text": "Knossos derives from...",
  "text_length": 245,
  "truncated": false,
  "elapsed_ms": 4665
}
```

### Phase: `error`

Exception during any phase.

```json
{
  "phase": "error",
  "source": "soul_engine.parse_response",
  "error": "No <external_dialogue> found",
  "error_type": "ValueError"
}
```

## API

### `soul_log.emit(phase, trace_id, channel="", thread_ts="", **kwargs)`

Append a phase entry to the soul stream. Never raises — failures are logged and swallowed.

- Thread-safe via `fcntl.flock`
- `json.dumps(entry, default=str)` handles non-serializable types
- Gated by `SOUL_LOG_ENABLED` config flag

### `soul_log.read_log(path=None, last_n=0)`

Read JSONL entries from the log file. Returns `list[dict]`. Skips malformed lines.

### `soul_log.read_trace(trace_id, path=None)`

Read all entries for a specific trace_id, ordered by timestamp.

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `CLAUDIUS_SOUL_LOG` | `true` | Enable/disable soul stream logging |
| `CLAUDIUS_SOUL_LOG` (path) | `$CLAUDIUS_HOME/soul-stream.jsonl` | Custom log file path (env: `CLAUDIUS_SOUL_LOG`) |

## Emit Points

The soul stream is populated from four daemon modules:

| Module | Phases Emitted | When |
|--------|---------------|------|
| `claude_handler.py` | stimulus, response, error | Before `build_prompt()`, before return |
| `context.py` | context | End of `build_context()` (when trace_id provided) |
| `soul_engine.py` | cognition, decision, memory | After each `working_memory.add()` in `parse_response()` |
| `pipeline.py` | cognition, decision, memory | After each `working_memory.add()` in split-mode steps |

## Trace Reconstruction

A typical trace contains 5-8 entries:

```
stimulus → context → cognition(monologue) → cognition(dialogue) → decision(model_check) → response
```

With state updates active:

```
stimulus → context → cognition(monologue) → cognition(dialogue) → decision(model_check) → memory(model_update) → decision(state_check) → memory(state_update) → response
```

Use `read_trace()` or jq to reconstruct:

```bash
cat ~/.claudius/soul-stream.jsonl | jq -s 'group_by(.trace_id) | .[] | sort_by(.ts)'
```

## Relationship to Other Logs

- **slack_log.py** captures everything that hits Slack (including filtered-out messages). Soul stream captures only messages that enter the cognitive pipeline.
- **working_memory** stores structured rows queryable by SQL. Soul stream is append-only JSONL for streaming consumption.
- All three share trace_id when available, enabling cross-layer correlation.
