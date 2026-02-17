# Testing

## Overview

Claudius has a comprehensive pytest-based test suite covering all four architecture layers: Identity (soul engine), Cognition (pipeline), Memory (three-tier SQLite), and Channels (Slack bridge, WhatsApp, inbox watcher). The suite runs 176 tests in under 0.5s with zero real API calls, zero real Slack tokens, and zero real DB files touched outside of `tmp_path`.

## Running Tests

```bash
# Install test dependencies
cd ~/Desktop/Programming/claudius
uv pip install -e ".[test]"

# Run all tests
python3 -m pytest daemon/tests/ -v

# Run only unit tests (fast, no integration)
python3 -m pytest daemon/tests/ -v -k "not bridge and not handler and not smoke"

# Run integration tests only
python3 -m pytest daemon/tests/test_bridge_flow.py daemon/tests/test_claude_handler.py -v

# Run a specific test file
python3 -m pytest daemon/tests/test_soul_engine.py -v

# Run with coverage
python3 -m pytest daemon/tests/ --cov=daemon --cov-report=term-missing
```

## Dependencies

Defined in `pyproject.toml`:

```toml
[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
testpaths = ["daemon/tests"]
pythonpath = ["daemon"]
asyncio_mode = "auto"
```

The `pythonpath = ["daemon"]` setting lets tests import daemon modules directly (e.g., `import soul_engine`) without path manipulation. The `asyncio_mode = "auto"` setting eliminates the need for `@pytest.mark.asyncio` on async tests (though it's used explicitly for clarity).

## Test Structure

```
daemon/tests/
├── __init__.py                 # Package marker
├── conftest.py                 # Shared fixtures (7 categories, all autouse)
├── helpers.py                  # MockProvider, constants, inbox utilities
│
│   Phase 1: Memory Layer (no inter-module deps)
├── test_config.py              #  8 tests — _env() precedence, config defaults
├── test_working_memory.py      # 17 tests — CRUD, TTL, format_for_prompt
├── test_user_models.py         # 14 tests — templates, CRUD, interaction counting
├── test_soul_memory.py         # 13 tests — defaults, get_all merge, format_for_prompt
├── test_session_store.py       #  8 tests — save/get/touch, TTL expiry, cleanup
│
│   Phase 2: Core Logic (depends on memory modules)
├── test_soul_engine.py         # 37 tests — XML parsing, prompt building, gating
├── test_providers.py           # 11 tests — registry, fallback chain, protocol
│
│   Phase 3: Pipeline (depends on soul_engine + providers)
├── test_pipeline.py            # 16 tests — split-mode routing, per-step calls
│
│   Phase 4: Integration (depends on everything above)
├── test_bridge_flow.py         # 13 tests — inbox → watcher → pipeline → response
├── test_claude_handler.py      # 10 tests — subprocess handler, session lifecycle
├── test_whatsapp_utils.py      # 15 tests — phone normalization, gateway comms
├── test_whatsapp_read.py       #  7 tests — inbox filtering for WhatsApp
│
│   Phase 5: Smoke
└── test_smoke.py               #  7 tests — E2E import validation, round-trip tests
```

Total: 15 files, ~1,700 LOC, 176 tests.

## Fixture System

All fixtures live in `conftest.py` and `helpers.py`. Four fixtures are `autouse=True`—they run before every test automatically, ensuring complete isolation.

### 1. DB Isolation (`autouse=True`)

Every test gets a fresh SQLite database in `tmp_path`. All four memory modules (`working_memory`, `user_models`, `soul_memory`, `session_store`) have their `DB_PATH` monkeypatched and their `threading.local()` objects reset to force reconnection.

```python
@pytest.fixture(autouse=True)
def isolate_databases(tmp_path, monkeypatch):
    mem_db = str(tmp_path / "memory.db")
    sess_db = str(tmp_path / "sessions.db")
    for mod in [working_memory, user_models, soul_memory]:
        monkeypatch.setattr(mod, "DB_PATH", mem_db)
        mod._local = threading.local()
    monkeypatch.setattr(session_store, "DB_PATH", sess_db)
    session_store._local = threading.local()
    yield tmp_path
    for mod in [working_memory, user_models, soul_memory, session_store]:
        mod.close()
```

**Why `threading.local()` reset?** All DB modules cache their SQLite connection in a `threading.local()` object. Without resetting it, tests would share connections across a session, defeating isolation.

### 2. Clean Environment (`autouse=True`)

Strips all `CLAUDIUS_*`, `SLACK_DAEMON_*`, `WHATSAPP_*`, and API key environment variables before each test. Prevents real credentials or config from leaking into tests.

### 3. Soul Engine Cache Reset (`autouse=True`)

Nullifies `_soul_cache`, `_skills_cache`, and `_global_interaction_count` before and after each test. The soul engine caches soul.md and skills.md at the module level—without this fixture, one test's soul.md would bleed into the next.

### 4. Pipeline Counter Reset (`autouse=True`)

Zeros out `_pipeline_interaction_count` before and after each test. The pipeline tracks interactions for periodic soul state checks—leakage here would cause tests to see unexpected periodic behavior.

### 5. MockProvider

A fake LLM provider that returns configurable responses and records all invocations:

```python
class MockProvider:
    def __init__(self, name="mock", response=""):
        self.name = name
        self.response = response
        self.calls: list[dict] = []

    def generate(self, prompt: str, model: str = "") -> str:
        self.calls.append({"prompt": prompt, "model": model})
        return self.response

    async def agenerate(self, prompt: str, model: str = "") -> str:
        self.calls.append({"prompt": prompt, "model": model})
        return self.response
```

Implements the `Provider` protocol. Use `mock_provider` for a ready-made instance or `mock_provider_factory` to create providers with specific names and responses.

### 6. Sample Soul Files

`soul_md_path` and `skills_md_path` write minimal soul.md / skills.md content to `tmp_path` and return the path. Used by any test that needs `soul_engine.build_prompt()`.

### 7. Inbox Helpers

`inbox_file` creates an empty `inbox.jsonl` in `tmp_path`. `make_inbox_entry()` and `write_inbox_entry()` provide factories for creating and persisting inbox entries.

## Coverage by Architecture Layer

### Identity Layer

**`test_soul_engine.py`** (37 tests)—the most critical file.

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestExtractTag` | 6 | `_extract_tag()` regex: with/without verb, multiline, nested, not-found, special chars |
| `TestStripAllTags` | 2 | XML tag removal, plain text preservation |
| `TestBuildPrompt` | 10 | Soul.md injection, message fencing, UNTRUSTED INPUT warning, skills on first turn only, user model gating, cognitive instructions, soul state periodic, display_name handling |
| `TestParseResponse` | 9 | Dialogue extraction, monologue/dialogue stored in working_memory, user_model_check true/false, soul_state_update parsing, fallback on no tags, empty response, interaction increment |
| `TestShouldInjectUserModel` | 4 | Samantha-Dreams gate: empty→True, last query true/false, metadata as dict |
| `TestApplySoulStateUpdate` | 4 | Valid/invalid keys, lines without colon, tool action stored |
| `TestStoreHelpers` | 2 | `store_user_message()`, `store_tool_action()` |

### Cognition Layer

**`test_pipeline.py`** (16 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestIsSplitMode` | 2 | Config-based mode detection |
| `TestBuildContext` | 3 | Soul inclusion, user message, user model on first turn |
| `TestBuildStepPrompt` | 3 | Context inclusion, prior outputs section, empty prior handling |
| `TestRunPipeline` | 8 | Full success with mock providers, working memory storage, model check true/false paths, monologue failure resilience, soul state periodic check, fallback dialogue, interaction increment |

**`test_providers.py`** (11 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestRegistry` | 4 | register/get/list, unknown raises KeyError, empty name defaults to claude_cli |
| `TestGenerateWithFallback` | 3 | First succeeds, fallback chain, all-fail raises RuntimeError |
| `TestMockProviderProtocol` | 4 | Provider protocol compliance (name, generate, agenerate, call recording) |

### Memory Layer

**`test_working_memory.py`** (17 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestAdd` | 5 | add/get_recent, thread scoping, verb storage, metadata JSON roundtrip, None metadata |
| `TestGetRecent` | 2 | Limit, chronological order |
| `TestGetUserHistory` | 1 | Cross-thread user history |
| `TestFormatForPrompt` | 7 | Empty, userMessage, internalMonologue, externalDialog, mentalQuery with result, toolAction, custom soul_name |
| `TestCleanup` | 2 | TTL removal of old entries, preservation of recent |

**`test_user_models.py`** (14 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestEnsureExists` | 3 | Template creation, idempotency, user_id fallback |
| `TestSaveGet` | 4 | Round-trip, nonexistent returns None, update, display_name preservation |
| `TestGetDisplayName` | 2 | Name retrieval, None for unknown |
| `TestInteractionCounting` | 5 | Initial count, increment, should_check at interval, not before interval, nonexistent user |

**`test_soul_memory.py`** (13 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestGetSet` | 4 | Default for unset, set/get, update existing, unknown key |
| `TestGetAll` | 3 | All defaults when empty, stored overrides defaults, all keys present |
| `TestFormatForPrompt` | 6 | Empty when all defaults, header when content, neutral emotion hidden, non-neutral shown, multiple fields, conversation summary |

**`test_session_store.py`** (8 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestSaveGetTouch` | 4 | Save/get, nonexistent, update, touch refreshes |
| `TestTTLExpiry` | 2 | Expired returns None, expired deleted on get |
| `TestCleanup` | 2 | Removes expired, preserves active |

**`test_config.py`** (8 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestEnvHelper` | 5 | CLAUDIUS_ prefix, SLACK_DAEMON_ fallback, precedence, default, empty string |
| `TestConfigDefaults` | 3 | PIPELINE_MODE, SESSION_TTL, SOUL_ENGINE_ENABLED defaults after reload |

### Channel Layer

**`test_bridge_flow.py`** (13 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestReadUnhandled` | 5 | Empty inbox, missing file, populated, line_index, malformed JSON |
| `TestMarkHandled` | 3 | Valid mark, invalid index, negative index |
| `TestProcessEntry` | 5 | Unified mode, split mode, WhatsApp routing, WhatsApp failure (not marked handled), response truncation |

**`test_claude_handler.py`** (10 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestProcess` | 10 | New session, resume session, soul engine on/off, timeout, JSON parse failure, is_error flag, session touch, CLAUDE_CODE_* env stripping, truncation, nonzero returncode |

**`test_whatsapp_utils.py`** (15 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestNormalizePhone` | 7 | E.164, digits-only, parentheses, dashes, empty, no digits, international |
| `TestChannelDetection` | 4 | is_whatsapp_channel, phone_from_channel |
| `TestHealthCheck` | 2 | Unreachable, success |
| `TestSendMessage` | 2 | Success, HTTP error |

**`test_whatsapp_read.py`** (7 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestReadInbox` | 7 | WhatsApp-only filter, from_phone, unhandled, combined filters, empty, missing file, limit |

### Smoke Tests

**`test_smoke.py`** (7 tests)

| Test Class | Count | What It Validates |
|------------|-------|-------------------|
| `TestImports` | 2 | All daemon modules import without error, provider functions importable |
| `TestSoulEngineRoundTrip` | 1 | build_prompt → craft XML → parse_response → verify dialogue + DB state |
| `TestPipelineRoundTrip` | 1 | Mock providers → run_pipeline → verify PipelineResult fields |
| `TestMultiTurnCognitiveCycle` | 1 | 3-turn cycle verifying Samantha-Dreams gate across turns |
| `TestSessionContinuity` | 1 | 2-turn session with session_store save/resume/touch |
| `TestProviderRegistryMock` | 1 | Register → get_provider → generate → verify calls recorded |

## Mocking Strategy

All tests run without real API calls or network access. The mocking approach varies by module:

| Module | What's Mocked | How |
|--------|--------------|-----|
| Memory modules | `DB_PATH` | `monkeypatch.setattr(mod, "DB_PATH", tmp_path / "memory.db")` |
| Soul engine | `_SOUL_MD_PATH`, `_SKILLS_MD_PATH` | `monkeypatch.setattr` to `soul_md_path` fixture |
| Providers | `_registry` | `_registry.clear()` + `register(MockProvider(...))` |
| Pipeline | `_resolve_provider`, `_resolve_model` | `monkeypatch.setattr` to lambda returning MockProviders |
| Inbox watcher | `INBOX`, `slack_post`, `slack_react` | `monkeypatch.setattr` to tmp_path / MagicMock |
| Claude handler | `subprocess.run` | `MagicMock` returning JSON with configurable stdout/returncode |
| WhatsApp utils | `urllib.request.urlopen` | `monkeypatch.setattr` with fake response classes |
| Config | env vars | `monkeypatch.setenv` / `monkeypatch.delenv` + `importlib.reload(config)` |

## Adding New Tests

### Convention

- One test file per daemon module, named `test_{module}.py`
- Test classes group related tests: `class TestFeatureName:`
- Test methods use `test_` prefix with descriptive names
- Use existing fixtures from conftest.py—don't create ad hoc DB paths

### Template

```python
"""Tests for daemon/{module}.py — brief description."""

import {module}


class TestFeature:
    """Tests for feature()."""

    def test_basic_behavior(self):
        result = module.feature("input")
        assert result == "expected"

    def test_edge_case(self):
        result = module.feature("")
        assert result is None
```

For async tests:

```python
@pytest.mark.asyncio
async def test_async_operation(self, monkeypatch, soul_md_path):
    monkeypatch.setattr(soul_engine, "_SOUL_MD_PATH", soul_md_path)
    result = await pipeline.run_pipeline("hi", "U1", "C1", "T1")
    assert result.dialogue == "expected"
```

### Key Patterns

1. **Monkeypatch soul paths** when testing anything that calls `build_prompt()`:
   ```python
   monkeypatch.setattr(soul_engine, "_SOUL_MD_PATH", soul_md_path)
   ```

2. **Clear the provider registry** before registry tests:
   ```python
   from providers import _registry
   _registry.clear()
   ```

3. **Backdate timestamps** for TTL tests instead of mocking `time.time()`:
   ```python
   conn = session_store._get_conn()
   conn.execute("UPDATE sessions SET last_used = ?", (time.time() - 999999,))
   conn.commit()
   ```

4. **Mock pipeline providers** via `_resolve_provider`:
   ```python
   monkeypatch.setattr(pipeline, "_resolve_provider", lambda step: MockProvider(...))
   monkeypatch.setattr(pipeline, "_resolve_model", lambda s: "")
   ```

5. **Mock inbox watcher I/O** by patching `INBOX` and the post/react functions:
   ```python
   monkeypatch.setattr(inbox_watcher, "INBOX", inbox_file)
   monkeypatch.setattr(inbox_watcher, "slack_post", MagicMock())
   ```

## Troubleshooting

### `ModuleNotFoundError: No module named 'conftest'`

Don't import from conftest directly. Shared test utilities live in `tests/helpers.py`:

```python
from tests.helpers import MockProvider, SAMPLE_SOUL_MD
```

### Tests fail with `DB_PATH` or connection errors

The `isolate_databases` fixture must be running. If you're seeing real `memory.db` paths, ensure conftest.py is being discovered (check that `daemon/tests/__init__.py` exists).

### `AttributeError: module has no attribute`

Some modules use local imports inside functions (e.g., `inbox_watcher.process_entry()` imports `get_provider` locally). Mock at the source module, not the importing module:

```python
# Wrong: monkeypatch.setattr("inbox_watcher.get_provider", ...)
# Right:
monkeypatch.setattr("providers.get_provider", ...)
```

### Config tests fail after env changes

Config values are set at module import time. Use `importlib.reload(config)` after changing env vars:

```python
monkeypatch.setenv("CLAUDIUS_PIPELINE_MODE", "split")
importlib.reload(config)
assert config.PIPELINE_MODE == "split"
```
