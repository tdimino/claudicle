#!/usr/bin/env python3
"""
Inbox watcher daemon — auto-responds to Slack messages via configurable provider.

Polls inbox.jsonl for unhandled messages and processes them through the
cognitive pipeline using any provider (Haiku, Groq, Ollama, etc.).
Architecturally parallel to slack_listen.py — two lightweight daemons,
one catches messages, one responds.

    slack_listen.py --bg     ← catches @mentions/DMs, writes inbox.jsonl (free)
    inbox_watcher.py --bg    ← polls inbox, processes via provider, posts responses

Usage:
    python3 inbox_watcher.py           # foreground (for testing)
    python3 inbox_watcher.py --bg      # daemonize, write PID file
    python3 inbox_watcher.py --stop    # kill running watcher
    python3 inbox_watcher.py --status  # check if running

Configuration (env vars):
    CLAUDIUS_WATCHER_PROVIDER   Provider name (default: DEFAULT_PROVIDER)
    CLAUDIUS_WATCHER_MODEL      Model override (default: DEFAULT_MODEL)
    CLAUDIUS_WATCHER_POLL       Poll interval in seconds (default: 3)
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time

DAEMON_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DAEMON_DIR)

from config import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    MAX_RESPONSE_LENGTH,
    WATCHER_MODEL,
    WATCHER_POLL_INTERVAL,
    WATCHER_PROVIDER,
)

INBOX = os.path.join(DAEMON_DIR, "inbox.jsonl")
PID_FILE = os.path.join(DAEMON_DIR, "watcher.pid")
SCRIPTS_DIR = os.path.join(os.path.dirname(DAEMON_DIR), "scripts")
ADAPTERS_DIR = os.path.join(os.path.dirname(DAEMON_DIR), "adapters")

log = logging.getLogger("claudius.watcher")


# ---------------------------------------------------------------------------
# PID lifecycle (same pattern as slack_listen.py)
# ---------------------------------------------------------------------------

def _read_pid():
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cmd_stop():
    pid = _read_pid()
    if not _is_running(pid):
        print("Watcher is not running.")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        return
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        if not _is_running(pid):
            break
        time.sleep(0.1)
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass
    print(f"Watcher (PID {pid}) stopped.")


def cmd_status():
    pid = _read_pid()
    if _is_running(pid):
        provider = WATCHER_PROVIDER or DEFAULT_PROVIDER
        model = WATCHER_MODEL or DEFAULT_MODEL or "(default)"
        print(f"Watcher running (PID {pid}) — provider={provider}, model={model}, poll={WATCHER_POLL_INTERVAL}s")
    else:
        print("Watcher is not running.")
        if pid is not None:
            try:
                os.remove(PID_FILE)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Inbox I/O
# ---------------------------------------------------------------------------

def read_unhandled():
    """Read unhandled entries from inbox.jsonl.

    Uses fcntl file locking to prevent race conditions when multiple
    processes read the inbox concurrently. The lock is held briefly
    during the read scan only.
    """
    import fcntl

    if not os.path.exists(INBOX):
        return []
    entries = []
    try:
        with open(INBOX, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)  # shared read lock
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if not entry.get("handled", False):
                        entry["_line_index"] = i
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
            # flock released on close
    except OSError as e:
        log.warning("read_unhandled failed: %s", e)
    return entries


def mark_handled(line_index: int):
    """Mark an inbox entry as handled by rewriting the line.

    Uses fcntl file locking to prevent TOCTOU races with the listener
    (which appends concurrently) and /slack-respond (which may also mark handled).
    """
    import fcntl

    if not os.path.exists(INBOX):
        return
    if line_index < 0:
        log.warning("mark_handled called with invalid line_index=%d", line_index)
        return
    try:
        with open(INBOX, "r+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            lines = f.readlines()
            if line_index < len(lines):
                entry = json.loads(lines[line_index])
                entry["handled"] = True
                lines[line_index] = json.dumps(entry) + "\n"
                f.seek(0)
                f.writelines(lines)
                f.truncate()
            # flock released on close
    except (json.JSONDecodeError, ValueError, OSError) as e:
        log.warning("mark_handled failed for line %d: %s", line_index, e)


# ---------------------------------------------------------------------------
# Slack posting (via scripts)
# ---------------------------------------------------------------------------

def slack_post(channel: str, text: str, thread_ts: str = ""):
    """Post a message to Slack using slack_post.py."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "slack_post.py"), channel, text]
    if thread_ts:
        cmd.extend(["--thread", thread_ts])
    try:
        subprocess.run(cmd, timeout=30, capture_output=True)
    except Exception as e:
        log.error("Failed to post to Slack: %s", e)


def slack_react(channel: str, timestamp: str, emoji: str, remove: bool = False):
    """Add or remove a reaction using slack_react.py."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "slack_react.py"), channel, timestamp, emoji]
    if remove:
        cmd.append("--remove")
    try:
        subprocess.run(cmd, timeout=15, capture_output=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Message processing
# ---------------------------------------------------------------------------

async def process_entry(entry: dict):
    """Process a single inbox entry through the cognitive pipeline."""
    import pipeline
    import soul_engine
    from providers import get_provider

    text = entry.get("text", "")
    user_id = entry.get("user_id", "unknown")
    channel = entry.get("channel", "")
    thread_ts = entry.get("thread_ts", "")
    display_name = entry.get("display_name", user_id)

    log.info("Processing: %s in %s: %s", display_name, channel, text[:60])

    # Route through pipeline (split or unified)
    if pipeline.is_split_mode():
        # Split mode: run pipeline FIRST (so _should_inject_user_model
        # sees empty working_memory on first turn), then store message
        result = await pipeline.run_pipeline(
            text, user_id, channel, thread_ts,
            display_name=display_name,
        )
        soul_engine.store_user_message(text, user_id, channel, thread_ts)
        dialogue = result.dialogue
    else:
        # Unified mode: build prompt FIRST (so _should_inject_user_model
        # sees empty working_memory on first turn), then store message
        prompt = soul_engine.build_prompt(
            text, user_id=user_id, channel=channel,
            thread_ts=thread_ts, display_name=display_name,
        )
        soul_engine.store_user_message(text, user_id, channel, thread_ts)

        provider_name = WATCHER_PROVIDER or DEFAULT_PROVIDER
        provider = get_provider(provider_name)
        model = WATCHER_MODEL or DEFAULT_MODEL

        raw = await provider.agenerate(prompt, model=model)
        dialogue = soul_engine.parse_response(
            raw, user_id=user_id, channel=channel, thread_ts=thread_ts,
        )

    # Truncate if needed
    if len(dialogue) > MAX_RESPONSE_LENGTH:
        dialogue = dialogue[:MAX_RESPONSE_LENGTH] + "\n\n_(truncated)_"

    # Post response — route by channel type
    send_ok = True
    if channel.startswith("whatsapp:"):
        phone = channel.replace("whatsapp:", "")
        whatsapp_send = os.path.join(ADAPTERS_DIR, "whatsapp", "whatsapp_send.py")
        try:
            result = subprocess.run(
                [sys.executable, whatsapp_send, phone, dialogue],
                timeout=30, capture_output=True,
            )
            if result.returncode != 0:
                log.error("WhatsApp send failed (exit %d): %s", result.returncode, result.stderr.decode()[:200])
                send_ok = False
        except Exception as e:
            log.error("Failed to send WhatsApp message: %s", e)
            send_ok = False
    else:
        slack_post(channel, dialogue, thread_ts=thread_ts)
        slack_react(channel, thread_ts, "hourglass_flowing_sand", remove=True)
        slack_react(channel, thread_ts, "white_check_mark")

    # Only mark handled if send succeeded (or Slack, which has its own retry)
    if send_ok:
        mark_handled(entry["_line_index"])
    else:
        log.warning("Message NOT marked handled — will retry on next poll")

    log.info("Responded to %s in %s (%d chars)", display_name, channel, len(dialogue))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def watch_loop():
    """Poll inbox.jsonl and process unhandled messages."""
    provider_name = WATCHER_PROVIDER or DEFAULT_PROVIDER
    model = WATCHER_MODEL or DEFAULT_MODEL or "(default)"
    log.info(
        "Watcher started: provider=%s, model=%s, poll=%ds",
        provider_name, model, WATCHER_POLL_INTERVAL,
    )

    while True:
        try:
            entries = read_unhandled()
            for entry in entries:
                try:
                    await process_entry(entry)
                except Exception as e:
                    log.error(
                        "Failed to process message from %s: %s",
                        entry.get("display_name", "?"), e,
                    )
                    # Mark handled to avoid infinite retry
                    mark_handled(entry["_line_index"])
        except Exception as e:
            log.error("Watch loop error: %s", e)

        await asyncio.sleep(WATCHER_POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Daemon entry point
# ---------------------------------------------------------------------------

def run_watcher(background=False):
    """Start the inbox watcher.

    Single-instance: only one watcher should run at a time. Multiple watchers
    reading the same inbox.jsonl can produce duplicate responses because
    read_unhandled() and mark_handled() are not atomic across processes.
    """
    pid = _read_pid()
    if _is_running(pid):
        print(f"Watcher already running (PID {pid}). Use --stop first.")
        sys.exit(1)

    if background:
        pid = os.fork()
        if pid > 0:
            with open(PID_FILE, "w") as f:
                f.write(str(pid))
            provider = WATCHER_PROVIDER or DEFAULT_PROVIDER
            print(f"Watcher started in background (PID {pid})")
            print(f"Provider: {provider}, Poll: {WATCHER_POLL_INTERVAL}s")
            print(f"Inbox: {INBOX}")
            return
        os.setsid()
        log_path = os.path.join(DAEMON_DIR, "logs", "watcher.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        log_fd = open(log_path, "a")
        os.dup2(log_fd.fileno(), sys.stdout.fileno())
        os.dup2(log_fd.fileno(), sys.stderr.fileno())
    else:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Graceful shutdown
    def _cleanup(signum, frame):
        log.info("Watcher shutting down...")
        try:
            os.remove(PID_FILE)
        except FileNotFoundError:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print(f"Inbox watcher started (PID {os.getpid()})", flush=True)
    asyncio.run(watch_loop())


def main():
    parser = argparse.ArgumentParser(description="Inbox watcher daemon")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bg", action="store_true", help="Run in background")
    group.add_argument("--stop", action="store_true", help="Stop running watcher")
    group.add_argument("--status", action="store_true", help="Check if running")
    args = parser.parse_args()

    if args.stop:
        cmd_stop()
    elif args.status:
        cmd_status()
    else:
        run_watcher(background=args.bg)


if __name__ == "__main__":
    main()
