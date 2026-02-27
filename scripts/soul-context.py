#!/usr/bin/env python3
"""Output soul context block for sub-daimon injection.

Mirrors soul-activate.py's injection layers but outputs to stdout,
callable by any sub-daimon at boot to absorb the soul identity.

Layers: soul personality, soul state, user model, prior daimon memory.

Usage:
    python3 $CLAUDICLE_HOME/scripts/soul-context.py
    python3 $CLAUDICLE_HOME/scripts/soul-context.py --agent mnemon
"""

import argparse
import os
import sys

CLAUDICLE_HOME = os.environ.get(
    "CLAUDICLE_HOME", os.path.expanduser("~/.claudicle")
)
DAEMON_DIR = os.path.join(CLAUDICLE_HOME, "daemon")


def _resolve_soul_md():
    """Resolve the active soul.md path using profile resolution."""
    try:
        sys.path.insert(0, DAEMON_DIR)
        from engine.soul_path import resolve_soul_path
        return resolve_soul_path(CLAUDICLE_HOME)
    except ImportError:
        return os.path.join(CLAUDICLE_HOME, "soul", "soul.md")
    finally:
        if DAEMON_DIR in sys.path:
            sys.path.remove(DAEMON_DIR)


SOUL_MD = _resolve_soul_md()


def _read_soul_md():
    """Read the soul personality file."""
    try:
        with open(SOUL_MD) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _get_soul_state():
    """Get formatted soul state from memory.db."""
    try:
        sys.path.insert(0, DAEMON_DIR)
        from memory import soul_memory
        state = soul_memory.format_for_prompt()
        soul_memory.close()
        return state
    except (ImportError, Exception):
        return ""
    finally:
        if DAEMON_DIR in sys.path:
            sys.path.remove(DAEMON_DIR)


def _get_user_model():
    """Get the primary user's model from memory.db."""
    try:
        sys.path.insert(0, DAEMON_DIR)
        import config
        from memory import user_models
        model = user_models.get(config.PRIMARY_USER_ID)
        user_models.close()
        return model or ""
    except (ImportError, Exception):
        return ""
    finally:
        if DAEMON_DIR in sys.path:
            sys.path.remove(DAEMON_DIR)


def _get_daimon_memory(agent_name: str) -> str:
    """Load and format prior memory for a subdaimon."""
    try:
        sys.path.insert(0, DAEMON_DIR)
        from memory.daimon_memory import make_context, load_memory, load_lessons, format_for_boot
        ctx = make_context(agent_name)
        memory = load_memory(ctx, limit=20)
        lessons = load_lessons(agent_name)
        return format_for_boot(ctx, memory, lessons)
    except (ImportError, Exception):
        return ""
    finally:
        if DAEMON_DIR in sys.path:
            sys.path.remove(DAEMON_DIR)


def main():
    parser = argparse.ArgumentParser(description="Output soul context for sub-daimon injection")
    parser.add_argument("--agent", help="Load prior memory for this subdaimon")
    args = parser.parse_args()

    parts = []

    soul_md = _read_soul_md()
    if soul_md:
        parts.append(soul_md)

    soul_state = _get_soul_state()
    if soul_state:
        parts.append(soul_state)

    user_model = _get_user_model()
    if user_model:
        parts.append("## User Model\n\n" + user_model)

    if args.agent:
        daimon_mem = _get_daimon_memory(args.agent)
        if daimon_mem:
            parts.append(daimon_mem)

    if parts:
        print("\n\n".join(parts))


if __name__ == "__main__":
    main()
