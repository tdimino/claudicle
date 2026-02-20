---
title: "Structured Soul Stream — Three-Log Observability"
date: 2026-02-18
status: implemented
implemented_in:
  - "1f5cba4 feat: structured soul stream — three-log observability architecture"
  - "203332f feat: extract context.py, add trace_id system, AGENTS.md + Codex config"
changes_from_plan:
  - "Monitor TUI trace panel deferred to future iteration"
  - "Self-inspection cognitive instruction (periodic self-reflection) not added"
  - "step_stats() function not implemented—trace queries sufficient for now"
---

# Structured Soul Log — Cognitive Cycle JSONL Stream

**Date**: 2026-02-18

## Summary

Added `soul_log.py`—a `tail -f`-able JSONL stream capturing the soul's full cognitive cycle from stimulus through response.

## Three-Log Architecture

| Layer | File | What it captures | Storage |
|-------|------|------------------|---------|
| Raw events | `slack_log.py` | Pre-processing Slack events | JSONL |
| Cognitive store | `working_memory.py` | Post-processing step outputs | SQLite |
| Soul stream | `soul_log.py` | Full cognitive cycle phases | JSONL |

## Seven Phases

1. **stimulus** — user message received
2. **context** — prompt assembly details
3. **cognition** — one per cognitive step
4. **decision** — boolean gate outcomes
5. **memory** — state mutations
6. **response** — final output
7. **error** — exception capture

All entries threaded by `trace_id`. Gated by `SOUL_LOG_ENABLED`. Thread-safe via `fcntl.flock`.
