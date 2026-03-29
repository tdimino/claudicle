---
title: "feat: Mycelium Cognitive Layer — Soul Thinks About Files"
type: feat
status: completed
date: 2026-03-28
---

# Mycelium Cognitive Layer — Soul Thinks About Files

## Overview

The Claude Code hooks are done—they surface mycelium notes as `additionalContext` from outside the soul. This plan makes the soul *think* about file-level knowledge from inside its cognitive pipeline. Three pieces: a context region that injects notes before cognitive steps, a subprocess that decides whether to shed spores after each cycle, and a cognitive step + entry type for the pipeline to reason about file context explicitly.

## Problem Statement

The hooks layer (`mycelium-context.py`, `mycelium-arrive.sh`) runs outside the soul engine—it's Claude Code infrastructure, not Claudicle cognition. The soul itself has no awareness of mycelium. It can't:

- Reason about whether a file-level constraint applies to the current conversation
- Decide proactively to leave a note based on what it learned during a cognitive cycle
- Distinguish between mycelium context (file-anchored, cross-session) and other memory regions

The hooks inject context, but the soul doesn't *think* about it. The subprocess `shedsMyceliumSpores` closes this gap—the soul produces spores as a deliberate cognitive act, not as a side effect of a Claude Code hook.

## Proposed Solution

### Architecture

```
Perception arrives
    │
    ▼
MemoryIntegrator (context.py)
    │
    ├─ core (soul.md)
    ├─ mycelium (git notes for referenced files)  ◀── NEW
    ├─ soul state
    ├─ user models
    ├─ dossiers
    └─ user message
    │
    ▼
Cognitive Pipeline (pipeline.py)
    │
    ├─ internal_monologue
    ├─ mycelium_context (new step, conditional)    ◀── NEW
    ├─ external_dialogue
    ├─ user_model_check → user_model_update
    └─ soul_state_check → soul_state_update
    │
    ▼
apply_output() — atomic commit
    │
    ▼
Reflection Subprocesses (reflect.py)
    │
    ├─ modelsTheUser
    ├─ updatesState
    ├─ compressesMemory
    └─ shedsMyceliumSpores                         ◀── NEW
```

### Open Souls Paradigm Mapping

| Open Souls Concept | Claudicle Implementation |
|--------------------|--------------------------|
| `MemoryIntegrator` + `withRegion("mycelium")` | `context.py:build_context()` — inject notes as region between daimonic whispers and user models |
| `mentalQuery` gate | `mycelium_context` cognitive step with `category="gate"` — "Does this conversation involve specific files?" |
| `learnsAboutTheUser` subprocess | `shedsMyceliumSpores` subprocess — gate → reflect → write note |
| `useSoulMemory` | `process_memory.set("shedsMyceliumSpores", ...)` for composting thresholds |
| `useProcessMemory` | Per-cycle spore tracking (reset on process transition) |

## Technical Approach

### Phase 1: Context Region (`mycelium` region in `build_context()`)

**File:** `daemon/engine/context.py`

**What:** Insert a mycelium region between daimonic whispers (line ~229) and user models (line ~232). Extract file paths from the current perception, run `mycelium.sh context <file>` for each, format as context.

**How:**

```python
# daemon/engine/mycelium_bridge.py (new file)

import os
import re
import subprocess
import threading

_mycelium_available: bool | None = None
_lock = threading.Lock()


def _check_available() -> bool:
    """Check if mycelium.sh is installed and we're in a git repo."""
    global _mycelium_available
    with _lock:
        if _mycelium_available is not None:
            return _mycelium_available
        try:
            result = subprocess.run(
                ["which", "mycelium.sh"],
                capture_output=True, timeout=2,
            )
            _mycelium_available = result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            _mycelium_available = False
        return _mycelium_available


def get_repo_root(cwd: str | None = None) -> str | None:
    """Get git repo root, or None if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
            cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass
    return None


def extract_file_paths(text: str) -> list[str]:
    """Extract plausible file paths from text."""
    patterns = [
        r'`([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})`',
        r'(?:^|\s)([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})(?:\s|$|[,;:\)])',
    ]
    paths = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1)
            if not path.startswith(("http", "www.", "//")):
                paths.add(path)
    return list(paths)[:5]


def get_mycelium_context(file_paths: list[str], repo_root: str) -> str | None:
    """Get mycelium notes for the given file paths. Best-effort, non-blocking."""
    if not _check_available():
        return None

    notes = []
    for fp in file_paths:
        try:
            result = subprocess.run(
                ["mycelium.sh", "context", fp],
                capture_output=True, text=True, timeout=2,
                cwd=repo_root,
            )
            if result.returncode == 0 and result.stdout.strip():
                notes.append(result.stdout.strip())
        except (subprocess.SubprocessError, OSError):
            continue

    if not notes:
        return None
    return "\n---\n".join(notes)


def write_spore(
    file_path: str, kind: str, body: str,
    slot: str = "", repo_root: str | None = None,
) -> bool:
    """Write a mycelium note. Best-effort, non-blocking."""
    if not _check_available():
        return False

    cmd = ["mycelium.sh", "note", file_path, "-k", kind, "-m", body]
    if slot:
        cmd.extend(["--slot", slot])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=5,
            cwd=repo_root,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
```

**Injection in `build_context()`** (after daimonic whispers, ~line 229):

```python
# Mycelium region — file-level knowledge from git notes
file_paths = mycelium_bridge.extract_file_paths(text)
if file_paths:
    repo_root = mycelium_bridge.get_repo_root()
    if repo_root:
        mycelium_notes = mycelium_bridge.get_mycelium_context(file_paths, repo_root)
        if mycelium_notes:
            _log_decision(channel, thread_ts, trace_id, "mycelium_context",
                          True, f"Injected notes for {len(file_paths)} file(s)")
            parts.append(f"## File Knowledge (Mycelium)\n\n{mycelium_notes}")
        else:
            _log_decision(channel, thread_ts, trace_id, "mycelium_context",
                          False, "No mycelium notes found for referenced files")
```

**Success criteria:** `mycelium.sh context economy.rs` output appears in the soul's context between daimonic whispers and user models. Decision gate logged.

### Phase 2: Cognitive Step (`mycelium_context`)

**File:** `daemon/cognitive_steps/steps.py`

**What:** A conditional cognitive step that fires when the monologue mentions specific files. The soul reflects on whether mycelium constraints apply.

```python
CognitiveStep(
    name="mycelium_context",
    prompt=dedent("""\
        {soul_name} is aware of file-level knowledge (constraints, warnings,
        decisions) from prior sessions. Review the mycelium notes in context
        and consider:
        - Do any constraints apply to what's being discussed?
        - Are there warnings about fragile areas being touched?
        - Is there a decision that explains why something is the way it is?

        If file knowledge is relevant, note how it shapes your response.
        If not, say "No file context applies."
    """),
    xml_tag="mycelium_context",
    category="conditional",
    description="Reflect on file-level mycelium notes when files are referenced",
)
```

**Entry type:** `myceliumContext` (camelCase per convention)

**XML tag:** `<mycelium_context>` (snake_case per convention)

**Pipeline insertion** (`pipeline.py`): After `internal_monologue`, before `external_dialogue`. Conditional on mycelium region being non-empty in the context.

```python
# After monologue, before dialogue — only if mycelium context was injected
if mycelium_injected:
    content, verb, raw_step = await _run_step(
        "mycelium_context", shared_context, prior, trace_id, channel
    )
    if content:
        output = output.with_entry("myceliumContext", content, verb=verb, trace_id=trace_id)
        prior += raw_step
```

**format_for_prompt()** addition in `working_memory.py` (~line 465):

```python
elif entry_type == "myceliumContext":
    display = f"[file context] {content[:200]}"
```

**Success criteria:** When mycelium notes are in context and the soul discusses files, the `<mycelium_context>` tag appears in the response. Stored as `myceliumContext` entry type.

### Phase 3: Subprocess (`shedsMyceliumSpores`)

**File:** `daemon/engine/reflect.py`

**What:** After the main cognitive cycle, decide whether the soul learned something worth preserving as a mycelium note. Follows the `learnsAboutTheUser` pattern.

```python
def _execute_shed_spores(raw, channel, thread_ts, trace_id, ctx) -> dict:
    """Subprocess: decide whether to shed a mycelium spore."""
    import importlib
    mycelium_bridge = importlib.import_module("engine.mycelium_bridge")

    result = {"check": False, "shed": False, "file": None, "kind": None}

    # Only run in git repos with mycelium
    repo_root = mycelium_bridge.get_repo_root()
    if not repo_root:
        return result

    # Extract monologue content from this cycle
    monologue = ctx.get("monologue_content", "")
    if not monologue:
        return result

    # Gate: did the monologue reference specific files with novel insight?
    file_paths = mycelium_bridge.extract_file_paths(monologue)
    if not file_paths:
        return result

    result["check"] = True

    # Heuristic gate: does the monologue contain decision/warning language?
    spore_signals = [
        "because", "must", "should not", "constraint", "warning",
        "decided", "chose", "requires", "breaks if", "depends on",
    ]
    signal_count = sum(1 for s in spore_signals if s in monologue.lower())
    if signal_count < 2:
        return result

    # Extract the insight and classify the kind
    for keyword, kind in [
        ("warning", "warning"), ("constraint", "constraint"),
        ("decided", "decision"), ("chose", "decision"),
        ("because", "context"),
    ]:
        if keyword in monologue.lower():
            # Truncate to 500 chars for note body
            body = monologue[:500].strip()
            target_file = file_paths[0]

            success = mycelium_bridge.write_spore(
                file_path=target_file,
                kind=kind,
                body=body,
                slot=config.SOUL_NAME.lower(),
                repo_root=repo_root,
            )

            if success:
                result["shed"] = True
                result["file"] = target_file
                result["kind"] = kind

                # Record in working memory
                working_memory.add(
                    channel=channel,
                    thread_ts=thread_ts,
                    user_id="system",
                    entry_type="myceliumSpore",
                    content=f"Shed {kind} spore on {target_file}: {body[:100]}...",
                    trace_id=trace_id,
                    region="mycelium",
                )

                # Track in process memory
                count = process_memory.get(
                    "shedsMyceliumSpores", "total_spores", default=0
                )
                process_memory.set(
                    "shedsMyceliumSpores", "total_spores", count + 1
                )
            break

    return result
```

**Registration** (append to `SUBPROCESSES` in `reflect.py:290`):

```python
SUBPROCESSES = [
    Subprocess("modelsTheUser", _execute_models_user),
    Subprocess("updatesState", _execute_updates_state),
    Subprocess("compressesMemory", _execute_compression),
    Subprocess("shedsMyceliumSpores", _execute_shed_spores),  # NEW
]
```

**Success criteria:** After a cognitive cycle where the soul reasons about a specific file with decision/warning language, a mycelium note appears in git notes. `myceliumSpore` entry in working memory. Soul stream JSONL shows subprocess start/end.

### Phase 4: Repo Discovery

**Problem:** The daemon runs as a background process. How does it know which git repo the conversation is about?

**Solution:** Use the `cwd` from the Claude Code session that spawned the daemon. The daemon already knows its working directory via `config.py`. For terminal sessions, `os.getcwd()` at daemon start. For Slack/SMS/Telegram, no git repo applies—mycelium features degrade gracefully (bridge functions return `None`, subprocess returns `{"check": False}`).

```python
# In mycelium_bridge.py — cache repo root per daemon lifetime
_repo_root_cache: str | None = None

def get_repo_root(cwd: str | None = None) -> str | None:
    global _repo_root_cache
    if _repo_root_cache is not None:
        return _repo_root_cache if _repo_root_cache != "" else None
    # ... detect and cache ...
```

For the orchestrator API (`POST /api/orchestrate`), the `cwd` field in the request body specifies the repo.

## System-Wide Impact

### Interaction Graph

Perception arrives → `build_context()` extracts file paths from message → `mycelium_bridge.get_mycelium_context()` shells out to `mycelium.sh context` (2s timeout) → notes injected as `## File Knowledge (Mycelium)` region → pipeline runs `mycelium_context` step (conditional) → soul reasons about file constraints → `apply_output()` commits entries → `shedsMyceliumSpores` subprocess checks monologue for spore-worthy content → `mycelium_bridge.write_spore()` shells out to `mycelium.sh note` (5s timeout) → `myceliumSpore` entry written to working memory.

### Error Propagation

- `mycelium.sh` not installed → `_check_available()` returns `False`, all functions return `None`/`False`
- Not in git repo → `get_repo_root()` returns `None`, context region skipped, subprocess returns early
- `mycelium.sh` timeout → `SubprocessError` caught, function returns `None`/`False`
- Git lock contention → `mycelium.sh` fails, caught by try/except, logged but not fatal
- **No error blocks the response pipeline.** Follows `git_tracker.py` best-effort pattern.

### State Lifecycle Risks

- **Orphaned spores:** If the daemon writes a spore but the conversation is abandoned, the note persists in git. This is by design—spores are durable.
- **Concurrent writes:** Multiple daemon instances in the same repo could write conflicting notes. Mitigated by mycelium's slot system—each soul instance writes to its own slot.
- **Composting debt:** Automated composting is handled by the Claude Code `mycelium-depart.sh` hook, not the daemon. The daemon only writes; it never composts.

### API Surface Parity

- **Terminal channel:** Full support (daemon has cwd in a git repo).
- **Slack/SMS/Telegram:** Graceful no-op (no git repo).
- **Orchestrator API:** Full support via `cwd` field in request body.
- **Unified launcher:** Full support (inherits cwd from Claude Code session).

## Acceptance Criteria

### Functional

- [ ] `mycelium_bridge.py` created with `get_repo_root()`, `get_mycelium_context()`, `write_spore()`, `extract_file_paths()`
- [ ] `build_context()` injects mycelium region when file paths found in perception
- [ ] Decision gate logged for mycelium context injection
- [ ] `mycelium_context` cognitive step registered in `STEP_INSTRUCTIONS`
- [ ] `myceliumContext` entry type renders in `format_for_prompt()`
- [ ] `shedsMyceliumSpores` subprocess appended to `SUBPROCESSES` list
- [ ] Subprocess writes notes via `mycelium.sh note` with soul name as slot
- [ ] `myceliumSpore` entries stored in working memory with `region="mycelium"`
- [ ] Graceful degradation: all features no-op outside git repos or without mycelium installed

### Non-Functional

- [ ] `mycelium.sh` calls have 2s (read) / 5s (write) timeouts
- [ ] No `mycelium.sh` failure blocks the response pipeline
- [ ] Thread-safe availability check with `threading.Lock`
- [ ] Repo root cached per daemon lifetime
- [ ] All entry types follow `camelCase`, XML tags follow `snake_case`

### Testing

- [ ] Unit test: `mycelium_bridge.extract_file_paths()` extracts paths from conversation text
- [ ] Unit test: `mycelium_bridge` functions return `None`/`False` when mycelium not installed
- [ ] Integration test: `build_context()` includes mycelium region when notes exist
- [ ] Integration test: subprocess writes note when monologue contains file insights
- [ ] Sandbox test: `python3 scripts/sandbox.py --message "Tell me about economy.rs"` shows mycelium context

## Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| `mycelium.sh` subprocess latency (~100ms per call) | 2s timeout, cached availability check, max 5 files per perception |
| git lock contention with concurrent Claude Code sessions | Mycelium slots prevent write conflicts; read contention is harmless |
| Gratuitous spore generation flooding git notes | Heuristic gate (2+ signal words), max 1 spore per cognitive cycle |
| Daemon cwd not in a git repo (Slack/SMS channels) | `get_repo_root()` returns `None`, all features degrade to no-op |
| Stale availability cache after `mycelium.sh` install mid-session | Acceptable—daemon restart clears cache. Not worth polling. |

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `daemon/engine/mycelium_bridge.py` | **Create** | Bridge module: availability check, repo discovery, note read/write, file extraction |
| `daemon/engine/context.py` | **Modify** | Inject mycelium region in `build_context()` (~line 229) |
| `daemon/cognitive_steps/steps.py` | **Modify** | Register `mycelium_context` CognitiveStep |
| `daemon/engine/pipeline.py` | **Modify** | Add conditional `mycelium_context` step after monologue |
| `daemon/engine/reflect.py` | **Modify** | Add `shedsMyceliumSpores` to SUBPROCESSES list |
| `daemon/memory/working_memory.py` | **Modify** | Add `myceliumContext` and `myceliumSpore` rendering in `format_for_prompt()` |
| `docs/extending-claudicle.md` | **Modify** | Document mycelium as extension example |
| `CLAUDE.md` | **Modify** | Add `myceliumContext` and `myceliumSpore` to entry types list |

## Sources & References

### Internal (Claudicle)
- `daemon/cognitive_steps/steps.py:87-101` — CognitiveStep dataclass
- `daemon/engine/context.py:171-343` — build_context() assembly order
- `daemon/engine/pipeline.py:330-443` — run_pipeline() execution flow
- `daemon/engine/reflect.py:48-50, 290-294` — Subprocess registration
- `daemon/memory/working_memory.py:103-141` — add() signature
- `daemon/memory/git_tracker.py` — best-effort subprocess pattern
- `daemon/memory/process_memory.py` — cross-invocation subprocess state
- `docs/extending-claudicle.md` — extension guide

### Internal (Open Souls references)
- `skills/open-souls-paradigm/references/memory-regions.md` — withRegion() API
- `skills/open-souls-paradigm/references/subprocesses.md` — learnsAboutTheUser pattern
- `skills/open-souls-paradigm/references/cognitive-steps.md` — pure function mapping

### External
- [Mycelium](https://github.com/openprose/mycelium) — git notes CLI
- Prior plan: `~/Desktop/Programming/docs/plans/2026-03-28-002-feat-mycelium-claudicle-daimonic-spores-plan.md` — hooks layer (completed)
