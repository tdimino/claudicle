"""
Mycelium bridge — file-level knowledge via git notes.

Shells out to mycelium.sh for reading and writing notes on git objects.
All operations are best-effort and non-blocking — failures are logged
but never block the cognitive pipeline.

Follows the git_tracker.py pattern: subprocess.run with capture_output=True,
timeout, try/except for FileNotFoundError/TimeoutExpired/CalledProcessError.
"""

import logging
import os
import re
import subprocess
import threading
from typing import Optional

log = logging.getLogger(__name__)

# Shared constant — used by context.py (injection) and pipeline.py (detection)
MYCELIUM_HEADER = "## File Knowledge (Mycelium)"

# Cached availability — checked once per daemon lifetime
_mycelium_available: Optional[bool] = None
_repo_root_cache: Optional[str] = None  # "" means checked and not in a repo
_lock = threading.Lock()

READ_TIMEOUT = 2   # seconds for mycelium.sh context/find
WRITE_TIMEOUT = 5  # seconds for mycelium.sh note
MAX_FILES = 5       # cap file paths extracted per perception


def _check_available() -> bool:
    """Check if mycelium.sh is on PATH. Cached per daemon lifetime."""
    global _mycelium_available
    if _mycelium_available is not None:
        return _mycelium_available
    with _lock:
        if _mycelium_available is not None:
            return _mycelium_available
        try:
            result = subprocess.run(
                ["which", "mycelium.sh"],
                capture_output=True, timeout=2,
            )
            _mycelium_available = result.returncode == 0
        except (subprocess.SubprocessError, OSError):
            _mycelium_available = False
        if not _mycelium_available:
            log.info("mycelium.sh not found — mycelium integration disabled")
        return _mycelium_available


def get_repo_root(cwd: Optional[str] = None) -> Optional[str]:
    """Get git repo root for the given cwd, or None if not in a repo.

    Cached per daemon lifetime (repo root doesn't change mid-session).
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
                cwd=cwd,
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

    Returns at most MAX_FILES paths, filtering URLs and common false positives.
    """
    patterns = [
        r'`([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})`',
        r'(?:^|\s)([a-zA-Z0-9_./-]+\.[a-zA-Z]{1,6})(?:\s|$|[,;:\)])',
    ]
    paths = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1)
            if path.startswith(("http", "www.", "//", "v0.", "v1.", "v2.", "v3.")):
                continue
            # Skip common false positives
            if path in ("e.g.", "i.e.", "etc.", "vs.", "fig.", "eq."):
                continue
            paths.add(path)
    return list(paths)[:MAX_FILES]


def get_context(file_paths: list[str], repo_root: Optional[str] = None) -> Optional[str]:
    """Get mycelium notes for the given file paths.

    Returns formatted notes string, or None if no notes found.
    Best-effort — individual file failures are skipped.
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
                if "no notes" not in output.lower():
                    notes.append(output)
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
    """Reset cached state. Used for testing."""
    global _mycelium_available, _repo_root_cache
    with _lock:
        _mycelium_available = None
        _repo_root_cache = None
