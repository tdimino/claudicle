# Telegram Adapter

python-telegram-bot integration for Claudicle. Polling mode — no webhook server needed.

## Setup

1. Message @BotFather on Telegram
2. Send `/newbot`, follow prompts (username must end in `bot`)
3. Copy the bot token and set `TELEGRAM_BOT_TOKEN`
4. Start a conversation with your bot or add it to a group

## Environment Variables

```bash
TELEGRAM_BOT_TOKEN=                          # Token from @BotFather
CLAUDICLE_TELEGRAM_ALLOWED_CHATS=            # Comma-separated chat IDs (empty = all)
CLAUDICLE_TELEGRAM_RESPOND_TO_MENTIONS=true  # Respond to @mentions in groups
CLAUDICLE_TELEGRAM_RESPOND_TO_DMS=true       # Respond to private messages
```

## Usage

### Unified Launcher (recommended)

```bash
cd daemon && python3 claudicle.py
# Telegram bot starts automatically if TELEGRAM_BOT_TOKEN is set
# Use --no-telegram to disable
```

### Session Bridge (standalone)

```bash
python3 telegram_listen.py --bg    # Start background listener
python3 telegram_listen.py --stop  # Stop listener
python3 telegram_listen.py --status
```

## Scripts

| Script | Purpose |
|--------|---------|
| `telegram_listen.py` | Session Bridge: writes to inbox.jsonl |
| `telegram_post.py` | Post responses to chats |
| `_telegram_utils.py` | Channel ID helpers, message splitting, config |

## Channel Format

`telegram:{chat_id}` — e.g. `telegram:987654321` (private), `telegram:-100123456789` (group)

## Features

- @mention responses in groups
- All messages in private chats
- Thread tracking via reply_to_message
- Daimon identity via name prefix (`[Kothar wa Khasis]: response`)
- Daimon mode commands: `!artifex speak`, `!kothar off`
- 4096-char message splitting
- Rate limiting handled by python-telegram-bot

## Limitations

- Telegram bots cannot change display name per-message (unlike Discord webhooks)
- Telegram bots cannot add reactions to messages
- Groups require the bot to be @mentioned (unlike DMs)
