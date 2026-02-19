# Troubleshooting Guide

Comprehensive troubleshooting for Claudicle—installation, Slack, soul engine, memory, sessions, performance, and hooks.

---

## Installation Issues

| Problem | Fix |
|---------|-----|
| `setup.sh` fails on Python version | Requires Python 3.10+. Check: `python3 --version` |
| `ModuleNotFoundError: slack_bolt` | `uv pip install --system slack_bolt slack_sdk` |
| `ModuleNotFoundError: claude_code_sdk` | `uv pip install --system claude-agent-sdk` (unified launcher only) |
| `setup.sh` can't find `claude` | Ensure Claude Code CLI is in PATH: `which claude` |
| Hooks not wiring | Check `~/.claude/settings.json` contains Claudicle hook entries. Re-run `setup.sh` if missing. |
| `CLAUDICLE_HOME` not set | Default is `~/.claudicle`. Set explicitly: `export CLAUDICLE_HOME=~/.claudicle` |
| `uv` not found | Install: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `skills.md` empty or missing | Re-run `setup.sh`—it generates `daemon/skills.md` from installed Claude Code skills |

---

## Slack Connection Issues

| Problem | Fix |
|---------|-----|
| Bot not responding to @mentions | Verify Socket Mode is ON and `SLACK_APP_TOKEN` (xapp-) is exported |
| "missing_scope" error | Add scope in OAuth & Permissions → **reinstall** the app to workspace |
| No DMs received | Subscribe to `message.im` event → reinstall |
| No search results | Invite bot to channels: `/invite @Claudicle` |
| "Sending messages turned off" | App Home → enable "Allow users to send Slash commands and messages" |
| Bot can't post to channel | Invite with `/invite @Claudicle` and verify `chat:write` scope |
| Listener exits immediately | Check `SLACK_APP_TOKEN` is set; run foreground first: `python3 slack_listen.py` |
| Launcher exits immediately | Verify `which claude` returns a path |
| "Credit balance is too low" | Check Anthropic billing at console.anthropic.com |
| No green presence dot | Add `users:write` scope → reinstall |
| App Home tab blank | Subscribe to `app_home_opened` event → reinstall |
| Monitor TUI won't start | `uv pip install --system textual psutil` |
| SDK import error | `uv pip install --system claude-agent-sdk` |
| Rate limited (429) | Scripts auto-retry; reduce message frequency |

**After any scope or event subscription change:** Reinstall the app (Install App → Reinstall to Workspace) and restart the listener/launcher.

---

## Soul Engine Issues

| Problem | Fix |
|---------|-----|
| No cognitive tags in response | Check `SOUL_ENGINE_ENABLED` is `true` (default). Verify `_COGNITIVE_INSTRUCTIONS` in `soul_engine.py` is intact. |
| Fallback response (raw text, no XML) | The LLM occasionally skips XML formatting. `parse_response()` returns raw text as fallback. Not an error—retry usually fixes it. |
| Verb not extracted | Ensure `<external_dialogue verb="said">` format. Check regex in `_extract_tag()`. |
| Soul state not updating | Soul state only checks every N interactions (`SOUL_STATE_UPDATE_INTERVAL`, default 3). Send more messages to trigger a check. |
| User model not injecting | Samantha-Dreams gate: user model only injects on first turn or when prior `user_model_check` returned `true`. Check working memory for the last mentalQuery entry. |
| Soul personality feels flat | Check `soul/soul.md` is under 100 lines. Long soul files dilute personality. |
| Wrong emotional state | Check current state: `sqlite3 memory.db "SELECT value FROM soul_memory WHERE key='emotionalState'"`. The LLM drives transitions—add clearer spectrum descriptions in `soul.md`. |

---

## Memory Issues

| Problem | Fix |
|---------|-----|
| Stale data in soul state | `sqlite3 memory.db "UPDATE soul_memory SET value='' WHERE key='currentTopic'"` |
| Working memory not clearing | TTL is 72h by default. Force cleanup: `sqlite3 memory.db "DELETE FROM working_memory WHERE created_at < datetime('now', '-72 hours')"` |
| User model corrupted | View: `sqlite3 memory.db "SELECT model_md FROM user_models WHERE user_id='U123'"`. Reset: `sqlite3 memory.db "UPDATE user_models SET model_md='' WHERE user_id='U123'"` |
| Database locked | Another process has the SQLite file open. Check: `fuser memory.db` or `lsof memory.db`. Kill stale processes or wait. |
| Database file missing | `soul_engine.py` auto-creates tables on first use. Verify `daemon/` directory exists. |
| Too many working memory entries | Large histories slow gating queries. Clean old entries: `sqlite3 memory.db "DELETE FROM working_memory WHERE created_at < datetime('now', '-7 days')"` |

### Inspecting Memory

```bash
cd ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon

# Soul state (global)
sqlite3 memory.db "SELECT key, value FROM soul_memory WHERE value != ''"

# User models
sqlite3 memory.db "SELECT user_id, display_name, interaction_count FROM user_models"

# Recent working memory
sqlite3 memory.db "SELECT entry_type, verb, substr(content, 1, 80) FROM working_memory ORDER BY created_at DESC LIMIT 10"

# Session mappings
sqlite3 sessions.db "SELECT channel, thread_ts, session_id FROM sessions ORDER BY updated_at DESC LIMIT 10"
```

### Resetting Memory

```bash
cd ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon

# Reset soul state to defaults
sqlite3 memory.db "DELETE FROM soul_memory"

# Clear all working memory
sqlite3 memory.db "DELETE FROM working_memory"

# Clear specific user model
sqlite3 memory.db "DELETE FROM user_models WHERE user_id='U123'"

# Nuclear option: delete and recreate
rm memory.db sessions.db
# Tables will be auto-created on next interaction
```

---

## Session Issues

| Problem | Fix |
|---------|-----|
| Orphan sessions in registry | Run: `python3 hooks/soul-registry.py cleanup` |
| Stale PID in registry | Cleanup checks PIDs automatically. Force: delete `~/.claude/soul-sessions/registry.json` |
| Session not resuming | Check `sessions.db` for TTL expiry. Default 24h. Increase via `CLAUDICLE_SESSION_TTL`. |
| `/ensoul` not persisting through compaction | Verify marker file exists: `ls ~/.claude/soul-sessions/active/` |
| Missing handoff file | Handoffs write on Stop/PreCompact events. Crash exits may miss them. |
| Registry file corrupted | Delete `~/.claude/soul-sessions/registry.json`—recreated on next SessionStart. |
| Multiple sessions bound to same channel | This is intentional and supported. Check with `soul-registry.py list`. |

---

## Hook Issues

| Problem | Fix |
|---------|-----|
| SessionStart hook not firing | Verify `~/.claude/settings.json` has the hook entry. Check path is absolute. |
| Soul not injected on resume | Verify ensoul marker file exists and SessionStart hook is wired. |
| Handoff not writing | `claudicle-handoff.py` runs on Stop and PreCompact. Check it's in `settings.json`. |
| Slack inbox hook silent | Expected when no unhandled messages or listener not running. Test: `python3 scripts/slack_inbox_hook.py` |
| Hook conflicts | Claudicle hooks are non-destructive—they merge into existing `settings.json` without overwriting. If conflicts occur, check for duplicate entries. |
| Hook permissions | Ensure hook scripts are executable: `chmod +x hooks/*.py` |

### Verifying Hook Wiring

```bash
# Check settings.json for Claudicle hooks
python3 -c "
import json
with open('$HOME/.claude/settings.json') as f:
    s = json.load(f)
for event, hooks in s.get('hooks', {}).items():
    for h in hooks:
        if 'claudicle' in h.get('command', '').lower() or 'soul' in h.get('command', '').lower():
            print(f'{event}: {h[\"command\"]}')"
```

---

## Performance Issues

| Problem | Fix |
|---------|-----|
| Slow responses | Check Claude API status. Reduce `MAX_RESPONSE_LENGTH` if responses are being truncated anyway. |
| High API costs | Use Session Bridge mode (no extra API costs). Consider per-step model selection for cost optimization. |
| Monitor TUI laggy | The watcher polls SQLite files. Increase poll interval if needed. |
| Large inbox file | Clear handled messages: `python3 scripts/slack_check.py --clear` |
| SQLite performance | Run `VACUUM` periodically: `sqlite3 memory.db "VACUUM"` |

---

## Configuration Reference

All settings in `daemon/config.py` with environment variable overrides:

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| Installation root | `CLAUDICLE_HOME` | `~/.claudicle` | Root directory |
| Claude timeout | `CLAUDICLE_TIMEOUT` | `120` s | Invocation timeout |
| Working directory | `CLAUDICLE_CWD` | `~` | Claude subprocess CWD |
| Slack tools | `CLAUDICLE_TOOLS` | `Read,Glob,Grep,Bash,WebFetch` | Tools for Slack |
| Terminal tools | `CLAUDICLE_TERMINAL_TOOLS` | above + `Edit,Write` | Tools for terminal |
| Terminal soul | `CLAUDICLE_TERMINAL_SOUL` | `false` | Soul engine for terminal |
| Soul engine | `CLAUDICLE_SOUL_ENGINE` | `true` | Master toggle |
| Session TTL | `CLAUDICLE_SESSION_TTL` | `24` h | Session expiry |
| Memory window | `CLAUDICLE_MEMORY_WINDOW` | `20` entries | Gating query window |
| Memory TTL | `CLAUDICLE_MEMORY_TTL` | `72` h | Working memory cleanup |
| User model interval | `CLAUDICLE_USER_MODEL_INTERVAL` | `5` | Turns between checks |
| Soul state interval | `CLAUDICLE_SOUL_STATE_INTERVAL` | `3` | Turns between checks |

Legacy prefix `SLACK_DAEMON_*` is also supported as a fallback.

---

## Getting Help

If you're stuck:

1. Check this guide for your specific issue
2. Inspect the relevant SQLite database directly
3. Run the failing component in foreground mode with `--verbose`
4. Check `daemon/logs/` for listener and hook logs
5. Open an issue on the Claudicle repository
