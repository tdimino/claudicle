# Claudicle — Soul Agent Framework

Open-source soul agent for Claude Code. Turns any Claude Code session into a persistent personality with three-tier memory, a cognitive pipeline, and channel adapters for Slack, SMS, and terminal. Pairs with any skill repo.

## Stack
- Python 3.10+ (daemon, hooks, scripts, adapters)
- SQLite (three-tier memory: working, user models, soul state)
- Slack Bolt (Socket Mode for Slack integration)
- Claude Agent SDK (unified launcher mode)

## Structure
- `/agents` — Sub-daimon definitions: 7 cognitive agents (3 craft + 4 cognitive) with YAML frontmatter and structured protocols
- `/daemon` — Core: context assembly, soul engine, cognitive pipeline, memory, monitoring, monitor TUI
- `/daemon/cognitive_steps` — Cognitive step definitions (CognitiveStep dataclass, STEP_INSTRUCTIONS registry)
- `/daemon/engine/onboarding.py` — First ensoulment mental process (4-stage interview state machine)
- `/daemon/engine/reflect.py` — Retrospective cognitive pipeline for terminal sessions (channel-agnostic reflection)
- `/daemon/skills/interview` — Core skill: onboarding interview prompts and skills catalog discovery
- `/soul` — Personality files (soul.md default, `profiles/` for named souls, `active` symlink for switching)
- `/hooks` — Claude Code lifecycle (SessionStart/End)
- `/commands` — Slash commands (/activate, /ensoul, /switch-soul, /slack-sync, /slack-respond, /thinker, /watcher, /daimon)
- `/scripts` — Slack utility CLIs + soul infrastructure (`soul-context.py`, `soul-profiles.py`, `test-reflect.py`)
- `/adapters` — Channel transports (SMS via Telnyx/Twilio, WhatsApp via Baileys)
- `/docs` — Architecture and reference documentation (includes `sub-daimones.md`)
- `/setups` — Ready-to-go configurations (personal, company)
- `/agent_docs` — Reference docs installed to ~/.claude/agent_docs/

## Commands
- Install: `./setup.sh --personal` or `./setup.sh --company`
- Daemon (bridge): `cd daemon && python3 slack_listen.py --bg`
- Daemon (unified): `cd daemon && python3 claudicle.py`
- Monitor TUI: `cd daemon && uv run python monitor.py`
- Test: `python3 -m pytest daemon/tests/ -v` (383 tests, <5s)
- Smoke test: `cd daemon && python3 -c "import soul_engine; print('OK')"`

## Conventions
- All paths use `CLAUDICLE_HOME` env var (default: `~/.claudicle`)
- Config in `daemon/config.py` uses `_env()` helper: reads `CLAUDICLE_` prefix, falls back to `SLACK_DAEMON_`
- Cognitive steps use XML tags: `<stimulus_verb>`, `<internal_monologue>`, `<external_dialogue>`, `<user_model_check>`, `<soul_state_check>`
- Stimulus verb narration (`<stimulus_verb>`) is toggleable via `STIMULUS_VERB_ENABLED`; defaults to "said" when disabled
- First ensoulment: 4-stage onboarding interview for new users (toggleable via `ONBOARDING_ENABLED`), state tracked in user model frontmatter (`onboardingComplete`, `role`) + working memory (`onboardingStep`). Primary user designation via `PRIMARY_USER_ID` config (auto-assigned by `ensure_exists()` or onboarding stage 1)
- Step instructions defined in `cognitive_steps/steps.py` (CognitiveStep dataclass), re-exported as `STEP_INSTRUCTIONS` dict—single source of truth for unified and split modes
- Context assembly in `daemon/context.py`—shared between `soul_engine.build_prompt()`, `pipeline.run_pipeline()`, and `reflect.build_reflection_prompt()`
- Working memory entry types: `userMessage`, `internalMonologue`, `externalDialog`, `mentalQuery`, `toolAction`, `decision`, `daimonicIntuition`, `onboardingStep`
- Each cognitive cycle generates a trace_id (12-char hex) grouping all working_memory entries from that cycle
- Decision gates (skills injection, user model gate, dossier injection) logged as `entry_type="decision"` with trace_id
- Structured soul stream (`soul_log.py`) captures full cognitive cycle as JSONL—`tail -f $CLAUDICLE_HOME/soul-stream.jsonl`
- Working memory stream (`wm_stream.py`) mirrors every `working_memory.add()` call—`tail -f $CLAUDICLE_HOME/working-memory-stream.jsonl`
- Channel IDs: Slack uses channel IDs (e.g. `C04ABC123`), terminal uses `terminal:{session_id}`, SMS uses `sms:{phone}`
- Terminal reflection: Stop hook (`hooks/soul-reflect.py`, shipped in-repo) runs cognitive pipeline retrospectively via `engine/reflect.py` → writes to shared `working_memory.db` with `terminal:` channel prefix. Provider-agnostic: `REFLECT_PROVIDER` supports `groq` (default), `openrouter`, or any OpenAI-compatible URL. Default model: Kimi-K2 on Groq. Config: `TERMINAL_REFLECT_ENABLED`, `REFLECT_PROVIDER`, `REFLECT_MODEL`, `REFLECT_COOLDOWN`
- Soul personality resolves via `engine/soul_path.py`: `CLAUDICLE_SOUL_PROFILE` env var → `soul/active` symlink → `soul/soul.md` fallback. Never hardcoded in daemon code
- Multi-soul: `soul_memory` is scoped by `soul_id` column (defaults to `config.SOUL_NAME.lower()`). Each profile has independent state
- Soul shedding: `memory/soul_journal.py` tracks soul.md evolution as git history in `soul/`. Themistokles proposes, main session applies via Edit tool
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
- `docs/sub-daimones.md` — Sub-daimon architecture: 7 agents, precedents (Open Souls, Samantha-Dreams), invocation, dry-run testing
- `docs/slack-setup.md` — Slack app creation, scopes, Socket Mode, runtime mode selection
- `docs/session-bridge.md` — Session Bridge installation, inbox format, usage workflow
- `docs/unified-launcher-architecture.md` — Agent SDK integration, threading model, data flow
- `docs/extending-claudicle.md` — Adding cognitive steps, memory tiers, subprocesses, adapters
- `docs/cognitive-pipeline.md` — Cognitive step internals, prompt assembly, response parsing
- `docs/soul-stream.md` — Structured soul stream JSONL schema, phases, jq recipes, emit points
