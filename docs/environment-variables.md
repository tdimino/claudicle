# Environment Variables

Configuration for Claudicle's daemon, soul engine, and channel adapters. All use the `CLAUDICLE_` prefix.

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_HOME` | `~/.claudicle` | Installation directory |
| `CLAUDICLE_CWD` | `~` | Working directory for Claude |
| `CLAUDICLE_TIMEOUT` | `120` | Response timeout (seconds) |
| `CLAUDICLE_TOOLS` | `Read,Glob,Grep,Bash,WebFetch` | Allowed Claude tools |
| `CLAUDICLE_SOUL_ENGINE` | `true` | Enable cognitive pipeline |
| `CLAUDICLE_MEMORY_TTL` | `72` | Working memory TTL (hours) |

## Soul Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_SOUL` | `0` | Always-on soul injection (`1` = inject soul.md into every session, `0` = opt-in via `/ensoul`) |
| `CLAUDICLE_SOUL_PROFILE` | — | Override active soul profile for this session (e.g. `CLAUDICLE_SOUL_PROFILE=researcher claude`) |
| `CLAUDICLE_PRIMARY_USER_ID` | `DEFAULT_SLACK_USER_ID` | Soul owner's user ID (gets `role: "primary"` in user model) |

Resolution order: `CLAUDICLE_SOUL_PROFILE` env var > `soul/active` symlink > `soul/soul.md` fallback.

## Daimonic Intercession

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_KOTHAR_ENABLED` | `false` | Enable Kothar daimonic intercession via HTTP daemon |
| `CLAUDICLE_KOTHAR_GROQ_ENABLED` | `false` | Enable Kothar daimonic intercession via Groq |
| `CLAUDICLE_ARTIFEX_ENABLED` | `false` | Enable Artifex daimonic intercession via HTTP daemon |
| `CLAUDICLE_ARTIFEX_GROQ_ENABLED` | `false` | Enable Artifex daimonic intercession via Groq |

## Slack

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | — | Slack bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | — | Slack app-level token for Socket Mode (`xapp-...`) |

## Terminal Reflection

| Variable | Default | Description |
|----------|---------|-------------|
| `TERMINAL_REFLECT_ENABLED` | `true` | Enable retrospective cognitive reflection after terminal exchanges |
| `REFLECT_PROVIDER` | `groq` | Reflection LLM provider (`groq`, `openrouter`, or OpenAI-compatible URL) |
| `REFLECT_MODEL` | `moonshotai/kimi-k2-instruct` | Model for reflection pipeline |
| `REFLECT_COOLDOWN` | `60` | Minimum seconds between reflections |
| `STIMULUS_VERB_ENABLED` | `true` | Enable stimulus verb narration in cognitive stream |
