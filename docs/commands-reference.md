# Commands Reference

Quick reference for all Claudius slash commands. Commands live in `commands/*.md` and extend Claude Code sessions with soul agent capabilities.

---

## `/activate [stop]`

Full activation — ensouls the session, starts both daemons, runs a terminal boot sequence, and narrates situational awareness in-character. The single command to go from zero to running.

**Invocation**: User-only (`disable-model-invocation: true`)

**Arguments**:
- Empty — Full activation (ensoul + daemons + boot sequence + narration)
- `stop` — Deactivate (stop daemons, de-ensoul)

**What it does**:
1. Runs `activate_sequence.py` — terminal boot animation (glitch text banner, progress bars, status readout, random quote from Tom's poetry)
2. Ensouls the session (marker file at `~/.claude/soul-sessions/active/{session_id}`)
3. Starts listener + watcher daemons (if not already running)
4. Runs `situational_awareness.py` — gathers workspace name, soul state, recent channels, known users, inbox summary
5. Narrates the situational awareness in-character as Claudius (3-5 sentences)

**Boot sequence**: The terminal animation uses amber/gold aesthetics with glitch-resolving Unicode banner, system init scroll, hex data stream, progress bars, and a random activation quote sourced from Tom's poetry in `~/Desktop/minoanmystery-astro/souls/minoan/dossiers/`.

**Stop behavior**: Stops both daemons (watcher first, then listener), removes the ensoul marker file.

---

## `/ensoul`

Activate the Claudius soul identity in the current session.

**Invocation**: User-only (`disable-model-invocation: true`)

**What it does**:
1. Creates marker file at `~/.claude/soul-sessions/active/{session_id}`
2. Reads `soul/soul.md` and adopts the personality
3. Loads soul state from `soul_memory` (emotional state, current topic, etc.)
4. Displays active sibling sessions from the soul registry
5. Confirms activation

**Persistence**: The marker file tells the SessionStart hook to re-inject soul.md on future compaction/resume events. The personality survives context compaction.

**Without `/ensoul`**: Sessions are still registered in the soul registry (for sibling awareness) but receive no persona injection. The session uses default Claude Code behavior.

**Alternative**: Set `CLAUDIUS_SOUL=1` environment variable to auto-ensoul all sessions.

---

## `/slack-sync [#channel]`

Bind the current session to a Slack channel for bidirectional awareness.

**Invocation**: User-only (`disable-model-invocation: true`)

**Arguments**:
- `#channel-name` or `C12345` (channel ID)
- No arguments: shows current binding status and active sessions

**What it does**:
1. Resolves channel name to ID via `slack_channels.py`
2. Ensures the Session Bridge listener is running (starts it if not)
3. Binds session to channel in the soul registry via `soul-registry.py bind`
4. Posts announcement to the channel: *"Claudius connected from {cwd}"*
5. Confirms binding

**Binding behavior**:
- Per-session: binding is removed when the session ends
- Multiple sessions can bind to the same channel
- Other sessions see the binding in their Active Sessions display

**Prerequisite**: `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` must be set.

---

## `/slack-respond [N|all]`

Process unhandled Slack messages through the full cognitive pipeline.

**Invocation**: Both user and model can invoke (enables automated processing)

**Arguments**:
- `N` — Process only message number N from the inbox
- `all` or empty — Process all unhandled messages

**What it does per message**:
1. Loads memory context (user model, soul state, working memory)
2. Frames the message as an Open Souls perception
3. Posts a "processing..." thinking indicator to the thread
4. Generates a cognitive response (internal monologue + external dialogue + checks)
5. Extracts and posts the external dialogue to the correct Slack thread
6. Deletes the thinking indicator
7. Removes the hourglass reaction
8. Updates user model if `user_model_check` returned `true`
9. Updates soul state if `soul_state_check` returned `true`
10. Logs to working memory and marks message as handled

**Prerequisite**: Session Bridge listener must be running (`slack_listen.py --bg`).

**Dynamic context**: The command uses `!` backtick syntax to inject the current inbox contents and soul personality at invocation time.

---

## `/thinker`

Toggle visible internal monologue per-thread.

**Invocation**: User-only (`disable-model-invocation: true`)

**What it does**:
- **Toggle on**: After posting external dialogue, also posts the internal monologue as an italic follow-up message with a `thought_balloon` reaction
- **Toggle off**: Returns to normal behavior (monologue logged but not posted)

**Natural language triggers**:
- On: "think out loud", "show me your thoughts"
- Off: "stop thinking out loud", "quiet", "hide your thoughts"

**Confirmation messages**:
- On: *"You want to see inside the workshop. Very well."*
- Off: *"Back behind the curtain."*

**Storage**: Thinker state is stored in working memory (per-thread, 72h TTL). Each thread has its own toggle. When the thread goes stale, thinker mode expires with it.

---

## `/watcher [start|stop|status]`

Manage the inbox watcher and listener daemon pair.

**Invocation**: User-only (`disable-model-invocation: true`)

**Arguments**:
- Empty or `status` — Show current daemon status and inbox summary
- `start` — Start both daemons (listener first, then watcher)
- `stop` — Stop both daemons (watcher first, then listener — consumer before producer)

**What it does**:
- Displays pre-injected status of both daemons (via dynamic context injection at load time)
- Starts/stops daemons idempotently (checks if running before starting)

**Provider configuration**: The watcher is provider-agnostic. Provider and model are set via environment variables, not by this command:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDIUS_WATCHER_PROVIDER` | `claude_cli` | LLM provider |
| `CLAUDIUS_WATCHER_MODEL` | (provider default) | Model override |
| `CLAUDIUS_WATCHER_POLL` | `3` | Poll interval in seconds |

**Related**: `/activate` starts both daemons as part of full activation. `/watcher` provides granular daemon management without ensouling.

---

## Command Discovery

### Where Commands Live

```
commands/
├── activate.md       # 95 LOC  — Full activation (ensoul + daemons + boot sequence)
├── ensoul.md         # 55 LOC  — Soul activation only
├── slack-sync.md     # 87 LOC  — Channel binding
├── slack-respond.md  # 114 LOC — Cognitive processing
├── thinker.md        # 83 LOC  — Monologue toggle
└── watcher.md        # 88 LOC  — Daemon management
```

### How Commands Are Installed

`setup.sh` symlinks the `commands/` directory into your Claude Code project configuration. Commands appear in the `/` menu automatically.

### Command Format

All commands use Claude Code's custom command format:

```yaml
---
name: command-name
description: "What this command does"
argument-hint: [optional-args]
disable-model-invocation: true  # user-only
---

# Instructions follow as Markdown
```

The `disable-model-invocation: true` flag prevents Claude from invoking the command automatically—only the user can trigger it via `/command-name`.

---

## Workflow Examples

### Full Activation (Recommended)

```
/activate                  # Ensoul + daemons + boot sequence + narration
# ... Claudius is fully online and autonomous ...
/activate stop             # Shut everything down
```

### Personal Soul Session

```
/ensoul                    # Activate soul identity only (no daemons)
# ... work normally with soul personality ...
```

### Slack-Connected Session

```
/activate                  # Full activation (or manually below)
/slack-sync #general       # Bind to #general channel
/slack-respond             # Process any pending messages
/thinker                   # (optional) Show internal reasoning
```

### Daemon Management Only

```
/watcher start             # Start listener + watcher (no ensoul)
/watcher status            # Check daemon status
/watcher stop              # Stop both daemons
```

### Monitoring Slack Without Soul

```
/slack-sync #engineering   # Bind to channel (no soul needed)
/slack-respond 1           # Process specific message
```
