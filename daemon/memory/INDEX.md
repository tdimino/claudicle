---
title: "Memory"
directory: daemon/memory/
files: 5
created: 2026-02-19
description: "Three-tier memory system — working (72h), user models (permanent), soul state (permanent)"
tiers:
  - working_memory (per-thread, SQLite, 72h TTL)
  - user_models (per-user, markdown, permanent)
  - soul_memory (global, key-value, permanent)
---

# Memory

Three-tier memory system for Claudicle. Each tier serves a different scope and lifetime.

---

| Tier | File | Scope | Storage | TTL |
|------|------|-------|---------|-----|
| Working Memory | `working_memory.py` | Per-thread | SQLite | 72 hours |
| User Models | `user_models.py` | Per-user | Markdown files | Permanent |
| Soul Memory | `soul_memory.py` | Global | Key-value store | Permanent |

## Support Modules

| File | Purpose |
|------|---------|
| `session_store.py` | Thread-to-session mapping (SQLite, 24h TTL) |
| `git_tracker.py` | Git-versioned memory export to `$CLAUDICLE_HOME/memory/` |

## Key Concepts

- **Working memory** stores all cognitive outputs (monologue, dialogue, verbs, tool actions) grouped by `trace_id`. Not injected into prompts—used for gating decisions and analytics.
- **User models** are living markdown profiles (modeled after `tomModel.md`) with YAML frontmatter (`userName`, `role`, `onboardingComplete`). Git-tracked for evolution history.
- **Soul memory** is global state that persists across all threads and sessions—the soul's permanent knowledge.
- **Session store** maps Slack threads to Claude sessions so multi-turn conversations resume context.
