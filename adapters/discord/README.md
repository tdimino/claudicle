# Discord Adapter

discord.py-based integration for Claudicle. Bot listens in configured channels and DMs.

## Setup

1. Create a Discord Application at https://discord.com/developers/applications
2. Create a Bot under the application
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Generate a bot token and set `DISCORD_BOT_TOKEN`
5. Invite the bot to your server with scopes: `bot`, permissions: `Send Messages`, `Read Message History`, `Add Reactions`, `Manage Webhooks`

## Environment Variables

```bash
DISCORD_BOT_TOKEN=                           # Bot token from Developer Portal
CLAUDICLE_DISCORD_ALLOWED_CHANNELS=          # Comma-separated channel IDs (empty = all)
CLAUDICLE_DISCORD_RESPOND_TO_MENTIONS=true   # Respond to @mentions in channels
CLAUDICLE_DISCORD_RESPOND_TO_DMS=true        # Respond to direct messages
```

## Usage

### Unified Launcher (recommended)

```bash
cd daemon && python3 claudicle.py
# Discord bot starts automatically if DISCORD_BOT_TOKEN is set
# Use --no-discord to disable
```

### Session Bridge (standalone)

```bash
python3 discord_listen.py --bg    # Start background listener
python3 discord_listen.py --stop  # Stop listener
python3 discord_listen.py --status
```

## Scripts

| Script | Purpose |
|--------|---------|
| `discord_listen.py` | Session Bridge: writes to inbox.jsonl |
| `discord_post.py` | Post responses to channels |
| `_discord_utils.py` | Channel ID helpers, message splitting, config |

## Channel Format

`discord:{channel_id}` — e.g. `discord:1234567890123456789`

## Features

- @mention responses in channels
- Direct message responses
- Thread tracking via reply references
- Daimon identity via webhooks (custom username + avatar per-channel)
- Daimon mode commands: `!artifex speak`, `!kothar off`
- Message deduplication (bounded set, 1000 IDs)
- 2000-char message splitting
