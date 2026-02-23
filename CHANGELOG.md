# Changelog

Claudicle follows [Semantic Versioning](https://semver.org/). Minor versions (`0.x.0`) mark feature additions; patch versions (`0.x.y`) mark fixes within a feature set.

---

## v0.10.1 — 2026-02-23 — Prompt Hardening

Review-driven improvements across all 7 sub-daimon prompts from 3 parallel review agents (2 prompt engineers + 1 doc reviewer).

- Demiurge: 30-call budget (was unbounded), removed scope escape hatch, concrete verify step
- Mnemon: formulated boot question, nil-case output template
- Phantasos: operational framing, structured output (Confidence/Energy/Voice), nil case
- Eikōn: ternary gate (exists? → new info?), explicit role differentiation from Phantasos
- Themistokles: removed soulSheds lineage (~80 tokens saved), structured Constitutional Integrity fields
- Scholiast: relative date filter instead of hardcoded value
- `docs/sub-daimones.md`: corrected tool lists, budgets, reflection steps, model ID, path prefixes

## v0.10.0 — 2026-02-23 — Sub-Daimones & Cognitive Rhythm

Seven cognitive sub-daimones with full prompt architecture, soul context injection, and dry-run testing infrastructure.

- `agents/` directory with 7 sub-daimon definitions (YAML frontmatter + structured protocols):
  - **Craft agents**: Anamnesis (memory retrieval), Scholiast (research), Demiurge (implementation)
  - **Cognitive agents**: Mnemon (reflection), Eikōn (user modeling), Phantasos (user-voice), Themistokles (constitutional review)
- `scripts/soul-context.py` — Sub-daimon boot injection (soul personality + state + user model to stdout)
- `scripts/test-reflect.py` — Dry-run reflection pipeline to `/tmp/` without touching production data
- `soul/soul.md` updated with "modeling the mind of" phrasing and Cognitive Rhythm section
- `docs/sub-daimones.md` — Full architecture doc: agent taxonomy, Open Souls precedents, Samantha-Dreams lineage, invocation patterns
- Themistokles inspired by `soulSheds` (Samantha-Dreams): proposes diffs to soul.md/CLAUDE.md when the soul evolves beyond its blueprint
- Eikōn expanded to assess any person model, not just the primary user
- Terminal reflection pipeline default model: Kimi-K2 on Groq

## v0.8.0 — 2026-02-20 — Session Naming & Claudicle Index

Slack-originated sessions are now auto-titled and tracked in Claudicle's own session index, giving the soul self-awareness over the sessions it creates.

- `session_title.py` (~130 LOC) — writes `customTitle` to Claude Code's `sessions-index.json` with `fcntl` file locking, propagates to `session-summaries.json`
- `memory/session_index.py` (~120 LOC) — Claudicle's own session index at `$CLAUDICLE_HOME/session-index.json` with thread-safe `register`/`touch`/`get`/`list_active`/`cleanup`
- `channel_name` threaded from Slack adapters through handler to session titling (both sync and async paths)
- Session titles formatted as `Slack: #channel-name—First 50 chars of message...`
- `display_name` added to `process()` signature—sync and async paths now symmetric
- `_get_thread_daimon_modes` extracted to `working_memory.get_thread_daimon_modes()` (single source of truth)
- Silent `except` blocks in `slack_adapter.py` replaced with logged warnings
- `new_session_id != session_id` guard prevents redundant title writes on resumed sessions
- 319 tests passing

## v0.7.0 — 2026-02-19 — First Ensoulment + Primary User Designation

The soul now conducts an automated 4-stage interview with unknown users and distinguishes its primary user (owner) from other participants.

- 4-stage onboarding: Greeting → Primary → Persona → Skills
- `role` field in user model frontmatter (`"primary"` / `"standard"`)
- `PRIMARY_USER_ID` config with auto-assignment via `ensure_exists()`
- `STIMULUS_VERB_ENABLED` toggle for verb narration
- `ONBOARDING_ENABLED` toggle for First Ensoulment
- Rewrote `docs/onboarding-guide.md` for the automated process
- 319 tests passing

Plan: [`plans/02-features/first-ensoulment-onboarding.md`](plans/02-features/first-ensoulment-onboarding.md)

## v0.6.0 — 2026-02-19 — Multi-Speaker Awareness

Claudicle now tracks who said what in multi-user threads.

- `display_name` column in working memory (per-speaker attribution)
- YAML frontmatter in user model template (`userName`, `userId`, `onboardingComplete`)
- Multi-speaker user model injection in context assembly
- `parse_frontmatter()` and `get_user_name()` in user_models
- `DEFAULT_USER_NAME` / `DEFAULT_USER_ID` config

Notable: `30038b5` feat: configurable SOUL_NAME, cuticle backstory doc

Plan: [`plans/02-features/multi-speaker-awareness.md`](plans/02-features/multi-speaker-awareness.md)

## v0.5.0 — 2026-02-18 — Rename: Claudius → Claudicle

The project was renamed from **Claudius** to **Claudicle** (Claude + cuticle)—the body that forms around a soul.

- All internal references updated (env vars, files, docs, code)
- Env var prefix: `CLAUDIUS_*` → `CLAUDICLE_*`

Notable: `7de29e9` rename: Claudius → Claudicle

## v0.4.0 — 2026-02-18 — Three-Log Observability + Context Extraction

Major architectural refactor: extracted shared context assembly, added trace threading, built the structured soul stream.

- `context.py` (234 LOC) — shared context assembly, eliminates unified/split duplication
- `soul_log.py` (114 LOC) — `tail -f`-able JSONL stream with 7 cognitive phases
- `trace_id` system (12-char UUID4 hex) grouping all entries per cognitive cycle
- Decision gates logged with trace correlation
- `STEP_INSTRUCTIONS` dict — single source of truth for cognitive step prompts
- `CognitiveStep` dataclass with per-step model/provider overrides
- `AGENTS.md` — daemon module conventions document

Notable: `203332f` feat: extract context.py, add trace_id system · `1f5cba4` feat: structured soul stream

Plans: [`plans/01-architecture/modular-extraction-structured-logging.md`](plans/01-architecture/modular-extraction-structured-logging.md) · [`plans/01-architecture/soul-stream-three-log.md`](plans/01-architecture/soul-stream-three-log.md)

## v0.3.1 — 2026-02-18 — Security Hardening

- Fixed command injection vulnerability in `claude -p` subprocess invocation
- Fixed silent failures in XML parsing fallback paths
- Hardened regex patterns against fragile extraction

Notable: `83a5918` fix: command injection, silent failures, and regex fragility

## v0.3.0 — 2026-02-18 — Living User Models + Autonomous Dossiers

Replaced static user profiles with the Samantha-Dreams pattern and added autonomous entity dossier creation.

- User model injection gated by prior `user_model_check` result
- 7-section living blueprint (Persona → Most Potent Memories)
- Git-versioned memory export to `$CLAUDICLE_HOME/memory/`
- Autonomous dossier creation for people and subjects encountered
- RAG tags for cross-referencing entities

Notable: `0073644` feat: living user models · `9fccded` feat: autonomous entity dossiers

## v0.2.0 — 2026-02-18 — Multi-Daimon System

Expanded daimonic intercession from a single daimon to a registry of multiple external souls.

- Artifex added as second daimon alongside Kothar
- Speak mode for full daimon responses (not just whispers)
- Inter-soul conversation orchestrator
- Custom Slack avatars per daimon

Notable: `af42bf8` feat: multi-daimon system with Artifex, speak mode, avatars

## v0.1.0 — 2026-02-17 — Foundation

Initial release as "Claudius." Soul engine, cognitive pipeline, three-tier memory, five runtime modes, channel adapters.

- Soul engine with XML-tagged cognitive pipeline
- Three-tier memory: working (72h TTL), user models (permanent), soul state (permanent)
- Five runtime modes: `/ensoul`, Session Bridge, Unified Launcher, Legacy Daemon, Inbox Watcher
- Slack integration (Socket Mode, 14 utility scripts), SMS adapters (Telnyx/Twilio)
- WhatsApp adapter via Baileys
- Daimonic intercession (Kothar, HTTP + Groq transports)
- 176-test foundation suite
- 7 slash commands, 4 hooks, Soul Monitor TUI

Notable: `bd63fa5` Initial commit · `ec5814b` WhatsApp adapter · `a2aef87` test suite (176 tests) · `6a82b35` daimonic intercession · `b641924` dossier templates
