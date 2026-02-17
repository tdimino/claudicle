# Soul Architecture Reference

On-demand reference for the Claudius soul engine internals. Loaded via `@agent_docs/soul-architecture.md` when working on soul-related features.

## Cognitive Pipeline

Every Slack response passes through structured cognitive steps:

```
soul_engine.build_prompt(text, user_id, channel, thread_ts)
  |
  +-- Load soul.md personality (first message only)
  +-- Load skills.md capabilities (first message only)
  +-- Load soul_memory state (always)
  +-- Load user_model (gated by Samantha-Dreams pattern)
  +-- Inject cognitive instructions (XML output format)
  +-- Fence user message as untrusted input

  --> Claude processes -->

soul_engine.parse_response(raw_response, user_id, channel, thread_ts)
  |
  +-- Extract <internal_monologue> --> store in working_memory
  +-- Extract <external_dialogue>  --> returned as the response
  +-- Extract <user_model_check>   --> boolean gate
  +-- Extract <user_model_update>  --> save if check=true
  +-- Extract <soul_state_check>   --> boolean gate (every Nth turn)
  +-- Extract <soul_state_update>  --> persist if check=true
```

## Three-Tier Memory

| Tier | Scope | TTL | Storage | Table |
|------|-------|-----|---------|-------|
| Working memory | Per-thread | 72h | `memory.db` | `working_memory` |
| User models | Per-user | Permanent | `memory.db` | `user_models` |
| Soul state | Global | Permanent | `memory.db` | `soul_memory` |

All tiers share a single SQLite database at `$CLAUDIUS_HOME/daemon/memory.db`.

### Samantha-Dreams Pattern

User model injection is gated: models are only loaded into the prompt when the prior turn's `<user_model_check>` returned true (meaning something new was learned). This prevents stale personality data from consuming context on every turn.

## Soul Registry

File-based JSON at `~/.claude/soul-sessions/registry.json`. Tracks:
- Active Claude Code sessions (ensouled or not)
- Slack channel bindings per session
- Current topic per session
- Session timestamps for lifecycle management

Companion file: `~/.claude/soul-sessions/SESSIONS.md` — human-readable session list injected into soul context.

## Key Files

| File | Purpose |
|------|---------|
| `daemon/soul_engine.py` | Cognitive step builder + response parser |
| `daemon/working_memory.py` | Per-thread metadata store |
| `daemon/user_models.py` | Per-user personality profiles |
| `daemon/soul_memory.py` | Global soul state |
| `daemon/session_store.py` | Thread-to-session mapping |
| `daemon/config.py` | All settings with env var overrides |
| `hooks/soul-registry.py` | Session registry management |
| `hooks/soul-activate.py` | SessionStart: inject soul + state |
| `soul/soul.md` | Default personality definition |

## Documentation

| Document | Description |
|----------|-------------|
| `docs/cognitive-pipeline.md` | Cognitive step deep-dive: prompt assembly, response parsing, verb system, gating logic |
| `docs/extending-claudius.md` | Developer guide: adding cognitive steps, memory tiers, subprocesses, adapters |
| `docs/soul-customization.md` | Soul identity customization: personality, emotional spectrum, templates |
| `docs/session-management.md` | Session lifecycle, soul registry, monitoring, troubleshooting |
| `docs/commands-reference.md` | `/ensoul`, `/slack-sync`, `/slack-respond`, `/thinker` reference |
| `docs/troubleshooting.md` | Comprehensive troubleshooting guide |
| `skills/open-souls-paradigm/SKILL.md` | Open Souls paradigm reference with 14 extension pattern files |
