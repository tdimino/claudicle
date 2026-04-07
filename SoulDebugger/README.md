# Soul Debugger

Native macOS debugger for Claudicle's cognitive architecture. Built with Swift 6, The Composable Architecture (TCA) 1.25, GRDB 7, and SwiftUI.

> **Status** — Phase 1: scaffold complete, build succeeds, service clients stubbed. See [parent plan](../docs/plans/2026-03-24-001-feat-soul-debugger-native-macos-plan.md) for the full roadmap and [`docs/soul-debugger.md`](../docs/soul-debugger.md) for the user guide.

## What it is

Soul Debugger is the **visual surface of Claudicle's [Open Souls](https://docs.souls.chat) adaptation**. Each tab is a live window into one Open Souls primitive as it lives in Claudicle's SQLite databases and JSONL streams. It replaces the Python Textual TUI (`daemon/monitoring/monitor.py`) with a native read-only observer you can run alongside the daemon while it thinks.

Claudicle itself is documented in [`docs/open-souls-alignment.md`](../docs/open-souls-alignment.md) — the canonical mapping of Open Souls concepts to Claudicle's Python daemon. This debugger is that mapping made visible.

## The Open Souls mapping

This table is the soul of this README. Every view in the app renders exactly one of these primitives.

| Open Souls primitive | Claudicle storage | Soul Debugger view |
|----------------------|-------------------|--------------------|
| `WorkingMemory` | `memory.db` → `working_memory` | **Working Memory** tab — entries by channel, region, and `trace_id` |
| `CognitiveStep` phases | `~/.claudicle/soul-stream.jsonl` | **Cognitive Stream** tab — phase-colored live tail |
| `Subprocess` (`modelsTheUser`, `updatesState`) | `soul-stream.jsonl` `phase="subprocess"` | **Cognitive Stream** tab — nested under cognition |
| `SoulMemory` | `memory.db` → `soul_memory` | **Soul State** tab — key/value cross-session state |
| Topic stack | `memory.db` → `soul_topics` | **Soul State** tab — 1 primary + 7 subtopics, FIFO cascade |
| State transitions | `memory.db` → `soul_state_transitions` | **Soul State** tab — timestamped audit log |
| `mentalQuery` (boolean gates with reasoning) | `working_memory.entry_type='mentalQuery'` | Both tabs — rendered with the gate's reasoning context |
| `internalMonologue` / `externalDialog` | `working_memory.entry_type=...` | **Working Memory** — color-coded by `EntryType` |
| `trace_id` (one cognitive cycle) | UUID hex column on every row | Used as the grouping key in Cognitive Stream |

Canonical definitions for each primitive live in the `open-souls-paradigm` skill:

- [`core-concepts.md`](../../../.claude/skills/open-souls-paradigm/references/core-concepts.md) — `WorkingMemory`, `CognitiveStep`, `MentalProcess`
- [`opensouls-repo/working-memory.md`](../../../.claude/skills/open-souls-paradigm/references/opensouls-repo/working-memory.md) — immutable `Memory` shape and region API
- [`opensouls-repo/cognitive-step.md`](../../../.claude/skills/open-souls-paradigm/references/opensouls-repo/cognitive-step.md) — the `CognitiveStep` contract
- [`opensouls-repo/subprocesses.md`](../../../.claude/skills/open-souls-paradigm/references/opensouls-repo/subprocesses.md) — how subprocesses frame background work

## Architecture

```
SwiftUI Views  ──reads──▶  TCA Reducers  ──@Dependency──▶  Service Clients
                                                           ├── DatabaseClient (GRDB read-only pool)
                                                           └── StreamClient   (DispatchSource on JSONL)
                                                                    │
                                                                    ▼
                                                     ~/.claudicle/
                                                       ├── memory.db
                                                       ├── sessions.db
                                                       ├── soul-stream.jsonl
                                                       └── working-memory-stream.jsonl
```

**Read-only by design.** GRDB opens with `Configuration.readonly = true`; the debugger never writes to Claudicle's databases. The daemon runs SQLite in WAL mode (see prerequisites in the parent plan), which allows zero-blocking concurrent reads while the daemon continues to write.

**Sandbox disabled.** `ENABLE_USER_SCRIPT_SANDBOXING: false` in `project.yml` so the app can read `~/.claudicle/`.

**Swift 6 strict concurrency.** `SWIFT_STRICT_CONCURRENCY: complete` — every model is `Sendable`, every closure is `@Sendable`, and `Equatable` lives on the struct declaration (not a retroactive extension) so TCA's state-change detection catches content updates, not just identity changes.

## Directory layout

```
Sources/
├── App/                    # SoulDebuggerApp + AppFeature (root reducer + tab nav)
├── Design/                 # Theme.swift (SoulColor, SoulFont), EntryTypeBadge.swift
├── Features/
│   ├── CognitiveStream/    # Phase-colored JSONL tail (StreamClient consumer)
│   ├── WorkingMemory/      # Channel / region / entry list (DatabaseClient consumer)
│   ├── SoulState/          # Topic stack + emotional state + transition history
│   ├── Sidebar/            # Phase 2 — empty scaffold
│   ├── Inspector/          # Phase 2 — empty scaffold
│   ├── UserModels/         # Phase 2 — empty scaffold
│   ├── Daimons/            # Phase 2 — empty scaffold
│   └── Sessions/           # Phase 2 — empty scaffold
├── Models/                 # 9 GRDB FetchableRecord types + JSONL Codable types
│   ├── MemoryEntry.swift       # working_memory + working_memory_archive (14 EntryTypes)
│   ├── SoulTopic.swift         # soul_topics
│   ├── SoulTransition.swift    # soul_state_transitions
│   ├── UserModel.swift         # user_models + user_model_modules
│   ├── ShedRecord.swift        # model_sheds (soul shedding archaeology)
│   ├── Checkpoint.swift        # wm_checkpoints
│   ├── Session.swift           # sessions.db
│   ├── SoulMemoryEntry.swift   # soul_memory
│   ├── SoulStreamEvent.swift   # JSONL phase events
│   └── CognitiveTrace.swift    # view model grouping entries by trace_id
├── Services/               # TCA @DependencyClient service layer
│   ├── DatabaseClient.swift    # GRDB queries (stubbed in Phase 1)
│   └── StreamClient.swift      # JSONL tail via DispatchSource (stubbed in Phase 1)
└── Resources/              # Info.plist
```

## Build & run

One-time setup:

```bash
brew install xcodegen
```

Build:

```bash
cd SoulDebugger
xcodegen generate                # regenerates SoulDebugger.xcodeproj from project.yml
xcodebuild -scheme SoulDebugger \
  -destination 'platform=macOS' \
  -skipMacroValidation build
```

Open in Xcode and run:

```bash
open SoulDebugger.xcodeproj      # then ⌘R
```

The `-skipMacroValidation` flag is required on first build because TCA, Dependencies, and CasePaths use Swift macros that need one-time trust. Inside Xcode this appears as a "Trust & Enable" dialog — click through it once and the flag is no longer needed for interactive builds.

Never hand-edit `SoulDebugger.xcodeproj`. It is regenerated from `project.yml` by `xcodegen`, and the `.xcodeproj` is gitignored.

## Dependencies

All via Swift Package Manager, resolved on first build:

| Package | Version | Purpose |
|---------|---------|---------|
| [swift-composable-architecture](https://github.com/pointfreeco/swift-composable-architecture) | 1.25.0+ | `@Reducer`, `@ObservableState`, `Scope`, `@Dependency`, tree-based nav |
| [GRDB.swift](https://github.com/groue/GRDB.swift) | 7.0.0+ | Read-only SQLite pool against `memory.db` and `sessions.db` |
| [swift-identified-collections](https://github.com/pointfreeco/swift-identified-collections) | 1.1.0+ | `IdentifiedArrayOf` for O(1) list diffing in reducers |

**Requirements:** macOS 15 (Sequoia) or later, Xcode 16, Swift 6.

## Phase status

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** | Scaffold, 3 core views, models, design system, service stubs | ✅ Complete — builds |
| **Phase 2** | `DatabaseClient.liveValue` (read-only GRDB pool), `StreamClient.liveValue` (`DispatchSource` JSONL tail), wire Cognitive Stream to live events, periodic refresh for Working Memory and Soul State tabs | Next |
| **Phase 3** | Inspector pane, EntityGraph view, Daimon channels, Sessions list, checkpoint/rollback UI, keyboard shortcut expansion | Planned |

See the [parent plan](../docs/plans/2026-03-24-001-feat-soul-debugger-native-macos-plan.md) for the full scope of each phase, including performance targets (< 100 MB memory, < 200 ms latency from daemon write to UI update).

## Contributing conventions

- **Every feature is a `@Reducer`.** State is `@ObservableState`, actions are an `enum`, side effects live inside `.run { send in ... }`. Scope child features via `Scope(state: \.child, action: \.child) { ChildFeature() }`.
- **No retroactive `Equatable` extensions on models.** `Equatable` lives on the struct declaration so TCA diffs content changes, not just identity changes. A latent UI-staleness bug is fixed by this rule.
- **All models are `Sendable`.** Strict concurrency is on. Service-client closures are `@Sendable`.
- **No writes.** DatabaseClient never opens a writer pool. If you need a feature that writes to the daemon's database, route it through Claudicle's orchestrator HTTP API instead (`daemon/orchestrator.py`).
- **xcodegen is the source of truth.** Edit `project.yml`, then re-run `xcodegen generate`. Don't touch the generated `.xcodeproj`.
- **Keep the Open Souls vocabulary.** When adding a new view or model, refer back to the mapping table above and to `docs/open-souls-alignment.md`. Don't invent new names for primitives that already have canonical ones.

## References

### Internal
- [Parent plan](../docs/plans/2026-03-24-001-feat-soul-debugger-native-macos-plan.md) — full Phase 1→3 implementation plan, 743 lines
- [Open Souls alignment](../docs/open-souls-alignment.md) — the canonical Claudicle → Open Souls mapping
- [Soul stream schema](../docs/soul-stream.md) — JSONL phase schema for the Cognitive Stream tab
- [Cognitive pipeline](../docs/cognitive-pipeline.md) — how XML-tagged steps become working memory entries
- [User guide](../docs/soul-debugger.md) — what the tabs show and how to read them

### Open Souls paradigm skill (local)
- `~/.claude/skills/open-souls-paradigm/references/core-concepts.md`
- `~/.claude/skills/open-souls-paradigm/references/opensouls-repo/working-memory.md`
- `~/.claude/skills/open-souls-paradigm/references/opensouls-repo/cognitive-step.md`
- `~/.claude/skills/open-souls-paradigm/references/opensouls-repo/subprocesses.md`
- `~/.claude/skills/open-souls-paradigm/references/opensouls-repo/memory-regions.md`

### External
- [TCA 1.25.x](https://github.com/pointfreeco/swift-composable-architecture) — `@ObservableState`, `@Reducer`, tree-based navigation
- [GRDB.swift](https://github.com/groue/GRDB.swift) — Swift SQLite wrapper with read-only pool support
- [Open Souls docs](https://docs.souls.chat) — the paradigm this debugger visualizes
