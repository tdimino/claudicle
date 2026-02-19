# Channel Adapters

How to add a new channel adapter (Telegram, Discord, WhatsApp, etc.) to Claudicle.

## Adapter Pattern

Each adapter provides scripts for sending, reading, and managing messages on a specific platform. The soul engine is channel-agnostic — it produces text responses. Adapters handle platform-specific formatting and delivery.

## Required Scripts

At minimum, an adapter needs:

| Script | Purpose |
|--------|---------|
| `{platform}_send.py` | Send a message |
| `{platform}_read.py` | Read incoming messages |
| `_{platform}_utils.py` | Shared API client and auth |

## Optional Scripts

| Script | Purpose |
|--------|---------|
| `{platform}_conversation.py` | Thread/conversation management |
| `{platform}_react.py` | Reactions or acknowledgments |
| `{platform}_upload.py` | File/media uploads |

## Integration Points

### 1. Session Bridge Mode

Add inbox support to `slack_listen.py` or create a parallel listener. The listener catches platform events and writes them to an inbox file. `/slack-respond` (or a platform-specific respond command) processes the inbox.

### 2. Unified Launcher Mode

Add the platform as an input channel in `claudicle.py`. The launcher routes responses to the correct platform based on the channel/thread metadata.

### 3. Cognitive Pipeline

The soul engine (`soul_engine.py`) is platform-agnostic. It takes text in, produces structured XML out. The adapter formats the external dialogue for the target platform.

## Existing Adapters

### Slack (`scripts/`)

Full integration with 14 scripts. Uses Socket Mode for real-time events, web API for posting.

### SMS (`adapters/sms/`)

Telnyx and Twilio support. Webhook-based for incoming, API-based for outgoing.

### WhatsApp (`adapters/whatsapp/`)

Baileys-based WhatsApp Web integration. A Node.js gateway connects as a linked device (QR code pairing, no Meta developer account needed). Incoming messages write to `inbox.jsonl`; outbound via Express HTTP `POST /send`. See `adapters/whatsapp/README.md` for setup.

| Script | Purpose |
|--------|---------|
| `gateway.js` | Baileys WhatsApp Web client + HTTP send server |
| `_whatsapp_utils.py` | Shared config, phone normalization, gateway API |
| `whatsapp_send.py` | Send messages via gateway |
| `whatsapp_read.py` | Read WhatsApp messages from inbox |
| `whatsapp_listen.py` | Gateway lifecycle (start/stop/status/pair) |

Channel format: `whatsapp:+15551234567`. The inbox watcher auto-detects this prefix and routes responses through the WhatsApp adapter instead of Slack.

## Inbox Message Format

All adapters write incoming messages to `daemon/inbox.jsonl` in a shared format. One JSON object per line, append-only:

```json
{
  "ts": 1739300000.123,
  "channel": "C12345",
  "thread_ts": "1739300000.123456",
  "user_id": "U12345",
  "display_name": "Tom",
  "text": "What's the status?",
  "handled": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ts` | float | Unix timestamp of the message |
| `channel` | string | Platform-specific channel/conversation ID |
| `thread_ts` | string | Thread identifier (same as `ts` if top-level) |
| `user_id` | string | Platform-specific user ID |
| `display_name` | string | Human-readable name for the user |
| `text` | string | Message content (plain text) |
| `handled` | bool | `false` when new, `true` after processing |

The inbox watcher and `/slack-respond` both consume this format. The first to process marks `handled: true`.

## Posting Interface

Adapters post responses using standalone scripts. The soul engine produces text; the adapter formats and delivers it.

Required posting capabilities:

| Capability | Slack Example | Purpose |
|------------|--------------|---------|
| Post to channel/thread | `slack_post.py "C123" "text" --thread TS` | Deliver response |
| Add reaction | `slack_react.py "C123" TS emoji` | Status indicators |
| Remove reaction | `slack_react.py "C123" TS emoji --remove` | Clear thinking indicator |

The inbox watcher calls these as subprocesses. New adapters should follow the same CLI pattern: `{platform}_post.py CHANNEL TEXT [--thread TS]`.

## Identity Resolution

Each adapter maps platform user IDs to display names for the soul engine's user model system.

| Platform | User ID Format | Resolution |
|----------|---------------|------------|
| Slack | `U12345678` | `users.info` API → `real_name` or `display_name` |
| SMS | `+15551234567` | Phone number (display_name = number or contact name) |
| Discord | `123456789012345678` | `user.display_name` from gateway event |

The `display_name` field in the inbox entry is resolved by the listener at write time, not at processing time.

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Listener loses connection | Reconnect with exponential backoff (Slack Socket Mode handles this) |
| Post fails | Log error, mark message as handled to prevent infinite retry |
| Invalid inbox entry | Skip with `json.JSONDecodeError`, continue processing next entry |
| Rate limit (429) | Slack scripts auto-retry with backoff |

## Adding an Adapter

1. Create `adapters/{platform}/`
2. Implement `_{platform}_utils.py` with auth and client setup
3. Implement `{platform}_send.py` and `{platform}_read.py`
4. Create a listener that writes to `daemon/inbox.jsonl` in the shared format above
5. Add env vars to `config.py` or use platform-specific env vars
6. Create a respond command in `commands/` if using Session Bridge mode
7. Update `daemon/claudicle.py` if adding to Unified Launcher mode
