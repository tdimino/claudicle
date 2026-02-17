# WhatsApp Adapter

WhatsApp integration via the WhatsApp Business API. Follows the same adapter pattern as SMS (Telnyx/Twilio).

**Status**: Planned. See `docs/channel-adapters.md` for the adapter interface.

## Design Notes

- WhatsApp Business API requires a Meta developer account and verified business number
- Message format: rich text with media support (images, documents, voice)
- Webhook-based: incoming messages arrive via HTTP POST
- Session model: 24-hour customer service window, template messages outside window
- Rate limits: per-phone-number, per-business
