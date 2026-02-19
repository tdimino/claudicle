# Claudicle Daemon

Core engine for the soul agent framework. Handles the cognitive pipeline, three-tier memory, provider routing, and channel adapter integration.

## Key Modules

- `soul_engine.py` -- `STEP_INSTRUCTIONS` dict (cognitive step prompts), `build_prompt()`, `parse_response()`, `extract_tag()`
- `context.py` -- Shared context assembly: soul.md, skills, user model gate (conditional injection based on interaction count), dossiers, decision logging
- `pipeline.py` -- Per-step cognitive routing orchestrator (split mode, per-provider models)
- `claude_handler.py` -- `process()` (subprocess via `claude -p`) + `async_process()` (Agent SDK `query()`)
- `working_memory.py` -- Per-thread SQLite store, 72h TTL, `trace_id` grouping, self-inspection queries
- `user_models.py` -- Per-user markdown profiles + entity dossiers, git-versioned export
- `soul_memory.py` -- Global soul state (`key: value` pairs, permanent)
- `session_store.py` -- Thread-to-session mapping (SQLite, 24h TTL)
- `config.py` -- `_env()` helper with `CLAUDICLE_`/`SLACK_DAEMON_` dual-prefix support
- `providers/` -- Provider abstraction layer (6 providers + registry in `__init__.py`)

## Conventions

- `trace_id`: 12-char UUID4 hex prefix, generated in `build_prompt()` or `run_pipeline()`.
- `trace_id` threads through `context.build_context()` (logging decision gates) and `parse_response()` (logging cognitive outputs). All entries from one cycle share the same `trace_id`.
- XML parsing: regex-based extraction in `parse_response()` via `extract_tag()`. Fallback returns raw text if no tags found.
- 8 cognitive step tags: `internal_monologue`, `external_dialogue`, `user_model_check`, `user_model_update`, `dossier_check`, `dossier_update`, `soul_state_check`, `soul_state_update`. Dossier steps (4b/4c) are unified-mode only; `pipeline.py` implements the other 6.
- Provider abstraction: each provider implements `generate()` and `agenerate()`, registered via `providers/__init__.py`.
- Memory modules use module-level `threading.local()` for per-thread SQLite connections.
- `DB_PATH` is a module-level constant in each memory module -- tests monkeypatch it to `tmp_path` for isolation.
- `_trace_local` in `soul_engine.py` is thread-local state: `build_prompt()` generates and stashes the trace_id, `parse_response()` consumes it. Thread-safe via `threading.local()`.

## Cognitive Step Flow

1. `build_prompt()` generates `trace_id`, delegates to `context.build_context()`, appends `STEP_INSTRUCTIONS`
2. LLM returns XML-tagged response (all 8 tags listed above)
3. `parse_response()` extracts tags via regex, stores each to `working_memory`, returns `external_dialogue`
4. Side effects: `user_model_update` -> `user_models.save()`, `dossier_update` -> `user_models.save_dossier()`, `soul_state_update` -> `soul_memory.set()`, `increment_interaction()`, `consume_all_whispers()`

## Test Patterns

- All tests import daemon modules directly (`pythonpath = ["daemon"]` in `pyproject.toml`).
- `MockProvider` (in `tests/helpers.py`): records `calls[]`, returns configurable response string.
- DB isolation: `conftest.py` monkeypatches `DB_PATH` to `tmp_path`, resets `threading.local()` per test.
- 5 autouse fixtures: DB isolation (+ trace_id reset), clean env (strips `CLAUDICLE_*`/`SLACK_DAEMON_*`/`WHATSAPP_*`/API keys), context cache reset (soul/skills caches + interaction counter), provider registry reset, daimonic isolation.
- Test XML parsing: build raw XML strings, pass to `parse_response()`, verify extracted content.
- Test memory: use `tmp_path` DB, verify CRUD operations, TTL cleanup, trace queries.
- `helpers.py` exports: `MockProvider`, `SAMPLE_SOUL_MD`, `SAMPLE_SKILLS_MD`, `make_inbox_entry()`, `write_inbox_entry()`.

## Boundaries

- Always: Run tests from project root (`python3 -m pytest daemon/tests/ -v`)
- Always: Register new providers in `providers/__init__.py`
- Ask: Before changing DB schema in any memory module
- Ask: Before modifying the `STEP_INSTRUCTIONS` dict or `_assemble_instructions()` logic
- Never: Import from `tests/` in daemon source code
- Never: Hardcode API keys, Slack tokens, or credentials
- Never: Bypass `memory.db` Python modules with direct `sqlite3` writes
- Never: Use `pip install` directly -- use `uv pip install` or `uv add`
