# Environment Variables

Configuration for Claudicle's daemon, soul engine, and channel adapters. All settings are defined in `daemon/config.py` as a Pydantic `BaseSettings` class with a custom `LegacyPrefixedEnvSource`. Every variable supports dual-prefix resolution: `CLAUDICLE_` first, `SLACK_DAEMON_` fallback. Pydantic handles type coercion (int, bool, str) and validation automatically—setting an invalid type (e.g. `CLAUDICLE_SESSION_TTL=not-an-int`) raises a `ValidationError` at import time.

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_HOME` | `~/.claudicle` | Installation directory |
| `CLAUDICLE_CWD` | `~` | Working directory for Claude |
| `CLAUDICLE_TIMEOUT` | `120` | Response timeout (seconds) |
| `CLAUDICLE_TOOLS` | `Read,Glob,Grep,Bash,WebFetch` | Allowed Claude tools |
| `CLAUDICLE_SOUL_ENGINE` | `true` | Enable cognitive pipeline |
| `CLAUDICLE_MEMORY_TTL` | `72` | Working memory TTL (hours) |
| `CLAUDICLE_SESSION_TTL` | `24` | Session expiry (hours) |
| `CLAUDICLE_ONBOARDING` | `true` | Enable first-ensoulment onboarding interview |
| `CLAUDICLE_SOUL_LOG` | `true` | Enable structured cognitive cycle JSONL stream |

## Soul Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_SOUL` | `0` | Always-on soul injection (`1` = inject soul.md into every session, `0` = opt-in via `/ensoul`) |
| `CLAUDICLE_SOUL_NAME` | `Claudius` | Soul name (used for prompt assembly and soul_memory scoping) |
| `CLAUDICLE_SOUL_PROFILE` | — | Override active soul profile for this session (e.g. `CLAUDICLE_SOUL_PROFILE=researcher claude`) |
| `CLAUDICLE_PRIMARY_USER_ID` | `DEFAULT_SLACK_USER_ID` | Soul owner's user ID (gets `role: "primary"` in user model) |

Resolution order: `CLAUDICLE_SOUL_PROFILE` env var > `soul/active` symlink > `soul/soul.md` fallback.

## Memory Compression (Hypermnesia)

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_COMPRESSION` | `true` | Enable Hypermnesia memory compression |
| `CLAUDICLE_COMPRESSION_THRESHOLD` | `50` | Minimum entries before compression triggers |
| `CLAUDICLE_COMPRESSION_KEEP` | `20` | Number of recent entries to preserve uncompressed |
| `CLAUDICLE_COMPRESSION_INTERVAL` | `5` | Compression runs every N reflection cycles |
| `CLAUDICLE_COMPRESSION_LLM` | `false` | Use LLM for compression (vs heuristic) |
| `CLAUDICLE_COMPRESSION_MODEL` | — | Model for LLM compression |
| `CLAUDICLE_COMPRESSION_PROVIDER` | — | Provider for LLM compression |
| `CLAUDICLE_COMPRESSION_ARCHIVE` | `true` | Archive compressed entries (vs delete) |

## Working Memory

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_WM_PROMPT_INJECT` | `false` | Inject raw working memory into prompt |
| `CLAUDICLE_WM_WINDOW` | `40` | Max entries to include in prompt injection |
| `CLAUDICLE_WM_STREAM` | `true` | Enable working memory JSONL stream |

## Subdaimon Memory

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_DAIMON_MEMORY_TTL` | `720` | Subdaimon memory TTL (hours). `daimon:` channels are exempt from default working memory TTL and use this instead (30 days default) |

## Provider Routing

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_PROVIDER` | `claude_cli` | Default LLM provider |
| `CLAUDICLE_MODEL` | — | Default model override |
| `CLAUDICLE_PIPELINE_MODE` | `unified` | `unified` (single call) or `split` (per-step) |

### Per-Step Overrides (split mode only)

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_PROVIDER_MONOLOGUE` | — | Provider for internal_monologue step |
| `CLAUDICLE_PROVIDER_DIALOGUE` | — | Provider for external_dialogue step |
| `CLAUDICLE_PROVIDER_GATE` | — | Provider for user_model_check and soul_state_check |
| `CLAUDICLE_PROVIDER_UPDATE` | — | Provider for user_model_update and soul_state_update |
| `CLAUDICLE_MODEL_MONOLOGUE` | — | Model for internal_monologue step |
| `CLAUDICLE_MODEL_DIALOGUE` | — | Model for external_dialogue step |
| `CLAUDICLE_MODEL_GATE` | — | Model for gate steps |
| `CLAUDICLE_MODEL_UPDATE` | — | Model for update steps |

## Daimonic Intercession

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_KOTHAR_ENABLED` | `false` | Enable Kothar daimonic intercession via HTTP daemon |
| `CLAUDICLE_KOTHAR_GROQ_ENABLED` | `false` | Enable Kothar daimonic intercession via Groq |
| `CLAUDICLE_KOTHAR_HOST` | `localhost` | Kothar daemon host |
| `CLAUDICLE_KOTHAR_PORT` | `3033` | Kothar daemon port |
| `CLAUDICLE_KOTHAR_SOUL_MD` | `~/souls/kothar/soul.md` | Path to Kothar's soul personality file |
| `CLAUDICLE_KOTHAR_MODE` | `whisper` | Kothar mode: `whisper`, `speak`, `both`, `off` |
| `CLAUDICLE_ARTIFEX_ENABLED` | `false` | Enable Artifex daimonic intercession via HTTP daemon |
| `CLAUDICLE_ARTIFEX_GROQ_ENABLED` | `false` | Enable Artifex daimonic intercession via Groq |
| `CLAUDICLE_ARTIFEX_HOST` | `localhost` | Artifex daemon host |
| `CLAUDICLE_ARTIFEX_PORT` | `3034` | Artifex daemon port |
| `CLAUDICLE_ARTIFEX_SOUL_MD` | `~/souls/artifex/soul.md` | Path to Artifex's soul personality file |
| `CLAUDICLE_ARTIFEX_MODE` | `whisper` | Artifex mode: `whisper`, `speak`, `both`, `off` |
| `CLAUDICLE_ARTIFEX_GROQ_MODEL` | `moonshotai/kimi-k2-instruct` | Model for Artifex Groq mode |
| `GROQ_API_KEY` | — | Shared Groq API key (not prefixed) |

## Autonomous Dossiers

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_DOSSIER_ENABLED` | `true` | Enable autonomous dossier creation for people and subjects |
| `CLAUDICLE_MAX_DOSSIER_INJECTION` | `3` | Max dossiers to inject per prompt |

## Memory Versioning

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_MEMORY_GIT_ENABLED` | `true` | Enable git-versioned memory (user models and soul state) |

## Slack

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | — | Slack bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | — | Slack app-level token for Socket Mode (`xapp-...`) |

## WhatsApp

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_WHATSAPP_GATEWAY_URL` | `http://localhost:3847` | WhatsApp gateway URL |
| `CLAUDICLE_WHATSAPP_GATEWAY_PORT` | `3847` | WhatsApp gateway port |
| `CLAUDICLE_WHATSAPP_ALLOWED_SENDERS` | — | Comma-separated allowed phone numbers |
| `CLAUDICLE_WHATSAPP_RATE_LIMIT` | `10` | Max messages per minute per sender |

## Terminal

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_TERMINAL_TOOLS` | `Read,Glob,Grep,Bash,WebFetch,Edit,Write` | Allowed tools in terminal mode |
| `CLAUDICLE_TERMINAL_SOUL` | `false` | Enable soul in terminal mode |

## Terminal Reflection

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_TERMINAL_REFLECT` | `true` | Enable retrospective cognitive reflection after terminal exchanges |
| `CLAUDICLE_REFLECT_PROVIDER` | `groq` | Reflection LLM provider (`groq`, `openrouter`, or OpenAI-compatible URL) |
| `CLAUDICLE_REFLECT_MODEL` | `moonshotai/kimi-k2-instruct` | Model for reflection pipeline |
| `CLAUDICLE_REFLECT_COOLDOWN` | `60` | Minimum seconds between reflections |
| `CLAUDICLE_STIMULUS_VERB` | `true` | Enable stimulus verb narration in cognitive stream |

## Inbox Watcher

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_WATCHER_PROVIDER` | — | Provider override for inbox watcher (empty = default) |
| `CLAUDICLE_WATCHER_MODEL` | — | Model override for inbox watcher |
| `CLAUDICLE_WATCHER_POLL` | `3` | Poll interval in seconds |
