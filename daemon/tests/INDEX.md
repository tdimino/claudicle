---
title: "Tests"
directory: daemon/tests/
files: 18
total_tests: 319
created: 2026-02-19
description: "Test suite covering cognitive pipeline, memory, providers, adapters, and onboarding"
run: "python3 -m pytest daemon/tests/ -v"
---

# Tests

319 tests covering the daemon's cognitive pipeline, memory, providers, adapters, and onboarding.

Run: `python3 -m pytest daemon/tests/ -v`

---

## Test Files

| File | Module | What it covers |
|------|--------|----------------|
| `test_smoke.py` | — | Import checks, config loading, basic sanity |
| `test_config.py` | `config.py` | Env var parsing, dual-prefix support, defaults |
| `test_soul_engine.py` | `engine/soul_engine.py` | `build_prompt()`, `parse_response()`, XML tag extraction |
| `test_pipeline.py` | `engine/pipeline.py` | Split-mode cognitive routing, per-step provider dispatch |
| `test_onboarding.py` | `engine/onboarding.py` | 4-stage interview state machine, role assignment, stage transitions |
| `test_working_memory.py` | `memory/working_memory.py` | SQLite store, TTL expiry, trace_id grouping, verb storage |
| `test_user_models.py` | `memory/user_models.py` | Profile creation, frontmatter parsing, `ensure_exists()`, role field |
| `test_soul_memory.py` | `memory/soul_memory.py` | Global key-value state, persistence, cross-thread access |
| `test_session_store.py` | `memory/session_store.py` | Thread-to-session mapping, TTL, cleanup |
| `test_soul_log.py` | `adapters/slack_log.py` | JSONL soul stream, trace threading, phase capture |
| `test_slack_log.py` | `adapters/slack_log.py` | Slack event logging, append-only JSONL |
| `test_providers.py` | `providers/` | Provider registry, fallback chains, response parsing |
| `test_claude_handler.py` | `claude_handler.py` | Subprocess invocation, SDK query, session routing |
| `test_bridge_flow.py` | — | End-to-end Session Bridge flow |
| `test_daimonic.py` | `daimonic/` | Registry, whisper generation, speak mode, inter-soul conversations |
| `test_whatsapp_read.py` | — | WhatsApp message ingestion |
| `test_whatsapp_utils.py` | — | WhatsApp adapter utilities |

## Support Files

| File | Purpose |
|------|---------|
| `conftest.py` | Shared fixtures, `ONBOARDING_ENABLED=False` autouse fixture |
| `helpers.py` | Test utilities and mock factories |
| `__init__.py` | Package marker |
