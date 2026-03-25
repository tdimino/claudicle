# Claudicle — Soul Agent Framework

Open-source soul agent for Claude Code. Turns any Claude Code session into a persistent personality with three-tier memory, a cognitive pipeline, and channel adapters for Slack, SMS, and terminal. Pairs with any skill repo.

## Stack
- Python 3.10+ (daemon, hooks, scripts, adapters)
- SQLite (three-tier memory: working, user models, soul state)
- Slack Bolt (Socket Mode for Slack integration)
- Claude Agent SDK (unified launcher mode)

## Structure
- `/subdaimones` — Sub-daimon definitions: 12 across 3 tiers (2 meta + 5 cognitive + 5 craft) with YAML frontmatter and structured protocols
- `/daimones` — Privy council: example daimon and Kothar (9 mental processes, Open Souls paradigm). User daimones live externally (e.g. `~/daimones/`)
- `/daemon` — Core: context assembly, soul engine, cognitive pipeline, memory, monitoring, monitor TUI, daemon lifecycle
- `/daemon/lifecycle.py` — Daemon lifecycle primitives: PID file (atomic write via tempfile+rename), liveness detection (`os.kill` + start_time), version handshake, `fcntl.flock` startup lock, `ensure_daemon()` fire-and-forget auto-start, `stop_daemon()` with SIGTERM→SIGKILL escalation
- `/daemon/VERSION` — Semantic version string (e.g. `0.15.0`), read by lifecycle.py, written by setup.sh
- `/daemon/cognitive_steps` — Cognitive step definitions (CognitiveStep dataclass, STEP_INSTRUCTIONS registry)
- `/daemon/daimonic/summoning.py` — Daimon summoning: awaken any entity (user model, dossier) as an ephemeral speaking daimon via Groq. `summon_entity()`/`dismiss_entity()`/`list_summoned()` API, cache trick (soul.md in memory, no filesystem writes)
- `/daemon/daimonic/whispers.py` — Daimonic intercession (external soul whispers into cognitive pipeline)
- `/daemon/processes` — Emotional state process handlers: `main_process.py` (default), `focused_process.py`, `frustrated_process.py`, `_shared.py` (shared prompt fragments)
- `/daemon/providers` — LLM provider implementations: `claude_cli.py`, `claude_sdk.py`, `anthropic_api.py`, `groq_provider.py`, `ollama_provider.py`, `openai_compat.py`
- `/daemon/monitoring` — Soul Monitor TUI (`monitor.py`), SQLite watcher (`watcher.py`), soul stream JSONL (`soul_log.py`), working memory stream (`wm_stream.py`)
- `/daemon/engine/onboarding.py` — First ensoulment mental process (4-stage interview state machine)
- `/daemon/engine/reflect.py` — Retrospective cognitive pipeline for terminal sessions (channel-agnostic reflection)
- `/daemon/engine/helpers.py` — Shared helpers: `extract_tag`, `strip_all_tags`, `store_and_emit` (extracted from soul_engine)
- `/daemon/engine/llm_client.py` — Shared LLM caller for reflection/compression (provider routing, API key resolution)
- `/daemon/engine/soul_engine.py` — Core soul engine: prompt building, cognitive cycle execution
- `/daemon/engine/pipeline.py` — Cognitive pipeline runner (multi-step XML-tagged processing)
- `/daemon/engine/context.py` — Context assembly shared across soul engine, pipeline, and reflection
- `/daemon/engine/perception.py` — Perception intake and routing for unified launcher
- `/daemon/engine/process_base.py` — Base class for mental processes (Open Souls paradigm)
- `/daemon/engine/process_router.py` — Intent classification and mental process routing
- `/daemon/engine/soul_path.py` — Soul personality file resolution (env var → symlink → fallback)
- `/daemon/engine/compaction.py` — Context compaction for long-running sessions
- `/daemon/memory/compression.py` — Hypermnesia memory compression (heuristic/LLM, delegates to working_memory public APIs)
- `/daemon/memory/soul_state.py` — Unified soul state: topic stack (1 primary + 7 subtopics, FIFO cascade), emotional state transitions, timestamped audit log, narrative `soulStateShift` entries to working memory, `format_for_prompt()` with relative times and artifact references
- `/daemon/memory/snapshot.py` — Immutable data types (`MemoryEntry`, `WorkingMemorySnapshot`, `CognitiveOutput`), copy-on-write `with_*` methods, `load_snapshot()`/`apply_output()` boundary (routes soul state updates through `soul_state.set_state_key()`)
- `/daemon/memory/checkpoint.py` — Point-in-time bookmarks for working memory rollback (frozen `Checkpoint` dataclass, `wm_checkpoints` table)
- `/daemon/memory/daimon_memory.py` — Subdaimon persistent memory (context creation, load/store, lessons, communication logging, boot formatting)
- `/daemon/memory/daimon_output_parser.py` — Parse `## Memory Updates` markdown from subdaimon output into `CognitiveOutput` (pure `parse_output()` + deprecated `parse_and_store()` wrapper)
- `/daemon/memory/frontmatter.py` — Pure parsing for YAML frontmatter, `[[wiki links]]`, and `RAG:` tags. Single source of truth replacing duplicate parsers in user_models.py and usermodel_resolver.py
- `/daemon/memory/entity_graph.py` — Frozen entity graph for Obsidian-inspired entity awareness. Multi-signal relevance scoring (name/alias/tags/RAG keywords/backlink boost) replaces substring matching in `get_relevant_dossiers()`. Indexes dossiers AND user models; cached per-process, invalidated on writes
- `/daemon/memory/model_journal.py` — Model/dossier shedding archaeology: `model_sheds` SQLite table, `ShedRecord` dataclass, structured diffs, optional meta commentary. Hooked into `user_models.save()`/`save_dossier()` for automatic shed capture
- `/daemon/memory/db.py` — Thread-safe `ConnectionPool` with migration locking (shared by all memory modules)
- `/daemon/memory/process_memory.py` — Per-subprocess persistent state (soul_memory-backed, namespaced keys, maps to Open Souls useProcessMemory)
- `/daemon/memory/working_memory.py` — Core working memory: add, query, cleanup, regions, region operations
- `/daemon/memory/user_models.py` — User model CRUD, primary user designation, interaction tracking
- `/daemon/memory/soul_memory.py` — Key-value soul memory (persistent cross-session state)
- `/daemon/memory/soul_journal.py` — Soul shedding git history (two-commit ceremony)
- `/daemon/memory/git_tracker.py` — Best-effort git operations for soul journal (non-blocking, 10s timeout)
- `/daemon/memory/session_index.py` — Session index for cross-session discovery
- `/daemon/memory/session_store.py` — Session persistence (SQLite-backed, sessions.db)
- `/daemon/skills/interview` — Core skill: onboarding interview prompts and skills catalog discovery
- `/soul` — Personality files (soul.md default, `profiles/` for named souls, `active` symlink for switching)
- `/hooks` — Claude Code lifecycle (SessionStart/End), permission gating (smart-auto-approve), visual dev loop (auto-screenshot), session handoff (`claudicle-handoff.py`), soul registry (`soul-registry.py`, `soul-deregister.py`), daemon auto-start (`soul-activate.py` calls `lifecycle.ensure_daemon()` on SessionStart)
- `/config` — Versioned configuration: `auto-approve-whitelist.template.json` (permission deny/allow patterns for daemon-spawned sessions)
- `/commands` — 9 slash commands: /activate, /ensoul, /switch-soul, /slack-sync, /slack-respond, /thinker, /watcher, /daimon
- `/scripts` — Slack utility CLIs, soul infrastructure (`soul-context.py`, `soul-profiles.py`, `test-reflect.py`), working memory management (`wm-manage.py`), maintenance (`claudicle-gc.py`), activation sequence (`activate_sequence.py`), situational awareness (`situational_awareness.py`), sandbox scenarios (`sandbox_scenarios.py`)
- `/adapters` — Channel transports (Discord via discord.py, Telegram via python-telegram-bot, SMS via Telnyx/Twilio, WhatsApp via Baileys)
- `/adapters/sms/sms_respond.py` — SMS daemon with message debouncing (10s quiet / 60s max wait), URL classification, batch processing, and `store_decisions` noise suppression for bare-URL batches
- `/adapters/shared/claudicle_memory.py` — Soul-aware memory routing: working memory, user models, soul state, and selective `prune_working_memory()` for maintenance
- `/adapters/shared/usermodel_resolver.py` — Phone/email/Slack ID → user model resolution with cached indexes
- `/daemon/adapters/terminal_ui.py` — Terminal stdin/stdout adapter for unified launcher
- `/daemon/adapters/inbox_watcher.py` — Always-on inbox.jsonl watcher for async channel processing
- `/daemon/adapters/slack_log.py` — Structured JSONL logging for Slack events
- `/docs` — Architecture and reference documentation (includes `sub-daimones.md`)
- `/setups` — Ready-to-go configurations (personal, company)
- `/agent_docs` — Reference docs installed to ~/.claude/agent_docs/

## Commands
- Install: `./setup.sh --personal` or `./setup.sh --company`
- Daemon (bridge): `cd daemon && python3 slack_listen.py --bg`
- Daemon (unified): `cd daemon && python3 claudicle.py`
- Daemon (background): `cd daemon && python3 claudicle.py --daemon` (detached, writes PID file, fast exit on shutdown)
- Monitor TUI: `cd daemon && uv run python monitoring/monitor.py`
- Test: `python3 -m pytest daemon/tests/ -v` (954 tests, <36s)
- WM manage: `uv run scripts/wm-manage.py {query|stats|checkpoint|rollback|delete|export} [options]`
- Smoke test: `cd daemon && python3 -c "import soul_engine; print('OK')"`
- Sandbox: `uv run scripts/sandbox.py --message "Hello" [--scenario NAME] [--repl] [--provider groq] [--keep] [--soul PATH] [--daimonic]`
- GC: `python3 scripts/claudicle-gc.py status|gc|wipe [--age DAYS] [--dry-run] [--keep-models]`

## Conventions
- All paths use `CLAUDICLE_HOME` env var (default: `~/.claudicle`)
- Config in `daemon/config.py`: Pydantic `BaseSettings` with `LegacyPrefixedEnvSource` for dual-prefix env vars (`CLAUDICLE_` first, `SLACK_DAEMON_` fallback). Module globals re-exported via `globals().update(settings.model_dump())`
- Two-tier config: global settings (soul personality, provider list, `SOUL_NAME`, `SOUL_PROFILE`) baked at startup—require daemon restart. Per-operation settings (compression thresholds, watcher params) read fresh per-request. `settings.global_config_hash` (8-char SHA-256) detects staleness
- Daemon lifecycle config: `DAEMON_AUTO_START` (toggle hook auto-start), `DAEMON_HEALTH_TIMEOUT` (seconds for /api/health check)
- Compression config in `daemon/config.py`: `COMPRESSION_ENABLED`, `COMPRESSION_THRESHOLD`, `COMPRESSION_KEEP_RECENT`, `COMPRESSION_REFLECT_INTERVAL`, `COMPRESSION_USE_LLM`, `COMPRESSION_PROVIDER`, `COMPRESSION_MODEL`, `COMPRESSION_ARCHIVE`, `WORKING_MEMORY_PROMPT_INJECT`, `WORKING_MEMORY_WINDOW`
- Cognitive steps use XML tags: `<stimulus_verb>`, `<internal_monologue>`, `<external_dialogue>`, `<user_model_check>`, `<soul_state_check>`
- Stimulus verb narration (`<stimulus_verb>`) is toggleable via `STIMULUS_VERB_ENABLED`; defaults to "said" when disabled
- First ensoulment: 4-stage onboarding interview for new users (toggleable via `ONBOARDING_ENABLED`), state tracked in user model frontmatter (`onboardingComplete`, `role`) + working memory (`onboardingStep`). Primary user designation via `PRIMARY_USER_ID` config (auto-assigned by `ensure_exists()` or onboarding stage 1)
- Step instructions defined in `cognitive_steps/steps.py` (CognitiveStep dataclass), re-exported as `STEP_INSTRUCTIONS` dict—single source of truth for unified and split modes
- Context assembly in `daemon/engine/context.py`—shared between `soul_engine.build_prompt()`, `pipeline.run_pipeline()`, and `reflect.build_reflection_prompt()`
- Working memory entry types: `userMessage`, `internalMonologue`, `externalDialog`, `mentalQuery`, `toolAction`, `decision`, `daimonicIntuition`, `onboardingStep`, `memorySummary`, `soulStateShift`, `lifecycle`, `modelShed`
- Each cognitive cycle generates a trace_id (12-char hex) grouping all working_memory entries from that cycle
- Decision gates (skills injection, user model gate, dossier injection) logged as `entry_type="decision"` with trace_id
- Structured soul stream (`soul_log.py`) captures full cognitive cycle as JSONL—`tail -f $CLAUDICLE_HOME/soul-stream.jsonl`
- Working memory stream (`wm_stream.py`) mirrors every `working_memory.add()` call + lifecycle events (checkpoint, rollback, delete)—`tail -f $CLAUDICLE_HOME/working-memory-stream.jsonl`
- Channel IDs: Slack uses channel IDs (e.g. `C04ABC123`), Discord uses `discord:{channel_id}`, Telegram uses `telegram:{chat_id}`, terminal uses `terminal:{session_id}`, SMS uses `sms:{phone}`, WhatsApp uses `whatsapp:{phone}`, subdaimones use `daimon:{agent_name}`
- Terminal reflection: Stop hook (`hooks/soul-reflect.py`, shipped in-repo) runs cognitive pipeline retrospectively via `engine/reflect.py` → writes to shared `working_memory.db` with `terminal:` channel prefix. Provider-agnostic: `REFLECT_PROVIDER` supports `groq` (default), `openrouter`, or any OpenAI-compatible URL. Default model: Kimi-K2 on Groq. Config: `TERMINAL_REFLECT_ENABLED`, `REFLECT_PROVIDER`, `REFLECT_MODEL`, `REFLECT_COOLDOWN`
- Reflection subprocesses (`engine/reflect.py`): `modelsTheUser`, `updatesState`, `compressesMemory` (Hypermnesia inline memory compression)
- Soul personality resolves via `engine/soul_path.py`: `CLAUDICLE_SOUL_PROFILE` env var → `soul/active` symlink → `soul/soul.md` fallback. Never hardcoded in daemon code
- Multi-soul: `soul_memory` and `soul_state` are scoped by `soul_id` column (defaults to `config.SOUL_NAME.lower()`). Each profile has independent state
- Unified soul state: `soul_state.py` is the single source of truth for emotional state, topic stack, and state transitions across all channels. `apply_output()` routes through `soul_state.set_state_key()` which logs transitions and writes narrative `soulStateShift` entries to working memory
- Soul shedding: `memory/soul_journal.py` tracks soul.md evolution as git history in `soul/`. Themistokles proposes, main session applies via Edit tool
- Skills manifest (`daemon/skills.md`) is generated at install time by setup.sh, not shipped
- Cognitive output uses frozen `CognitiveOutput` dataclass with copy-on-write `with_*` methods via `dataclasses.replace()`. Side effects collected immutably, committed atomically via `apply_output()` at the pipeline boundary
- Frontmatter parsing uses `memory.frontmatter` (single source of truth)—supports flat `key: value` and one-level nesting (`tags:\n  concepts: [minoan]`). Never duplicate the parser
- Entity graph (`memory.entity_graph`) indexes all dossiers AND user models with multi-signal scoring. Call `invalidate_graph()` after any write to `user_models` table
- Invisible daemon: auto-starts from `soul-activate.py` SessionStart hook via `lifecycle.ensure_daemon()` (fire-and-forget, background subprocess). PID file at `$CLAUDICLE_HOME/claudicle.pid` (3 lines: pid, version, start_time_iso). Startup lock via `fcntl.flock` prevents concurrent hooks from spawning multiple daemons. Version handshake on `/api/health` detects stale daemons after upgrade—mismatch triggers stop + restart
- Daemon shutdown uses resource-closure pattern (CocoIndex): close orchestrator listener → drain queue (5s) → stop watchers → stop adapters → close SQLite pools → remove PID file → `os._exit(0)`. PID file removal is the completion signal—clients poll for its absence, not `os.kill(pid, 0)`
- No credentials in code — all tokens via env vars or ~/.claude.json

## Principles
- Skill-agnostic: discover capabilities at install, don't bundle them
- Fork-able: clone, edit soul.md, run setup.sh — your own soul agent in minutes
- Local-first: all data on your machine, your API keys, your memory.db
- Three-tier memory: working (per-thread, 72h TTL; subdaimon channels exempt, 30-day TTL via `DAIMON_MEMORY_TTL_HOURS`), user models (permanent), soul state (permanent)
- Assumptions are the enemy. Benchmark, don't estimate.

## Orchestrator API

Kothar (or any daimon) can autonomously spawn Claude Code sessions via the orchestrator HTTP gateway (`daemon/orchestrator.py`). Registered via portless as `claudicle-api`.

**Endpoints:**
- `POST /api/orchestrate` — spawn a Claude Code session with `bypassPermissions`. Body: `{"task": "...", "cwd": "...", "soul_enabled": false}`
- `POST /api/perception` — inject a perception into the Claudicle message queue. Body: `{"action": "orchestrate", "content": {"task": "..."}}`
- `GET /api/health` — liveness + version handshake. Returns `{"status": "ok", "version": "0.15.0", "config_hash": "a1b2c3d4", "uptime_seconds": 3421, "watchers": {}}`

**Auth:** Bearer token via `CLAUDICLE_API_TOKEN` env var. Required on `/api/orchestrate` and `/api/perception`. Set in `~/.config/env/secrets.env`.

**Permission model:** Daemon-spawned sessions use `bypassPermissions` but are gated by `smart-auto-approve.py` which loads deny/allow patterns from `config/auto-approve-whitelist.template.json`. 12 deny categories block destructive commands even in headless mode.

## Kothar Mental Processes

Kothar's soul engine uses the Open Souls paradigm (TypeScript, `daimones/kothar/mentalProcesses/`):

| Process | Trigger | Role |
|---------|---------|------|
| `initialProcess` | Every perception | Intent classifier + router |
| `craftsman` | `code_assistance` | Architect/builder split — Kothar reasons, Opus implements via orchestrator API |
| `scholar` | `research_query` | Academic research + source synthesis |
| `guardian` | `system_operation` | Hardware health monitoring |
| `orchestrator` | `orchestrate` perception | Multi-step delegation with work-shape reasoning |
| `herald` | `social_post` | Social media composition |
| `outraged` | `moral_offense` | Ethical boundary response |
| `surrealistDream` | `dreamTime` (midnight-8am) | Creative dreaming |
| `dreamReflection` | Post-dream | Dream interpretation |

**Orchestrator work-shape reasoning:** Instead of naming skills, Kothar reasons about *phases* (research → design → implement → verify) and *delegation modes* (sequential, plan-first, parallel-swarm). Spawned sessions pick their own tools.

**Direct-handling gate:** Simple tasks route directly to `craftsman`/`scholar`/`guardian` without delegation overhead.

## Key Architecture References
- `ARCHITECTURE.md` — Full system design, four-layer architecture, file map, totals
- `docs/sub-daimones.md` — Sub-daimon architecture: 12 agents (3-tier taxonomy), precedents (Open Souls, Samantha-Dreams), invocation, dry-run testing
- `docs/daimones.md` — The privy council: four sources, strategos pattern, anatomy, evolution
- `agent_docs/claudicle-daimones.md` — On-demand daimones quick reference
- `docs/slack-setup.md` — Slack app creation, scopes, Socket Mode, runtime mode selection
- `docs/session-bridge.md` — Session Bridge installation, inbox format, usage workflow
- `docs/unified-launcher-architecture.md` — Agent SDK integration, threading model, data flow
- `docs/extending-claudicle.md` — Adding cognitive steps, memory tiers, subprocesses, adapters
- `docs/cognitive-pipeline.md` — Cognitive step internals, prompt assembly, response parsing
- `docs/soul-stream.md` — Structured soul stream JSONL schema, phases, jq recipes, emit points
- `docs/channel-adapters.md` — Channel adapter pattern, integration points, shared inbox format
- `docs/sms-setup.md` — SMS setup: Telnyx + Twilio, webhooks, message batching
- `docs/telegram-setup.md` — Telegram setup: BotFather, polling mode, daimon identity
- `docs/discord-setup.md` — Discord setup: Developer Portal, Message Content Intent, webhooks
- `docs/whatsapp-setup.md` — WhatsApp setup: Baileys gateway, QR pairing, security
- `docs/channel-comparison.md` — Side-by-side channel feature matrix
- `config/INDEX.md` — Permission whitelist/denylist documentation (12 deny categories, review cadence)
- `config/auto-approve-whitelist.template.json` — Template for `~/.claude/config/auto-approve-whitelist.json`
