---
title: "feat: Daimonic Evolution — Invisible Daemon, Self-Initiating Sub-daimones, Per-Request IPC"
type: feat
status: active
date: 2026-03-25
---

# Daimonic Evolution — Invisible Daemon, Self-Initiating Sub-daimones, Per-Request IPC

## Overview

Three-phase architectural evolution of Claudicle's daemon layer, applying patterns from CocoIndex's invisible daemon architecture and Riley Tomasek's AI daemon concept. Transforms the daemon from a manually-started process with on-demand sub-daimones and tightly-coupled adapters into an invisible, self-healing process with persistent role-based cognitive watchers and per-request IPC.

**Core insight from Riley Tomasek**: "Agents complete tasks. Daemons fulfill roles." The sub-daimones were always conceived as ongoing presences, not one-shot tools. This plan makes that real.

**Core insight from CocoIndex**: "When debugging gets complex, question the design." Per-request connections eliminate entire categories of bugs — leaked connections, stale state, shutdown races — by construction.

## Problem Statement

### Current State

1. **Manual daemon lifecycle.** `claudicle.py` requires explicit `python3 claudicle.py` or `python3 slack_listen.py --bg`. Hooks (`soul-activate.py`) register sessions but never check if the daemon is running. No version handshake. No auto-restart. No health detection.

2. **On-demand sub-daimones.** All 12 sub-daimones are invoked as Task-tool subagents: boot via `soul-context.py`, run one assessment, return output. They don't watch, accumulate context, or initiate action. Maintenance work (memory compression, soul.md drift detection, user model staleness) requires human attention to notice and prompt.

3. **Tight adapter coupling.** The unified launcher imports adapters and `claude_handler` into the same process. Adapter crashes take down the soul engine. The SMS adapter works around this by duplicating the entire prompt-building pipeline and calling `claude -p` as a subprocess. The shared memory adapter (`claudicle_memory.py`) uses `sys.path.insert(0, DAEMON_DIR)` to import daemon modules directly — import-coupled, not IPC.

### Consequences

- No soul daemon running after a reboot unless the user remembers to start it
- Memory compression only happens during terminal reflection or when explicitly triggered
- Soul.md drifts from accumulated experience because Themistokles only runs when invoked
- User models go stale because Eikon doesn't watch for new interaction patterns
- An adapter crash in Slack kills processing for all channels
- SMS adapter has its own `build_prompt()` that diverges from the soul engine's version

## Proposed Solution

Three phases, each independently shippable, each building on the previous:

| Phase | Deliverable | Key Pattern |
|-------|-------------|-------------|
| **1. Invisible Daemon** | Auto-start, version handshake, resource-closure shutdown | CocoIndex: "users should never think about the daemon" |
| **2. Watcher Roles** | 4 persistent sub-daimon watchers on JSONL streams | Tomasek: "daemons fulfill roles, not tasks" |
| **3. Per-Request IPC** | `POST /api/process`, adapters as thin clients | CocoIndex: "per-request connections can't leak by construction" |

## Technical Approach

### Architecture

```
                                    Phase 1: Invisible Daemon
                                    ┌─────────────────────────────────┐
                                    │  Claudicle Daemon               │
  Claude Code hooks ───auto-start──►│  ┌──────────────────────────┐   │
  /ensoul command  ───auto-start──►│  │  Soul Engine              │   │
                                    │  │  (build_prompt, parse,    │   │
  Phase 3: Per-Request IPC         │  │   apply_output)           │   │
  ┌──────────┐  POST /api/process  │  └──────────────────────────┘   │
  │ SMS      ├────────────────────►│                                  │
  │ adapter  │◄────────────────────│  Phase 2: Watcher Roles          │
  └──────────┘   response + close  │  ┌──────────────────────────┐   │
  ┌──────────┐  POST /api/process  │  │  StreamTailer             │   │
  │ Telegram ├────────────────────►│  │  ┌─────┐ ┌──────┐        │   │
  │ adapter  │◄────────────────────│  │  │Hyper│ │Themis│ ...    │   │
  └──────────┘                     │  │  │mnsia│ │tokles│        │   │
                                    │  │  └──┬──┘ └──┬───┘        │   │
  Phase 1 (in-process, legacy)     │  │     │       │             │   │
  ┌──────────┐  asyncio.Queue     │  │     ▼       ▼             │   │
  │ Slack    ├────────────────────►│  │  wm_stream  soul_log      │   │
  │ adapter  │                     │  └──────────────────────────┘   │
  └──────────┘                     │                                  │
                                    │  PID: $CLAUDICLE_HOME/claudicle.pid
                                    │  API: http://claudicle-api.localhost
                                    └─────────────────────────────────┘
```

### Implementation Phases

---

#### Phase 1: Invisible Daemon Lifecycle

**Goal**: Users never think about the daemon. It starts when needed, restarts on upgrade, shuts down cleanly.

##### 1.1 — Daemon PID File and Liveness Protocol

**New file**: `daemon/lifecycle.py`

```python
# Core daemon lifecycle primitives
PIDFILE = Path(os.environ.get("CLAUDICLE_HOME", "~/.claudicle")).expanduser() / "claudicle.pid"
VERSION_FILE = Path(__file__).parent / "VERSION"  # written at install time

def read_pid() -> int | None: ...
def is_alive(pid: int) -> bool: ...         # os.kill(pid, 0) + /proc check
def write_pid(pid: int) -> None: ...        # atomic write via tempfile + rename
def remove_pid() -> None: ...               # called as last cleanup step
def read_version() -> str: ...              # from VERSION file
def daemon_version() -> str | None: ...     # from /api/health if daemon running
```

**Startup lock**: Use `fcntl.flock(LOCK_EX | LOCK_NB)` on the PID file during the start sequence. First caller wins; second detects lock and waits with backoff (100ms, 200ms, 400ms, up to 5 retries). This prevents the concurrent-hook race condition identified by SpecFlow (Gap 1).

**PID file contents**: `{pid}\n{version}\n{start_time_iso}` — three lines for disambiguation against PID recycling. The liveness check validates both PID and start time against `/proc/{pid}/stat` creation time (Linux) or `sysctl kern.proc.pid` (macOS).

##### 1.2 — Version Handshake

**Version string**: Semantic version in `daemon/VERSION`, written by `setup.sh` from git tag or `pyproject.toml`. Format: `0.X.Y` (e.g., `0.15.0`).

**Handshake endpoint**: Extend `/api/health` response:

```json
{
  "status": "ok",
  "version": "0.15.0",
  "config_hash": "a1b2c3d4",
  "uptime_seconds": 3421,
  "watchers": {}
}
```

**Config hash**: SHA-256 of the sorted, serialized global config values that require restart (soul personality path, provider list, `SOUL_NAME`, `CLAUDICLE_HOME`). Computed at daemon startup, returned in health response. Client compares against its own computation.

**Mismatch behavior**:
- Version mismatch on first connection: stop old daemon, start new one (CocoIndex pattern)
- Config hash mismatch: warn in hook's `additionalContext`, suggest `/restart-daemon`
- Subsequent connections in same session: raise error (unusual — daemon replaced mid-session)

##### 1.3 — Auto-Start from Hooks

**Modified file**: `hooks/soul-activate.py`

Add daemon auto-start to the existing SessionStart hook:

```python
def ensure_daemon():
    """Auto-start daemon if not running. Fire-and-forget."""
    pid = lifecycle.read_pid()
    if pid and lifecycle.is_alive(pid):
        # Daemon running — check version
        remote_version = lifecycle.daemon_version()
        if remote_version and remote_version != lifecycle.read_version():
            # Version mismatch — restart
            lifecycle.stop_daemon(pid)
        else:
            return  # Daemon healthy

    # Start daemon as detached background process
    subprocess.Popen(
        [sys.executable, "-m", "claudicle", "--daemon"],
        cwd=DAEMON_DIR,
        start_new_session=True,
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
    )
    # Don't wait — daemon will be available by next hook invocation
```

**Fire-and-forget design** (SpecFlow Gap 2): The hook does NOT wait for the daemon to finish starting. Hook timeout budget is limited; daemon startup involves aiohttp init, SQLite migrations, and portless registration. The hook proceeds with existing disk-based soul context injection. The daemon will be available for the *next* hook invocation or for adapter connections.

**Modified file**: `commands/ensoul.md` — add `ensure_daemon()` call after soul marker creation.

##### 1.4 — Resource-Closure Shutdown

**Modified file**: `daemon/claudicle.py`

Replace the current `_shutdown()` with the CocoIndex pattern:

```python
# Current: imperative stop-the-world
async def _shutdown(self):
    self._shutting_down = True
    self._ui.stop()
    if self._slack: self._slack.stop()
    ...

# New: resource-closure, drain-first
async def _shutdown(self):
    self._shutting_down = True

    # 1. Stop accepting new connections
    if self._orchestrator:
        await self._orchestrator.stop()  # closes aiohttp listener

    # 2. Drain in-flight queue items (5s timeout)
    try:
        await asyncio.wait_for(self._drain_queue(), timeout=5.0)
    except asyncio.TimeoutError:
        pass

    # 3. Stop watchers (Phase 2)
    await self._stop_watchers()

    # 4. Stop adapters
    for adapter in [self._slack, self._discord, self._telegram]:
        if adapter:
            adapter.stop()

    # 5. Close resources
    session_store.close()
    soul_memory.close()
    memory_pool.close()

    # 6. Remove PID file (completion signal)
    lifecycle.remove_pid()

    # 7. Fast exit (skip Python teardown)
    if threading.current_thread() is threading.main_thread():
        os._exit(0)
```

**Signal handling**: SIGTERM and SIGINT call `loop.stop()`, which causes `run_forever()` to return into a `finally` block that runs `_shutdown()`. The CocoIndex pattern: event loop on the main thread, accept loop in a background thread.

##### 1.5 — Two-Level Config

**Modified file**: `daemon/config.py`

Classify settings into two tiers:

| Tier | Examples | Staleness detection | Reload strategy |
|------|----------|--------------------|----|
| **Global** (daemon-wide state) | `SOUL_NAME`, `SOUL_PROFILE`, provider list, `CLAUDICLE_HOME`, `API_TOKEN` | Config hash in `/api/health` | Daemon restart required |
| **Per-operation** (read fresh) | `COMPRESSION_THRESHOLD`, `WATCHER_*` params, `STIMULUS_VERB_ENABLED`, per-channel toggles | None needed | Read at operation time |

Add to `Settings`:

```python
@property
def global_config_hash(self) -> str:
    """Hash of values that require daemon restart when changed."""
    import hashlib
    vals = sorted([
        ("SOUL_NAME", self.SOUL_NAME),
        ("CLAUDICLE_HOME", str(self.CLAUDICLE_HOME)),
        ("SOUL_PROFILE", self.SOUL_PROFILE or ""),
        # ... other global values
    ])
    return hashlib.sha256(str(vals).encode()).hexdigest()[:8]
```

Per-operation settings re-read from `config.py` at call time. Since Pydantic `BaseSettings` reads env vars at instantiation, per-operation callers instantiate a fresh `Settings()` object or call `settings.model_validate({})` to refresh from current env.

##### Phase 1 Files Changed

| File | Change |
|------|--------|
| `daemon/lifecycle.py` | **New** — PID file, liveness, version, startup lock |
| `daemon/VERSION` | **New** — Semantic version string |
| `daemon/claudicle.py` | Shutdown rewrite, daemon mode flag (`--daemon`), signal handlers |
| `daemon/orchestrator.py` | Extend `/api/health` with version, config_hash, uptime |
| `daemon/config.py` | `global_config_hash` property, tier classification |
| `hooks/soul-activate.py` | Add `ensure_daemon()` auto-start |
| `commands/ensoul.md` | Add `ensure_daemon()` call |
| `scripts/claudicle-gc.py` | Use `lifecycle.py` primitives instead of ad-hoc PID handling |

##### Phase 1 Acceptance Criteria

- [ ] Daemon auto-starts on SessionStart hook when not running
- [ ] Daemon auto-restarts when version mismatch detected by hook
- [ ] PID file written atomically with startup lock preventing concurrent starts
- [ ] `/api/health` returns version, config_hash, uptime
- [ ] Config hash mismatch triggers warning in hook `additionalContext`
- [ ] Shutdown completes in <1 second (resource closure, no signal polling)
- [ ] Stale PID file (dead process) cleaned up on next hook invocation
- [ ] `--daemon` flag detaches from terminal, writes PID file, redirects to log
- [ ] All 927 existing tests pass (lifecycle.py has its own test file)

---

#### Phase 2: Self-Initiating Sub-Daimon Watcher Roles

**Goal**: Four sub-daimones become persistent, self-initiating watchers that tail JSONL streams and act on matching events. No human prompts. Zero marginal attention.

##### 2.1 — StreamTailer: Generic JSONL Subscription

**New file**: `daemon/monitoring/stream_tailer.py`

```python
@dataclass
class StreamTailer:
    """Tail a JSONL file with rotation handling.

    Handles: initial seek to end, line-by-line yield, EOF wait,
    inode-change detection (rotation), and reconnection.
    """
    path: Path
    poll_interval: float = 1.0  # seconds between EOF checks

    async def tail(self) -> AsyncIterator[dict]:
        """Yield parsed JSONL entries as they appear."""
        fd = open(self.path, "r")
        fd.seek(0, 2)  # seek to end
        inode = os.fstat(fd.fileno()).st_ino

        while True:
            line = fd.readline()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue  # skip malformed lines
            else:
                # EOF — check for rotation
                try:
                    current_inode = os.stat(self.path).st_ino
                except FileNotFoundError:
                    await asyncio.sleep(self.poll_interval)
                    continue
                if current_inode != inode:
                    # File rotated — reopen from beginning
                    fd.close()
                    fd = open(self.path, "r")
                    inode = current_inode
                else:
                    await asyncio.sleep(self.poll_interval)
```

This addresses SpecFlow Gap 7 (JSONL rotation handling) via inode comparison.

##### 2.2 — Watcher Framework

**New file**: `daemon/watchers/base.py`

```python
@dataclass
class WatcherConfig:
    name: str
    stream: str  # "soul_log" or "wm_stream"
    debounce_seconds: float = 30.0
    max_fires_per_hour: int = 10
    enabled: bool = True

class Watcher(ABC):
    """Base class for persistent sub-daimon watchers."""

    def __init__(self, config: WatcherConfig):
        self.config = config
        self.state = "stopped"  # stopped | running | rate_limited | error
        self.last_fired: datetime | None = None
        self.fires_total: int = 0
        self._window: deque[dict] = deque(maxlen=100)  # sliding window

    @abstractmethod
    def should_fire(self, entry: dict, window: deque[dict]) -> bool:
        """Return True if this entry (plus window context) should trigger."""
        ...

    @abstractmethod
    async def execute(self, trigger_entry: dict, window: deque[dict]) -> CognitiveOutput | None:
        """Run the watcher's cognitive function. Return output for apply_output()."""
        ...

    async def run(self, tailer: StreamTailer):
        """Main watcher loop."""
        self.state = "running"
        async for entry in tailer.tail():
            self._window.append(entry)
            if not self._rate_ok():
                continue
            if self.should_fire(entry, self._window):
                try:
                    output = await self.execute(entry, self._window)
                    if output:
                        apply_output(output)  # commit to working memory
                    self.last_fired = datetime.now()
                    self.fires_total += 1
                except Exception as e:
                    logger.warning(f"Watcher {self.config.name} error: {e}")
                    self.state = "error"
                    await asyncio.sleep(self.config.debounce_seconds * 2)  # backoff
                    self.state = "running"
```

##### 2.3 — Four Concrete Watchers

**Decision**: Exclude Bohen from the initial watcher set (SpecFlow Gap 12). Bohen's verification role maps to implementation events (git, test output), not JSONL stream entries. Keep it as on-demand Task invocation. Revisit after Phase 2 ships.

**New files**: `daemon/watchers/{hypermnesia,themistokles,eikon,leb}.py`

| Watcher | Stream | Trigger Condition | Debounce | Max/hr | Channel |
|---------|--------|-------------------|----------|--------|---------|
| **Hypermnesia** | `wm_stream` | `count(entry_type in [userMessage, externalDialog] in window) > COMPRESSION_THRESHOLD` | 5 min | 6 | `daimon:hypermnesia` |
| **Themistokles** | `soul_log` | `count(phase="response" in window) > 20` AND `hours_since_last_fire > 24` | 24 hr | 1 | `daimon:themistokles` |
| **Eikon** | `wm_stream` | `entry.metadata.get("user_model_check") == True` OR `entry_type == "userMessage" AND user_id not seen in last N fires` | 10 min | 4 | `daimon:eikon` |
| **Leb** | `soul_log` | `phase == "response" AND (elapsed_ms > 5000 OR entry.metadata.get("emotional_shift"))` | 2 min | 10 | `daimon:leb` |

Each watcher uses `llm_client.call_llm()` (from `engine/llm_client.py`) with the cheapest available provider. Default: Groq free tier (`REFLECT_PROVIDER`). Fallback: Ollama local.

**Watcher output routing** (SpecFlow Gap 10): Each watcher writes to its own channel (`daimon:{name}`) with the 30-day TTL from `DAIMON_MEMORY_TTL_HOURS`. The trigger entry's `channel` and `thread_ts` are stored in the output metadata for traceability, but the watcher's output is its own cognitive product, not a thread reply.

##### 2.4 — Watcher Lifecycle in Daemon

**Modified file**: `daemon/claudicle.py`

```python
class Claudicle:
    async def _start_watchers(self):
        """Start all enabled watchers as asyncio tasks."""
        self._watcher_tasks = {}
        for watcher_cls in [HypermnesiaWatcher, ThemistoklesWatcher, EikonWatcher, LebWatcher]:
            config = watcher_cls.default_config()
            if not config.enabled:
                continue
            watcher = watcher_cls(config)
            stream_path = self._stream_path(config.stream)
            tailer = StreamTailer(stream_path)
            task = asyncio.create_task(watcher.run(tailer), name=f"watcher:{config.name}")
            self._watcher_tasks[config.name] = (watcher, task)

    async def _stop_watchers(self):
        """Cancel all watcher tasks."""
        for name, (watcher, task) in self._watcher_tasks.items():
            task.cancel()
            watcher.state = "stopped"
        await asyncio.gather(
            *[t for _, t in self._watcher_tasks.values()],
            return_exceptions=True
        )
```

**Watcher status in health endpoint** (SpecFlow Gap 20):

```json
{
  "watchers": {
    "hypermnesia": {"state": "running", "last_fired": "2026-03-25T14:02:00Z", "fires_total": 42},
    "themistokles": {"state": "running", "last_fired": "2026-03-24T08:00:00Z", "fires_total": 3},
    "eikon": {"state": "rate_limited", "last_fired": "2026-03-25T14:10:00Z", "fires_total": 18},
    "leb": {"state": "running", "last_fired": "2026-03-25T14:15:00Z", "fires_total": 107}
  }
}
```

##### 2.5 — Watcher Configuration

**Modified file**: `daemon/config.py`

```python
# Per-watcher toggles and tuning (per-operation tier — read fresh)
WATCHER_HYPERMNESIA_ENABLED: bool = True
WATCHER_HYPERMNESIA_DEBOUNCE: int = 300       # seconds
WATCHER_HYPERMNESIA_MAX_PER_HOUR: int = 6
WATCHER_THEMISTOKLES_ENABLED: bool = True
WATCHER_THEMISTOKLES_DEBOUNCE: int = 86400    # 24 hours
WATCHER_EIKON_ENABLED: bool = True
WATCHER_EIKON_DEBOUNCE: int = 600             # 10 min
WATCHER_LEB_ENABLED: bool = True
WATCHER_LEB_DEBOUNCE: int = 120               # 2 min
WATCHER_PROVIDER: str = "groq"                # cheapest available
WATCHER_MODEL: str = ""                       # provider default
```

##### Phase 2 Files Changed

| File | Change |
|------|--------|
| `daemon/monitoring/stream_tailer.py` | **New** — Generic JSONL tail with rotation handling |
| `daemon/watchers/__init__.py` | **New** — Package init |
| `daemon/watchers/base.py` | **New** — Watcher ABC, WatcherConfig, run loop |
| `daemon/watchers/hypermnesia.py` | **New** — Memory compression watcher |
| `daemon/watchers/themistokles.py` | **New** — Constitutional review watcher |
| `daemon/watchers/eikon.py` | **New** — User model update watcher |
| `daemon/watchers/leb.py` | **New** — Reflection/subtext watcher |
| `daemon/claudicle.py` | `_start_watchers()`, `_stop_watchers()`, watcher tasks |
| `daemon/orchestrator.py` | Per-watcher status in `/api/health` |
| `daemon/config.py` | `WATCHER_*` settings (per-operation tier) |

##### Phase 2 Acceptance Criteria

- [ ] StreamTailer handles: normal tail, EOF wait, file rotation (inode change), missing file
- [ ] Four watchers start as asyncio tasks on daemon startup
- [ ] Each watcher fires only when its trigger condition is met (not on every entry)
- [ ] Debounce and max-per-hour rate limiting prevents token waste
- [ ] Watcher output committed via `apply_output()` to `daimon:{name}` channel
- [ ] Individual watcher failure doesn't affect other watchers (error + backoff)
- [ ] `/api/health` returns per-watcher state, last_fired, fires_total
- [ ] Watchers use `WATCHER_PROVIDER` (default: Groq) for cheapest LLM calls
- [ ] `WATCHER_*_ENABLED=false` disables individual watchers without daemon restart
- [ ] Watcher `--dry-run` mode logs trigger matches without making LLM calls
- [ ] All existing tests pass; new test file `daemon/tests/test_watchers.py`

---

#### Phase 3: Per-Request IPC

**Goal**: Adapters become thin clients. Each request opens a connection, sends a message, gets a response, closes. Adapter crashes are non-fatal to the soul engine.

##### 3.1 — POST /api/process Endpoint

**Modified file**: `daemon/orchestrator.py`

```python
@routes.post("/api/process")
async def handle_process(request: web.Request):
    """Process a message through the cognitive pipeline.

    Request body:
    {
        "text": str,
        "channel": str,          # e.g. "sms:+17327595647"
        "thread_ts": str,        # default: "default"
        "user_id": str,
        "display_name": str,
        "origin": str,           # "sms", "telegram", "discord", etc.
        "soul_enabled": bool,    # default: true
    }

    Response body:
    {
        "response": str,         # the soul engine's response text
        "trace_id": str,         # for correlation
        "soul_state": {...},     # current emotional state (optional)
    }

    Error codes:
    - 400: Malformed input (missing required fields)
    - 401: Invalid or missing auth token
    - 503: Daemon not ready (still starting, soul engine not loaded)
    - 504: LLM timeout (configurable, default 120s)
    - 500: Unexpected error
    """
    # Auth check (existing pattern)
    if not _check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    body = await request.json()
    # Validate required fields
    for field in ("text", "channel", "user_id"):
        if field not in body:
            return web.json_response({"error": f"missing field: {field}"}, status=400)

    try:
        result = await asyncio.wait_for(
            claude_handler.async_process(
                text=body["text"],
                channel=body["channel"],
                thread_ts=body.get("thread_ts", "default"),
                user_id=body["user_id"],
                display_name=body.get("display_name", body["user_id"]),
                origin=body.get("origin", "api"),
                soul_enabled=body.get("soul_enabled", True),
            ),
            timeout=float(os.environ.get("CLAUDICLE_PROCESS_TIMEOUT", "120"))
        )
        return web.json_response({
            "response": result.response_text,
            "trace_id": result.trace_id,
        })
    except asyncio.TimeoutError:
        return web.json_response({"error": "LLM timeout"}, status=504)
    except Exception as e:
        logger.error(f"/api/process error: {e}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)
```

**Session continuity** (SpecFlow Gap 14): The daemon owns session continuity. The adapter sends `(channel, thread_ts)` and the daemon resolves session_id internally via `session_store.get()`. Adapters never see session IDs.

**Request timeout** (SpecFlow Gap 15): Configurable via `CLAUDICLE_PROCESS_TIMEOUT` (default 120s). On timeout, the in-flight LLM call is cancelled via `asyncio.wait_for`. The adapter receives 504 and can retry or report to the user.

##### 3.2 — Thin Client Library

**New file**: `daemon/client.py`

```python
"""Thin client for Claudicle daemon API. No state, no class, no close() to forget."""

import requests

DAEMON_URL = os.environ.get("CLAUDICLE_API_URL", "http://claudicle-api.localhost")
API_TOKEN = os.environ.get("CLAUDICLE_API_TOKEN", "")

def health() -> dict:
    """Check daemon health and version."""
    resp = requests.get(f"{DAEMON_URL}/api/health", timeout=5)
    resp.raise_for_status()
    return resp.json()

def process(text: str, channel: str, user_id: str, **kwargs) -> dict:
    """Send a message through the cognitive pipeline. Per-request connection."""
    resp = requests.post(
        f"{DAEMON_URL}/api/process",
        json={"text": text, "channel": channel, "user_id": user_id, **kwargs},
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=float(os.environ.get("CLAUDICLE_PROCESS_TIMEOUT", "120")) + 5,
    )
    resp.raise_for_status()
    return resp.json()
```

No class. No state. No `close()` to forget. Each call is a per-request connection. The overhead is negligible for human-initiated message processing.

##### 3.3 — SMS Adapter Migration (Proof of Concept)

**Modified file**: `adapters/sms/sms_respond.py`

Replace the current `build_prompt()` + `invoke_claude()` (lines 263-343) with:

```python
from daemon.client import process

async def _process_message(self, text, phone, our_number):
    """Process via daemon API instead of local build_prompt + claude -p."""
    try:
        result = process(
            text=text,
            channel=f"sms:{phone}",
            user_id=phone,
            display_name=self._resolve_name(phone),
            origin="sms",
        )
        return result["response"]
    except requests.ConnectionError:
        logger.error("Daemon unreachable — falling back to direct mode")
        return await self._process_message_direct(text, phone, our_number)
```

**Fallback behavior** (SpecFlow Gap 16): During the migration period, if the daemon API is unreachable, the SMS adapter falls back to its existing direct mode (`build_prompt()` + `claude -p`). This preserves backward compatibility while the IPC path is proven. The fallback is logged prominently so it's visible during testing.

**Feature flag**: `CLAUDICLE_IPC_MODE=true` env var enables the API path. Default: `false` (existing behavior). Set to `true` per-adapter as each is migrated.

##### 3.4 — Migration Path for Other Adapters

| Adapter | Current Coupling | Migration Strategy | Priority |
|---------|-----------------|-------------------|----------|
| **SMS** | Subprocess (`claude -p`) + local `build_prompt()` | Replace with `daemon.client.process()` | **First** (already partially decoupled) |
| **Telegram** | `inbox.jsonl` → `inbox_watcher.py` → in-process `async_process()` | Replace `inbox_watcher` processing with `daemon.client.process()` | Second |
| **Discord** | In-process via `claudicle.py` queue | Extract to standalone adapter + `daemon.client.process()` | Third |
| **Slack** | In-process via `claudicle.py` queue (Socket Mode) | Keep in-process for now (Socket Mode requires persistent connection); extract later | Last |
| **WhatsApp** | Baileys Node.js gateway → `inbox.jsonl` | Same as Telegram | With Telegram |

Both modes coexist during migration via the `CLAUDICLE_IPC_MODE` feature flag per adapter.

##### Phase 3 Files Changed

| File | Change |
|------|--------|
| `daemon/orchestrator.py` | Add `POST /api/process` endpoint |
| `daemon/client.py` | **New** — Stateless thin client library |
| `adapters/sms/sms_respond.py` | Replace `build_prompt()` + `invoke_claude()` with `client.process()` |
| `daemon/claude_handler.py` | Return structured result (not just side effects) for API consumption |
| `daemon/config.py` | `CLAUDICLE_IPC_MODE`, `CLAUDICLE_PROCESS_TIMEOUT` |

##### Phase 3 Acceptance Criteria

- [ ] `POST /api/process` accepts message, returns cognitive response with trace_id
- [ ] Auth token required (existing `CLAUDICLE_API_TOKEN`)
- [ ] Error codes: 400 (bad input), 401 (auth), 503 (not ready), 504 (timeout), 500 (error)
- [ ] SMS adapter uses API when `CLAUDICLE_IPC_MODE=true`, falls back to direct mode
- [ ] SMS adapter crash does not affect daemon or other channels
- [ ] Daemon crash returns connection error to SMS adapter, which retries or falls back
- [ ] Session continuity managed by daemon (adapter sends channel + thread_ts)
- [ ] `daemon/client.py` has no state, no class, no `close()` — module-level functions only
- [ ] 120s default timeout with cancellation of in-flight LLM call
- [ ] All existing tests pass; new test file `daemon/tests/test_api_process.py`

---

## Alternative Approaches Considered

### Unix Socket vs HTTP for IPC

**Considered**: Unix domain socket (like CocoIndex) with msgspec binary protocol.

**Rejected**: The orchestrator already uses aiohttp with portless registration. Adding a separate Unix socket IPC layer means two server implementations, two auth mechanisms, two health checks. HTTP over loopback is ~1ms per request — negligible for human-paced message processing. If latency becomes an issue (unlikely), Unix socket can be added later without changing the client interface.

### Event Bus (Redis/ZMQ) vs JSONL Tail for Watchers

**Considered**: Redis pub/sub or ZMQ for watcher event distribution.

**Rejected**: Violates local-first principle. Adds a dependency (Redis server) that must be installed, started, and managed. JSONL tail with `StreamTailer` is zero-dependency, uses existing infrastructure, and the files already exist. The 1-second poll interval is fine for cognitive watchers that fire at most 10 times per hour.

### Watchers as Separate Processes vs In-Daemon Coroutines

**Considered**: Each watcher as its own Python process with PID file, like `inbox_watcher.py`.

**Rejected**: Five additional processes means five PID files, five startup sequences, five shutdown drains. The watchers share the daemon's LLM client, config, and memory pool — running them out-of-process means either duplicating these resources or adding IPC to access them. In-daemon coroutines are simpler and sufficient. If a watcher needs isolation (e.g., loading a heavy model), it can be extracted later.

### All 5 Sub-daimones as Watchers

**Considered**: Including Bohen (verification) in the watcher set.

**Rejected** (per SpecFlow Gap 12): Bohen's verification role triggers on implementation events (code changes, test results), not JSONL stream entries. Forcing it into the stream-watcher pattern would produce a watcher that either fires on the wrong signals or rarely fires at all. Bohen remains on-demand. Revisit if `toolAction` entries prove sufficient as triggers.

## System-Wide Impact

### Interaction Graph

**Phase 1**: `soul-activate.py` hook → `lifecycle.ensure_daemon()` → `subprocess.Popen(claudicle.py --daemon)` → daemon writes PID → daemon starts orchestrator → orchestrator registers with portless → hook reads PID on next invocation → version handshake via `/api/health`.

**Phase 2**: Daemon startup → `_start_watchers()` → 4 `asyncio.create_task(watcher.run())` → each watcher creates `StreamTailer` → tailer opens JSONL file → tailer yields entries → watcher checks `should_fire()` → watcher calls `llm_client.call_llm()` → watcher constructs `CognitiveOutput` → `apply_output()` writes to working memory → `wm_stream.emit()` writes to JSONL (which other watchers may see — cascading is possible but rate-limited).

**Phase 3**: SMS adapter receives inbound → `client.process(text, channel, user_id)` → HTTP POST to daemon → daemon calls `claude_handler.async_process()` → soul engine builds prompt, calls LLM, parses response → daemon returns JSON response → SMS adapter sends via Twilio → connection closes.

### Error Propagation

- **Hook timeout**: Hook proceeds without daemon confirmation. Soul context injected from disk (existing behavior). Daemon will be available on next invocation.
- **Watcher LLM failure**: Individual watcher enters `error` state, backs off (2x debounce), retries. Other watchers unaffected. No user-facing impact.
- **API process timeout**: 504 returned to adapter. Adapter can retry or report. In-flight LLM call cancelled via `asyncio.wait_for`.
- **Daemon crash**: PID file becomes stale. Next hook invocation detects dead PID, cleans up, starts fresh daemon. Adapters in IPC mode get connection errors and fall back to direct mode.
- **SQLite busy**: WAL mode + `busy_timeout=5000` handles concurrent watcher writes + adapter reads. If a watcher blocks for 5s, its debounce window absorbs the delay. Monitor via `watcher.state == "error"`.

### State Lifecycle Risks

- **Partial shutdown**: If daemon crashes between stopping orchestrator and removing PID file, the PID file becomes stale. Mitigated by liveness check (PID + start_time) on next hook invocation.
- **Watcher output during shutdown**: If a watcher's `apply_output()` races with SQLite pool closure, the write fails silently (existing `try/except` in `apply_output()`). Mitigated by stopping watchers before closing pools in shutdown sequence.
- **Split-brain during migration**: In-process Slack adapter and IPC SMS adapter both write to the same `memory.db`. This is safe because SQLite WAL mode handles concurrent writers, and `ConnectionPool` uses thread-local connections. Both paths go through the same `working_memory.add()` function.

### API Surface Parity

| Interface | Needs updating | Shares code path |
|-----------|---------------|-----------------|
| `claude_handler.async_process()` | Return structured result (not just side effects) | Yes — `/api/process` calls it directly |
| `sms_respond.py` `build_prompt()` | Replace with `client.process()` | No — currently divergent, will converge |
| `claudicle_memory.py` imports | Eventually replace with API calls | No — import-coupled, Phase 3+ |
| Monitor TUI (`monitor.py`) | Add watcher status display | Read-only, no writes |

### Integration Test Scenarios

1. **Hook auto-starts daemon, SMS adapter connects**: Start Claude Code session → hook fires → daemon starts → SMS receives message → `client.process()` succeeds → response sent.
2. **Version mismatch triggers restart**: Daemon running v0.14. User updates code to v0.15. New session hook detects mismatch → stops old daemon → starts new → watchers resume from current JSONL position.
3. **Watcher fires during active conversation**: User chatting via Slack (in-process). Hypermnesia watcher fires, compresses memory. Next Slack message uses compressed context. No visible disruption.
4. **Daemon crash recovery**: Kill daemon with SIGKILL (simulates crash). PID file is stale. Next hook detects dead PID → cleans up → starts fresh daemon. SMS adapter reconnects automatically.
5. **Concurrent hook startup race**: Three Claude Code sessions start simultaneously (minoan-swarm). All three hooks try `ensure_daemon()`. Only one acquires the file lock and starts the daemon. Other two wait and confirm it's running.

## Dependencies & Prerequisites

| Dependency | Status | Blocks |
|------------|--------|--------|
| Existing orchestrator (`daemon/orchestrator.py`) | Ready — has aiohttp, portless, auth | Phase 1, 3 |
| `soul_log.py` and `wm_stream.py` JSONL streams | Ready — append-only, `fcntl.flock` | Phase 2 |
| `engine/llm_client.py` with Groq provider | Ready — used by `reflect.py` | Phase 2 |
| `apply_output()` in `snapshot.py` | Ready — routes through `soul_state.set_state_key()` | Phase 2 |
| `claude_handler.async_process()` | Needs modification — currently returns `None`, must return structured result | Phase 3 |
| portless for daemon URL routing | Ready — `portless claudicle-api` | Phase 1 |

## Risk Analysis & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Concurrent hook startup race | Medium | Two daemon processes, port conflict | File lock (`fcntl.flock`) on PID file |
| Watcher token cost overrun | Low | Unexpected API spend | Rate limiting per watcher, Groq free tier default, cost monitoring in health endpoint |
| JSONL file grows unbounded | Low | Disk space, slow tail startup | Existing `rotate_if_needed()` + StreamTailer rotation handling |
| Adapter fallback masks daemon bugs | Medium | Bugs go unnoticed | Log fallback prominently, alert after N consecutive fallbacks |
| Watcher cascade (output triggers another watcher) | Low | Infinite loop | Each watcher writes to its own `daimon:` channel; watchers only watch system-level streams, not daimon channels |
| SQLite contention from concurrent watchers | Low | 5s busy_timeout delays | WAL mode, separate write paths (watchers debounced), monitor via watcher state |

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Daemon auto-start success rate | >99% on SessionStart | Count hook invocations where daemon is running on second hook |
| Shutdown time | <1 second | Measure from SIGTERM to PID file removal |
| Watcher fire accuracy | >80% meaningful triggers | Manual review of watcher output in `daimon:*` channels |
| Watcher cost | <$1/day at normal usage | Groq free tier or track via `fires_total * avg_cost` |
| SMS adapter IPC latency | <200ms overhead vs direct mode | Compare end-to-end response time with and without IPC |
| Adapter crash isolation | 100% (adapter crash never kills daemon) | Integration test: kill adapter, verify daemon health |

## Future Considerations

- **Bohen as a git-hook watcher**: Once the watcher framework is proven, add Bohen with a trigger on `post-commit` git hooks or file system events rather than JSONL streams.
- **Streaming `/api/process`**: SSE or WebSocket for real-time token streaming to adapters. Not needed for the current message-response pattern.
- **launchd integration**: Auto-start daemon on macOS login via launchd plist. Currently deferred in favor of hook-based auto-start which is cross-platform.
- **Watcher coordination**: Watchers that inform each other (e.g., Hypermnesia tells Zakar which memories were compressed). Currently each watcher is independent; coordination can use working memory as the shared bus.
- **Remote daemon**: Run the daemon on a server (Mac Mini) with adapters connecting over the network. The HTTP IPC pattern makes this possible without code changes — just set `CLAUDICLE_API_URL` to the remote host.

## Documentation Plan

| Document | Change |
|----------|--------|
| `CLAUDE.md` | Add `daemon/lifecycle.py`, `daemon/watchers/`, `daemon/client.py` to Structure section |
| `ARCHITECTURE.md` | Update system diagram with watcher layer and IPC |
| `docs/daemon-architecture.md` | Rewrite startup/shutdown sections for invisible daemon |
| `docs/sub-daimones.md` | Add "Watcher Roles" section distinguishing on-demand vs persistent |
| `docs/extending-claudicle.md` | Add "Creating a Watcher" guide |

## Sources & References

### External References

- [Building an Invisible Daemon](https://cocoindex.io/blogs/building-an-invisible-daemon) — CocoIndex, March 2026. Architecture patterns: per-request connections, version handshake, resource-closure shutdown, two-level settings.
- [AI Daemons: A new category](https://x.com/rileytomasek/status/2035042454483714317) — Riley Tomasek, March 2026. Conceptual framework: task vs role, persistent/self-initiating/role-based daemons.

### Internal References

- `daemon/orchestrator.py:57-243` — Existing HTTP API (Phase 1 and 3 extension point)
- `daemon/adapters/slack_listen.py:33-79` — PID file pattern to replicate
- `daemon/engine/reflect.py:290-406` — Subprocess pattern (Phase 2 template)
- `daemon/monitoring/soul_log.py:38-78` — JSONL stream (Phase 2 watcher source)
- `daemon/monitoring/wm_stream.py:33-77` — JSONL stream (Phase 2 watcher source)
- `adapters/sms/sms_respond.py:263-343` — SMS adapter (Phase 3 first migration)
- `adapters/shared/claudicle_memory.py:43-97` — Import-coupled memory (Phase 3 replacement)
- `daemon/memory/db.py:33-176` — ConnectionPool (concurrency considerations)
- `hooks/soul-activate.py:105-179` — SessionStart hook (Phase 1 auto-start)
