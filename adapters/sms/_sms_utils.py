"""
Shared SMS utilities — config, provider abstraction, HTTP helpers.

All sms_*.py scripts import from this module.

Requires: requests (pip install requests)
Credentials: TELNYX_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN env vars
             Falls back to ~/.claude.json for Telnyx key
"""

import os
import sys
import json
import re
import requests
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# ── Provider Phone Number Registry ──────────────────────────────────────────

TELNYX_NUMBERS = {
    # Add your Telnyx numbers here:
    # "+18001234567": {"type": "longcode", "label": "Primary"},
}

TWILIO_NUMBERS = {
    # Add your Twilio numbers here:
    # "+18001234567": {"type": "local", "label": "Main"},
}

# Defaults — override with --from flag or populate the registries above
DEFAULT_TELNYX_FROM = os.environ.get("TELNYX_DEFAULT_FROM", "")
DEFAULT_TWILIO_FROM = os.environ.get("TWILIO_DEFAULT_FROM", "")
DEFAULT_PROVIDER = os.environ.get("SMS_DEFAULT_PROVIDER", "telnyx")

TELNYX_MESSAGING_PROFILE_ID = os.environ.get("TELNYX_MESSAGING_PROFILE_ID", "")


# ── Credential Loading ──────────────────────────────────────────────────────

def _load_claude_json() -> Dict[str, Any]:
    """Load ~/.claude.json for fallback credentials."""
    path = Path.home() / ".claude.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_telnyx_api_key() -> str:
    """Get Telnyx API key from env var or ~/.claude.json."""
    key = os.environ.get("TELNYX_API_KEY")
    if key:
        return key
    config = _load_claude_json()
    key = config.get("mcpServers", {}).get("telnyx", {}).get("env", {}).get("TELNYX_API_KEY")
    if key:
        return key
    print("Error: TELNYX_API_KEY not found in env vars or ~/.claude.json", file=sys.stderr)
    sys.exit(1)


def get_twilio_credentials() -> Tuple[str, str]:
    """Get Twilio Account SID and Auth Token from env vars."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        print("Error: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set", file=sys.stderr)
        sys.exit(1)
    return sid, token


# ── Phone Number Utilities ──────────────────────────────────────────────────

def normalize_e164(number: str) -> str:
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX for US)."""
    digits = re.sub(r"[^\d+]", "", number)
    if digits.startswith("+"):
        return digits
    if digits.startswith("1") and len(digits) == 11:
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


def detect_provider(from_number: str) -> str:
    """Detect provider from a from-number by checking known registries."""
    if from_number in TELNYX_NUMBERS:
        return "telnyx"
    if from_number in TWILIO_NUMBERS:
        return "twilio"
    return DEFAULT_PROVIDER


def get_default_from(provider: str) -> str:
    """Get the default from-number for a provider."""
    if provider == "telnyx":
        return DEFAULT_TELNYX_FROM
    return DEFAULT_TWILIO_FROM


def resolve_from_and_provider(from_number: Optional[str], provider: Optional[str]) -> Tuple[str, str]:
    """
    Resolve the from-number and provider from user flags.

    Priority:
    1. If --from given, detect provider from number (unless --provider also given)
    2. If --provider given without --from, use that provider's default number
    3. If neither, use DEFAULT_PROVIDER and its default number
    """
    if from_number:
        from_number = normalize_e164(from_number)
        if not provider:
            provider = detect_provider(from_number)
        return from_number, provider

    if provider:
        return get_default_from(provider), provider

    return get_default_from(DEFAULT_PROVIDER), DEFAULT_PROVIDER


# ── HTTP Helpers ────────────────────────────────────────────────────────────

class SMSError(Exception):
    """Raised when an SMS API call fails."""
    def __init__(self, provider: str, status: int, detail: str):
        self.provider = provider
        self.status = status
        self.detail = detail
        super().__init__(f"[{provider}] HTTP {status}: {detail}")


def telnyx_request(method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
    """Make a request to the Telnyx API."""
    key = get_telnyx_api_key()
    url = f"https://api.telnyx.com/v2{endpoint}"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    resp = requests.request(method, url, headers=headers, **kwargs)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("errors", [{}])[0].get("detail", resp.text)
        except (json.JSONDecodeError, IndexError, KeyError):
            detail = resp.text
        raise SMSError("telnyx", resp.status_code, detail)
    if resp.status_code == 204 or not resp.text:
        return {}
    return resp.json()


def twilio_request(method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
    """Make a request to the Twilio API."""
    sid, token = get_twilio_credentials()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}{endpoint}"
    resp = requests.request(method, url, auth=(sid, token), **kwargs)
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("message", resp.text)
        except (json.JSONDecodeError, KeyError):
            detail = resp.text
        raise SMSError("twilio", resp.status_code, detail)
    return resp.json()


# ── Local Message Log ──────────────────────────────────────────────────────

MESSAGE_LOG_PATH = Path(__file__).parent.parent / "data" / "messages.jsonl"


def log_message(msg: Dict[str, Any]) -> None:
    """Append a message record to the local JSONL log."""
    MESSAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": msg.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "direction": msg.get("direction", "outbound"),
        "from": msg.get("from", "?"),
        "to": msg.get("to", "?"),
        "body": msg.get("body", ""),
        "status": msg.get("status", "?"),
        "provider": msg.get("provider", "?"),
        "id": msg.get("id", "?"),
    }
    with open(MESSAGE_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_message_log(
    their_number: str = None,
    our_number: str = None,
    direction: str = None,
    provider: str = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Read messages from the local JSONL log, with optional filters."""
    if not MESSAGE_LOG_PATH.exists():
        return []

    messages = []
    for line in MESSAGE_LOG_PATH.read_text().strip().split("\n"):
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        if direction and msg.get("direction") != direction:
            continue
        if provider and msg.get("provider") != provider:
            continue
        if their_number:
            their = normalize_e164(their_number)
            involves = normalize_e164(msg.get("from", "")) == their or normalize_e164(msg.get("to", "")) == their
            if not involves:
                continue
        if our_number:
            our = normalize_e164(our_number)
            involves = normalize_e164(msg.get("from", "")) == our or normalize_e164(msg.get("to", "")) == our
            if not involves:
                continue

        messages.append(msg)

    # Most recent first
    messages.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return messages[:limit]


# ── Formatting ──────────────────────────────────────────────────────────────

def format_timestamp(ts: str) -> str:
    """Parse ISO 8601 or RFC 2822 timestamp to readable local time."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    # Twilio uses RFC 2822
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(ts)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass
    return ts


def truncate(text: str, max_len: int = 80) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"
