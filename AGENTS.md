# Claudius -- Soul Agent Framework

Open-source soul agent framework for Claude Code. Adds persistent personality, structured cognition, three-tier memory, and channel adapters (Slack, SMS, WhatsApp, terminal) to any Claude Code session. Python 3.10+, SQLite, Slack Bolt, Claude Agent SDK. 81 files, 15,149 LOC.

## Commands

- Install: `./setup.sh --personal` (or `--company`)
- Test all: `python3 -m pytest daemon/tests/ -v` (238 tests, <2.5s)
- Test single: `python3 -m pytest daemon/tests/test_name.py::TestClass::test_method -v`
- Smoke test: `cd daemon && python3 -c "import soul_engine; print('OK')"`
- Daemon (unified): `cd daemon && python3 claudius.py`
- Daemon (bridge): `cd daemon && python3 slack_listen.py --bg`
- Inbox watcher: `cd daemon && python3 inbox_watcher.py`
- Monitor TUI: `cd daemon && uv run python monitor.py`

## Structure

- `/daemon` -- Core engine, pipeline, memory, providers, monitor (23 files, 6,084 LOC)
- `/daemon/tests` -- pytest suite (14 test files, 238 tests, 2,653 LOC)
- `/daemon/providers` -- LLM provider abstraction (6 providers + registry)
- `/soul` -- Personality files (`soul.md`, dossier templates)
- `/hooks` -- Claude Code lifecycle hooks (SessionStart/End, handoff)
- `/commands` -- Slash commands (activate, ensoul, slack-sync, slack-respond, thinker, watcher, daimon)
- `/scripts` -- Slack utility CLIs (14 scripts + 2 boot scripts)
- `/adapters` -- Channel transports (SMS via Telnyx/Twilio, WhatsApp via Baileys)
- `/docs` -- Architecture and reference documentation

## Testing

- 238 tests in `daemon/tests/`, pytest + pytest-asyncio, <2.5s. Zero real API calls or DB files.
- See `daemon/AGENTS.md` for test patterns, fixtures, and helpers.

## Boundaries

- Always: Run full test suite before committing (`python3 -m pytest daemon/tests/ -v`)
- Always: Use `tmp_path` fixture for temp files in tests -- never write to project directories
- Always: Keep soul personality in `soul/soul.md`, not in Python code
- Ask: Before adding production dependencies to `pyproject.toml`
- Ask: Before modifying `conftest.py` autouse fixtures (affects all 238 tests)
- Ask: Before changing `STEP_INSTRUCTIONS` in `soul_engine.py` (single source of truth for both modes)
- Never: Commit `.env`, `memory.db`, `sessions.db`, or API tokens
- Never: Write directly to `memory.db` or `sessions.db` via `sqlite3` -- use the Python modules
- Never: Remove or modify `STEP_INSTRUCTIONS` without updating both unified and split mode paths
- Never: Use `pip install` directly -- use `uv pip install` or `uv add`
