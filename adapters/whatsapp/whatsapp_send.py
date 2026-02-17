#!/usr/bin/env python3
"""Send a WhatsApp message via the Claudius WhatsApp Gateway.

Usage:
    python3 whatsapp_send.py "+15551234567" "Hello from Claudius"
    python3 whatsapp_send.py "+15551234567" "Hello" --json
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import _whatsapp_utils as utils


def main():
    parser = argparse.ArgumentParser(description="Send a WhatsApp message")
    parser.add_argument("phone", help="Recipient phone number (E.164 format)")
    parser.add_argument("text", help="Message text to send")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")
    args = parser.parse_args()

    try:
        result = utils.send_message(args.phone, args.text)
    except Exception as exc:
        print(f"Failed to send: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        phone = utils.normalize_phone(args.phone)
        print(f"Sent to {phone} ({result.get('length', '?')} chars)")


if __name__ == "__main__":
    main()
