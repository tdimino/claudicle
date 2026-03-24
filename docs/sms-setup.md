# SMS Setup

Connect Claudicle to SMS via Telnyx and/or Twilio. Both providers are supported simultaneously — each phone number auto-detects its provider.

---

## Prerequisites

- A Telnyx account with at least one phone number, OR
- A Twilio account with at least one phone number
- Python 3.10+

## Provider Setup

### Telnyx

1. Create a [Telnyx account](https://portal.telnyx.com/)
2. Purchase a phone number under **Numbers → Buy Numbers**
3. Create a Messaging Profile under **Messaging → Profiles**
4. Assign your number to the messaging profile
5. Set the webhook URL to `http://YOUR_HOST:9147/telnyx/webhook` (for inbound messages)
6. Copy your API key from **Auth → API Keys**

### Twilio

1. Create a [Twilio account](https://console.twilio.com/)
2. Purchase a phone number
3. Note your Account SID and Auth Token from the dashboard
4. Twilio inbound messages are polled (no webhook needed for basic setup)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELNYX_API_KEY` | For Telnyx | API key from Telnyx portal |
| `TWILIO_ACCOUNT_SID` | For Twilio | Account SID from Twilio console |
| `TWILIO_AUTH_TOKEN` | For Twilio | Auth token from Twilio console |

Set these in `~/.config/env/secrets.env` or as environment variables.

## Number Registration

Phone numbers and their providers are registered in `adapters/sms/_sms_utils.py`. The system auto-detects whether a number belongs to Telnyx or Twilio based on a provider mapping.

All phone numbers must be in **E.164 format**: `+1XXXXXXXXXX` (e.g., `+17327595647`).

## Running

### Listener (inbound messages)

```bash
cd adapters/sms
python3 sms_listen.py
```

This starts both subsystems:
- **Telnyx**: Webhook server on port 9147
- **Twilio**: Polling loop for new messages

Inbound messages are written to `daemon/inbox.jsonl` for the Claudicle responder.

### Sending messages

```bash
cd adapters/sms
python3 sms_send.py --to "+1XXXXXXXXXX" --from "+1YYYYYYYYYY" "Hello from Claudicle"
```

### Auto-responder

```bash
cd adapters/sms
python3 sms_respond.py
```

The responder includes:
- **Message batching**: 10s quiet period, 60s max wait, up to 50 messages per batch
- **URL classification**: `bare_url`, `url_with_text`, `text` — Twitter domains detected automatically
- **Deduplication**: Prevents duplicate processing within cooldown windows
- **Dead-letter handling**: Failed messages get apology responses (rate-limited to 1/hour)
- **Memory integration**: Three-tier memory via `adapters/shared/claudicle_memory.py`

## Integration with Claudicle

SMS channels use the format `sms:{phone}` (e.g., `sms:+17327595647`). Working memory, user models, and soul state are all accessible through the shared memory router.

User models are resolved by phone number via `adapters/shared/usermodel_resolver.py`, which scans `~/.claude/userModels/*/` for YAML frontmatter containing `phone:` fields.

## Troubleshooting

- **Messages not arriving**: Check that the Telnyx webhook URL is correct and publicly accessible, or that Twilio polling is running
- **Wrong provider**: Verify the number → provider mapping in `_sms_utils.py`
- **E.164 format**: All numbers must include country code with `+` prefix
