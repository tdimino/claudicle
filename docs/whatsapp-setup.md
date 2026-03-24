# WhatsApp Setup

Connect Claudicle to WhatsApp via a Baileys (WhatsApp Web protocol) Node.js gateway. No Meta developer account needed — uses linked device pairing.

**Status: Beta** — requires manual gateway management and fragile auth state.

---

## Prerequisites

- Node.js 18+
- Python 3.10+
- A WhatsApp account on a phone

## Install

```bash
cd adapters/whatsapp
npm install
```

## First-Time Pairing

```bash
python3 whatsapp_listen.py --pair
```

This starts the Baileys gateway and displays a QR code in the terminal. Scan it with your phone:

1. Open WhatsApp on your phone
2. Go to **Settings → Linked Devices → Link a Device**
3. Scan the QR code

Auth state is saved in `adapters/whatsapp/auth_info/` (gitignored). Subsequent starts don't need re-pairing unless the session expires.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WHATSAPP_ALLOWED_SENDERS` | Recommended | `""` (reject all) | Comma-separated E.164 phone numbers allowed to message |
| `WHATSAPP_RATE_LIMIT` | No | `10` | Max messages per minute per sender |
| `WHATSAPP_GATEWAY_URL` | No | `http://localhost:3847` | Gateway HTTP endpoint |
| `WHATSAPP_GATEWAY_PORT` | No | `3847` | Gateway server port |

## Architecture

```
WhatsApp Web ← Baileys → Node.js gateway (port 3847) → inbox.jsonl
                              ↑
                    Python adapters (send/read/listen)
```

The Node.js gateway (`gateway.js`) handles the WhatsApp Web protocol via Baileys. Python scripts communicate with it over HTTP.

## Running

### Start the gateway

```bash
cd adapters/whatsapp
python3 whatsapp_listen.py
```

### Send a message

```bash
cd adapters/whatsapp
python3 whatsapp_send.py --to "+1XXXXXXXXXX" "Hello from Claudicle"
```

### Check gateway status

```bash
python3 whatsapp_listen.py --status
```

## Security

- **Sender allowlist**: By default, all senders are rejected. Set `WHATSAPP_ALLOWED_SENDERS` to E.164 numbers you trust
- **Rate limiting**: 10 messages per minute per sender (configurable)
- **Echo prevention**: Baileys `fromMe` flag prevents the bot from responding to its own messages
- **Groups blocked**: Only individual chats are processed (security by design)

## Limitations

- **No unified launcher integration** — WhatsApp only works via Session Bridge (inbox.jsonl watcher)
- **Groups blocked** — by design, for security
- **Fragile auth** — Baileys reverse-engineers the WhatsApp Web protocol; auth can break on WhatsApp updates
- **Requires Node.js** — the gateway is JavaScript, unlike other adapters which are pure Python
- **No daimon identity** — WhatsApp doesn't support changing display name per-message

## Channel ID Format

WhatsApp channels use `whatsapp:{phone}` (e.g., `whatsapp:+17327595647`).
