# Session Management Guide

Manage Claudius sessions across all runtime modes—track active sessions, recover from crashes, monitor state, and troubleshoot orphans.

---

## What Is a Session?

A Claudius session is a Claude Code conversation context identified by a session ID. Sessions carry forward personality, memory, and conversation history via `--resume` (subprocess) or `resume=` (Agent SDK).

Each session maps to a specific scope:

| Runtime Mode | Session Key | Continuity |
|-------------|-------------|------------|
| `/ensoul` | Claude Code's native session ID | `--resume` on compaction |
| Session Bridge | `channel + thread_ts` | `--resume SESSION_ID` |
| Unified Launcher | `channel + thread_ts` | SDK `resume=session_id` |
| Legacy Daemon | `channel + thread_ts` | CLI `--resume` flag |

Thread-to-session mappings are stored in `daemon/sessions.db`.

---

## Session Lifecycle

### Creation

Sessions are created on first interaction:

1. **`/ensoul`**: Marker file created at `~/.claude/soul-sessions/active/{session_id}`. SessionStart hook injects soul.md on this and future turns.
2. **Slack modes**: First message in a new thread creates a session mapping in `sessions.db`. Subsequent messages in the same thread resume that session.
3. **Terminal (unified launcher)**: A single persistent session keyed as `terminal/terminal`.

### Registration

All sessions are registered in the soul registry (`~/.claude/soul-sessions/registry.json`) via the SessionStart hook. Registration happens whether or not the session is ensouled.

Registry entry contents:
- Session ID, PID, working directory
- Model (opus, sonnet, etc.)
- Start time, last active timestamp
- Channel binding (if `/slack-sync` was used)

### Heartbeat

The `claudius-handoff.py` hook fires on every `Stop` event (~5 minutes), updating the session's `last_active` timestamp and optionally the current topic.

### Expiration

- **Session TTL**: Sessions in `sessions.db` expire after `SESSION_TTL_HOURS` (default: 24h)
- **Working memory TTL**: Entries expire after `WORKING_MEMORY_TTL_HOURS` (default: 72h)
- **Registry cleanup**: Stale sessions (dead PIDs, >2h inactive) are cleaned on every SessionStart

### Deregistration

When a session ends:
1. `soul-deregister.py` hook fires (SessionEnd and Stop events)
2. Session removed from registry
3. Ensoul marker file deleted
4. Handoff YAML written to `~/.claude/handoffs/{session_id}.yaml`

---

## Soul Registry

File-based JSON registry at `~/.claude/soul-sessions/registry.json`. Implemented in `hooks/soul-registry.py` with six subcommands.

### Viewing Sessions

```bash
# Markdown table (human-readable)
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/hooks/soul-registry.py" list --md

# JSON output (machine-readable)
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/hooks/soul-registry.py" list --json

# Plain text
python3 "${CLAUDIUS_HOME:-$HOME/.claudius}/hooks/soul-registry.py" list
```

A companion `SESSIONS.md` file is auto-regenerated on every registry write.

### Registry Subcommands

| Subcommand | Purpose | Called By |
|------------|---------|-----------|
| `register` | Add session with CWD, PID, model | SessionStart hook |
| `deregister` | Remove session | SessionEnd/Stop hook |
| `bind` | Bind session to Slack channel | `/slack-sync` command |
| `heartbeat` | Update `last_active`, optional topic | Stop hook |
| `list` | Print sessions (text/json/md) | `/ensoul`, `/slack-sync`, manual |
| `cleanup` | Remove stale sessions | SessionStart hook |

### Concurrency Safety

The registry uses `fcntl` file locking and atomic writes (temp file + rename) to handle concurrent access from multiple sessions.

---

## Session Continuity

### Compaction and Resume

When Claude Code's context window fills, it compacts the conversation. Claudius preserves identity through this:

1. **PreCompact hook** (`claudius-handoff.py`): Saves full session state to `~/.claude/handoffs/{session_id}.yaml`
2. **SessionStart hook** (`soul-activate.py`): On resume, re-injects soul.md + soul state + sibling sessions if the session is ensouled

### Handoff Files

Location: `~/.claude/handoffs/`

```yaml
# ~/.claude/handoffs/{session_id}.yaml
session_id: "abc123"
project: "~/Desktop/Programming"
trigger: "compact"  # or "stop", "prompt_input_exit"
objective: "Working on BG3SE macOS port"
completed:
  - "Fixed ARM64 hooking"
decisions:
  - "Use Dobby over fishhook"
blockers: []
next_steps:
  - "Test Lua 5.4 integration"
```

An `INDEX.md` at `~/.claude/handoffs/INDEX.md` is auto-maintained with recent session summaries for quick recovery.

### Recovering from Crashes

1. Read the handoff index: `~/.claude/handoffs/INDEX.md`
2. Find the relevant session's YAML for full context
3. Resume with `claude --resume {session_id}` if the session is still valid

---

## Multi-Session Awareness

When ensouled, sessions are aware of their siblings. The SessionStart hook injects active session information:

```
## Active Sessions
- `abc123` in ~/Desktop/Programming, 2h15m ← this session
- `def456` in ~/souls/kothar, 45m
```

This enables:
- Awareness of what other sessions are working on
- Channel binding visibility (which session is connected to which Slack channel)
- Avoiding duplicate work across sessions

---

## Monitoring

### Soul Monitor TUI

Live Textual-based dashboard showing all activity:

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon && uv run python monitor.py
```

Displays:
- Active sessions and their state
- Memory statistics (working memory entries, user models, soul state)
- Cognitive stream (monologue, dialogue, model checks)
- Message flow across channels

### Direct Database Inspection

```bash
cd ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon

# Soul state (global)
sqlite3 memory.db "SELECT key, value FROM soul_memory WHERE value != ''"

# User models
sqlite3 memory.db "SELECT user_id, display_name, interaction_count FROM user_models"

# Recent working memory
sqlite3 memory.db "SELECT entry_type, verb, substr(content, 1, 80) FROM working_memory ORDER BY created_at DESC LIMIT 10"

# Session mappings
sqlite3 sessions.db "SELECT channel, thread_ts, session_id FROM sessions ORDER BY updated_at DESC LIMIT 10"

# Active sessions in registry
cat ~/.claude/soul-sessions/registry.json | python3 -m json.tool
```

### Slack App Home

If configured (`app_home_opened` event subscription), the Slack App Home tab displays session and memory status. Built by `scripts/slack_app_home.py`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Orphan sessions in registry | Run `soul-registry.py cleanup` manually, or wait for next SessionStart |
| Stale PID in registry | The cleanup subcommand checks PIDs against running processes |
| Session not resuming | Check `sessions.db` for TTL expiry: `sqlite3 sessions.db "SELECT * FROM sessions WHERE channel='C123'"` |
| Soul state not persisting | Verify `soul_memory.set()` is being called: check `memory.db` directly |
| Missing handoff file | Handoffs only write on Stop and PreCompact events—crash exits may miss them |
| Multiple sessions bound to same channel | This is allowed. Check with `soul-registry.py list --json` |
| Registry file corrupted | Delete `~/.claude/soul-sessions/registry.json`—it will be recreated on next SessionStart |
