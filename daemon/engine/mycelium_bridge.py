"""
Mycelium bridge — file-level knowledge via git notes.

Shells out to mycelium.sh for reading and writing notes on git objects.
All operations are best-effort and non-blocking — failures are logged
but never block the cognitive pipeline.

Follows the git_tracker.py pattern: subprocess.run with capture_output=True,
timeout, try/except for FileNotFoundError/TimeoutExpired/CalledProcessError.

Single-repo scoped: the daemon caches the repo root at first use. If the
daemon's cwd is not inside a git repo, all mycelium features are no-ops.
A daemon restart is required after installing mycelium.sh or changing repos.
"""

import logging
import os
import re
import subprocess
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

# Shared constant — used by context.py (injection) and pipeline.py (detection)
MYCELIUM_HEADER = "## File Knowledge (Mycelium)"

# Availability cache with TTL — re-checks after AVAILABILITY_TTL_SECONDS
# so mid-session installs of mycelium.sh are detected without daemon restart.
_mycelium_available: Optional[bool] = None
_mycelium_checked_at: float = 0.0
AVAILABILITY_TTL_SECONDS = 120.0  # re-check every 2 minutes if unavailable

# Repo root — cached permanently (repo root doesn't change mid-session)
_repo_root_cache: Optional[str] = None  # "" means checked and not in a repo
_lock = threading.Lock()

READ_TIMEOUT = 2   # seconds for mycelium.sh context/find
WRITE_TIMEOUT = 5  # seconds for mycelium.sh note
MAX_FILES = 5       # cap file paths extracted per perception


def _check_available() -> bool:
    """Check if mycelium.sh is on PATH.

    Cached with TTL when unavailable — re-checks periodically so
    mid-session installs are detected. Once available, stays cached.
    """
    global _mycelium_available, _mycelium_checked_at
    now = time.monotonic()

    # Fast path: already confirmed available (permanent)
    if _mycelium_available is True:
        return True

    # Fast path: checked recently and unavailable (TTL)
    if _mycelium_available is False and (now - _mycelium_checked_at) < AVAILABILITY_TTL_SECONDS:
        return False

    with _lock:
        # Re-check inside lock
        if _mycelium_available is True:
            return True
        if _mycelium_available is False and (now - _mycelium_checked_at) < AVAILABILITY_TTL_SECONDS:
            return False

        try:
            result = subprocess.run(
                ["which", "mycelium.sh"],
                capture_output=True, timeout=2,
            )
            _mycelium_available = result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            _mycelium_available = False

        _mycelium_checked_at = now

        if _mycelium_available:
            log.info("mycelium.sh found — mycelium integration enabled")
        else:
            log.debug("mycelium.sh not found — will re-check in %ds", int(AVAILABILITY_TTL_SECONDS))

        return _mycelium_available


def get_repo_root() -> Optional[str]:
    """Get git repo root for the daemon's cwd, or None if not in a repo.

    Cached permanently per daemon lifetime — repo root doesn't change
    mid-session. Returns None for non-git directories (Slack, SMS channels).
    """
    global _repo_root_cache
    if _repo_root_cache is not None:
        return _repo_root_cache if _repo_root_cache != "" else None
    with _lock:
        if _repo_root_cache is not None:
            return _repo_root_cache if _repo_root_cache != "" else None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                _repo_root_cache = result.stdout.strip()
                log.info("Mycelium repo root: %s", _repo_root_cache)
            else:
                _repo_root_cache = ""
                log.debug("Not in a git repo — mycelium features disabled")
        except (subprocess.SubprocessError, OSError):
            _repo_root_cache = ""
        return _repo_root_cache if _repo_root_cache != "" else None


def is_active(repo_root: Optional[str] = None) -> bool:
    """Check if mycelium is activated in the repo (notes ref exists)."""
    if not _check_available():
        return False
    root = repo_root or get_repo_root()
    if not root:
        return False
    try:
        result = subprocess.run(
            ["git", "notes", "--ref=mycelium", "list"],
            capture_output=True, timeout=2, cwd=root,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def extract_file_paths(text: str) -> list[str]:
    """Extract plausible file paths from text (backtick-quoted or bare).

    Returns at most MAX_FILES paths, filtering URLs, path traversal,
    absolute paths, and common false positives.
    """
    patterns = [
        r'`([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})`',
        r'(?:^|\s)([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})(?:\s|$|[,;:\)])',
    ]
    paths = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1)
            # Filter URLs
            if path.startswith(("http", "www.", "//", "v0.", "v1.", "v2.", "v3.")):
                continue
            # Filter common false positives
            if path in ("e.g.", "i.e.", "etc.", "vs.", "fig.", "eq."):
                continue
            # Filter path traversal
            if ".." in path:
                continue
            # Filter absolute paths (untrusted input shouldn't probe filesystem)
            if path.startswith("/"):
                continue
            paths.add(path)
    return list(paths)[:MAX_FILES]


def _looks_like_notes(output: str) -> bool:
    """Validate that mycelium.sh output looks like actual notes, not an error message.

    Notes contain structured headers like 'kind', 'edge', or section markers
    like '=== context:' from the context command.
    """
    indicators = ["kind ", "edge ", "=== context:", "[exact]", "[tree]", "[stale]"]
    return any(ind in output for ind in indicators)


def get_context(file_paths: list[str], repo_root: Optional[str] = None) -> Optional[str]:
    """Get mycelium notes for the given file paths.

    Returns formatted notes string, or None if no notes found.
    Best-effort — individual file failures are skipped.
    Validates output looks like actual notes (not error messages).
    """
    if not _check_available():
        return None
    root = repo_root or get_repo_root()
    if not root:
        return None

    notes = []
    for fp in file_paths:
        try:
            result = subprocess.run(
                ["mycelium.sh", "context", fp],
                capture_output=True, text=True, timeout=READ_TIMEOUT,
                cwd=root,
            )
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                if "no notes" not in output.lower() and _looks_like_notes(output):
                    notes.append(output)
                elif not _looks_like_notes(output):
                    log.warning("mycelium.sh context for %s returned unexpected output: %.100s",
                                fp, output)
            elif result.returncode != 0:
                log.debug("mycelium.sh context rc=%d for %s: %s",
                          result.returncode, fp, (result.stderr or "").strip()[:200])
        except subprocess.TimeoutExpired:
            log.warning("mycelium.sh context timed out for %s", fp)
        except (subprocess.SubprocessError, OSError) as e:
            log.debug("mycelium.sh context failed for %s: %s", fp, e)

    if not notes:
        return None
    return "\n---\n".join(notes)


def get_constraints(repo_root: Optional[str] = None) -> Optional[str]:
    """Get all constraint notes in the repo."""
    if not _check_available():
        return None
    root = repo_root or get_repo_root()
    if not root:
        return None

    try:
        result = subprocess.run(
            ["mycelium.sh", "find", "constraint"],
            capture_output=True, text=True, timeout=READ_TIMEOUT,
            cwd=root,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.warning("mycelium.sh find constraint timed out")
    except (subprocess.SubprocessError, OSError) as e:
        log.debug("mycelium.sh find constraint failed: %s", e)
    return None


def write_spore(
    file_path: str,
    kind: str,
    body: str,
    slot: str = "",
    repo_root: Optional[str] = None,
) -> bool:
    """Write a mycelium note (spore). Best-effort, non-blocking.

    Returns True if the note was written successfully.
    """
    if not _check_available():
        return False
    root = repo_root or get_repo_root()
    if not root:
        return False

    # Truncate body to prevent oversized notes
    body = body[:500].strip()
    if not body:
        return False

    cmd = ["mycelium.sh", "note", file_path, "-k", kind, "-m", body]
    if slot:
        cmd.extend(["--slot", slot])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=WRITE_TIMEOUT,
            cwd=root,
        )
        if result.returncode == 0:
            log.info("Shed %s spore on %s (slot=%s)", kind, file_path, slot or "default")
            return True
        else:
            log.warning("mycelium.sh note failed (rc=%d): %s",
                        result.returncode, result.stderr.strip()[:200])
            return False
    except subprocess.TimeoutExpired:
        log.warning("mycelium.sh note timed out for %s", file_path)
        return False
    except (subprocess.SubprocessError, OSError) as e:
        log.debug("mycelium.sh note failed: %s", e)
        return False


def reset_cache() -> None:
    """Reset cached state. Called from tests and session-start hooks."""
    global _mycelium_available, _mycelium_checked_at, _repo_root_cache
    with _lock:
        _mycelium_available = None
        _mycelium_checked_at = 0.0
        _repo_root_cache = None
