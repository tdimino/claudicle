# Telegram Setup

Connect Claudicle to Telegram via the Bot API. Uses polling mode — no webhook server required.

---

## Prerequisites

- A Telegram account
- Python 3.10+ with `python-telegram-bot` v21+

## Create a Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Choose a display name (e.g., "Claudicle")
4. Choose a username ending in `bot` (e.g., `claudicle_bot`)
5. Copy the bot token BotFather gives you

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Token from BotFather |
| `CLAUDICLE_TELEGRAM_ALLOWED_CHATS` | No | `""` (all) | Comma-separated chat IDs to respond in |
| `CLAUDICLE_TELEGRAM_RESPOND_TO_MENTIONS` | No | `true` | Respond when @mentioned in groups |
| `CLAUDICLE_TELEGRAM_RESPOND_TO_DMS` | No | `true` | Respond to direct messages |

Set `TELEGRAM_BOT_TOKEN` in `~/.config/env/secrets.env`.

## Running

### Session Bridge mode (standalone listener)

```bash
cd adapters/telegram
python3 telegram_listen.py
```

Writes inbound messages to `daemon/inbox.jsonl` for async processing.

### Unified Launcher mode (integrated)

```bash
cd daemon
python3 claudicle.py
```

The unified launcher starts the Telegram adapter alongside Slack, Discord, and terminal. Responds in real-time.

### Sending messages

```bash
cd adapters/telegram
python3 telegram_post.py --chat-id CHAT_ID "Hello from Claudicle"
```

## Features

- **Polling mode**: No webhook server needed — works behind NAT/firewalls
- **Thread tracking**: Via `reply_to_message_id`
- **Daimon identity**: Name prefix pattern (Telegram bots cannot change display name per-message)
- **Message splitting**: Automatic at 4096 characters
- **@mention stripping**: Bot username removed from message text before processing
- **Chat allowlist**: Restrict responses to specific chats via `CLAUDICLE_TELEGRAM_ALLOWED_CHATS`

## Daimon Mode

In groups, use daimon mode commands:
- `!artifex speak` — Activate a daimon voice
- `!kothar off` — Deactivate daimon mode

## Limitations

- Telegram bots cannot change their display name per-message (daimon identity uses name prefix)
- Telegram bots cannot add reactions to messages
- In groups, the bot only responds to @mentions (DMs respond to all messages)

## Channel ID Format

Telegram channels use `telegram:{chat_id}` (e.g., `telegram:123456789`).
