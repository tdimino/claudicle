# Channel Comparison

Side-by-side feature matrix for all Claudicle channel adapters.

| Feature | SMS | Slack | Discord | Telegram | WhatsApp |
|---------|-----|-------|---------|----------|----------|
| **Runtime Mode** | Session Bridge | Both | Both | Both | Session Bridge only |
| **Status** | Production | Production | Production | Production | Beta |
| **Auth Method** | API keys (Telnyx/Twilio) | OAuth + Socket Mode | Bot token | Bot token (BotFather) | QR code (linked device) |
| **Reactions** | No | Yes | Via webhooks | No | No |
| **File Uploads** | MMS | Yes | Yes | Yes | No |
| **Daimon Identity** | N/A | Bot name | Webhooks (custom name + avatar) | Name prefix | N/A |
| **Thread Tracking** | Phone number | `thread_ts` | Reply references | `reply_to_message_id` | N/A |
| **Rate Limiting** | 30s cooldown | Slack API built-in | Discord API built-in | python-telegram-bot | 10 msgs/min/sender |
| **Message Limit** | 1,600 chars | ~40,000 chars | 2,000 chars | 4,096 chars | No hard limit |
| **Group Support** | No | Yes | Yes (allowlist) | Yes (@mention required) | No (blocked) |
| **Message Batching** | Yes (10s/60s) | No | No | No | No |
| **URL Classification** | Yes | No | No | No | No |
| **Webhook Required** | Yes (Telnyx) | No (Socket Mode) | No | No (polling) | No |
| **Channel ID Format** | `sms:{phone}` | `C04ABC123` | `discord:{id}` | `telegram:{id}` | `whatsapp:{phone}` |

## Runtime Modes

- **Session Bridge**: Standalone listener writes to `daemon/inbox.jsonl`, processed asynchronously by the inbox watcher
- **Unified Launcher**: Adapter runs inside `daemon/claudicle.py` for real-time, synchronous processing
- **Both**: Supports either mode

## Daimon Identity

How each channel represents different daimon voices:

| Channel | Mechanism | Richness |
|---------|-----------|----------|
| Discord | Webhooks with custom username + avatar per message | Best — full identity per message |
| Slack | Bot display name | Medium — one identity per bot |
| Telegram | Name prefix in message text | Basic — text-only |
| SMS/WhatsApp | Not supported | None |

## Setup Guides

- [Slack Setup](slack-setup.md) — OAuth, Socket Mode, 13 scopes
- [SMS Setup](sms-setup.md) — Telnyx + Twilio, webhooks, batching
- [Telegram Setup](telegram-setup.md) — BotFather, polling mode
- [Discord Setup](discord-setup.md) — Developer Portal, Message Content Intent
- [WhatsApp Setup](whatsapp-setup.md) — Baileys gateway, QR pairing
- [Channel Adapters](channel-adapters.md) — Shared architecture and inbox pattern
