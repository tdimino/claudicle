---
title: "feat: Claudicle Soul Debugger — Native macOS Dashboard"
type: feat
status: active
date: 2026-03-24
deepened: 2026-03-24
---

## Enhancement Summary

**Deepened on:** 2026-03-24
**Research agents used:** architecture-strategist, performance-oracle, 3x scholiast (TCA+GRDB, visual rendering, cognitive visualization)

### Key Improvements from Deepening
1. **Phase 1 re-scoped** — cut from 11 features to 5-6. Sidebar is an enum, not a reducer. Inspector is a view, not a feature. Config is a one-shot query.
2. **Daemon prerequisites identified** — WAL mode not enabled (DELETE journal default), no indexes on working_memory table. Both must be fixed before the debugger can perform well.
3. **GRDB ValueObservation won't work** — uses sqlite3_update_hook which requires the writing connection. Must use DispatchSource on WAL file + high-water-mark polling (mirror Python SQLiteWatcher pattern).
4. **Missing tables** — `working_memory_archive` and `user_model_modules` were not in original plan. Actual count is 10 tables across 2 databases.
5. **Pagination required** — 10K entries in SwiftUI List exceeds 100MB memory target. Paginate to 200-500 visible entries with cursor-based GRDB queries.
6. **Chart windowing** — Swift Charts re-renders entire chart on data change. Window to last 2 hours (~50 points).
7. **JSONL tailing hardened** — must seek-to-end on launch, buffer partial lines, handle missing files, use GCD DispatchSource (not FSEventStream).

### Daemon-Side Prerequisites (new)
Before building the debugger, these changes to the Claudicle daemon are required:
1. Enable WAL mode: add `PRAGMA journal_mode=WAL` to `ConnectionPool.__init__` in `daemon/memory/db.py`
2. Add 4 indexes to `working_memory` table in `daemon/memory/working_memory.py`:
   - `idx_wm_channel_thread_created ON working_memory(channel, thread_ts, created_at DESC)`
   - `idx_wm_created_at ON working_memory(created_at)`
   - `idx_wm_trace_id ON working_memory(trace_id)`
   - `idx_wm_entry_type ON working_memory(entry_type)`
3. Add JSONL log rotation to `daemon/monitoring/soul_log.py` and `wm_stream.py` (rotate at 10MB)

### New Considerations Discovered
- `working_memory_archive` table holds compressed entries — must be displayed or compression history is invisible
- `user_model_modules` table exists for modular user models — missing from original inventory
- Region semantics (`default`, `summary`, `lessons`, `comms`, `context`) are critical for understanding data flow
- Soul ID scoping — all queries need `soul_id` parameter; multi-soul installations interleave data
- Phase 3 write operations (checkpoint rollback, daimon summoning) require new orchestrator API endpoints that don't exist yet

# Claudicle Soul Debugger — Native macOS Dashboard

A native macOS app for real-time observation of Claudicle's cognitive architecture: working memory streams, soul state transitions, daimon activity, entity graphs, and the full inner life of an ensouled session. Built with Swift, SwiftUI, and The Composable Architecture (TCA 1.25).

## Overview

The existing monitor is a Python Textual TUI (`daemon/monitoring/monitor.py`) — functional but limited to terminal, no interactivity beyond keybindings, no drill-down, no graph visualization, no cross-session comparison. The Soul Debugger replaces it with a native macOS experience that treats cognitive cycles as archaeological artifacts, not log lines.

**Design thesis**: Every existing agent debugging tool is built for engineers inspecting production incidents. A soul debugger is built for an archivist excavating a cognitive cycle — so the ontological units (cognitive steps, daimonic invocations, soulStateShift entries) are first-class visual objects, not generic spans.

## Problem Statement

1. **No drill-down**: The TUI shows streams but you can't click a trace_id to see the full cognitive cycle
2. **No entity graph**: Dossier/user model relationships are invisible
3. **No daimon visibility**: Subdaimon memory, lessons, and invocation history are buried in SQLite
4. **No cross-session awareness**: Can't see all ensouled sessions, their channels, or compare memory states
5. **No visual soul state**: Topic stack transitions and emotional state are text lines, not timelines
6. **No compression visibility**: Can't see what Hypermnesia compressed, what was preserved, what was lost

## Technical Approach

### Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Architecture | TCA (swift-composable-architecture) | 1.25.x |
| UI | SwiftUI + NavigationSplitView | macOS 15+ |
| SQLite | GRDB (via SQLiteData / SharingGRDB) | Latest |
| Charts | Swift Charts | macOS 15 |
| Streaming | AsyncStream + URLSession bytes | Native |
| 3D/Ambient | SceneKit or Metal (entity graph) | Optional Phase 3 |
| Target | macOS 15 Sequoia+ (Apple Silicon) | ARM64 |

### Data Sources

All data is **local-first** — the debugger reads directly from Claudicle's SQLite databases and JSONL log files. No server needed for basic operation; the orchestrator API is optional for live session control.

| Source | Path | Access Method |
|--------|------|---------------|
| Working Memory | `~/.claudicle/daemon/memory.db` → `working_memory` table | GRDB read-only |
| Soul State | `~/.claudicle/daemon/memory.db` → `soul_topics`, `soul_state_transitions` | GRDB read-only |
| Soul Memory | `~/.claudicle/daemon/memory.db` → `soul_memory` | GRDB read-only |
| User Models | `~/.claudicle/daemon/memory.db` → `user_models` | GRDB read-only |
| Model Sheds | `~/.claudicle/daemon/memory.db` → `model_sheds` | GRDB read-only |
| Checkpoints | `~/.claudicle/daemon/memory.db` → `wm_checkpoints` | GRDB read-only |
| Sessions | `~/.claudicle/daemon/sessions.db` | GRDB read-only |
| Daimon Memory | `~/.claudicle/daemon/memory.db` → channels matching `daimon:*` | GRDB read-only |
| Soul Stream | `~/.claudicle/soul-stream.jsonl` | AsyncStream file tail |
| WM Stream | `~/.claudicle/working-memory-stream.jsonl` | AsyncStream file tail |
| Orchestrator | `http://claudicle-api.localhost:PORT/api/health` | URLSession (optional) |
| Config | `daemon/config.py` values reflected in `soul_memory` | GRDB read |

### Architecture (TCA)

#### Phase 1 Decomposition (5 reducers + navigation enum)

```
AppFeature (root)
  navigation: SidebarSection (enum, NOT a reducer)
  inspectedItem: InspectedItem? (enum, drives trailing column)
  ├── CognitiveStreamFeature (soul-stream.jsonl tailing + trace correlation)
  ├── WorkingMemoryFeature (working_memory + working_memory_archive, region-aware)
  ├── SoulStateFeature (soul_memory + soul_topics + soul_state_transitions)
  ├── UserModelsFeature (user_models + user_model_modules + model_sheds)
  └── SessionsFeature (sessions.db)
```

#### Phase 2 Additions
```
  ├── EntityGraphFeature (force-directed graph from entity_graph scoring)
  └── DaimonFeature (daimon:* channel memory + lessons + invocations)
```

**Key corrections from architecture review:**
- Sidebar is an enum (`case cognitiveStream, workingMemory, soulState, userModels, sessions`), not a reducer — it has no effects
- Inspector is a view that pattern-matches on the active feature's `selectedItem`, not an independent state machine
- Config is a one-shot GRDB query at launch, stored in AppFeature state
- Compression is a filtered view of `working_memory_archive` + entries with `region="summary"` — it's a query mode of WorkingMemoryFeature, not a separate domain

Each feature is a `@Reducer` with `@ObservableState`, composed at the root via `Scope`.

### Data Access Pattern

> **Critical**: GRDB's `ValueObservation` uses `sqlite3_update_hook` which only fires on the *writing* connection. Since the Python daemon writes and the Swift app reads, ValueObservation will NOT detect external changes.

**Correct pattern** (mirrors Python `watcher.py`):
1. `DispatchSource.makeFileSystemObjectSource` on the `.db-wal` file — fires on every daemon commit
2. On each notification, run high-water-mark queries (e.g., `SELECT * FROM working_memory WHERE id > ?`)
3. Coalesce notifications with 500ms throttle to prevent overload
4. Paginate all queries to 200-500 entries max

```swift
// Change detection via WAL file monitoring
let walPath = dbPath + "-wal"
let fd = open(walPath, O_RDONLY | O_EVTONLY)
let source = DispatchSource.makeFileSystemObjectSource(
    fileDescriptor: fd,
    eventMask: [.write, .extend],
    queue: .global(qos: .userInitiated)
)
source.setEventHandler { [weak self] in
    self?.pollForChanges()
}
```

### Data Sources (corrected — 10 tables across 2 databases)

| Source | Table | DB | Notes |
|--------|-------|-----|-------|
| Working Memory | `working_memory` | memory.db | 12 entry types, region-scoped |
| WM Archive | `working_memory_archive` | memory.db | Compressed entries (was missing) |
| Checkpoints | `wm_checkpoints` | memory.db | Point-in-time bookmarks |
| User Models | `user_models` | memory.db | Markdown profiles + dossiers |
| User Model Modules | `user_model_modules` | memory.db | Modular sub-models (was missing) |
| Model Sheds | `model_sheds` | memory.db | Evolution diffs + monologues |
| Soul Memory | `soul_memory` | memory.db | Key-value global state |
| Soul Topics | `soul_topics` | memory.db | Ranked topic stack |
| Soul Transitions | `soul_state_transitions` | memory.db | Emotional state audit log |
| Sessions | `sessions` | sessions.db | Ensouled session registry |
| Soul Stream | — | soul-stream.jsonl | Cognitive cycle phases |
| WM Stream | — | working-memory-stream.jsonl | Entry-level event log |

---

## Implementation Phases

### Phase 1: Foundation — Read-Only Observer (MVP)

The core value: see Claudicle's inner life in real-time, drill into any cognitive cycle.

#### 1.1 Project Scaffold

- Xcode project: `SoulDebugger.xcodeproj` (macOS app, Swift 6, macOS 15+)
- SPM dependencies:
  - `swift-composable-architecture` (1.25.x) — state management
  - `GRDB.swift` — SQLite read-only access
  - `swift-identified-collections` — `IdentifiedArray` for O(1) list diffing
  - `Grape` (SwiftGraphs, 1.1.0) — force-directed entity graph (Phase 2)
  - `swift-markdown-ui` (2.4.1) — user model markdown rendering (Phase 2)
- Directory structure:
  ```
  SoulDebugger/
  ├── App/
  │   ├── SoulDebuggerApp.swift          # @main, root Store
  │   └── AppFeature.swift               # Root reducer + state
  ├── Features/
  │   ├── Sidebar/
  │   │   ├── SidebarFeature.swift
  │   │   └── SidebarView.swift
  │   ├── CognitiveStream/
  │   │   ├── CognitiveStreamFeature.swift
  │   │   └── CognitiveStreamView.swift
  │   ├── WorkingMemory/
  │   │   ├── WorkingMemoryFeature.swift
  │   │   └── WorkingMemoryView.swift
  │   ├── SoulState/
  │   │   ├── SoulStateFeature.swift
  │   │   └── SoulStateView.swift
  │   ├── UserModels/
  │   │   ├── UserModelsFeature.swift
  │   │   └── UserModelsView.swift
  │   ├── Daimons/
  │   │   ├── DaimonFeature.swift
  │   │   └── DaimonView.swift
  │   ├── Sessions/
  │   │   ├── SessionsFeature.swift
  │   │   └── SessionsView.swift
  │   └── Inspector/
  │       ├── InspectorFeature.swift
  │       └── InspectorView.swift
  ├── Services/
  │   ├── DatabaseClient.swift           # GRDB dependency (DependencyKey)
  │   ├── StreamClient.swift             # JSONL file tail (DependencyKey)
  │   └── OrchestratorClient.swift       # HTTP API (DependencyKey)
  ├── Models/
  │   ├── MemoryEntry.swift              # Maps working_memory table
  │   ├── SoulTopic.swift                # Maps soul_topics table
  │   ├── SoulTransition.swift           # Maps soul_state_transitions table
  │   ├── UserModel.swift                # Maps user_models table
  │   ├── ShedRecord.swift               # Maps model_sheds table
  │   ├── Checkpoint.swift               # Maps wm_checkpoints table
  │   ├── SoulStreamEvent.swift          # JSONL soul-stream schema
  │   └── CognitiveTrace.swift           # Grouped trace_id → events
  ├── Design/
  │   ├── Theme.swift                    # Color system + typography
  │   ├── EntryTypeBadge.swift           # Colored badges per entry_type
  │   └── GlyphSystem.swift             # Minoan-inspired iconography
  └── Resources/
      └── Assets.xcassets
  ```

#### 1.2 Database Client (TCA Dependency)

```swift
@DependencyClient
struct DatabaseClient {
    // Working Memory
    var recentEntries: @Sendable (_ channel: String, _ limit: Int) async throws -> [MemoryEntry]
    var entriesForTrace: @Sendable (_ traceId: String) async throws -> [MemoryEntry]
    var regions: @Sendable (_ channel: String, _ threadTs: String) async throws -> [String]
    var regionEntries: @Sendable (_ channel: String, _ threadTs: String, _ region: String) async throws -> [MemoryEntry]

    // Soul State
    var topicStack: @Sendable () async throws -> [SoulTopic]
    var transitions: @Sendable (_ limit: Int) async throws -> [SoulTransition]
    var emotionalState: @Sendable () async throws -> String

    // Soul Memory
    var soulMemory: @Sendable () async throws -> [String: String]

    // User Models
    var allModels: @Sendable () async throws -> [UserModel]
    var modelSheds: @Sendable (_ entityId: String) async throws -> [ShedRecord]

    // Daimon Memory
    var daimonChannels: @Sendable () async throws -> [String]  // "daimon:*" channels
    var daimonEntries: @Sendable (_ agentName: String, _ limit: Int) async throws -> [MemoryEntry]
    var daimonLessons: @Sendable (_ agentName: String) async throws -> [MemoryEntry]

    // Sessions
    var activeSessions: @Sendable () async throws -> [Session]

    // Checkpoints
    var checkpoints: @Sendable (_ channel: String) async throws -> [Checkpoint]

    // Stats
    var entryCount: @Sendable () async throws -> Int
    var channelList: @Sendable () async throws -> [String]
}
```

#### 1.3 Stream Client (JSONL Tail — hardened)

```swift
@DependencyClient
struct StreamClient {
    var soulStream: @Sendable () -> AsyncStream<SoulStreamEvent>
    var wmStream: @Sendable () -> AsyncStream<MemoryEntry>
}
```

**Implementation** (from performance review):
- Use `DispatchSource.makeFileSystemObjectSource` on JSONL files (lower latency than FSEventStream)
- Seek to end on initial open — do NOT replay full history
- Buffer partial lines between read cycles (Python writes with `fcntl.flock`, reader may see partial lines)
- Handle `ENOENT` gracefully (files may not exist on first launch)
- Bound in-memory buffer to last 500 entries
- Parse only display fields eagerly (`phase`, `trace_id`, `entry_type`, `ts`); defer full JSON to detail views

```swift
func tailJSONL(at path: URL) -> AsyncStream<Data> {
    AsyncStream { continuation in
        let fd = open(path.path, O_RDONLY | O_EVTONLY)
        guard fd >= 0 else { continuation.finish(); return }
        // Seek to end
        lseek(fd, 0, SEEK_END)
        var offset = lseek(fd, 0, SEEK_CUR)
        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fd, eventMask: [.extend, .write],
            queue: .global(qos: .userInitiated))
        source.setEventHandler {
            // Read new bytes from offset to EOF
            // Buffer partial lines (split on \n)
            // Yield complete lines
        }
        source.resume()
        continuation.onTermination = { _ in source.cancel(); close(fd) }
    }
}
```

#### 1.4 Layout: Three-Column NavigationSplitView

```
┌──────────────┬─────────────────────────────┬───────────────────┐
│   SIDEBAR    │        MAIN CONTENT         │    INSPECTOR      │
│              │                             │                   │
│ ▸ Cognitive  │  [Live stream of cognitive  │  [Detail view of  │
│   Stream     │   events, filterable by     │   selected entry, │
│ ▸ Working    │   entry_type, channel,      │   trace, model,   │
│   Memory     │   trace_id]                 │   or daimon]      │
│ ▸ Soul State │                             │                   │
│ ▸ User Models│                             │                   │
│ ▸ Daimons    │                             │                   │
│ ▸ Sessions   │                             │                   │
│ ▸ Config     │                             │                   │
│              │                             │                   │
│ ─────────── │                             │                   │
│ SOUL STATUS  │                             │                   │
│ 😌 neutral   │                             │                   │
│ 📌 claudicle │                             │                   │
│   docs audit │                             │                   │
└──────────────┴─────────────────────────────┴───────────────────┘
```

#### 1.5 Views (Phase 1 Scope — reduced from original 11)

**Phase 1 ships 3 core views + tab navigation.** Ship a working observer before investing in three-column layout and inspector.

**Cognitive Stream** — Live tail of `soul-stream.jsonl` with phase-colored entries:
- `stimulus` (amber), `context` (slate), `cognition` (violet), `decision` (teal), `memory` (green), `response` (blue), `error` (red)
- Click any entry → sheet showing full JSON + linked trace
- Filter bar: by phase, channel, time range
- Group by trace_id toggle (collapse a full cognitive cycle into one row)
- Auto-scroll to bottom with manual scroll override

**Working Memory** — Channel selector → paginated entry list:
- Each entry: colored badge (entry_type), verb, truncated content, relative timestamp
- Click → sheet shows full content, metadata JSON, trace_id links
- Region tabs: default, summary, lessons, comms (critical for understanding compression flow)
- **Paginate to 200-500 entries** with "Load More" for history (from perf review)
- Use `IdentifiedArray` from swift-identified-collections for O(1) lookup
- Include `working_memory_archive` entries in a separate "Archive" tab

**Soul State** — Topic stack + emotional state (current values + recent transitions):
- Topic stack: ranked list (primary = bold, subtopics indented), metadata tooltips
- Emotional state: current badge + last 10 transitions as a compact table
- **Chart deferred to Phase 2** (Swift Charts windowing needed)

**Deferred to Phase 2:**
- User Models view (list + markdown rendering + shed diffs)
- Sessions view (session registry)
- Three-column NavigationSplitView layout (Phase 1 uses tab bar)
- Inspector panel (Phase 1 uses sheets)
- Daimons view (subdaimon memory grid)
- Entity graph visualization
- Compression inspector
- Config view

### Phase 2: Interactivity + Visual Polish

#### 2.1 Design System — Minoan-Daimonic Aesthetic

**Color palette** (extending the existing TUI theme):
```swift
enum SoulColor {
    // Primary spectrum (from monitor.py)
    static let violet = Color(hex: "#bb86fc")      // Primary brand
    static let teal = Color(hex: "#03dac6")         // Accent / daimonic
    static let navy = Color(hex: "#0a0a1a")         // Deep background
    static let surface = Color(hex: "#16213e")      // Panel background

    // Entry type colors (12 types → 12 hues)
    static let userMessage = Color(hex: "#64b5f6")      // Soft blue
    static let internalMonologue = Color(hex: "#ce93d8") // Lavender
    static let externalDialog = Color(hex: "#81c784")    // Soft green
    static let mentalQuery = Color(hex: "#ffb74d")       // Amber gate
    static let toolAction = Color(hex: "#4fc3f7")        // Cyan
    static let decision = Color(hex: "#fff176")          // Gold
    static let daimonicIntuition = Color(hex: "#f48fb1") // Rose
    static let onboardingStep = Color(hex: "#a5d6a7")    // Mint
    static let memorySummary = Color(hex: "#90a4ae")     // Slate
    static let soulStateShift = Color(hex: "#b39ddb")    // Deep violet
    static let lifecycle = Color(hex: "#78909c")         // Grey-blue
    static let modelShed = Color(hex: "#ffcc80")         // Warm amber

    // Emotional state gradient
    static let neutral = Color(hex: "#90a4ae")
    static let engaged = Color(hex: "#66bb6a")
    static let focused = Color(hex: "#42a5f5")
    static let sardonic = Color(hex: "#ef5350")
    static let frustrated = Color(hex: "#ff7043")
    static let absorbed = Color(hex: "#ab47bc")
    static let curious = Color(hex: "#26c6da")
}
```

**Typography**: SF Mono for data, SF Pro for labels. Daimon names in italic small-caps.

**Glyph system**: Each of the 12 entry types gets a symbolic glyph (not emoji). Each of the 12 subdaimones gets a sigil derived from their name etymology.

#### 2.2 Entity Graph Visualization

Interactive force-directed graph of user models + dossiers:
- Nodes sized by interaction count
- Edges from wiki links (`[[Entity]]`)
- Edge weight from relevance scoring signals
- Color by entity_type (user=blue, person=green, subject=amber)
- Click node → Inspector shows full model
- Backlink highlighting on hover

Implementation: **Grape** (SwiftGraphs) `ForceDirectedGraph` with `ManyBodyForce(strength: -80)`, `LinkForce()`, `CenterForce()`, `CollisionForce()`. Tested to 1,296 nodes. For >200 labeled nodes, fall back to Canvas with simplified Verlet integration. Do not use SpriteKit (no proper charge force).

#### 2.3 Cognitive Trace Drill-Down

Click any trace_id → full cognitive cycle visualization:
```
trace: a1b2c3d4e5f6
┌─────────────────────────────────────────────────┐
│ STIMULUS   │ "said" → userMessage               │
│ MONOLOGUE  │ "pondered" → internalMonologue     │
│ DIALOGUE   │ "explained" → externalDialog       │
│ GATE       │ user_model_check → true            │
│ REFLECT    │ user_model_reflection → "..."      │
│ UPDATE     │ user_model_update → [diff view]    │
│ GATE       │ soul_state_check → false           │
│ COMMIT     │ apply_output() → 6 entries written │
└─────────────────────────────────────────────────┘
```

Each step is a colored card showing the XML tag extracted, the verb, the content (expandable), and the metadata. Gates show pass/fail with green/red indicator.

#### 2.4 Compression Inspector

View what Hypermnesia compressed:
- Before/after entry counts
- Preserved entries (daimonicIntuition, decisions with result=true)
- Summary text (in summary region)
- Compression method (heuristic vs LLM)
- Archive entries (if COMPRESSION_ARCHIVE=true)
- Time range covered

### Phase 3: Ambient + Advanced

#### 3.1 Soul Stream Particle Canvas

Live ambient visualization of the soul stream — each cognitive event becomes a particle:
- **Entry type → color** (12-hue palette from Phase 2)
- **Content length → particle size** (longer entries = larger)
- **Recency → opacity** (fade over time)
- **Trace_id → cluster** (entries from same cycle orbit each other)
- **Channel → lane** (SMS particles flow left, Slack center, Telegram right)

Implementation: `MTKView` + `NSViewRepresentable` (only Metal-in-SwiftUI path). `storageModeShared` MTLBuffer on Apple Silicon (unified memory — zero CPU-GPU copy). Compute kernel updates positions, render pass draws as point primitives. Batch cognitive events into particle spawns at 30fps, not per-event. CRT phosphor overlay via `layerEffect` + `[[stitchable]]` MSL composes on top. Inspired by Tailstream's particle flow visualization.

This becomes the "screensaver" / ambient mode — the soul's cognitive activity rendered as a living particle field. Toggle between data view and ambient view.

#### 3.2 Live Session Control (via Orchestrator API)

If the orchestrator is running:
- Spawn new Claude Code sessions from the debugger
- Inject perceptions
- View orchestrator health and registered portless aliases

```swift
@DependencyClient
struct OrchestratorClient {
    var health: @Sendable () async throws -> Bool
    var orchestrate: @Sendable (_ task: String, _ cwd: String?) async throws -> OrchestratorResponse
    var injectPerception: @Sendable (_ content: String) async throws -> Void
}
```

#### 3.3 Checkpoint/Rollback UI

- Visual timeline of checkpoints for each channel
- Preview what entries would be lost on rollback
- One-click rollback with confirmation (writes to DB — only write operation in the app)

#### 3.4 Daimon Summoning Panel

- View currently summoned daimones (from soul_memory `summoned_*` keys)
- Trigger summon/dismiss via orchestrator API
- Live conversation view for summoned entity

---

## Performance Research Insights

### SQLite Concurrent Access (Critical)

The daemon's `ConnectionPool` (`daemon/memory/db.py:74`) uses `sqlite3.connect()` with no `PRAGMA journal_mode=WAL`. This means **DELETE journal mode** (SQLite default) — readers block writers and writers block readers. With the debugger polling every 500ms, every read acquires a shared lock that delays daemon commits.

**Fix (daemon-side, required before debugger):**
```python
# In ConnectionPool.__init__ or get_conn():
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=5000")
```

**Fix (Swift-side):**
```swift
var config = Configuration()
config.readonly = true
let dbPool = try DatabasePool(path: dbPath, configuration: config)
```

### Missing Indexes (Critical)

`working_memory` has zero indexes beyond the primary key. Every `get_recent()` call is a full table scan of all entries. At 10K rows with 500ms polling = 2 full scans/second.

**Fix (daemon-side, required):**
```sql
CREATE INDEX IF NOT EXISTS idx_wm_channel_thread_created
  ON working_memory(channel, thread_ts, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wm_created_at ON working_memory(created_at);
CREATE INDEX IF NOT EXISTS idx_wm_trace_id ON working_memory(trace_id);
CREATE INDEX IF NOT EXISTS idx_wm_entry_type ON working_memory(entry_type);
```

### List Performance (Architecture Decision)

10K entries in SwiftUI `List` triggers O(n) identity diffing on every update. Each update compares all 10K identities. Memory: ~120-180MB without pagination vs ~50-60MB with.

**Solution:** Paginate all GRDB queries to 200-500 entries. Use `IdentifiedArray` (swift-identified-collections). Debounce observations to max 2-3/second.

### Swift Charts Windowing

Swift Charts re-renders the entire chart on data change (no incremental rendering). 500+ points will stutter.

**Solution:** Window to last 2 hours (~50 points). Use append+trim pattern on a `@State` array. Separate historical range selector for full timeline browsing.

### Memory Budget

| Component | With Pagination | Without |
|-----------|----------------|---------|
| 500 visible WM entries | 5MB | — |
| 10K WM entries in state | — | 80MB |
| JSONL tail buffer (500) | 250KB | — |
| GRDB pool + WAL | 5MB | 5MB |
| SQLite page cache | 2MB | 2MB |
| SwiftUI baseline | 35MB | 35MB |
| **Total** | **~50-60MB** | **~120-180MB** |

Target: < 100MB. Pagination is required, not optional.

## Visual Design Research Insights

### Cognitive Visualization: Industry-Standard Four-Component Trace UI

AgentPrism (Evil Martians, 2025) proved that 4 linked views reduce debugging time 80%:

1. **Tree View** — hierarchy, parent-child steps, red highlighting for failures, progressive disclosure
2. **Timeline/Gantt** — execution order, duration, color-coded status, real-time cost accumulation
3. **Detail Panel** — input/output per step, cost breakdown, all attributes
4. **Sequence/Replay** — step-by-step playback with play/pause, decision chain visualization

All four are **linked views** with one selected-span source of truth. Click anything, everything highlights.

**Claudicle's differentiators** (nothing in the field visualizes these):
- Soul state / emotional trajectory over a session
- Working memory as a live window (in-context vs. compressed)
- Cognitive step type as a first-class visual category (12 types, not generic "spans")
- Sub-daimon invocation as a distinct trace event
- Memory tier transitions (working → soul state → user models)

### Xcode Instruments as Layout Precedent

The strongest UI pattern to adapt is Instruments' **track-based timeline with cause-and-effect annotation**:

| Instruments Track | Soul Debugger Equivalent |
|---|---|
| CPU usage | Token consumption per cognitive step |
| Memory allocation | Working memory entry count + compression events |
| Network | LLM API calls (latency, model, cost) |
| Custom event | Soul state transitions (neutral → engaged → focused) |
| Cause markers | User message received / sub-daimon invoked |
| Effect annotations | External dialogue emitted / memory written |
| Detail pane | Full cognitive cycle: stimulus → monologue → dialogue |

### Emotional State: Delta Over Absolute

Research finding (Plurai/IntellAgent, 2025): **emotional change over time is more diagnostic than emotional state at a point.** The delta, not the absolute value.

- Thin color-coded strip (always visible in sidebar)
- Area chart for intensity + direction
- Click any transition → shows trigger from `soul_state_transitions` audit log
- Transition frequency as edge weights in optional state diagram view

### Memory Tier Visualization: Three-Lane Swimlane

Three horizontal lanes (Working Memory / Soul State / User Models) with migration arrows when `modelsTheUser` or `compressesMemory` fires. Entries have tier badges. Fade-to-compressed animation when Hypermnesia runs. Staleness/TTL indicators on aged entries.

### Implementation Libraries (from visual research)

| Component | Library | Status |
|-----------|---------|--------|
| Force-directed graph | [Grape](https://github.com/SwiftGraphs/Grape) v1.1.0 | MIT, 383 stars, macOS 14+, tested to 1,296 nodes |
| Markdown rendering | [swift-markdown-ui](https://github.com/gonzalezreal/swift-markdown-ui) v2.4.1 | Maintenance mode; evaluate [Textual](https://github.com/gonzalezreal/textual) as successor |
| CRT phosphor effect | [Priva28 CRT Gist](https://gist.github.com/Priva28/c4becef12fd8dd399cc769f2c7a5c246) | `[[stitchable]]` MSL via `layerEffect`, macOS 14+, drop-in |
| Metal particles | `MTKView` + `NSViewRepresentable` | Only Metal-in-SwiftUI path; use `storageModeShared` on Apple Silicon |
| File tailing | FSEventStream → `AsyncStream` | `kFSEventStreamCreateFlagFileEvents` + offset tracking |

### CRT Phosphor Shader (Phase 3 ambient mode)

A complete `[[stitchable]]` Metal shader exists that wraps any SwiftUI content with barrel distortion, green phosphor push, scanlines, and pixel mask — zero `MTKView` needed:

```swift
CRTWrapper {
    CognitiveStreamView(store: store)
}
```

Requires macOS 14+ for `layerEffect` API. Composes with MTKView particle canvases.

### Swift Charts Performance Boundary

| Points | Behavior |
|--------|----------|
| <5,000 | Smooth 60fps |
| ~20,000 | Visible lag |
| 500,000+ | Unusable |

Rolling 500-point window = several hours of soul activity. Safe. Use `chartScrollableAxes(.horizontal)` + `chartXVisibleDomain(length: 300)` for Health-app-style scrolling.

## Alternative Approaches Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Electron + React** | Cross-platform, rich ecosystem | Heavy, non-native, breaks Claudicle's local-first ethos | Rejected — soul tools should be native |
| **Web dashboard (Next.js)** | Easy to build, shareable | Requires running a server, not local-first | Rejected — adds deployment burden |
| **Extend existing Textual TUI** | Zero new dependencies, already works | No drill-down, no graphs, terminal-only | Rejected — ceiling too low for the vision |
| **SwiftUI without TCA** | Simpler, fewer deps | State management becomes ad-hoc at scale | Rejected — 10+ features need composable state |
| **AppKit** | Maximum control | SwiftUI is more productive, TCA integrates natively | Rejected — SwiftUI + TCA is the 2026 standard |

## Acceptance Criteria

### Functional

- [ ] Read all 8 SQLite tables from `memory.db` and display their contents
- [ ] Tail `soul-stream.jsonl` and `working-memory-stream.jsonl` in real-time
- [ ] Filter cognitive stream by phase, channel, entry_type, and trace_id
- [ ] Drill into any trace_id to see the full cognitive cycle as a step sequence
- [ ] Display topic stack with rank, metadata tooltips, and transition history
- [ ] Display emotional state timeline using Swift Charts
- [ ] Render user models as formatted markdown with shed diff history
- [ ] Show all 12 subdaimones with lessons, invocations, and communication logs
- [ ] List all ensouled sessions with status badges
- [ ] Three-column layout: sidebar, main content, inspector

### Non-Functional

- [ ] macOS 15+ (Sequoia), Apple Silicon
- [ ] < 100MB memory footprint with 10K working memory entries loaded
- [ ] < 200ms latency from JSONL write to UI update
- [ ] Read-only by default (no DB writes except checkpoint rollback in Phase 3)
- [ ] Follows TCA 1.25 conventions: `@ObservableState`, no ViewStore, `@Reducer` macro

### Quality Gates

- [ ] TCA unit tests for each reducer (state transitions + effects)
- [ ] Preview providers for all views with mock data
- [ ] Dark theme matches existing monitor.py palette (deep navy + violet + teal)

## Success Metrics

- **Completeness**: All 14 debuggable state categories from the audit are visualized
- **Latency**: Soul stream events appear in < 200ms
- **Adoption**: Replaces `uv run python monitoring/monitor.py` as the primary observation tool

## Dependencies & Prerequisites

- Xcode 16+ with Swift 6 support
- macOS 15 (Sequoia) for Swift Charts + NavigationSplitView
- TCA 1.25.x via SPM
- GRDB.swift via SPM
- Claudicle daemon running (for live data — static DB reading works without daemon)
- `~/.claudicle/` directory with populated `memory.db`

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **SQLite concurrent access without WAL** | High | High | Enable WAL mode on daemon side (daemon prerequisite) |
| **No indexes on working_memory** | High | High | Add 4 indexes (daemon prerequisite) |
| GRDB schema mismatch on migration | Medium | High | Use optional/dynamic columns; version-check schema on launch |
| GRDB ValueObservation won't fire on external writes | Certain | High | Use DispatchSource on WAL file + high-water-mark queries |
| JSONL files grow unbounded (100s of MB) | Medium | Medium | Add log rotation (daemon-side); seek-to-end on app launch |
| SwiftUI List chokes on 10K entries | High | Medium | Paginate to 200-500 with IdentifiedArray |
| TCA 2.0 ships mid-development | Low | Medium | Pin to 1.25.x; EffectOf aliases forward-compatible |
| Entity graph performance at 100+ nodes | Low | Medium | Use Canvas/SpriteKit, not SwiftUI layout; limit to top-N |
| Swift Charts stutters at 500+ points | Medium | Low | Window to last 2 hours; append+trim pattern |
| Soul ID scoping in multi-soul installations | Low | Medium | Detect active soul_id from soul_memory; provide soul selector |

## Future Considerations

- **iOS companion**: Lightweight soul state viewer for iPhone (topic stack + emotional state only)
- **Kothar integration**: View Kothar's mental processes and orchestrator decisions
- **Multi-soul comparison**: Side-by-side view when multiple soul profiles are active
- **Export**: Generate soul archaeology reports as PDF/HTML
- **Notification**: macOS notifications on specific soul state transitions or error phases

## Documentation Plan

- `docs/soul-debugger.md` — User guide (installation, features, keyboard shortcuts)
- `SoulDebugger/README.md` — Developer setup, architecture, contributing
- Update `CLAUDE.md` Structure section with new app directory
- Update `docs/INDEX.md` with soul debugger guide

## Sources & References

### Internal References
- `daemon/monitoring/monitor.py` — Existing Textual TUI (layout inspiration, color palette)
- `daemon/monitoring/soul_log.py` — Soul stream JSONL schema
- `daemon/monitoring/wm_stream.py` — Working memory stream schema
- `daemon/memory/working_memory.py` — Working memory schema (12 entry types, regions, trace_id)
- `daemon/memory/soul_state.py` — Soul state schema (topic stack, transitions)
- `daemon/memory/snapshot.py` — CognitiveOutput frozen dataclass (copy-on-write pattern)
- `daemon/memory/entity_graph.py` — Multi-signal relevance scoring (4 signal types)
- `daemon/memory/daimon_memory.py` — Daimon persistent memory (channels, lessons, comms)
- `daemon/memory/model_journal.py` — ShedRecord archaeology (diffs, monologues)
- `daemon/engine/pipeline.py` — Cognitive pipeline phases
- `daemon/cognitive_steps/steps.py` — 12 cognitive step definitions
- `daemon/orchestrator.py` — HTTP gateway API
- `docs/soul-stream.md` — JSONL schema reference
- `docs/cognitive-pipeline.md` — Pipeline architecture

### External References
- [TCA 1.25.x](https://github.com/pointfreeco/swift-composable-architecture) — `@ObservableState`, `@Reducer`, tree-based navigation
- [GRDB.swift](https://github.com/groue/GRDB.swift) — SQLite for Swift, reactive reads
- [NERV UI](https://github.com/TheGreatGildo/nerv-ui) — Operations console aesthetic (CRT effects, "screen is off until data demands it")
- [AgentDbg](https://github.com/AgentDbg/AgentDbg) — Local-first agent timeline debugger
- [Tailstream](https://tailstream.io) — Particle flow log visualization
- [EvoClaw](https://github.com/slhleosun/EvoClaw) — Soul evolution with belief tags and tiered memory UI
