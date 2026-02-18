# Soul Architecture Reference

On-demand reference for the Claudius soul engine internals. Loaded via `@agent_docs/soul-architecture.md` when working on soul-related features.

## Cognitive Pipeline

Every response passes through structured cognitive steps. A trace_id (12-char UUID4 hex) groups all entries from a single cycle.

```
soul_engine.build_prompt(text, user_id, channel, thread_ts)
  |
  +-- [trace_id generated]
  +-- context.build_context()          <-- shared between unified + split modes
  |     +-- Load soul.md personality (first message only)
  |     +-- Load skills.md capabilities (first message only)
  |     +-- Load soul_memory state (always)
  |     +-- Load daimonic whispers (if active)
  |     +-- Load user_model (gated by Samantha-Dreams pattern)
  |     +-- [decision gates logged to working_memory with trace_id]
  |     +-- Fence user message as untrusted input
  +-- Append cognitive instructions (from STEP_INSTRUCTIONS dict)

  --> Claude processes -->

soul_engine.parse_response(raw_response, user_id, channel, thread_ts)
  |                                    <-- consumes same trace_id
  +-- Extract <internal_monologue> --> store in working_memory
  +-- Extract <external_dialogue>  --> returned as the response
  +-- Extract <user_model_check>   --> boolean gate
  +-- Extract <user_model_update>  --> save if check=true
  +-- Extract <dossier_check>      --> boolean gate (when DOSSIER_ENABLED)
  +-- Extract <dossier_update>     --> save dossier if check=true
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
| `daemon/context.py` | Shared context assembly (soul.md, skills, user model gate, dossiers, decision logging) |
| `daemon/soul_engine.py` | Cognitive step instructions (STEP_INSTRUCTIONS), prompt builder, XML response parser |
| `daemon/working_memory.py` | Per-thread metadata store (trace_id grouping, self-inspection queries) |
| `daemon/pipeline.py` | Split-mode per-step cognitive routing with per-provider models |
| `daemon/user_models.py` | Per-user personality profiles + dossiers |
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
