---
title: "Memory"
directory: daemon/memory/
files: 6
created: 2026-02-19
updated: 2026-03-06
description: "Three-tier memory system — working (72h), user models (permanent), soul state (permanent)"
tiers:
  - working_memory (per-thread, SQLite, 72h TTL)
  - user_models (per-user, markdown, permanent)
  - soul_memory (global, key-value, permanent)
  - soul_state (unified, topic stack + transitions, permanent)
---

# Memory

Three-tier memory system for Claudicle. Each tier serves a different scope and lifetime.

---

| Tier | File | Scope | Storage | TTL |
|------|------|-------|---------|-----|
| Working Memory | `working_memory.py` | Per-thread | SQLite | 72 hours |
| User Models | `user_models.py` | Per-user | Markdown files | Permanent |
| Soul Memory | `soul_memory.py` | Global | Key-value store | Permanent |
| Soul State | `soul_state.py` | Global | Topic stack + transitions | Permanent |

## Support Modules

| File | Purpose |
|------|---------|
| `session_store.py` | Thread-to-session mapping (SQLite, 24h TTL) |
| `git_tracker.py` | Git-versioned memory export to `$CLAUDICLE_HOME/memory/` |

## Key Concepts

- **Working memory** stores all cognitive outputs (monologue, dialogue, verbs, tool actions) grouped by `trace_id`. Not injected into prompts—used for gating decisions and analytics. Renders `soulStateShift` entries as narrative ("Claudius shifted focus to...", "Claudius's mood shifted to...").
- **User models** are living markdown profiles (modeled after `tomModel.md`) with YAML frontmatter (`userName`, `role`, `onboardingComplete`). Git-tracked for evolution history.
- **Soul memory** is global state that persists across all threads and sessions—the soul's permanent knowledge. Key-value store for simple fields (currentProject, currentTask, conversationSummary, emotionalState).
- **Soul state** is the unified state manager across all channels. Adds: topic stack (1 primary + 7 subtopics, FIFO cascade), timestamped transition audit log (`soul_state_transitions` table), and narrative `soulStateShift` entries to working memory. `apply_output()` routes soul state updates through `soul_state.set_state_key()` instead of `soul_memory.set()` directly.
- **Session store** maps Slack threads to Claude sessions so multi-turn conversations resume context.
