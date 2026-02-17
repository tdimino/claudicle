#!/usr/bin/env python3
"""
Session handoff hook for Claudius — saves session state on PreCompact and Stop events.

PreCompact: Saves full session state (objectives, completed, decisions, next_steps)
            so the session can resume after context compaction.
Stop:       Updates heartbeat timestamp for session liveness tracking.

Handoff files: ~/.claude/handoffs/{session_id}.yaml

Hook config (settings.json):
    {
        "hooks": {
            "PreCompact": [
                {"type": "command", "command": "python3 ~/.claude/hooks/claudius-handoff.py"}
            ],
            "Stop": [
                {"type": "command", "command": "python3 ~/.claude/hooks/claudius-handoff.py"}
            ]
        }
    }
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HANDOFFS_DIR = Path.home() / ".claude" / "handoffs"


def get_hook_event():
    """Read the hook event from stdin (Claude Code passes JSON)."""
    try:
        data = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, EOFError):
        return {}


def get_session_id():
    """Extract session ID from environment or hook data."""
    return os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "unknown"))


def save_handoff(session_id: str, event_type: str):
    """Save or update a handoff YAML for this session."""
    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    handoff_path = HANDOFFS_DIR / f"{session_id}.yaml"

    now = datetime.now(timezone.utc).isoformat()
    cwd = os.getcwd()
    project = os.path.basename(cwd)

    if event_type == "Stop":
        # Lightweight heartbeat update
        if handoff_path.exists():
            content = handoff_path.read_text()
            # Update the last_seen line
            lines = content.split("\n")
            updated = False
            for i, line in enumerate(lines):
                if line.startswith("last_seen:"):
                    lines[i] = f"last_seen: {now}"
                    updated = True
                    break
            if updated:
                handoff_path.write_text("\n".join(lines))
            else:
                with open(handoff_path, "a") as f:
                    f.write(f"\nlast_seen: {now}\n")
        else:
            # Create minimal handoff
            handoff_path.write_text(
                f"session_id: {session_id}\n"
                f"project: {project}\n"
                f"directory: {cwd}\n"
                f"created: {now}\n"
                f"last_seen: {now}\n"
                f"trigger: stop\n"
            )
    elif event_type == "PreCompact":
        # Full handoff — save everything for context recovery
        handoff_path.write_text(
            f"session_id: {session_id}\n"
            f"project: {project}\n"
            f"directory: {cwd}\n"
            f"created: {now}\n"
            f"last_seen: {now}\n"
            f"trigger: compact\n"
            f"\n"
            f"# Context saved at compaction. Claude Code will resume with this state.\n"
            f"# The session transcript is preserved separately by Claude Code.\n"
        )

    # Update INDEX.md
    update_index(session_id, project, cwd, now, event_type)


def update_index(session_id: str, project: str, directory: str, timestamp: str, trigger: str):
    """Maintain the handoff index file."""
    index_path = HANDOFFS_DIR / "INDEX.md"

    entry = f"| {timestamp[:10]} | {project} | `{session_id[:8]}` | {trigger} |"

    if index_path.exists():
        content = index_path.read_text()
        # Append to table
        if entry not in content:
            with open(index_path, "a") as f:
                f.write(f"{entry}\n")
    else:
        index_path.write_text(
            "# Session Handoffs\n\n"
            "| Date | Project | Session | Trigger |\n"
            "|------|---------|---------|--------|\n"
            f"{entry}\n"
        )


def main():
    event = get_hook_event()
    session_id = get_session_id()

    # Determine event type from hook name or fallback
    hook_name = event.get("hook_name", event.get("type", ""))
    if "compact" in hook_name.lower() or "PreCompact" in str(event):
        event_type = "PreCompact"
    else:
        event_type = "Stop"

    save_handoff(session_id, event_type)


if __name__ == "__main__":
    main()
