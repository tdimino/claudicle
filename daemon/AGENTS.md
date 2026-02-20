# Claudicle Daemon

Core engine for the soul agent framework. Handles the cognitive pipeline, three-tier memory, provider routing, and channel adapter integration.

## Key Modules

- `soul_engine.py` -- `STEP_INSTRUCTIONS` dict (re-exported from `cognitive_steps`), `build_prompt()` (with onboarding interception), `parse_response()` (stimulus verb toggle + onboarding interception), `extract_tag()`
- `onboarding.py` -- First ensoulment mental process: `needs_onboarding()`, `get_stage()`, `build_instructions()`, `parse_response()` (4-stage interview state machine)
- `cognitive_steps/steps.py` -- CognitiveStep dataclass, STEP_INSTRUCTIONS/STEP_REGISTRY dicts, per-step model/provider overrides
- `context.py` -- Shared context assembly: soul.md, skills, user model gate (conditional injection based on interaction count), dossiers, decision logging
- `pipeline.py` -- Per-step cognitive routing orchestrator (split mode, per-provider models)
- `claude_handler.py` -- `process()` (subprocess via `claude -p`) + `async_process()` (Agent SDK `query()`)
- `working_memory.py` -- Per-thread SQLite store, 72h TTL, `trace_id` grouping, self-inspection queries
- `user_models.py` -- Per-user markdown profiles + entity dossiers, git-versioned export
- `soul_memory.py` -- Global soul state (`key: value` pairs, permanent)
- `session_store.py` -- Thread-to-session mapping (SQLite, 24h TTL)
- `config.py` -- `_env()` helper with `CLAUDICLE_`/`SLACK_DAEMON_` dual-prefix support. Feature toggles: `STIMULUS_VERB_ENABLED`, `ONBOARDING_ENABLED`, `DOSSIER_ENABLED`
- `skills/interview/` -- Core onboarding skill: stage prompts (`prompts.py`), skills catalog discovery (`catalog.py`)
- `providers/` -- Provider abstraction layer (6 providers + registry in `__init__.py`)

## Conventions

- `trace_id`: 12-char UUID4 hex prefix, generated in `build_prompt()` or `run_pipeline()`.
- `trace_id` threads through `context.build_context()` (logging decision gates) and `parse_response()` (logging cognitive outputs). All entries from one cycle share the same `trace_id`.
- XML parsing: regex-based extraction in `parse_response()` via `extract_tag()`. Fallback returns raw text if no tags found.
- 11 cognitive step tags: `stimulus_verb`, `internal_monologue`, `external_dialogue`, `user_model_check`, `user_model_reflection`, `user_model_update`, `user_whispers`, `dossier_check`, `dossier_update`, `soul_state_check`, `soul_state_update`. Dossier steps are unified-mode only; `pipeline.py` implements the other core/gate steps.
- `STIMULUS_VERB_ENABLED`: when `false`, the `stimulus_verb` step is excluded from prompt assembly and extraction is skipped. Working memory defaults to verb "said".
- `ONBOARDING_ENABLED`: when `true`, `build_prompt()` and `parse_response()` check `needs_onboarding(user_id)` before normal pipeline. Uses late-bound `_config.ONBOARDING_ENABLED` for monkeypatch compatibility.
- `onboardingComplete`: YAML frontmatter field in user models. Set to `false` when display_name is unknown or DEFAULT_USER_NAME ("Human"); `true` for known users (e.g. from Slack API).
- `onboardingStep`: working memory entry_type for completed onboarding stages. Metadata: `{"stage": int, ...}`.
- `role`: YAML frontmatter field in user models. `"primary"` for the soul's owner (matches `PRIMARY_USER_ID`), `"standard"` for all others. Set automatically by `ensure_exists()` or during onboarding stage 1.
- `PRIMARY_USER_ID`: config variable identifying the soul's owner. Defaults to `DEFAULT_SLACK_USER_ID`. Used by `ensure_exists()` for automatic role assignment.
- Provider abstraction: each provider implements `generate()` and `agenerate()`, registered via `providers/__init__.py`.
- Memory modules use module-level `threading.local()` for per-thread SQLite connections.
- `DB_PATH` is a module-level constant in each memory module -- tests monkeypatch it to `tmp_path` for isolation.
- `_trace_local` in `soul_engine.py` is thread-local state: `build_prompt()` generates and stashes the trace_id, `parse_response()` consumes it. Thread-safe via `threading.local()`.

## Cognitive Step Flow

1. `build_prompt()` generates `trace_id`, checks onboarding status (intercepts if `ONBOARDING_ENABLED` and user needs onboarding), delegates to `context.build_context()`, appends `STEP_INSTRUCTIONS`
2. Step 0 (`stimulus_verb`, toggleable via `STIMULUS_VERB_ENABLED`): narrates incoming message with a contextual verb
3. LLM returns XML-tagged response (all cognitive step tags)
4. `parse_response()` checks onboarding status (intercepts if needed), extracts tags via regex, stores each to `working_memory`, returns `external_dialogue`
5. Side effects: `stimulus_verb` -> `update_latest_verb()`, `user_model_update` -> `user_models.save()`, `dossier_update` -> `user_models.save_dossier()`, `soul_state_update` -> `soul_memory.set()`, `increment_interaction()`, `consume_all_whispers()`

## Test Patterns

- All tests import daemon modules directly (`pythonpath = ["daemon"]` in `pyproject.toml`).
- `MockProvider` (in `tests/helpers.py`): records `calls[]`, returns configurable response string.
- DB isolation: `conftest.py` monkeypatches `DB_PATH` to `tmp_path`, resets `threading.local()` per test.
- 6 autouse fixtures: DB isolation (+ trace_id reset), clean env (strips `CLAUDICLE_*`/`SLACK_DAEMON_*`/`WHATSAPP_*`/API keys), context cache reset (soul/skills caches + interaction counter), provider registry reset, onboarding disabled by default, daimonic isolation.
- Onboarding tests re-enable `ONBOARDING_ENABLED` via `monkeypatch.setattr(config, "ONBOARDING_ENABLED", True)`.
- Test XML parsing: build raw XML strings, pass to `parse_response()`, verify extracted content.
- Test memory: use `tmp_path` DB, verify CRUD operations, TTL cleanup, trace queries.
- `helpers.py` exports: `MockProvider`, `SAMPLE_SOUL_MD`, `SAMPLE_SKILLS_MD`, `make_inbox_entry()`, `write_inbox_entry()`.

## Boundaries

- Always: Run tests from project root (`python3 -m pytest daemon/tests/ -v`)
- Always: Register new providers in `providers/__init__.py`
- Ask: Before changing DB schema in any memory module
- Ask: Before modifying the `STEP_INSTRUCTIONS` dict or `_assemble_instructions()` logic
- Ask: Before modifying onboarding stages or interview prompts in `skills/interview/prompts.py`
- Never: Import from `tests/` in daemon source code
- Never: Hardcode API keys, Slack tokens, or credentials
- Never: Bypass `memory.db` Python modules with direct `sqlite3` writes
- Never: Use `pip install` directly -- use `uv pip install` or `uv add`
- Never: Use `from config import ONBOARDING_ENABLED` in soul_engine.py -- use `_config.ONBOARDING_ENABLED` (late-bound) for monkeypatch compatibility
