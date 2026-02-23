#!/usr/bin/env python3
"""
Soul profile management — create, list, switch between named soul profiles.

Profiles live in $CLAUDICLE_HOME/soul/profiles/ as individual .md files.
Switching creates an atomic symlink at soul/active → profiles/<name>.md.

Usage:
    soul-profiles.py list
    soul-profiles.py create <name> [--from PATH]
    soul-profiles.py switch <name>
    soul-profiles.py current
    soul-profiles.py journal [--limit N]
"""

import argparse
import os
import shutil
import sys
import tempfile

CLAUDICLE_HOME = os.environ.get("CLAUDICLE_HOME", os.path.expanduser("~/.claudicle"))
SOUL_DIR = os.path.join(CLAUDICLE_HOME, "soul")
PROFILES_DIR = os.path.join(SOUL_DIR, "profiles")
ACTIVE_LINK = os.path.join(SOUL_DIR, "active")


def cmd_list(args):
    """List all available soul profiles."""
    if not os.path.isdir(PROFILES_DIR):
        print("No profiles directory. Using default soul/soul.md.")
        return

    profiles = sorted(
        f[:-3] for f in os.listdir(PROFILES_DIR)
        if f.endswith(".md") and os.path.isfile(os.path.join(PROFILES_DIR, f))
    )
    if not profiles:
        print("No profiles found. Create one with: soul-profiles.py create <name>")
        return

    current = _get_current()
    for name in profiles:
        marker = " ← active" if name == current else ""
        path = os.path.join(PROFILES_DIR, f"{name}.md")
        # Read first non-empty, non-heading line as description
        desc = _get_profile_desc(path)
        if desc:
            print(f"  {name}{marker}  — {desc}")
        else:
            print(f"  {name}{marker}")


def cmd_create(args):
    """Create a new soul profile."""
    name = args.name.strip().lower().replace(" ", "-")
    os.makedirs(PROFILES_DIR, exist_ok=True)
    target = os.path.join(PROFILES_DIR, f"{name}.md")

    if os.path.exists(target):
        print(f"Profile '{name}' already exists at {target}", file=sys.stderr)
        sys.exit(1)

    if args.source:
        # Copy from existing file
        src = os.path.expanduser(args.source)
        if not os.path.isfile(src):
            print(f"Source file not found: {src}", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(src, target)
        print(f"Created profile '{name}' from {src}")
    else:
        # Create from default soul.md
        default = os.path.join(SOUL_DIR, "soul.md")
        if os.path.isfile(default):
            shutil.copy2(default, target)
            print(f"Created profile '{name}' from soul.md")
        else:
            # Minimal template
            with open(target, "w") as f:
                f.write(f"# {name.title()}\n\nA soul profile.\n")
            print(f"Created profile '{name}' (minimal template)")

    # Journal the creation
    _journal_commit(target, f"create: new soul profile '{name}'")


def cmd_switch(args):
    """Switch to a different soul profile."""
    name = args.name.strip().lower().replace(" ", "-")
    target = os.path.join(PROFILES_DIR, f"{name}.md")

    if not os.path.isfile(target):
        print(f"Profile '{name}' not found. Available:", file=sys.stderr)
        cmd_list(argparse.Namespace())
        sys.exit(1)

    # Atomic symlink: create temp link, then rename over active
    try:
        _atomic_symlink(target, ACTIVE_LINK)
    except OSError as e:
        print(f"Failed to switch profile: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Switched to soul profile: {name}")

    # Journal the switch
    _journal_commit(target, f"switch: activated soul profile '{name}'")


def cmd_current(args):
    """Show the currently active soul profile."""
    current = _get_current()
    if current == "default":
        print(f"default (soul/soul.md)")
    else:
        print(current)


def cmd_journal(args):
    """Show the soul shedding journal."""
    # Use soul_journal if available, fall back to git log
    soul_md = _resolve_active_path()
    try:
        daemon_dir = os.path.join(CLAUDICLE_HOME, "daemon")
        sys.path.insert(0, daemon_dir)
        from memory import soul_journal
        print(soul_journal.get_journal(soul_md, limit=args.limit))
    except ImportError:
        # Fallback: direct git log
        import subprocess
        result = subprocess.run(
            ["git", "log", f"--max-count={args.limit}", "--format=%h %s (%ar)"],
            cwd=SOUL_DIR, capture_output=True, text=True,
        )
        print(result.stdout.strip() or "No journal yet.")
    finally:
        if daemon_dir in sys.path:
            sys.path.remove(daemon_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current() -> str:
    """Get the name of the currently active profile (delegates to soul_path)."""
    try:
        daemon_dir = os.path.join(CLAUDICLE_HOME, "daemon")
        sys.path.insert(0, daemon_dir)
        from engine.soul_path import get_active_soul_name
        return get_active_soul_name(CLAUDICLE_HOME)
    except ImportError:
        # Fallback for standalone use
        if os.path.islink(ACTIVE_LINK):
            target = os.path.realpath(ACTIVE_LINK)
            if os.path.isfile(target):
                return os.path.splitext(os.path.basename(target))[0]
        return "default"
    finally:
        if daemon_dir in sys.path:
            sys.path.remove(daemon_dir)


def _resolve_active_path() -> str:
    """Resolve the path to the active soul.md (delegates to soul_path)."""
    try:
        daemon_dir = os.path.join(CLAUDICLE_HOME, "daemon")
        sys.path.insert(0, daemon_dir)
        from engine.soul_path import resolve_soul_path
        return resolve_soul_path(CLAUDICLE_HOME)
    except ImportError:
        # Fallback for standalone use
        if os.path.islink(ACTIVE_LINK):
            target = os.path.realpath(ACTIVE_LINK)
            if os.path.isfile(target):
                return target
        return os.path.join(SOUL_DIR, "soul.md")
    finally:
        if daemon_dir in sys.path:
            sys.path.remove(daemon_dir)


def _get_profile_desc(path: str) -> str:
    """Extract a one-line description from a profile file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line[:60]
    except OSError:
        pass
    return ""


def _atomic_symlink(target: str, link_path: str):
    """Create a symlink atomically (temp link + rename)."""
    link_dir = os.path.dirname(link_path)
    os.makedirs(link_dir, exist_ok=True)

    fd, tmp = tempfile.mkstemp(dir=link_dir, prefix=".soul-switch-")
    os.close(fd)
    os.unlink(tmp)  # mkstemp creates the file; we need the name for symlink

    os.symlink(target, tmp)
    os.rename(tmp, link_path)


def _journal_commit(filepath: str, message: str):
    """Best-effort git commit for profile changes (delegates to soul_journal)."""
    try:
        daemon_dir = os.path.join(CLAUDICLE_HOME, "daemon")
        sys.path.insert(0, daemon_dir)
        from memory import soul_journal
        soul_journal.commit(filepath, message)
    except ImportError:
        # Fallback: direct git commit
        try:
            import subprocess
            subprocess.run(
                ["git", "add", os.path.basename(filepath)],
                cwd=SOUL_DIR, capture_output=True, timeout=5,
            )
            if os.path.islink(ACTIVE_LINK):
                subprocess.run(
                    ["git", "add", "active"],
                    cwd=SOUL_DIR, capture_output=True, timeout=5,
                )
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=SOUL_DIR, capture_output=True, timeout=5,
            )
        except Exception:
            pass  # Best-effort
    except Exception:
        pass  # Best-effort
    finally:
        daemon_dir = os.path.join(CLAUDICLE_HOME, "daemon")
        if daemon_dir in sys.path:
            sys.path.remove(daemon_dir)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Soul profile management")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List available profiles")

    p_create = sub.add_parser("create", help="Create a new profile")
    p_create.add_argument("name", help="Profile name")
    p_create.add_argument("--from", dest="source", help="Copy from this file")

    p_switch = sub.add_parser("switch", help="Switch to a profile")
    p_switch.add_argument("name", help="Profile name")

    sub.add_parser("current", help="Show active profile")

    p_journal = sub.add_parser("journal", help="Show soul shedding journal")
    p_journal.add_argument("--limit", type=int, default=20, help="Max entries")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "create": cmd_create,
        "switch": cmd_switch,
        "current": cmd_current,
        "journal": cmd_journal,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
