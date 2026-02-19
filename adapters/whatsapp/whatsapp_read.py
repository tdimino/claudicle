#!/usr/bin/env python3
"""Read WhatsApp messages from the Claudicle inbox.

Usage:
    python3 whatsapp_read.py                       # All WhatsApp messages
    python3 whatsapp_read.py --from "+15551234567"  # From specific sender
    python3 whatsapp_read.py --unhandled            # Unhandled only
    python3 whatsapp_read.py --json                 # JSON output
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import _whatsapp_utils as utils


def read_inbox(from_phone=None, unhandled_only=False, limit=50):
    """Read WhatsApp messages from inbox.jsonl."""
    inbox = utils.inbox_path()
    if not os.path.exists(inbox):
        return []

    messages = []
    with open(inbox, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not utils.is_whatsapp_channel(entry.get("channel", "")):
                continue

            if unhandled_only and entry.get("handled", False):
                continue

            if from_phone:
                phone = utils.phone_from_channel(entry.get("channel", ""))
                if phone != utils.normalize_phone(from_phone):
                    continue

            messages.append(entry)

    return messages[-limit:]


def main():
    parser = argparse.ArgumentParser(description="Read WhatsApp messages from inbox")
    parser.add_argument("--from", dest="from_phone", help="Filter by sender phone")
    parser.add_argument("--unhandled", action="store_true", help="Show unhandled only")
    parser.add_argument("-n", "--limit", type=int, default=50, help="Max messages")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    messages = read_inbox(
        from_phone=args.from_phone,
        unhandled_only=args.unhandled,
        limit=args.limit,
    )

    if not messages:
        print("No WhatsApp messages found.")
        return

    if args.json:
        print(json.dumps(messages, indent=2))
        return

    for i, msg in enumerate(messages, 1):
        phone = utils.phone_from_channel(msg.get("channel", ""))
        name = msg.get("display_name", phone)
        text = msg.get("text", "")
        handled = "handled" if msg.get("handled") else "unhandled"
        print(f"[{i}] {name} ({phone}) [{handled}]: {text[:120]}")


if __name__ == "__main__":
    main()
