#!/usr/bin/env python3
"""
SMS auto-reply as Claudius via Claudicle cognitive pipeline.

Reads unhandled inbound messages from inbox.jsonl, generates soul-aware replies
using the same split-mode pipeline as the Slack daemon (engine/pipeline.py),
sends via Twilio, and updates 3-tier memory atomically.

Channel-agnostic: same cognitive steps, same memory, same soul state as
Slack/Discord/terminal. Only the transport layer (Twilio SMS) differs.

Two modes:
  Manual:  python3 sms_respond.py              (process once, exit)
  Daemon:  python3 sms_respond.py --daemon      (loop forever)

Requires: requests (for Twilio), Claudicle daemon on sys.path
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ── Path Setup ────────────────────────────────────────────────────────────
# Add daemon dir to sys.path so we can import engine, memory, etc.
_ADAPTER_DIR = Path(__file__).parent.resolve()
_DAEMON_DIR = Path(os.environ.get("CLAUDICLE_HOME", Path.home() / ".claudicle")) / "daemon"
if not _DAEMON_DIR.exists():
    # Fallback: relative to adapter location (repo layout)
    _DAEMON_DIR = _ADAPTER_DIR.parent.parent / "daemon"

sys.path.insert(0, str(_DAEMON_DIR))
sys.path.insert(0, str(_ADAPTER_DIR))

from _sms_utils import (
    read_inbox, mark_inbox_handled,
    twilio_request, log_message, normalize_e164,
    DEFAULT_TWILIO_FROM, SMSError,
)

# Claudicle daemon imports (now on sys.path)
import config
from engine import pipeline, soul_engine
from memory import working_memory
from monitoring import soul_log

log = logging.getLogger("claudicle.sms")

# ── Config ───────────────────────────────────────────────────────────────

DEFAULT_OUR_NUMBER = DEFAULT_TWILIO_FROM  # +18557066006
MAX_REPLY_LENGTH = 480  # 3 SMS segments
COOLDOWN_SECONDS = 30
DATA_DIR = _ADAPTER_DIR.parent / "data"
RESPONDER_PID = DATA_DIR / "responder.pid"
RESPONDER_LOG = DATA_DIR / "responder.log"

# ── Reply Dedup (local SQLite — lightweight, no sms_memory import) ────

_DEDUP_DB = DATA_DIR / "sms_dedup.db"
_dedup_local = threading.local()

def _dedup_conn() -> sqlite3.Connection:
    if not hasattr(_dedup_local, "conn") or _dedup_local.conn is None:
        _DEDUP_DB.parent.mkdir(parents=True, exist_ok=True)
        _dedup_local.conn = sqlite3.connect(str(_DEDUP_DB))
        _dedup_local.conn.execute(
            "CREATE TABLE IF NOT EXISTS replied (msg_id TEXT PRIMARY KEY, ts REAL)"
        )
        _dedup_local.conn.commit()
    return _dedup_local.conn

def was_replied(msg_id: str) -> bool:
    return _dedup_conn().execute("SELECT 1 FROM replied WHERE msg_id=?", (msg_id,)).fetchone() is not None

def mark_replied(msg_id: str) -> None:
    conn = _dedup_conn()
    conn.execute("INSERT OR IGNORE INTO replied (msg_id, ts) VALUES (?,?)", (msg_id, time.time()))
    conn.commit()

def cleanup_replied(max_age_hours: int = 168) -> int:
    conn = _dedup_conn()
    cur = conn.execute("DELETE FROM replied WHERE ts < ?", (time.time() - max_age_hours * 3600,))
    conn.commit()
    return cur.rowcount


# ── Channel Helpers ──────────────────────────────────────────────────────

def _sms_channel(phone: str) -> str:
    """Build Claudicle channel ID for an SMS conversation."""
    return f"sms:{phone}"


def _sms_thread(phone: str) -> str:
    """Stable thread_ts for SMS — one continuous thread per contact."""
    return f"sms_{phone.replace('+', '')}"


# ── Send Reply ───────────────────────────────────────────────────────────

def send_reply(to: str, body: str, from_number: str = DEFAULT_OUR_NUMBER) -> dict:
    """Send an SMS reply via Twilio and log it."""
    if len(body) > MAX_REPLY_LENGTH:
        body = body[:MAX_REPLY_LENGTH - 1] + "\u2026"

    result = twilio_request("POST", "/Messages.json", data={
        "From": from_number,
        "To": to,
        "Body": body,
    })

    log_message({
        "direction": "outbound",
        "from": from_number,
        "to": to,
        "body": body,
        "status": result.get("status", "unknown"),
        "provider": "twilio",
        "id": result.get("sid", "unknown"),
    })

    return {"id": result.get("sid", "unknown"), "status": result.get("status", "unknown")}


# ── Pipeline Invocation ──────────────────────────────────────────────────

async def _run_cognitive_pipeline(
    text: str,
    their_number: str,
    channel: str,
    thread_ts: str,
) -> Optional[str]:
    """Run the Claudicle cognitive pipeline and return the dialogue response.

    Same code path as the Slack daemon (claude_handler.async_process):
    store user message → emit stimulus → run_pipeline → return dialogue.
    """
    trace_id = working_memory.new_trace_id()

    # Store inbound message in canonical working memory
    soul_engine.store_user_message(
        text, their_number, channel, thread_ts,
        display_name=their_number,
    )

    soul_log.emit(
        "stimulus", trace_id, channel=channel, thread_ts=thread_ts,
        origin="sms", user_id=their_number, display_name=their_number,
        text=text, text_length=len(text),
    )

    stimulus_ts = time.time()

    # Run the split-mode pipeline (routes per-step to Groq/Ollama/etc.)
    result = await pipeline.run_pipeline(
        text, their_number, channel, thread_ts,
    )

    response = result.dialogue
    if not response:
        return None

    # Truncate for SMS
    if len(response) > MAX_REPLY_LENGTH:
        response = response[:MAX_REPLY_LENGTH - 1] + "\u2026"

    elapsed_ms = int((time.time() - stimulus_ts) * 1000)
    soul_log.emit(
        "response", trace_id, channel=channel, thread_ts=thread_ts,
        text=response, text_length=len(response),
        elapsed_ms=elapsed_ms,
    )

    return response


def invoke_pipeline(text: str, their_number: str) -> Optional[str]:
    """Sync wrapper for the async pipeline. Returns dialogue text or None."""
    channel = _sms_channel(their_number)
    thread_ts = _sms_thread(their_number)
    return asyncio.run(_run_cognitive_pipeline(text, their_number, channel, thread_ts))


# ── Process One Message ──────────────────────────────────────────────────

def process_message(msg: dict, dry_run: bool = False) -> bool:
    """Process a single inbound message. Returns True if reply was sent."""
    msg_id = msg.get("id", "?")
    their_number = normalize_e164(msg.get("from", ""))
    our_number = normalize_e164(msg.get("to", DEFAULT_OUR_NUMBER))
    body = msg.get("body", "").strip()

    if not body:
        print(f"  Skipping empty message {msg_id}")
        mark_inbox_handled(msg_id)
        return False

    # Dedup check
    if was_replied(msg_id):
        print(f"  Already replied to {msg_id}, skipping")
        mark_inbox_handled(msg_id)
        return False

    # Cooldown check — use canonical working memory
    channel = _sms_channel(their_number)
    thread_ts = _sms_thread(their_number)
    recent = working_memory.get_recent(channel, thread_ts, limit=1)
    if recent:
        last = recent[-1] if isinstance(recent[-1], dict) else dict(recent[-1])
        if last.get("entry_type") == "externalDialog":
            elapsed = time.time() - last.get("created_at", 0)
            if elapsed < COOLDOWN_SECONDS:
                print(f"  Cooldown active ({elapsed:.0f}s < {COOLDOWN_SECONDS}s), skipping")
                return False

    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] Processing: {their_number} -> \"{body[:60]}\"")

    # Run cognitive pipeline (same as Slack daemon)
    try:
        reply_text = invoke_pipeline(body, their_number)
    except Exception as e:
        print(f"  Pipeline error: {e}", file=sys.stderr, flush=True)
        log.exception("Pipeline error for %s", their_number)
        return False

    if not reply_text:
        print(f"  No dialogue in pipeline result, skipping send")
        mark_inbox_handled(msg_id)
        return False

    if dry_run:
        print(f"  [DRY RUN] Would send: \"{reply_text[:80]}\"")
    else:
        try:
            send_result = send_reply(their_number, reply_text, from_number=our_number)
            print(f"  Sent reply ({send_result['status']}): \"{reply_text[:60]}\"")
        except SMSError as e:
            print(f"  Send error: {e}", file=sys.stderr)
            return False

    # Mark as handled + dedup
    mark_inbox_handled(msg_id)
    mark_replied(msg_id)

    return True


# ── Main Loop ────────────────────────────────────────────────────────────

def process_inbox(dry_run: bool = False) -> int:
    """Process all unhandled inbox messages. Returns count of replies sent."""
    messages = read_inbox(filter_handled=True)
    if not messages:
        return 0

    count = 0
    for msg in messages:
        if process_message(msg, dry_run=dry_run):
            count += 1
    return count


def daemon_loop(interval: int, dry_run: bool = False):
    """Run the responder in daemon mode, polling inbox every `interval` seconds."""
    stop = False

    def _handle_signal(signum, frame):
        nonlocal stop
        stop = True
        print("\nResponder shutting down...", flush=True)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    mode = "split" if pipeline.is_split_mode() else "unified"
    print(f"SMS responder daemon started (PID {os.getpid()})", flush=True)
    print(f"  Pipeline: {mode}", flush=True)
    print(f"  Polling: every {interval}s", flush=True)
    print(f"  Dry run: {dry_run}", flush=True)

    cleanup_counter = 0

    while not stop:
        try:
            count = process_inbox(dry_run=dry_run)
            if count:
                print(f"  Processed {count} message(s)", flush=True)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Error: {e}", file=sys.stderr, flush=True)

        cleanup_counter += 1
        if cleanup_counter >= 360:  # Every ~30 min at 5s interval
            cleanup_replied()
            cleanup_counter = 0

        for _ in range(interval * 10):
            if stop:
                break
            time.sleep(0.1)

    try:
        RESPONDER_PID.unlink(missing_ok=True)
    except (AttributeError, FileNotFoundError):
        pass


# ── Daemon Lifecycle ─────────────────────────────────────────────────────

def cmd_status():
    try:
        pid = int(RESPONDER_PID.read_text().strip())
        os.kill(pid, 0)
        print(f"Responder running (PID {pid})")
    except (FileNotFoundError, ValueError, OSError):
        print("Responder is not running.")
        try:
            RESPONDER_PID.unlink(missing_ok=True)
        except (AttributeError, FileNotFoundError):
            pass


def cmd_stop():
    try:
        pid = int(RESPONDER_PID.read_text().strip())
        os.kill(pid, 0)
    except (FileNotFoundError, ValueError, OSError):
        print("Responder is not running.")
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    try:
        RESPONDER_PID.unlink(missing_ok=True)
    except (AttributeError, FileNotFoundError):
        pass
    print(f"Responder (PID {pid}) stopped.")


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SMS auto-reply as Claudius via Claudicle cognitive pipeline"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daemon", action="store_true", help="Run in daemon mode (loop)")
    group.add_argument("--status", action="store_true", help="Check if daemon is running")
    group.add_argument("--stop", action="store_true", help="Stop running daemon")

    parser.add_argument("--bg", action="store_true", help="Run daemon in background")
    parser.add_argument("--interval", type=int, default=5, help="Poll interval in seconds (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Process but don't send replies")

    args = parser.parse_args()

    if args.status:
        cmd_status()
        return
    if args.stop:
        cmd_stop()
        return

    if args.daemon:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        if args.bg:
            pid = os.fork()
            if pid > 0:
                RESPONDER_PID.write_text(str(pid))
                print(f"Responder started in background (PID {pid})")
                return
            os.setsid()
            log_fd = open(RESPONDER_LOG, "a")
            os.dup2(log_fd.fileno(), sys.stdout.fileno())
            os.dup2(log_fd.fileno(), sys.stderr.fileno())
        else:
            RESPONDER_PID.write_text(str(os.getpid()))

        daemon_loop(args.interval, dry_run=args.dry_run)
    else:
        count = process_inbox(dry_run=args.dry_run)
        if count:
            print(f"\nProcessed {count} message(s).")
        else:
            print("No unhandled messages in inbox.")


if __name__ == "__main__":
    main()
