"""Slack event tail-log — append-only JSONL stream of all Slack events.

Bolt global middleware captures every event before listeners process it.
The resulting JSONL file can be consumed by ``tail -f``, the monitor TUI,
or any downstream analytics process.

Usage::

    from slack_log import log_all_events
    app.use(log_all_events)
"""

import fcntl
import json
import logging
import os
from datetime import datetime, timezone

from config import CLAUDIUS_HOME

log = logging.getLogger(__name__)

LOG_PATH = os.environ.get(
    "CLAUDIUS_SLACK_LOG",
    os.path.join(CLAUDIUS_HOME, "slack-events.jsonl"),
)


def log_all_events(body, next):
    """Bolt global middleware: append every event to JSONL log.

    Always calls next() regardless of write success or failure.
    The ``next`` parameter name follows Bolt Python middleware convention.
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": body.get("type"),
            "event": body.get("event", {}),
            "team_id": body.get("team_id"),
            "event_id": body.get("event_id"),
        }
        with open(LOG_PATH, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(entry) + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        log.warning("Failed to write event log: %s", e)
    finally:
        next()


def read_log(path=None, last_n=0):
    """Read JSONL log entries. Returns list of dicts.

    Malformed lines are skipped with a warning.

    Args:
        path: Log file path (defaults to LOG_PATH).
        last_n: If positive, return only the last N entries.
    """
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = f.readlines()
    if last_n:
        lines = lines[-last_n:]
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("Skipping malformed log line: %r", line[:120])
    return entries
