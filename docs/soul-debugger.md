# Soul Debugger — User Guide

A native macOS app for watching a Claudicle soul think in real time. Read-only observer of the daemon's SQLite memory and JSONL cognitive streams.

> **Looking for setup?** See [`SoulDebugger/README.md`](../SoulDebugger/README.md) for build steps and architecture. This guide explains what the app *shows you* once it's running.

## What you see

Three tabs, each a window into one Open Souls primitive. If you've read [Open Souls alignment](open-souls-alignment.md), every view should feel like the same concepts you already know, rendered visually instead of as `tail -f | jq` output.

| Tab | What it shows | Open Souls equivalent |
|-----|---------------|-----------------------|
| **Cognitive Stream** | Phase-colored live tail of every cognitive cycle — stimulus in, response out | `CognitiveStep` phases + `Subprocess` boundaries |
| **Working Memory** | Every row written to `working_memory`, filterable by channel, region, and entry type | `WorkingMemory` |
| **Soul State** | Emotional state, topic stack (1 primary + 7 subtopics), and state-transition audit log | `SoulMemory` + topic stack |

## Prerequisites

- **macOS 15 (Sequoia) or later.**
- **Claudicle daemon installed and has run at least once.** The debugger opens `~/.claudicle/memory.db` and `~/.claudicle/sessions.db`; if those files don't exist, the daemon has never started. Run `cd daemon && python3 claudicle.py` once and send any message, then launch the debugger.
- **`CLAUDICLE_HOME` respected.** If you've overridden the default, the debugger will honor it (same resolution as the daemon).
- **Daemon running in WAL mode.** SQLite WAL is set by `daemon/memory/db.py`; this allows the debugger to read while the daemon writes, with zero blocking.

## Installation

See [`SoulDebugger/README.md`](../SoulDebugger/README.md). Short version:

```bash
brew install xcodegen
cd SoulDebugger
xcodegen generate
open SoulDebugger.xcodeproj   # ⌘R to build and run
```

## The three views

### Cognitive Stream

The most useful view for understanding *what the soul just did*. It tails `~/.claudicle/soul-stream.jsonl`, which the daemon writes one line per phase transition.

**Phases** (with their Soul Debugger colors):

| Phase | Color | Meaning |
|-------|-------|---------|
| `stimulus` | amber | A message arrived and entered the cognitive pipeline |
| `context` | slate | The prompt was assembled — soul.md, memory, user model, daimonic whispers, gates logged |
| `cognition` | violet | One cognitive step extracted from the response (e.g. `internalMonologue`, `externalDialog`) |
| `decision` | teal | A `mentalQuery` boolean gate evaluated (e.g. "should the user model be updated?") |
| `memory` | green | A state mutation committed (user model update, soul state update, dossier update) |
| `response` | blue | Final output delivered to the channel, with `elapsed_ms` |
| `subprocess` | — | Brackets a named subprocess (`modelsTheUser`, `updatesState`) with `start`/`end` events |
| `error` | red | Something blew up in the pipeline |

**One cognitive cycle = one `trace_id`.** A `trace_id` is a 12-char hex UUID generated at the start of a cycle and stamped onto every phase emitted during it. Filter the stream by `trace_id` to see a single perception → response in isolation. This mirrors Open Souls' immutable `WorkingMemory` snapshot pattern — Claudicle uses relational grouping instead of object copies, but the "one cycle, one snapshot" invariant is preserved.

**What to look for:**
- A `decision` phase with `result: true` followed immediately by a `memory` phase = a gate fired and the soul updated itself
- `subprocess` `start` → `end` pairs bracket reflection work (runs after the main response)
- A `response` phase with high `elapsed_ms` is the ground truth for cognitive latency
- `error` phases surface pipeline failures that would otherwise be invisible

Reference: [`docs/soul-stream.md`](soul-stream.md) for the full JSONL schema.

### Working Memory

Every entry the daemon has ever written to the `working_memory` table, filtered by channel. This is the per-thread cognitive log — the first tier of Claudicle's [three-tier memory](daemon-architecture.md).

**Channels** follow a namespaced convention:

| Prefix | Example | Source |
|--------|---------|--------|
| Slack channel ID | `C04ABC123` | Slack adapter |
| `discord:` | `discord:987654321` | Discord adapter |
| `telegram:` | `telegram:123456` | Telegram adapter |
| `terminal:` | `terminal:abc123…` | Terminal reflection (Stop hook) |
| `sms:` | `sms:+17327595647` | SMS adapter (Telnyx/Twilio) |
| `whatsapp:` | `whatsapp:+1…` | WhatsApp adapter |
| `daimon:` | `daimon:kothar` | Subdaimon persistent memory |

**Regions** partition a channel's working memory. You'll mostly see:

- `default` — normal cognitive entries
- `summary` — Hypermnesia memory compression output
- `lessons` — subdaimon cross-project lessons
- `comms` — subdaimon communication log
- `context` — subdaimon boot context

**The 14 entry types** that color each row:

| Entry type | What it is |
|------------|------------|
| `userMessage` | The raw user input that triggered a cycle |
| `internalMonologue` | The soul's private reflection, never shown to the user — first-person with verb narration |
| `externalDialog` | The outward-facing reply sent to the channel |
| `mentalQuery` | A boolean gate with reasoning context ("Should the user model be updated? Context: …") |
| `toolAction` | A tool call (file read, bash command, web fetch) |
| `decision` | A decision-gate outcome logged for traceability (skills inject, user model gate, dossier inject) |
| `daimonicIntuition` | A whisper from a daimon (Kothar, etc.) injected into context |
| `onboardingStep` | State from the 4-stage First Ensoulment interview |
| `memorySummary` | Compressed-out archive output from Hypermnesia |
| `soulStateShift` | Narrative record of an emotional-state or topic transition |
| `lifecycle` | Daemon lifecycle events (start, stop, checkpoint, rollback) |
| `modelShed` | Soul-shedding archaeology — diffs of user-model/dossier evolution |
| `myceliumContext` | Git-note context surfaced when editing a file (mycelium skill) |
| `myceliumSpore` | A daimonic spore written back to git notes after work on a file |

See [Open Souls alignment](open-souls-alignment.md) for the intentional mapping of these names to Open Souls' JavaScript `WorkingMemory` conventions.

**What to look for:**
- A `userMessage` → `mentalQuery` → `internalMonologue` → `externalDialog` sequence is a complete reflection cycle in canonical order
- `modelShed` entries are the most information-dense — they carry diffs, an internal monologue about the change, and optional meta commentary
- `daimon:` channels have a 30-day TTL (vs. the 72h default) so daimon memory persists across projects

### Soul State

The second and third [memory tiers](daemon-architecture.md) — `soul_memory` (key-value, per-soul) and `soul_topics` (the topic stack). This is what the daemon injects into every prompt when non-default.

**Emotional state** shows the current single-word state (one of `neutral`, `engaged`, `focused`, `sardonic`, `frustrated`, `absorbed`, `curious`) with its color.

**Topic stack** shows 1 primary topic + up to 7 subtopics in rank order. New topics push older ones down; rank 7 falls off the end. This FIFO cascade is documented in `daemon/memory/soul_state.py`.

**Transition history** reads from `soul_state_transitions`, showing every timestamped state change with old value → new value. This is the audit log the daemon writes whenever it calls `soul_state.set_state_key()`.

**What to look for:**
- A sudden emotional state shift often correlates with a visible phase error or a tense user message a few traces back in the Cognitive Stream
- The primary topic tells you what the soul thinks it's currently working on — useful for diagnosing "why is the soul answering as if we're still on the last topic?"

## Keyboard shortcuts

Phase 1 ships with tab navigation only:

| Shortcut | Action |
|----------|--------|
| `⌘1` | Cognitive Stream |
| `⌘2` | Working Memory |
| `⌘3` | Soul State |

Per-view shortcuts (filter focus, entry selection, trace pinning) land in Phase 3. See the [parent plan](plans/2026-03-24-001-feat-soul-debugger-native-macos-plan.md) for the full shortcut roadmap.

## Multi-soul installations

Claudicle supports multiple soul profiles via `soul/active` symlink or `CLAUDICLE_SOUL_PROFILE`. `soul_memory` and `soul_state` are scoped by a `soul_id` column (defaulting to `config.SOUL_NAME.lower()`).

Phase 1 shows the currently active soul. A soul selector dropdown is planned for Phase 3. For now, switch souls at the daemon level (`/switch-soul <name>`) and relaunch the debugger to see the new soul's state.

## Troubleshooting

**"Database not found"**
The daemon hasn't started yet, or `CLAUDICLE_HOME` is set to a different directory than what the debugger is reading. Confirm with `ls ~/.claudicle/memory.db`. If you've customized `CLAUDICLE_HOME`, export it in your shell before launching the debugger from Terminal (Xcode runs inherit the GUI environment, not your `.zshrc` — use `launchctl setenv CLAUDICLE_HOME ...` for GUI launches).

**"No events in Cognitive Stream"**
The debugger seeks JSONL files to EOF on open (Phase 2 behavior), so only *new* events after launch appear. Send a message through any channel and the stream will fill. If nothing appears after a known interaction, confirm `~/.claudicle/soul-stream.jsonl` is growing: `wc -l ~/.claudicle/soul-stream.jsonl` before and after.

**"Permission denied reading memory.db"**
App sandbox is intentionally disabled in `project.yml` (`ENABLE_USER_SCRIPT_SANDBOXING: false`). If you see this anyway, you've likely enabled the sandbox in Xcode project settings after `xcodegen generate` — re-run `xcodegen generate` to restore the declared config.

**"Events exist in working-memory-stream.jsonl but not in Working Memory tab"**
The tab reads from the SQLite table, not the JSONL stream. If the daemon is mid-write and WAL is disabled, you may see a stale snapshot. Verify WAL: `sqlite3 ~/.claudicle/memory.db 'PRAGMA journal_mode;'` should return `wal`.

**"Tab shows an empty state even though data exists"**
Phase 1 service clients are stubbed — they return empty arrays regardless of DB contents. This is expected; Phase 2 wires the real GRDB pool. Check the Phase column in [`SoulDebugger/README.md`](../SoulDebugger/README.md) for current status.

## Relationship to other tools

| Tool | Scope | Use when |
|------|-------|----------|
| **Soul Debugger** (this app) | Visual, native, persistent, filtered | You want to pin a trace, browse history, or watch state changes over a session |
| `daemon/monitoring/monitor.py` (Textual TUI) | Terminal-native, live-only, lighter | You're ssh'd into a remote Claudicle instance and want a quick heartbeat |
| `tail -f ~/.claudicle/soul-stream.jsonl \| jq` | Raw, scriptable, grep-friendly | You're composing a custom filter or piping to an analytics script |
| `uv run scripts/wm-manage.py query ...` | CLI query over SQLite | You want ad-hoc SQL-like queries with structured output |

The Soul Debugger doesn't replace any of these — it layers on top of the same JSONL streams and SQLite tables, so anything you see in the app you can also reproduce with `jq` or `sqlite3`.

## References

- [Open Souls alignment](open-souls-alignment.md) — the canonical mapping this debugger visualizes
- [Soul stream schema](soul-stream.md) — JSONL phase schema for the Cognitive Stream tab
- [Cognitive pipeline](cognitive-pipeline.md) — how XML-tagged cognitive steps become working memory entries
- [Daemon architecture](daemon-architecture.md) — the three-tier memory model
- [`SoulDebugger/README.md`](../SoulDebugger/README.md) — developer setup, architecture, contributing
- [Parent plan](plans/2026-03-24-001-feat-soul-debugger-native-macos-plan.md) — Phase 1→3 roadmap with performance targets
