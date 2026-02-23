"""
Git-journaled soul shedding — tracks the evolution of soul.md over time.

Each soul shed produces two commits: a pre-shed snapshot and the change
with Themistokles' rationale as the commit message. The git history of
$CLAUDICLE_HOME/soul/ becomes a daimon's diary — a readable record of
how the soul evolves.

All git operations follow git_tracker.py conventions: non-blocking
subprocess, 10s timeout, best-effort, logged warnings.

CLI usage:
    python3 soul_journal.py commit --soul-path PATH --rationale "..."
    python3 soul_journal.py log --soul-path PATH [--limit N]
"""

import argparse
import logging
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

_repo_initialized: dict[str, bool] = {}
_repo_lock = threading.Lock()


def _ensure_repo(soul_dir: Path) -> bool:
    """Initialize the soul directory as a git repo if not already."""
    key = str(soul_dir)
    if _repo_initialized.get(key):
        return True
    with _repo_lock:
        if _repo_initialized.get(key):
            return True

        try:
            soul_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.warning("Cannot create soul directory: %s", e)
            return False

        git_dir = soul_dir / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(
                    ["git", "init"], cwd=soul_dir,
                    capture_output=True, check=True, timeout=10,
                )
            except FileNotFoundError:
                log.warning("Git not installed — soul journal disabled")
                return False
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                log.warning("Git init failed: %s", e)
                return False

        _repo_initialized[key] = True
        return True


def _git_commit(soul_dir: Path, filepath: Path, message: str) -> bool:
    """Stage a file and commit (best-effort, 10s timeout)."""
    rel_path = str(filepath.relative_to(soul_dir))
    try:
        subprocess.run(
            ["git", "add", rel_path],
            cwd=soul_dir, capture_output=True, timeout=10,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=soul_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            stderr = result.stderr[:200] if result.stderr else ""
            # "nothing to commit" is not an error
            if "nothing to commit" in stderr or "nothing to commit" in (result.stdout or ""):
                return True
            log.warning("Git commit failed (exit %d): %s", result.returncode, stderr)
            return False
        return True
    except FileNotFoundError:
        log.warning("Git not installed — soul journal disabled")
        return False
    except subprocess.TimeoutExpired:
        log.warning("Git commit timed out for %s", rel_path)
        return False
    except Exception as e:
        log.warning("Git commit error for %s: %s", rel_path, e)
        return False


def _invalidate_cache() -> None:
    """Invalidate the soul cache in context.py after a shed."""
    try:
        from engine import context
        context.invalidate_soul_cache()
    except (ImportError, AttributeError):
        pass


def shed(soul_md_path: str, new_content: str, rationale: str, description: str = "") -> bool:
    """Perform a full soul shed: snapshot, write, commit with rationale.

    Creates two commits:
    1. Pre-shed snapshot of current soul.md
    2. The new content with Themistokles' rationale as commit message

    Returns True if the shed completed successfully.
    """
    path = Path(soul_md_path)
    soul_dir = path.parent

    if not _ensure_repo(soul_dir):
        return False

    # 1. Pre-shed snapshot
    if path.exists():
        desc = description or "snapshot"
        if not _git_commit(soul_dir, path, f"pre-shed: {desc}"):
            log.warning("Pre-shed snapshot commit failed for %s; rationale commit will proceed", path)

    # 2. Write new content
    try:
        path.write_text(new_content)
    except OSError as e:
        log.warning("Failed to write soul.md: %s", e)
        return False

    # 3. Commit with rationale
    success = _git_commit(soul_dir, path, rationale)

    # 4. Invalidate soul cache
    _invalidate_cache()

    return success


def commit(soul_md_path: str, rationale: str) -> bool:
    """Journal a soul.md change that was already applied (e.g. via Edit tool).

    Use when Claude Code's Edit tool already modified soul.md and you just
    need the git ceremony + cache invalidation.
    """
    path = Path(soul_md_path)
    soul_dir = path.parent

    if not _ensure_repo(soul_dir):
        return False

    success = _git_commit(soul_dir, path, rationale)
    _invalidate_cache()
    return success


def get_journal(soul_md_path: str, limit: int = 20) -> str:
    """Get the git log for soul.md — the daimon's diary."""
    path = Path(soul_md_path)
    soul_dir = path.parent

    if not _ensure_repo(soul_dir):
        return "No journal yet."

    if not path.exists():
        return "No journal yet."

    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={limit}",
                "--format=%h %s (%ar)",
                "--", path.name,
            ],
            cwd=soul_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"Error reading journal: {result.stderr[:100]}"
        return result.stdout.strip() or "No journal yet."
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "No journal yet."


def get_last_shed(soul_md_path: str) -> dict:
    """Get the most recent journal entry."""
    path = Path(soul_md_path)
    soul_dir = path.parent

    if not _ensure_repo(soul_dir):
        return {}

    if not path.exists():
        return {}

    try:
        result = subprocess.run(
            [
                "git", "log", "-1",
                "--format=%H%n%s%n%ai",
                "--", path.name,
            ],
            cwd=soul_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 3:
            return {
                "hash": lines[0],
                "rationale": lines[1],
                "timestamp": lines[2],
            }
        return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Soul shedding journal")
    sub = parser.add_subparsers(dest="command")

    p_commit = sub.add_parser("commit", help="Journal a soul.md change")
    p_commit.add_argument("--soul-path", required=True, help="Path to soul.md")
    p_commit.add_argument("--rationale", required=True, help="Commit rationale")

    p_log = sub.add_parser("log", help="View the soul journal")
    p_log.add_argument("--soul-path", required=True, help="Path to soul.md")
    p_log.add_argument("--limit", type=int, default=20, help="Max entries")

    args = parser.parse_args()

    if args.command == "commit":
        ok = commit(args.soul_path, args.rationale)
        if ok:
            print("Journal entry created.")
        else:
            print("Failed to create journal entry.", file=__import__("sys").stderr)
            raise SystemExit(1)
    elif args.command == "log":
        print(get_journal(args.soul_path, args.limit))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
