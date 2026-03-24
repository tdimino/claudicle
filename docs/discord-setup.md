# Discord Setup

Connect Claudicle to Discord via discord.py with webhook-based daimon identity.

---

## Prerequisites

- A Discord account with server admin access
- Python 3.10+ with `discord.py`

## Create a Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → name it (e.g., "Claudicle")
3. Go to **Bot** → click **Add Bot**
4. Enable **Message Content Intent** under Privileged Gateway Intents (required to read message text)
5. Copy the bot token

### Invite the Bot

Generate an invite URL under **OAuth2 → URL Generator**:
- **Scopes**: `bot`
- **Bot Permissions**: `Send Messages`, `Read Message History`, `Add Reactions`, `Manage Webhooks`

Open the generated URL in your browser to add the bot to your server.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | — | Token from Developer Portal |
| `CLAUDICLE_DISCORD_ALLOWED_CHANNELS` | No | `""` (all) | Comma-separated channel IDs |
| `CLAUDICLE_DISCORD_RESPOND_TO_MENTIONS` | No | `true` | Respond when @mentioned |
| `CLAUDICLE_DISCORD_RESPOND_TO_DMS` | No | `true` | Respond to direct messages |

Set `DISCORD_BOT_TOKEN` in `~/.config/env/secrets.env`.

## Running

### Session Bridge mode

```bash
cd adapters/discord
python3 discord_listen.py
```

### Unified Launcher mode

```bash
cd daemon
python3 claudicle.py
```

### Sending messages

```bash
cd adapters/discord
python3 discord_post.py --channel-id CHANNEL_ID "Hello from Claudicle"
```

## Features

- **Thread tracking**: Via Discord reply references
- **Daimon identity**: Webhook-based — each channel gets a cached webhook with custom username and avatar per daimon
- **Message deduplication**: Bounded deque (1000 IDs) prevents duplicate processing
- **Message splitting**: Automatic at 2000 characters
- **@mention stripping**: Bot mention removed from message text
- **Channel allowlist**: Restrict via `CLAUDICLE_DISCORD_ALLOWED_CHANNELS`

## Daimon Mode

Use daimon mode commands in channels:
- `!artifex speak` — Activate a daimon voice
- `!kothar off` — Deactivate daimon mode

Daimon identity uses Discord webhooks, which allow custom username and avatar per-message — the richest identity system of any channel.

## Limitations

- Message Content Intent is a privileged intent — must be enabled in Developer Portal
- Discord bots cannot change their own display name per-message (only webhooks can)

## Channel ID Format

Discord channels use `discord:{channel_id}` (e.g., `discord:1234567890`).
