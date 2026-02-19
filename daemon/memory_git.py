"""
Git-versioned memory — tracks evolution of user models and soul state.

Exports memory snapshots to markdown files in $CLAUDICLE_HOME/memory/ and
auto-commits each change with a descriptive message. The git history becomes
a full audit trail of how Claudicle's understanding of people and self evolves.

All git operations are non-blocking (subprocess.Popen) and best-effort —
failures are logged but never block the response pipeline.
"""

import logging
import re
import subprocess
from pathlib import Path

from config import CLAUDICLE_HOME

log = logging.getLogger(__name__)

MEMORY_DIR = Path(CLAUDICLE_HOME) / "memory"
USERS_DIR = MEMORY_DIR / "users"
DOSSIERS_PEOPLE_DIR = MEMORY_DIR / "dossiers" / "people"
DOSSIERS_SUBJECTS_DIR = MEMORY_DIR / "dossiers" / "subjects"

_repo_initialized = False


def _ensure_repo() -> None:
    """Initialize the memory directory as a git repo if not already."""
    global _repo_initialized
    if _repo_initialized:
        return

    try:
        USERS_DIR.mkdir(parents=True, exist_ok=True)
        DOSSIERS_PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
        DOSSIERS_SUBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Cannot create memory directories: %s", e)
        return

    git_dir = MEMORY_DIR / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(["git", "init"], cwd=MEMORY_DIR, capture_output=True, check=True)
        except FileNotFoundError:
            log.warning("Git not installed — memory versioning disabled")
            return
        except subprocess.CalledProcessError as e:
            log.warning("Git init failed: %s", e)
            return
        (MEMORY_DIR / ".gitkeep").touch()
        subprocess.run(["git", "add", "."], cwd=MEMORY_DIR, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initialize memory repository"],
            cwd=MEMORY_DIR,
            capture_output=True,
        )
        log.info("Initialized memory git repo at %s", MEMORY_DIR)

    _repo_initialized = True


def _safe_filename(display_name: str, user_id: str) -> str:
    """Create a filesystem-safe filename from display name."""
    name = display_name or user_id
    # Strip anything that isn't alphanumeric, dash, or underscore
    safe = re.sub(r'[^\w\-]', '_', name, flags=re.ASCII)
    return safe[:200] or user_id[:200]


def _git_commit(filepath: Path, message: str) -> None:
    """Stage a file and commit (best-effort, non-blocking)."""
    rel_path = str(filepath.relative_to(MEMORY_DIR))
    try:
        subprocess.run(
            ["git", "add", rel_path],
            cwd=MEMORY_DIR,
            capture_output=True,
            timeout=10,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=MEMORY_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log.warning("Git commit failed (exit %d): %s", result.returncode, result.stderr[:200])
    except FileNotFoundError:
        log.warning("Git not installed — memory versioning disabled")
    except subprocess.TimeoutExpired:
        log.warning("Git commit timed out for %s", rel_path)
    except Exception as e:
        log.warning("Git commit error for %s: %s", rel_path, e)


def export_user_model(
    user_id: str, display_name: str, model_md: str, change_note: str = ""
) -> None:
    """Write user model to file and commit."""
    _ensure_repo()
    safe_name = _safe_filename(display_name, user_id)
    filepath = USERS_DIR / f"{safe_name}.md"
    filepath.write_text(model_md)

    msg = f"Update {safe_name}"
    if change_note:
        msg += f": {change_note}"
    _git_commit(filepath, msg)
    log.debug("Exported user model for %s to %s", user_id, filepath)


def export_soul_state(state: dict) -> None:
    """Write soul state to file and commit."""
    _ensure_repo()
    filepath = MEMORY_DIR / "soul_state.md"
    lines = ["# Soul State", ""]
    for k, v in sorted(state.items()):
        lines.append(f"- **{k}**: {v}")
    filepath.write_text("\n".join(lines) + "\n")

    _git_commit(filepath, "Update soul state")
    log.debug("Exported soul state to %s", filepath)


def export_dossier(
    entity_name: str, model_md: str, entity_type: str = "subject", change_note: str = ""
) -> None:
    """Write a dossier (person or subject) to file and commit."""
    _ensure_repo()
    safe_name = _safe_filename(entity_name, entity_name)
    if entity_type == "person":
        filepath = DOSSIERS_PEOPLE_DIR / f"{safe_name}.md"
    else:
        filepath = DOSSIERS_SUBJECTS_DIR / f"{safe_name}.md"
    filepath.write_text(model_md)

    msg = f"Dossier: {entity_name}"
    if change_note:
        msg += f" — {change_note}"
    _git_commit(filepath, msg)
    log.debug("Exported dossier for %s (%s) to %s", entity_name, entity_type, filepath)


def get_history(user_id: str, display_name: str, limit: int = 20) -> str:
    """Get git log for a user model file."""
    _ensure_repo()
    safe_name = _safe_filename(display_name, user_id)
    filepath = USERS_DIR / f"{safe_name}.md"
    if not filepath.exists():
        return "No history yet."
    result = subprocess.run(
        [
            "git", "log",
            f"--max-count={limit}",
            "--format=%h %s (%ar)",
            "--",
            str(filepath.relative_to(MEMORY_DIR)),
        ],
        cwd=MEMORY_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning("Git log failed: %s", result.stderr[:200])
        return f"Error reading history: {result.stderr[:100]}"
    return result.stdout.strip() or "No history yet."


def get_diff(user_id: str, display_name: str, commits_back: int = 1) -> str:
    """Get diff showing recent changes to a user model."""
    _ensure_repo()
    safe_name = _safe_filename(display_name, user_id)
    filepath = USERS_DIR / f"{safe_name}.md"
    if not filepath.exists():
        return "No history yet."
    result = subprocess.run(
        [
            "git", "diff",
            f"HEAD~{commits_back}", "HEAD",
            "--",
            str(filepath.relative_to(MEMORY_DIR)),
        ],
        cwd=MEMORY_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning("Git diff failed: %s", result.stderr[:200])
        return f"Error reading diff: {result.stderr[:100]}"
    return result.stdout.strip() or "No changes."
