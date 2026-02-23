#!/usr/bin/env python3
"""Dry-run the soul reflection pipeline without persisting to real storage.

Redirects all DB writes, soul-stream logs, and user model exports to a
temporary directory, runs the full pipeline, and prints the results.

Usage:
    python3 scripts/test-reflect.py "user message" "assistant response"
    python3 scripts/test-reflect.py  # uses default test exchange

The temp directory is printed and preserved so you can inspect artifacts.
"""

import json
import os
import sys
import tempfile

# Create isolated temp directory for all storage
TEMP_DIR = tempfile.mkdtemp(prefix="soul-reflect-test-")
TEMP_DB = os.path.join(TEMP_DIR, "memory.db")
TEMP_SESSIONS_DB = os.path.join(TEMP_DIR, "sessions.db")
TEMP_STREAM = os.path.join(TEMP_DIR, "soul-stream.jsonl")
TEMP_MEMORY_DIR = os.path.join(TEMP_DIR, "memory")
os.makedirs(os.path.join(TEMP_MEMORY_DIR, "users"), exist_ok=True)

# Set env var BEFORE importing anything from daemon
os.environ["CLAUDICLE_SOUL_LOG"] = TEMP_STREAM

# Add daemon to path
CLAUDICLE_HOME = os.environ.get(
    "CLAUDICLE_HOME", os.path.expanduser("~/.claudicle")
)
DAEMON_DIR = os.path.join(CLAUDICLE_HOME, "daemon")
sys.path.insert(0, DAEMON_DIR)

# Monkeypatch DB paths before any module initializes connections
from memory import working_memory, user_models, soul_memory, session_store
working_memory.DB_PATH = TEMP_DB
user_models.DB_PATH = TEMP_DB
soul_memory.DB_PATH = TEMP_DB
session_store.DB_PATH = TEMP_SESSIONS_DB

# Monkeypatch git tracker to use temp dir (prevents real exports + git commits)
from memory import git_tracker
from pathlib import Path
git_tracker.MEMORY_DIR = Path(TEMP_MEMORY_DIR)
git_tracker.USERS_DIR = Path(TEMP_MEMORY_DIR) / "users"
git_tracker.DOSSIERS_PEOPLE_DIR = Path(TEMP_MEMORY_DIR) / "dossiers" / "people"
git_tracker.DOSSIERS_SUBJECTS_DIR = Path(TEMP_MEMORY_DIR) / "dossiers" / "subjects"
git_tracker._repo_initialized = False

# Reload soul_log to pick up the env var (already set above)
from monitoring import soul_log
soul_log.LOG_PATH = TEMP_STREAM

# Now import the reflection runner
from engine.reflect import run_reflection


def main():
    # Parse args or use defaults
    if len(sys.argv) >= 3:
        user_msg = sys.argv[1]
        assistant_msg = sys.argv[2]
    else:
        user_msg = "What sub-daimones have we built so far?"
        assistant_msg = (
            "We have built seven sub-daimones: Anamnesis, Scholiast, Demiurge, "
            "Mnemon, Eikon, Phantasos, and Themistokles."
        )

    print(f"=== Soul Reflection Test (dry-run) ===")
    print(f"Temp dir: {TEMP_DIR}")
    print(f"User: {user_msg[:80]}{'...' if len(user_msg) > 80 else ''}")
    print(f"Assistant: {assistant_msg[:80]}{'...' if len(assistant_msg) > 80 else ''}")
    print()

    result = run_reflection(
        user_message=user_msg,
        assistant_response=assistant_msg,
        user_id="test-user",
        channel="terminal:test-dry-run",
        thread_ts="test-dry-run",
        display_name="TestUser",
    )

    # Print results
    steps = result.get("steps", [])
    trace_id = result.get("trace_id", "?")

    if result.get("error"):
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if result.get("skipped"):
        print(f"SKIPPED: {result.get('reason', '?')}")
        sys.exit(0)

    print(f"Trace: {trace_id}")
    print(f"Steps ({len(steps)}):")
    for step in steps:
        print(f"  - {step}")
    print()

    # Show working memory contents
    import sqlite3
    conn = sqlite3.connect(TEMP_DB)
    rows = conn.execute(
        "SELECT entry_type, verb, content FROM working_memory ORDER BY created_at"
    ).fetchall()
    conn.close()

    if rows:
        print("=== Working Memory ===")
        for entry_type, verb, content in rows:
            label = f"{entry_type}" + (f" ({verb})" if verb else "")
            # Truncate long content for display
            preview = content[:200] + "..." if len(content) > 200 else content
            print(f"\n[{label}]")
            print(preview)

    # Show soul-stream
    if os.path.exists(TEMP_STREAM) and os.path.getsize(TEMP_STREAM) > 0:
        print(f"\n=== Soul Stream ({TEMP_STREAM}) ===")
        with open(TEMP_STREAM) as f:
            for line in f:
                entry = json.loads(line)
                phase = entry.get("phase", "?")
                print(f"  {phase}: {json.dumps({k: v for k, v in entry.items() if k != 'phase'}, default=str)[:120]}")

    # Show exported user model if any
    users_dir = os.path.join(TEMP_MEMORY_DIR, "users")
    for fname in os.listdir(users_dir):
        fpath = os.path.join(users_dir, fname)
        if os.path.getsize(fpath) > 0:
            print(f"\n=== Exported User Model: {fname} ===")
            with open(fpath) as f:
                print(f.read()[:500])

    print(f"\nAll artifacts in: {TEMP_DIR}")
    print("(temp dir preserved for inspection — delete manually when done)")


if __name__ == "__main__":
    main()
