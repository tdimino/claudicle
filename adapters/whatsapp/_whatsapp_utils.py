"""Shared utilities for the WhatsApp adapter."""

import json
import os
import re
import sys
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env(key, default=""):
    """Read CLAUDIUS_WHATSAPP_ prefixed env var, falling back to WHATSAPP_."""
    return os.environ.get(f"CLAUDIUS_WHATSAPP_{key}", os.environ.get(f"WHATSAPP_{key}", default))


GATEWAY_URL  = _env("GATEWAY_URL", "http://localhost:3847")
GATEWAY_PORT = int(_env("GATEWAY_PORT", "3847"))


# ---------------------------------------------------------------------------
# Phone Normalization
# ---------------------------------------------------------------------------

def normalize_phone(number: str) -> str:
    """Ensure phone number is in E.164 format (+1234567890)."""
    digits = re.sub(r"[^0-9]", "", number)
    if not digits:
        return number
    return f"+{digits}"


# ---------------------------------------------------------------------------
# Channel Detection
# ---------------------------------------------------------------------------

def is_whatsapp_channel(channel: str) -> bool:
    """Check if a channel string belongs to WhatsApp."""
    return channel.startswith("whatsapp:")


def phone_from_channel(channel: str) -> str:
    """Extract phone number from a whatsapp: channel string."""
    return channel.replace("whatsapp:", "")


# ---------------------------------------------------------------------------
# Gateway Communication
# ---------------------------------------------------------------------------

def health_check() -> dict:
    """GET /health — returns gateway status dict or raises."""
    url = f"{GATEWAY_URL}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        return {"status": "unreachable", "error": str(exc)}


def send_message(phone: str, text: str) -> dict:
    """POST /send — send a WhatsApp message via the gateway."""
    url = f"{GATEWAY_URL}/send"
    payload = json.dumps({"phone": normalize_phone(phone), "text": text}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() if exc.fp else ""
        print(f"Gateway error ({exc.code}): {body}", file=sys.stderr)
        raise
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as exc:
        print(f"Gateway unreachable: {exc}", file=sys.stderr)
        raise


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def adapter_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def daemon_dir() -> str:
    return os.path.join(adapter_dir(), "..", "..", "daemon")


def inbox_path() -> str:
    return os.path.join(daemon_dir(), "inbox.jsonl")
