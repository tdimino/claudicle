---
title: "Daemon"
directory: daemon/
files: 9
submodules: 7
created: 2026-02-19
description: "Core engine for the Claudicle soul agent framework"
entry_points:
  - claudicle.py (unified launcher)
  - bot.py (legacy Slack daemon)
---

# Daemon

Core engine for the Claudicle soul agent framework.

See also: [AGENTS.md](AGENTS.md) for module conventions.

---

## Entry Points

| File | Purpose |
|------|---------|
| `claudicle.py` | Unified launcher—terminal + Slack in one process |
| `bot.py` | Legacy Slack Socket Mode daemon (standalone) |
| `claude_handler.py` | Claude invocation: `process()` (CLI subprocess) + `async_process()` (Agent SDK) |

## Configuration

| File | Purpose |
|------|---------|
| `config.py` | All settings via `CLAUDICLE_*` env vars. Feature toggles, provider selection, paths |
| `requirements.txt` | Python dependencies |
| `skills.md` | Skills catalog (registered capabilities) |
| `tmux-layout.yaml` | Terminal multiplexer layout for daemon monitoring |

## Submodules

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| [`engine/`](engine/) | Cognitive pipeline, context assembly, onboarding | `soul_engine.py`, `context.py`, `onboarding.py`, `pipeline.py` |
| [`memory/`](memory/) | Three-tier memory system | `working_memory.py`, `user_models.py`, `soul_memory.py`, `session_store.py` |
| [`providers/`](providers/) | LLM provider abstraction (6 providers) | `claude_cli.py`, `anthropic_api.py`, `ollama_provider.py`, etc. |
| [`adapters/`](adapters/) | Channel I/O (Slack, terminal, inbox) | `slack_adapter.py`, `inbox_watcher.py`, `terminal_ui.py` |
| [`daimonic/`](daimonic/) | Multi-daimon intercession system | `registry.py`, `whispers.py`, `speak.py`, `converse.py` |
| [`cognitive_steps/`](cognitive_steps/) | Step definitions and routing | `steps.py`, `interview/` |
| [`tests/`](tests/) | 319 tests | [INDEX.md](tests/INDEX.md) |
