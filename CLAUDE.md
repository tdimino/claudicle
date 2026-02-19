# Claudicle — Soul Agent Framework

Open-source soul agent for Claude Code. Turns any Claude Code session into a persistent personality with three-tier memory, a cognitive pipeline, and channel adapters for Slack, SMS, and terminal. Pairs with any skill repo.

## Stack
- Python 3.10+ (daemon, hooks, scripts, adapters)
- SQLite (three-tier memory: working, user models, soul state)
- Slack Bolt (Socket Mode for Slack integration)
- Claude Agent SDK (unified launcher mode)

## Structure
- `/daemon` — Core: context assembly, soul engine, cognitive pipeline, memory, monitor TUI
- `/soul` — Personality files (user-editable soul.md)
- `/hooks` — Claude Code lifecycle (SessionStart/End)
- `/commands` — Slash commands (/activate, /ensoul, /slack-sync, /slack-respond, /thinker, /watcher, /daimon)
- `/scripts` — Slack utility CLIs (post, read, search, react, upload)
- `/adapters` — Channel transports (SMS via Telnyx/Twilio, WhatsApp via Baileys)
- `/docs` — Architecture and reference documentation
- `/setups` — Ready-to-go configurations (personal, company)
- `/agent_docs` — Reference docs installed to ~/.claude/agent_docs/

## Commands
- Install: `./setup.sh --personal` or `./setup.sh --company`
- Daemon (bridge): `cd daemon && python3 slack_listen.py --bg`
- Daemon (unified): `cd daemon && python3 claudicle.py`
- Monitor TUI: `cd daemon && uv run python monitor.py`
- Test: `python3 -m pytest daemon/tests/ -v` (280 tests, <2.5s)
- Smoke test: `cd daemon && python3 -c "import soul_engine; print('OK')"`

## Conventions
- All paths use `CLAUDICLE_HOME` env var (default: `~/.claudicle`)
- Config in `daemon/config.py` uses `_env()` helper: reads `CLAUDICLE_` prefix, falls back to `SLACK_DAEMON_`
- Cognitive steps use XML tags: `<internal_monologue>`, `<external_dialogue>`, `<user_model_check>`, `<soul_state_check>`
- Step instructions defined in `soul_engine.STEP_INSTRUCTIONS` dict—single source of truth for unified and split modes
- Context assembly in `daemon/context.py`—shared between `soul_engine.build_prompt()` and `pipeline.run_pipeline()`
- Each cognitive cycle generates a trace_id (12-char hex) grouping all working_memory entries from that cycle
- Decision gates (skills injection, user model gate, dossier injection) logged as `entry_type="decision"` with trace_id
- Structured soul stream (`soul_log.py`) captures full cognitive cycle as JSONL—`tail -f $CLAUDICLE_HOME/soul-stream.jsonl`
- Soul personality lives in `soul/soul.md` — never hardcoded in daemon code
- Skills manifest (`daemon/skills.md`) is generated at install time by setup.sh, not shipped
- No credentials in code — all tokens via env vars or ~/.claude.json

## Principles
- Skill-agnostic: discover capabilities at install, don't bundle them
- Fork-able: clone, edit soul.md, run setup.sh — your own soul agent in minutes
- Local-first: all data on your machine, your API keys, your memory.db
- Three-tier memory: working (per-thread, 72h TTL), user models (permanent), soul state (permanent)
- Assumptions are the enemy. Benchmark, don't estimate.

## Key Architecture References
- `ARCHITECTURE.md` — Full system design, four-layer architecture, file map, totals
- `docs/slack-setup.md` — Slack app creation, scopes, Socket Mode, runtime mode selection
- `docs/session-bridge.md` — Session Bridge installation, inbox format, usage workflow
- `docs/unified-launcher-architecture.md` — Agent SDK integration, threading model, data flow
- `docs/extending-claudicle.md` — Adding cognitive steps, memory tiers, subprocesses, adapters
- `docs/cognitive-pipeline.md` — Cognitive step internals, prompt assembly, response parsing
- `docs/soul-stream.md` — Structured soul stream JSONL schema, phases, jq recipes, emit points
