---
title: "WhatsApp Adapter"
directory: adapters/whatsapp/
files: 7
created: 2026-02-17
description: "WhatsApp integration via Baileys (WhatsApp Web protocol) — linked device, no Meta account needed"
protocol: "Baileys WebSocket + Express HTTP"
dependencies:
  - "@whiskeysockets/baileys"
  - express
  - qrcode-terminal
---

# WhatsApp Adapter

WhatsApp integration via Baileys (WhatsApp Web protocol). Connects as a linked device on your personal WhatsApp account—no Meta developer account or business verification needed.

## Architecture

```
WhatsApp ←→ Baileys Gateway (Node.js, port 3847)
              ├── incoming → daemon/inbox.jsonl (shared format)
              ├── outgoing ← POST /send (Express HTTP)
              └── auth: QR code pairing, persisted in auth_info/

Python adapter scripts:
  ├── _whatsapp_utils.py    shared config, phone normalization, gateway API
  ├── whatsapp_send.py      POST to gateway /send endpoint
  ├── whatsapp_read.py      read inbox.jsonl filtered by whatsapp: channels
  └── whatsapp_listen.py    start/stop/status for the Node.js gateway
```

## Setup

```bash
# 1. Install Node.js dependencies
cd adapters/whatsapp && npm install

# 2. First-time QR pairing (foreground)
python3 whatsapp_listen.py --pair
# → Scan QR code with WhatsApp → Settings → Linked Devices → Link a Device

# 3. Set allowed senders (E.164 format, comma-separated)
export WHATSAPP_ALLOWED_SENDERS="+15551234567,+15559876543"

# 4. Start gateway in background
python3 whatsapp_listen.py --start

# 5. Check status
python3 whatsapp_listen.py --status
```

Messages now flow into `daemon/inbox.jsonl`. The inbox watcher auto-responds, or process manually with `/slack-respond` (which handles all channel types).

## Commands

| Command | Description |
|---------|-------------|
| `python3 whatsapp_listen.py --pair` | First-time QR pairing (foreground) |
| `python3 whatsapp_listen.py --start` | Start gateway in background |
| `python3 whatsapp_listen.py --stop` | Stop gateway |
| `python3 whatsapp_listen.py --status` | Check gateway status |
| `python3 whatsapp_send.py "+1555..." "text"` | Send a message |
| `python3 whatsapp_read.py` | Read WhatsApp messages from inbox |
| `python3 whatsapp_read.py --unhandled` | Show unhandled messages only |

## Security

| Layer | Default | Configuration |
|-------|---------|---------------|
| Allowlist | Reject all (secure) | `WHATSAPP_ALLOWED_SENDERS` — comma-separated E.164 numbers |
| Rate limiting | 10 msgs/min/sender | `WHATSAPP_RATE_LIMIT` |
| Echo prevention | On | Baileys `fromMe` flag |
| Groups | Blocked | Only individual chats accepted |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WHATSAPP_ALLOWED_SENDERS` | (empty = reject all) | Comma-separated E.164 phone numbers |
| `WHATSAPP_RATE_LIMIT` | `10` | Max messages per sender per minute |
| `WHATSAPP_GATEWAY_PORT` | `3847` | Gateway HTTP server port |
| `WHATSAPP_GATEWAY_URL` | `http://localhost:3847` | Gateway URL (for Python scripts) |

## Files

| File | Purpose |
|------|---------|
| `gateway.js` | Baileys WhatsApp Web client + Express HTTP server |
| `package.json` | Node.js dependencies |
| `_whatsapp_utils.py` | Shared Python utilities |
| `whatsapp_send.py` | Send messages via gateway |
| `whatsapp_read.py` | Read WhatsApp messages from inbox |
| `whatsapp_listen.py` | Gateway lifecycle management |
| `auth_info/` | Baileys auth state (gitignored) |

## Integration

The inbox watcher (`daemon/inbox_watcher.py`) auto-detects WhatsApp messages by the `whatsapp:` channel prefix and routes responses through `whatsapp_send.py` instead of Slack. No changes needed to the core cognitive pipeline.

## Dependencies

**Node.js** (gateway only):
- `@whiskeysockets/baileys` — WhatsApp Web protocol
- `express` — HTTP server for outbound
- `qrcode-terminal` — QR code display

**Python** (no new dependencies):
- stdlib only (`subprocess`, `json`, `argparse`, `urllib.request`)
