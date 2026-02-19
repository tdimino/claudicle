# Scripts Reference

Full documentation for all 14 Slack utility scripts plus 2 activation scripts in `scripts/`. Each is a standalone Python CLI tool. Slack scripts require `SLACK_BOT_TOKEN`; activation scripts have no external dependencies.

All Slack scripts share `_slack_utils.py` (272 LOC) for token loading, channel name→ID resolution, and API error handling.

## 1. slack_post.py — Post Messages

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py`

Post messages, reply to threads, schedule, update, and delete messages.

```bash
# Post to a channel
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Hello from Claude"

# Reply to a thread
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Thread reply" --thread 1234567890.123456

# Post with rich blocks
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Update" \
  --blocks '[{"type":"section","text":{"type":"mrkdwn","text":"*Bold heading*\nDetails here"}}]'

# Schedule a message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Daily reminder" --schedule "2026-02-12T09:00:00"

# Update an existing message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Corrected text" --update 1234567890.123456

# Delete a message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" --delete 1234567890.123456

# Post with link unfurling
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#general" "Check: https://example.com" --unfurl
```

**Parameters**: `channel`, `text`, `--thread`, `--blocks`, `--schedule`, `--update`, `--delete`, `--unfurl`, `--json`

---

## 2. slack_read.py — Read Messages

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py`

Read channel history and thread replies.

```bash
# Read recent messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general"

# Read last 20 messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general" -n 20

# Read thread replies
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general" --thread 1234567890.123456

# Read since a specific date
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general" --since "2026-02-11"

# Resolve user IDs to names
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general" --resolve-users

# JSON output
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#general" --json
```

**Parameters**: `channel`, `-n/--num`, `--thread`, `--since`, `--resolve-users`, `--json`

---

## 3. slack_search.py — Search Messages & Files

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py`

Search messages and files across the workspace.

```bash
# Search messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "deployment failed"

# Search in a specific channel
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "bug report" --channel "#engineering"

# Search from a specific user
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "API update" --from "@tom"

# Date-filtered search
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "release" --after 2026-02-01 --before 2026-02-11

# Search files
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "architecture diagram" --files

# Sort by relevance
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "soul engine" --sort score
```

**Parameters**: `query`, `-n/--num`, `--channel`, `--from`, `--after`, `--before`, `--files`, `--sort`, `--page`, `--json`

**Note**: With a bot token (`xoxb-`), search only covers channels the bot is a member of. For workspace-wide search, use a user token (`xoxp-`) with `search:read` scope.

---

## 4. slack_react.py — Manage Reactions

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_react.py`

```bash
# Add a reaction
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_react.py "#general" 1234567890.123456 rocket

# Remove a reaction
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_react.py "#general" 1234567890.123456 rocket --remove

# List reactions on a message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_react.py "#general" 1234567890.123456 --list
```

**Parameters**: `channel`, `timestamp`, `emoji`, `--remove`, `--list`, `--json`

---

## 5. slack_upload.py — Upload Files

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py`

Upload files using the 2-step external upload API.

```bash
# Upload a file
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py "#general" ./report.pdf

# Upload with title and message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py "#general" ./chart.png --title "Q1 Results" --message "Latest chart"

# Upload to a thread
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py "#general" ./data.csv --thread 1234567890.123456

# Upload a code snippet
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py "#general" --snippet "print('hello')" --filetype python --title "Example"
```

**Parameters**: `channel`, `file`, `--title`, `--message`, `--thread`, `--snippet`, `--filetype`, `--json`

---

## 6. slack_channels.py — Channel Management

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py`

```bash
# List all channels
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py

# Show member counts
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py --members

# Get channel details
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py --info "#general"

# Join a channel
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py --join "#new-channel"

# Filter by name pattern
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py --filter "eng-"

# Include private channels
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_channels.py --private
```

**Parameters**: `--info`, `--join`, `--filter`, `--members`, `--private`, `--json`

---

## 7. slack_users.py — User Lookup

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py`

```bash
# List all users
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py

# Active humans only (no bots/deactivated)
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py --active

# Get user details by ID
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py --info U12345678

# Lookup by email
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py --email user@example.com
```

**Parameters**: `--info`, `--email`, `--active`, `--json`

---

## 8. slack_delete.py — Delete Messages

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_delete.py`

Delete single messages, batch delete by timestamp, or clean up entire threads.

```bash
# Delete a single message
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_delete.py "#general" 1234567890.123456

# Delete multiple messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_delete.py "#general" TS1 TS2 TS3

# Delete all bot messages in a thread
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_delete.py "#general" --thread 1234567890.123456 --all

# Delete bot messages before a timestamp
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_delete.py "#general" --thread 1234567890.123456 --before 1234567890.999999
```

**Parameters**: `channel`, `timestamps...`, `--thread`, `--all`, `--before`, `--json`

**Note**: The bot can only delete its own messages. Thread cleanup modes (`--all`, `--before`) filter to bot-authored messages automatically.

---

## 9. slack_check.py — Inbox Management

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py`

Read and manage unhandled messages from the Session Bridge inbox (`daemon/inbox.jsonl`).

```bash
# Show unhandled messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py

# Mark message #1 as handled
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py --ack 1

# Mark all as handled
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py --ack-all

# Delete inbox file
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py --clear

# One-line summary (for hooks), silent if none
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_check.py --quiet
```

**Parameters**: `--ack N`, `--ack-all`, `--clear`, `--quiet`, `--json`

**Output format** (default):
```
[1] #C12345 | Tom (thread: 1234567890.123456): "What's the status?"
[2] DM:D456 | Alice (thread: 1234567890.789012): "Check the tests"
```

---

## 10. slack_format.py — Cognitive Step Formatting

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py`

Standalone XML extraction and formatting for the Open Souls cognitive step paradigm. No SQLite imports—pure text processing.

```bash
# Format incoming message as a perception
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py perception "Tom" "What's the status?"
# → Tom said, "What's the status?"

# Extract external dialogue from a raw response (pipe or --text)
echo "$raw_response" | python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py extract

# Narrated extraction with verb
echo "$raw_response" | python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py extract --narrate
# → Claudius explained, "The BG3 port is at 93% parity."

# Log internal monologue to daemon/logs/monologue.log
echo "$raw_response" | python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py extract --log

# Get cognitive step XML instructions (for prompt injection)
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py instructions
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_format.py instructions --full
```

**Subcommands**: `perception`, `extract`, `instructions`

**Extract options**: `--narrate`, `--log`, `--json`, `--text "raw response"`

---

## 11. slack_memory.py — Memory CLI Wrapper

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py`

CLI interface to the three-tier memory system. Used by `/slack-respond` to load context and update memory from bash.

```bash
# Load full memory context for a user (soul state + user model + working memory gate)
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py load-context U12345 --display-name "Tom" --channel C123 --thread-ts 1234567890.123

# Update a user model with new observations
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py update-user-model U12345 "Prefers concise answers" --display-name "Tom"

# Update soul state
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py update-soul-state currentTopic "BG3 port"

# Log a working memory entry
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py log-working C123 1234567890.123 U12345 externalDialog --verb "explained" --content "Response text"

# Show a user's model
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py show-user-model U12345

# Increment interaction count
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_memory.py increment U12345
```

**Subcommands**: `load-context`, `update-user-model`, `update-soul-state`, `log-working`, `show-user-model`, `increment`

---

## 12. slack_app_home.py — App Home Tab

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_app_home.py`

Build and publish the Claudicle App Home tab using Block Kit. Terminal-brutalist aesthetic with ancient undertones.

```bash
# Publish for one user
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_app_home.py U12345678

# Publish for all known users
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_app_home.py --all

# Debug mode (print block JSON, no publish)
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_app_home.py --debug
```

**Parameters**: `user_id`, `--all`, `--debug`

The App Home displays: listener/watcher status, soul state, recent interactions, known users, and memory statistics. Automatically triggered by the `app_home_opened` event subscription.

---

## 13. slack_inbox_hook.py — Auto-Check Hook

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_inbox_hook.py`

Claude Code `UserPromptSubmit` hook that silently checks the inbox at the start of every turn.

- If unhandled messages exist: outputs `[Slack: N unhandled messages -- run /slack-check to view]`
- If inbox is empty or listener not running: silent (no output)

**Hook config** (`~/.claude/settings.json`):
```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "type": "command",
      "command": "python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_inbox_hook.py"
    }]
  }
}
```

Not wired by default—add manually or via `/slack-sync`.

---

## 14. activate_sequence.py — Boot Animation

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/activate_sequence.py`

Terminal boot sequence with Matrix/Tron aesthetic. Runs as the first step of `/activate`. Amber/gold color palette with cascading activation effects.

```bash
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/activate_sequence.py
```

No parameters. No external dependencies. Pure ANSI escape codes.

---

## 15. situational_awareness.py — Activation Readout

**Command**: `python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/situational_awareness.py`

Gathers workspace context for Claudicle to narrate in-character during `/activate`. Outputs structured data about the current environment.

```bash
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/situational_awareness.py
```

**Data gathered**:
- Workspace name (via `auth.test`)
- Soul state (emotional state, current topic/project)
- Recent Slack channels with activity timestamps
- Known users and interaction counts
- Unhandled inbox messages

Reads from `daemon/memory.db` and `daemon/inbox.jsonl`. Output is consumed by the `/activate` command, which narrates it through the soul engine.

---

## Common Workflows

### Post a Daily Update

```bash
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_post.py "#standup" \
  "*Daily Update — $(date +%Y-%m-%d)*
• Completed: feature X implementation
• In progress: testing Y
• Blocked: waiting on API keys"
```

### Monitor a Channel

```bash
# Read recent messages
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_read.py "#alerts" -n 5

# Search for specific issues
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_search.py "error" --channel "#alerts" --after $(date -v-1d +%Y-%m-%d)
```

### Share a File with Context

```bash
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_upload.py "#engineering" ./architecture.png \
  --title "System Architecture v2" \
  --message "Updated architecture diagram with the new caching layer"
```

### Find Someone's Email

```bash
python3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/scripts/slack_users.py --info U12345678
```
