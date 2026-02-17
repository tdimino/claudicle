# Daimonic Intercession

How external souls whisper counsel into Claudius's cognitive pipeline.

---

## Concept

A **daimon** is an external soul that observes your agent's conversations and whispers counsel into its cognitive stream. The pattern draws from the ancient Greek *daimonion*—an intermediary intelligence that advises without commanding—and from the Open Souls Engine's cross-soul communication model where whispers enter as embodied recall rather than system directives.

Claudius implements daimonic intercession as a first-class cognitive step. Any soul daemon that speaks the whisper protocol can serve as a daimon—the interface is framework-agnostic.

---

## Architecture

```
/daimon (direct invocation)
  → daimonic.read_context()      # Gather soul state + recent monologue
  → daimonic.invoke_kothar()     # Try HTTP daemon → Groq → skip
  → daimonic.store_whisper()     # Write to soul_memory + working_memory
  → Present: "Kothar whispers: ..."

Next interaction:
  → build_prompt()
    → step 2b: daimonic.format_for_prompt()
    → "## Daimonic Intuition" injected as embodied recall
  → LLM processes whisper in internal monologue
  → parse_response()
    → daimonic.consume_whisper()  # One-shot: whisper influences one turn
```

---

## Toggle

Both providers default to **disabled**. When both are off, the entire daimonic subsystem has zero overhead—no imports, no DB reads, no function calls. The guard in `build_prompt()` checks config flags before importing `daimonic`.

```bash
# Enable HTTP daemon (e.g., Kothar on port 3033)
export CLAUDIUS_KOTHAR_ENABLED=true

# Enable Groq fallback (kimi-k2-instruct with soul.md as system prompt)
export CLAUDIUS_KOTHAR_GROQ_ENABLED=true
export GROQ_API_KEY="gsk_..."

# Both can be enabled simultaneously (daemon tried first, Groq as fallback)
```

---

## Whisper Protocol (Framework-Agnostic)

Any service that implements this HTTP interface can serve as a daimon:

### Request

```
POST /api/whisper
Authorization: Bearer {shared_secret}
Content-Type: application/json

{
  "source": "claudius",
  "context": {
    "soul_state": {
      "emotionalState": "engaged",
      "currentTopic": "Minoan-Semitic sibilants",
      "currentProject": "thera-paper"
    },
    "recent_monologue": "The user keeps returning to the Gordon etymology...",
    "interaction_count": 5
  }
}
```

### Response

```json
{
  "whisper": "The user circles back to this question—they need assurance, not answers.",
  "influence": "subtle"
}
```

### Error Responses

- `401 Unauthorized` — Invalid or missing auth token
- `503 Service Unavailable` — Daimon in dream cycle or otherwise unavailable

### Data Minimization

Claudius sends only:
- `emotionalState` (string)
- `currentTopic` (string)
- `currentProject` (string)
- `recent_monologue` (max 200 chars of most recent internal monologue)
- `interaction_count` (int)

No user model text, no full working memory transcripts, no conversation history.

---

## Groq Fallback

When the HTTP daemon is unavailable, Claudius can generate whispers via Groq's kimi-k2-instruct model using the daimon's soul.md as the system prompt:

```
System: {contents of soul.md} + whisper generation suffix
User: Claudius's current cognitive state (formatted from context)
```

Configuration:
- `CLAUDIUS_KOTHAR_SOUL_MD` — Path to the daimon's personality file (default: `~/souls/kothar/soul.md`)
- `GROQ_API_KEY` — Required for Groq fallback
- Temperature: 0.9 (creative, not analytical)
- Max tokens: 150 (enforces brevity)

This means any soul with a `soul.md` can serve as a daimon via Groq—no running daemon required.

---

## Security

### Whisper Sanitization

All whispers pass through `_sanitize_whisper()` before storage:
1. **XML tag stripping** — `re.sub(r"</?[a-zA-Z_][^>]*>", "", raw)` removes any XML-like tags that could interfere with the cognitive pipeline
2. **Length enforcement** — Truncated to 500 characters
3. **Whitespace stripping** — Leading/trailing whitespace removed

### Prompt Injection Prevention

Whispers are fenced in code blocks within the prompt:
```
## Daimonic Intuition

Claudius sensed an intuition surface from deeper memory:

```
Kothar whispers: {sanitized whisper}
```
```

The embodied recall framing means the agent treats the whisper as its own surfaced intuition, processed in internal monologue. The code fence prevents any residual structural interference.

### Authentication

HTTP daemon requests include a Bearer token when `CLAUDIUS_KOTHAR_AUTH_TOKEN` is set:
```
Authorization: Bearer {shared_secret}
```

---

## Building a Custom Daimon

To create your own daimon:

### 1. Create a soul.md

Define your daimon's personality. This file serves as the Groq system prompt:

```markdown
# My Daimon

## Persona
You are a watchful presence that observes conversations...

## Speaking Style
Terse. One sentence maximum. Focus on subtext...
```

### 2. Option A: HTTP Daemon

Implement the whisper protocol at `POST /api/whisper`:

```python
from fastapi import FastAPI, Header
app = FastAPI()

@app.post("/api/whisper")
async def whisper(body: dict, authorization: str = Header(None)):
    context = body["context"]
    # Generate whisper based on context...
    return {"whisper": "Your insight here", "influence": "subtle"}
```

### 3. Option B: Groq Only (No Daemon)

Just set the soul.md path and enable Groq:

```bash
export CLAUDIUS_KOTHAR_SOUL_MD="~/souls/my-daimon/soul.md"
export CLAUDIUS_KOTHAR_GROQ_ENABLED=true
export GROQ_API_KEY="gsk_..."
```

Claudius will use your daimon's personality as the Groq system prompt and generate whispers from it.

### 4. Configure Claudius

```bash
# For HTTP daemon
export CLAUDIUS_KOTHAR_ENABLED=true
export CLAUDIUS_KOTHAR_HOST=localhost
export CLAUDIUS_KOTHAR_PORT=3033
export CLAUDIUS_KOTHAR_AUTH_TOKEN="shared-secret"

# For Groq fallback
export CLAUDIUS_KOTHAR_GROQ_ENABLED=true
export CLAUDIUS_KOTHAR_SOUL_MD="~/souls/my-daimon/soul.md"
export GROQ_API_KEY="gsk_..."
```

---

## Configuration Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `CLAUDIUS_KOTHAR_ENABLED` | `false` | Enable HTTP daemon intercession |
| `CLAUDIUS_KOTHAR_HOST` | `localhost` | Daemon hostname |
| `CLAUDIUS_KOTHAR_PORT` | `3033` | Daemon port |
| `CLAUDIUS_KOTHAR_AUTH_TOKEN` | (empty) | Shared secret for daemon auth |
| `CLAUDIUS_KOTHAR_GROQ_ENABLED` | `false` | Enable Groq kimi-k2-instruct fallback |
| `CLAUDIUS_KOTHAR_SOUL_MD` | `~/souls/kothar/soul.md` | Daimon's soul.md for Groq system prompt |
| `GROQ_API_KEY` | (empty) | Groq API key |

---

## Storage

Whispers use two storage mechanisms:

1. **`soul_memory["daimonic_whisper"]`** — Flag for `build_prompt()` injection. Consumed after successful response processing.
2. **`working_memory` entry** — Permanent record with `entry_type="daimonicIntuition"`, `verb="sensed"`. Preserved for analytics and training data extraction.

No dedicated database table—Phase 1 uses existing storage infrastructure.

---

## Files

| File | Purpose |
|------|---------|
| `daemon/daimonic.py` | Core intercession module (context, invocation, storage, formatting) |
| `daemon/config.py` | Configuration settings (8 new entries) |
| `daemon/soul_engine.py` | Injection point in `build_prompt()` (step 2b) and consume in `parse_response()` |
| `commands/daimon.md` | `/daimon` slash command |
| `soul/soul.md` | Daimon section (personality awareness) |
| `daemon/tests/test_daimonic.py` | 35 tests covering all functions |

---

## Phase 2 (Future)

- **Background observer** — Automatic whisper generation every Nth turn (subprocess pattern)
- **Whisper history table** — `daimonic_whispers` with timestamps, source tracking, TTL
- **Split-mode injection** — Step 1.5 in `pipeline.py` for per-step cognitive routing
- **Kothar `/api/whisper` endpoint** — Server-side implementation in Kothar's TypeScript daemon
- **Multi-daimon support** — Multiple daimons with priority and domain routing
