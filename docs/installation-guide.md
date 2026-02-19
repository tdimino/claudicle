# Installation Guide — What Claudicle Installs

`setup.sh` installs Claudicle into two locations: `CLAUDICLE_HOME` (default `~/.claudicle`) for the soul engine and daemon, and `~/.claude/` for Claude Code integration. This guide documents the full post-install layout.

---

## CLAUDICLE_HOME (`~/.claudicle/`)

The soul agent's home directory. Contains the daemon, soul personality, scripts, and all runtime data.

```
~/.claudicle/
├── daemon/
│   ├── soul_engine.py       # Cognitive pipeline (prompt builder + response parser)
│   ├── claude_handler.py    # Claude subprocess + Agent SDK integration
│   ├── claudicle.py          # Unified launcher (terminal + Slack, autonomous)
│   ├── bot.py               # Legacy standalone Slack daemon
│   ├── slack_listen.py      # Session Bridge listener (background, inbox.jsonl)
│   ├── slack_adapter.py     # Slack Socket Mode adapter (shared by claudicle.py)
│   ├── terminal_ui.py       # Async terminal interface
│   ├── working_memory.py    # Per-thread metadata (SQLite, 72h TTL)
│   ├── user_models.py       # Per-user profiles (SQLite, permanent)
│   ├── soul_memory.py       # Global soul state (SQLite, permanent)
│   ├── session_store.py     # Thread → Claude session ID mapping
│   ├── config.py            # Configuration with _env() dual-prefix helper
│   ├── monitor.py           # Soul Monitor TUI (Textual)
│   ├── watcher.py           # SQLite file watcher for monitor
│   ├── skills.md            # Auto-generated skills manifest
│   ├── memory.db            # Three-tier memory (auto-created at runtime)
│   ├── sessions.db          # Session mappings (auto-created at runtime)
│   ├── inbox.jsonl          # Session Bridge inbox (auto-created by listener)
│   └── launchd/             # macOS LaunchAgent for always-on deployment
├── soul/
│   ├── soul.md              # Your soul personality (edit this!)
│   ├── soul-example-personal.md
│   ├── soul-example-company.md
│   └── userModel-template.md
├── hooks/
│   ├── soul-activate.py     # SessionStart: register + inject soul
│   ├── soul-registry.py     # Session registry CLI (6 subcommands)
│   ├── soul-deregister.py   # SessionEnd/Stop: deregister session
│   └── claudicle-handoff.py  # Stop/PreCompact: heartbeat + handoff
├── commands/
│   ├── activate.md          # /activate — full activation (ensoul + daemons + boot)
│   ├── ensoul.md            # /ensoul — activate soul in session
│   ├── slack-sync.md        # /slack-sync — bind to channel
│   ├── slack-respond.md     # /slack-respond — process inbox
│   ├── thinker.md           # /thinker — toggle visible monologue
│   └── watcher.md           # /watcher — manage daemon pair
├── scripts/                 # 16 Slack/activation utility scripts
├── adapters/                # SMS (Telnyx/Twilio)
└── docs/                    # Reference documentation
```

---

## Claude Code Integration (`~/.claude/`)

`setup.sh` wires Claudicle into Claude Code's infrastructure. All changes are non-destructive—existing config is preserved and merged.

### What Gets Created/Modified

| Path | Created By | Purpose |
|------|-----------|---------|
| `~/.claude/settings.json` | Merged (not replaced) | Hook bindings for soul lifecycle |
| `~/.claude/commands/activate.md` | Copied (if not exists) | `/activate` slash command |
| `~/.claude/commands/ensoul.md` | Copied (if not exists) | `/ensoul` slash command |
| `~/.claude/commands/slack-sync.md` | Copied (if not exists) | `/slack-sync` slash command |
| `~/.claude/commands/slack-respond.md` | Copied (if not exists) | `/slack-respond` slash command |
| `~/.claude/commands/thinker.md` | Copied (if not exists) | `/thinker` slash command |
| `~/.claude/commands/watcher.md` | Copied (if not exists) | `/watcher` slash command |
| `~/.claude/agent_docs/claudicle-*.md` | Copied (if not exists) | Soul architecture reference docs |
| `~/.claude/soul-sessions/` | Created | Soul registry data directory |
| `~/.claude/soul-sessions/active/` | Created | Ensoul marker files |
| `~/.claude/soul-sessions/registry.json` | Created at runtime | Active session registry |
| `~/.claude/handoffs/` | Created | Session handoff YAML files |
| `~/.claude/handoffs/INDEX.md` | Created at runtime | Handoff index (auto-maintained) |
| `~/.claude/userModels/{name}/{name}Model.md` | Created (if opted in) | User personality profile |

### Hook Bindings in `settings.json`

After install, your `settings.json` will include these hooks (merged alongside any existing hooks):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "python3 ~/.claudicle/hooks/soul-activate.py"
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python3 ~/.claudicle/hooks/soul-deregister.py"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 ~/.claudicle/hooks/soul-deregister.py"
      },
      {
        "type": "command",
        "command": "python3 ~/.claudicle/hooks/claudicle-handoff.py"
      }
    ],
    "PreCompact": [
      {
        "type": "command",
        "command": "python3 ~/.claudicle/hooks/claudicle-handoff.py"
      }
    ]
  }
}
```

### Optional: Slack Auto-Notification Hook

Not wired by default. Add manually to surface unhandled Slack messages each turn:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "python3 ~/.claudicle/scripts/slack_inbox_hook.py"
      }
    ]
  }
}
```

---

## Shell Profile Changes

`setup.sh` appends to `~/.zshrc` or `~/.bashrc`:

```bash
# Claudicle soul agent
export CLAUDICLE_HOME="$HOME/.claudicle"
export SLACK_BOT_TOKEN="xoxb-..."   # if provided during setup
export SLACK_APP_TOKEN="xapp-..."   # if provided during setup
```

---

## User Models

Each person Claudicle models gets their own folder under `~/.claude/userModels/`. If you opted in during setup, a user model folder is created at `~/.claude/userModels/{name}/` containing `{name}Model.md`:

```
~/.claude/userModels/
├── INDEX.md              # Master index of all user models
└── {name}/
    ├── {name}Model.md    # Core persona (always loaded)
    └── ...               # Voice models, dossiers, data collections
```

The core model is a markdown file with sections for:

- **Persona** — Who you are, what you do
- **Communication Style** — How you prefer to interact
- **Interests & Domains** — Technical and intellectual focus areas
- **Working Patterns** — How you work (tools, flow, preferences)
- **Notes** — Anything else the soul should know

You can fill this in manually or let Claudicle build it automatically through conversation (see `docs/onboarding-guide.md`). To reference it from your CLAUDE.md:

```markdown
## Identity
@userModels/{name}/{name}Model.md
```

---

## Session Handoffs

When enabled, the handoff system saves session state on `Stop` and `PreCompact` events:

- **Stop (every ~5 min)**: Lightweight heartbeat — updates `last_seen` timestamp
- **PreCompact (context full)**: Full handoff — saves project, directory, objectives, completed work, decisions, next steps

Handoff files are YAML at `~/.claude/handoffs/{session_id}.yaml`. The index at `~/.claude/handoffs/INDEX.md` is auto-maintained with recent sessions sorted by date.

New sessions can read `INDEX.md` to recover context from prior sessions—useful after crashes, compaction, or when resuming work across days.

---

## Skills Manifest

`setup.sh` scans `~/.claude/skills/` and generates `~/.claudicle/daemon/skills.md` listing all discovered skills. This manifest is injected into the first message of each Slack conversation so the soul knows what tools are available.

To update after installing new skills:

```bash
cd ~/path/to/claudicle && ./setup.sh --personal
```

Or manually edit `~/.claudicle/daemon/skills.md`.

---

## Post-Install Verification

```bash
# Check hooks are wired
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); print(json.dumps(d.get('hooks',{}), indent=2))"

# Check soul file exists
cat ${CLAUDICLE_HOME:-$HOME/.claudicle}/soul/soul.md | head -5

# Check commands installed
ls ~/.claude/commands/{activate,ensoul,slack-sync,slack-respond,thinker,watcher}.md

# Check Python deps
python3 -c "import slack_bolt; print('slack_bolt OK')"
python3 -c "import textual; print('textual OK')"

# Test soul engine
cd ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon && python3 -c "import soul_engine; print('soul_engine OK')"
```

---

## Uninstalling

```bash
# Remove CLAUDICLE_HOME
rm -rf ${CLAUDICLE_HOME:-$HOME/.claudicle}

# Remove slash commands
rm -f ~/.claude/commands/{activate,ensoul,slack-sync,slack-respond,thinker,watcher}.md

# Remove agent docs
rm -f ~/.claude/agent_docs/claudicle-*.md

# Remove soul sessions
rm -rf ~/.claude/soul-sessions

# Remove hooks from settings.json (manual — edit the file)
# Remove CLAUDICLE_HOME export from shell profile (manual)
```

---

## Further Reading

| Document | What It Covers |
|----------|---------------|
| `docs/slack-setup.md` | Creating the Slack app, choosing a runtime mode |
| `docs/session-bridge.md` | Session Bridge workflow and inbox management |
| `docs/unified-launcher-architecture.md` | Autonomous daemon with Agent SDK |
| `docs/onboarding-guide.md` | Building user models via interview |
| `ARCHITECTURE.md` | Full system design and cognitive pipeline |
