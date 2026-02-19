#!/usr/bin/env python3
"""Situational awareness report for Claudicle activation.

Gathers workspace, soul state, recent channels, known users, and inbox
into a structured readout that Claudicle narrates in-character.
"""

import json
import os
import sqlite3
import sys
import time

CLAUDICLE_HOME = os.environ.get("CLAUDICLE_HOME", os.path.expanduser("~/.claudicle"))
DAEMON_DIR = os.path.join(CLAUDICLE_HOME, "daemon")
DB_PATH = os.path.join(DAEMON_DIR, "memory.db")
INBOX_PATH = os.path.join(DAEMON_DIR, "inbox.jsonl")

sys.path.insert(0, DAEMON_DIR)


def _ago(ts):
    """Human-readable time-ago string."""
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    return f"{int(delta / 86400)}d ago"


def get_workspace():
    """Get Slack workspace name via auth.test."""
    try:
        from slack_sdk import WebClient

        token = os.environ.get("SLACK_BOT_TOKEN", "")
        if not token:
            return None
        client = WebClient(token=token)
        info = client.auth_test()
        return info.get("team", None)
    except Exception:
        return None


def get_soul_state():
    """Get soul memory state."""
    try:
        import soul_memory

        state = soul_memory.get_all()
        soul_memory.close()
        return state
    except Exception:
        return {}


def get_recent_channels(conn, limit=8):
    """Get channels with most recent user messages."""
    try:
        rows = conn.execute(
            """SELECT channel, user_id, MAX(created_at) as last_seen
               FROM working_memory
               WHERE entry_type = 'userMessage'
               GROUP BY channel
               ORDER BY last_seen DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        results = []
        for ch, uid, ts in rows:
            name_row = conn.execute(
                "SELECT display_name FROM user_models WHERE user_id = ?", (uid,)
            ).fetchone()
            name = name_row[0] if name_row else uid
            results.append({"channel": ch, "user": name, "user_id": uid, "last_seen": ts})
        return results
    except Exception:
        return []


def get_known_users(conn, limit=10):
    """Get known users sorted by most recent interaction."""
    try:
        rows = conn.execute(
            """SELECT display_name, user_id, interaction_count, updated_at
               FROM user_models
               ORDER BY updated_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {"name": name or uid, "user_id": uid, "interactions": count, "last_seen": updated}
            for name, uid, count, updated in rows
        ]
    except Exception:
        return []


def get_inbox_summary():
    """Count unhandled inbox messages and extract channel info."""
    unhandled = []
    if not os.path.exists(INBOX_PATH):
        return unhandled
    try:
        with open(INBOX_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if not entry.get("handled"):
                    unhandled.append({
                        "channel": entry.get("channel", "?"),
                        "user": entry.get("display_name", entry.get("user_id", "?")),
                        "text": entry.get("text", "")[:80],
                    })
    except Exception:
        pass
    return unhandled


def main():
    # Workspace
    workspace = get_workspace()
    print(f"**Workspace**: {workspace or '(not connected)'}")

    # Soul state
    state = get_soul_state()
    emotion = state.get("emotionalState", "neutral")
    topic = state.get("currentTopic", "")
    project = state.get("currentProject", "")
    summary = state.get("conversationSummary", "")

    parts = []
    if emotion and emotion != "neutral":
        parts.append(f"**Emotional State**: {emotion}")
    if topic:
        parts.append(f"**Current Topic**: {topic}")
    if project:
        parts.append(f"**Current Project**: {project}")
    if parts:
        print("\n".join(parts))
    else:
        print("**Soul State**: defaults (fresh start)")
    if summary:
        print(f"**Last Context**: {summary}")

    # DB queries
    conn = None
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
        except Exception:
            pass

    if conn:
        # Recent channels
        channels = get_recent_channels(conn)
        if channels:
            print("\n### Channels (last pinged)")
            for ch in channels:
                print(f"- `{ch['channel']}` — {ch['user']}, {_ago(ch['last_seen'])}")

        # Known users
        users = get_known_users(conn)
        if users:
            print(f"\n### Known Users ({len(users)})")
            for u in users:
                print(f"- **{u['name']}** — {u['interactions']} interactions, last {_ago(u['last_seen'])}")

        conn.close()

    # Inbox
    unhandled = get_inbox_summary()
    if unhandled:
        print(f"\n### Inbox ({len(unhandled)} unhandled)")
        for msg in unhandled[:5]:
            print(f"- `{msg['channel']}` {msg['user']}: \"{msg['text']}\"")
        if len(unhandled) > 5:
            print(f"- ...and {len(unhandled) - 5} more")
    else:
        print("\n### Inbox: empty")


if __name__ == "__main__":
    main()
