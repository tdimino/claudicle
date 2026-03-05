# Cognitive Sandbox

Isolated environment for observing the Claudicle cognitive pipeline---gate firing, working memory formation, user model creation, and soul state updates---without touching production databases.

## Quick Start

```bash
# Single message
uv run scripts/sandbox.py --message "What's your take on Mediterranean trade routes?"

# Run a canned scenario
uv run scripts/sandbox.py --scenario first-meeting

# Interactive REPL
uv run scripts/sandbox.py --repl

# Use a specific provider (default: groq)
uv run scripts/sandbox.py --message "Hello" --provider groq

# Keep sandbox dir after exit for inspection
uv run scripts/sandbox.py --message "Hello" --keep

# Use a custom soul personality
uv run scripts/sandbox.py --message "Hello" --soul /path/to/custom-soul.md

# Enable daimonic whisper observation (requires Groq API key)
uv run scripts/sandbox.py --message "Hello" --daimonic

# Full observatory mode
uv run scripts/sandbox.py --repl --soul soul/profiles/minimal.md --daimonic --keep
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--message TEXT` | Run a single message through the pipeline |
| `--scenario NAME` | Run a canned multi-turn scenario |
| `--repl` | Interactive REPL mode |
| `--user-id ID` | Override speaker user_id (default: `U_SANDBOX`) |
| `--user-name NAME` | Override speaker display name (default: `Sandbox User`) |
| `--mode unified\|split` | Pipeline mode (default: from config) |
| `--provider NAME` | LLM provider: `groq`, `openrouter`, `anthropic` (default: `groq`) |
| `--model NAME` | Override LLM model |
| `--keep` | Preserve temp dir after exit |
| `--verbose` | Show raw LLM response in addition to structured output |
| `--soul PATH` | Use a custom soul.md file instead of the active profile |
| `--daimonic` | Enable daimonic whisper generation via Groq fallback |

## REPL Commands

| Command | Description |
|---------|-------------|
| `/wm` | Show all working memory entries |
| `/wm --type TYPE` | Filter working memory by entry type |
| `/user-model` | Show current user model (with YAML frontmatter parsing) |
| `/user-model-history` | Show user model check history across cycles |
| `/soul-state` | Show soul state |
| `/soul-log` | Show soul stream JSONL |
| `/soul` | Show active soul path and first 10 lines |
| `/soul-switch PATH` | Hot-swap soul.md mid-session |
| `/trace ID` | Show all entries for a trace_id |
| `/scenario NAME` | Run a canned scenario |
| `/reset` | Wipe sandbox memory, start fresh |
| `/mode split\|unified` | Switch pipeline mode |
| `/export` | Copy sandbox dir to `~/.claudicle/sandbox-exports/` |
| `/daimonic` | Show daimon registry status (enabled daimons, Groq models) |
| `/whispers` | Show all active daimonic whispers |
| `/subdaimones` | List all 12 subdaimon definitions (informational---subdaimones can't run in sandbox) |
| `/quit` | Exit REPL |

## Isolation Architecture

Every sandbox session runs in a temporary directory with complete isolation from production:

```
┌─────────────────────────────────────────────────┐
│ SandboxEnv(/tmp/claudicle-sandbox-XXXX)         │
│                                                 │
│  1. SQLite: memory.db, sessions.db              │
│     ConnectionPool.db_path → temp_dir           │
│     ConnectionPool.reset_local()                │
│                                                 │
│  2. JSONL: soul-stream.jsonl, wm-stream.jsonl   │
│     soul_log.LOG_PATH → temp_dir                │
│     wm_stream.WM_STREAM_PATH → temp_dir         │
│                                                 │
│  3. Git tracker → temp_dir/memory/              │
│     config.MEMORY_GIT_ENABLED = False           │
│                                                 │
│  4. Context caches → reset                      │
│     _soul_cache, _skills_cache = None           │
│                                                 │
│  5. Daimonic → conditional                      │
│     --daimonic: registry init + Groq-only       │
│     default: format_for_prompt = lambda: ""     │
│                                                 │
│  6. Config overrides                            │
│     ONBOARDING_ENABLED = False                  │
│                                                 │
│  7. Soul file from active profile or --soul     │
│     context._SOUL_MD_PATH overridden            │
│                                                 │
│  8. soul_memory._migrated = False (fresh schema)│
│     soul_engine._trace_local = threading.local()│
└─────────────────────────────────────────────────┘
```

**Production safety**: The sandbox patches `ConnectionPool` instances directly (`memory_pool.db_path`, `session_pool.db_path`) and calls `reset_local()` to force reconnection. This matches the isolation pattern used by `daemon/tests/conftest.py`. Module-level `DB_PATH` attributes are dead exports---the pool owns the path.

## Custom Soul

The `--soul` flag overrides the active soul profile for the entire sandbox session:

```bash
# Use a named profile
uv run scripts/sandbox.py --repl --soul soul/profiles/minimal.md

# Use an arbitrary soul file
uv run scripts/sandbox.py --message "Hello" --soul ~/Desktop/experimental-soul.md
```

The startup banner shows which soul is loaded:

```
  Soul: /path/to/custom-soul.md (custom)
  # or
  Soul: ~/.claudicle/soul/soul.md (default)
```

In REPL mode, `/soul` shows the active path and first 10 lines. `/soul-switch <path>` hot-swaps the soul mid-session by patching `context._SOUL_MD_PATH` and clearing the cache.

Scenarios can also specify a `soul_path` field to override the soul for that scenario only.

## Daimonic Observation

The `--daimonic` flag enables daimonic whisper generation inside the sandbox using the Groq fallback transport (no running daemon required):

```bash
# Single message with whispers
uv run scripts/sandbox.py --message "Hello" --daimonic

# REPL with full daimonic visibility
uv run scripts/sandbox.py --repl --daimonic
```

When enabled:
- The daimon registry is initialized from config (`KOTHAR_*`, `ARTIFEX_*` env vars)
- Daemon endpoints are disabled (Groq-only mode forced)
- Before each cognitive cycle, all whisperers are invoked via `invoke_all_whisperers()`
- Whispers are rendered in the cycle output between context decisions and gates

REPL commands:
- `/daimonic` --- Show registry status (enabled daimons, transport modes, Groq models)
- `/whispers` --- Show all active whispers from soul_memory
- `/subdaimones` --- List all 12 subdaimon definitions from `/subdaimones/*.md` (informational only---subdaimones are Claude Code Agents and cannot run inside the sandbox)

## User Model Observability

The sandbox surfaces detailed user model lifecycle data in each cognitive cycle:

### Context Decisions

Each cycle shows which context-assembly gates fired:

```
  CONTEXT: Inject user model? → true
  CONTEXT: Inject skills reference? → true
  CONTEXT: Inject dossiers? → false
```

These correspond to the `_log_decision()` calls in `build_context()`.

### Size Delta

User model size is tracked across cycles with a delta indicator:

```
  STATS: wm_entries=5, user_model=1.2KB (+384B), interaction=#3
```

Green `+NB` for growth, red `-NB` for shrinkage, gray `(new)` for first observation.

### Frontmatter

The `/user-model` REPL command now parses and displays YAML frontmatter separately:

```
  Frontmatter:
    userName: Alice
    onboardingComplete: true
    role: engineer
  ---
  # Alice
  ...
```

### Check History

The `/user-model-history` REPL command shows the user model check results across all cycles---which cycles triggered updates and which didn't:

```
  [abc123] user model check → true
  [def456] user model check → false
```

## Canned Scenarios

Defined in `scripts/sandbox_scenarios.py`. Each scenario specifies messages, optional user identity overrides, optional pre-seeded user models, and optional custom soul path.

| Scenario | Description |
|----------|-------------|
| `first-meeting` | New user, no prior context---tests `ensure_exists` + onboarding gate |
| `returning-user` | Pre-seeded user model---tests Samantha-Dreams injection gate |
| `gate-cascade` | Message designed to trigger all gates (user model, dossier, soul state) |
| `multi-speaker` | Thread with multiple speakers---tests active speaker tracking |
| `sms-channel` | SMS-style interaction---tests SMS channel defaults + modular loading |

### Scenario Format

```python
{
    "description": str,          # One-line summary
    "channel": str,              # Optional channel override (default: sandbox:test)
    "soul_path": str,            # Optional custom soul.md path (overrides --soul flag)
    "setup": {                   # Optional pre-seeding
        "user_id": str,
        "user_name": str,
        "model_md": str,         # Pre-seed user model markdown
    },
    "messages": [                # Ordered conversation turns
        {
            "text": str,         # Message content
            "user_id": str,      # Optional (default from CLI)
            "user_name": str,    # Optional (default from CLI)
        },
    ],
}
```

## Structured Output

Each cognitive cycle renders a structured ANSI panel showing:

- Stimulus verb
- Internal monologue (verb + content)
- External dialogue (verb + content)
- Context decisions: user model injection, skills injection, dossier injection
- Daimonic whispers (when `--daimonic` enabled)
- Gate decisions: `user_model_check`, `dossier_check`, `soul_state_check`
- Conditional updates (user model, soul state) when gates fire
- Working memory entries, user model size with delta, interaction count

## Provider Routing

Default: Groq (Kimi-K2) for fast iteration. Providers from `engine/llm_client.py`:

```bash
--provider groq          # Fast, cheap (default)
--provider openrouter    # Flexible model selection
--provider anthropic     # Direct Claude API
```

## Inspecting Results

With `--keep`, the sandbox temp dir persists after exit:

```bash
# List sandbox artifacts
ls /tmp/claudicle-sandbox-*/

# Inspect working memory
sqlite3 /tmp/claudicle-sandbox-*/memory.db "SELECT entry_type, verb, substr(content,1,80) FROM working_memory ORDER BY created_at"

# Read soul stream
cat /tmp/claudicle-sandbox-*/soul-stream.jsonl | python3 -m json.tool

# Check user model
sqlite3 /tmp/claudicle-sandbox-*/memory.db "SELECT model_md FROM user_models"

# Check context decisions
sqlite3 /tmp/claudicle-sandbox-*/memory.db "SELECT content, metadata FROM working_memory WHERE entry_type='decision' ORDER BY created_at"
```

## Sandbox vs pytest

The sandbox and the test suite serve different purposes:

| | pytest (`daemon/tests/`) | Sandbox (`scripts/sandbox.py`) |
|---|---|---|
| **Purpose** | Verify correctness | Observe behavior |
| **LLM calls** | Mocked (`MockProvider`) | Real (Groq, OpenRouter, etc.) |
| **Output** | Pass/fail assertions | Structured cognitive cycle rendering |
| **Speed** | 811 tests in <7s | One cycle per LLM call (~1-3s) |
| **Use case** | CI, regression | Development, debugging, pipeline tuning |

## Files

| File | LOC | Purpose |
|------|-----|---------|
| `scripts/sandbox.py` | 1100 | CLI, SandboxEnv, structured output, REPL, observatory features |
| `scripts/sandbox_scenarios.py` | 123 | Canned test scenarios |
