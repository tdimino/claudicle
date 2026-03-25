"""
Daemon lifecycle primitives — PID file, liveness, version, startup lock.

The daemon is invisible: auto-starts on first use, auto-restarts on version
mismatch, shuts down via resource closure. Users never run daemon commands.

PID file format (3 lines):
    {pid}
    {version}
    {start_time_iso}

Startup lock uses fcntl.flock(LOCK_EX | LOCK_NB) on the PID file to prevent
concurrent hooks from starting multiple daemons.
"""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("claudicle.lifecycle")

CLAUDICLE_HOME = Path(os.environ.get("CLAUDICLE_HOME", "~/.claudicle")).expanduser()
PIDFILE = CLAUDICLE_HOME / "claudicle.pid"
VERSION_FILE = Path(__file__).parent / "VERSION"
DAEMON_DIR = Path(__file__).parent
LOG_FILE = CLAUDICLE_HOME / "daemon" / "logs" / "claudicle-daemon.log"


@dataclass(frozen=True)
class DaemonInfo:
    """Parsed PID file contents."""
    pid: int
    version: str
    start_time: str


def read_version() -> str:
    """Read the installed daemon version from VERSION file."""
    try:
        return VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return "0.0.0"


def read_pid() -> DaemonInfo | None:
    """Read and parse the PID file. Returns None if missing or malformed."""
    try:
        lines = PIDFILE.read_text().strip().splitlines()
        if len(lines) < 3:
            return None
        return DaemonInfo(
            pid=int(lines[0]),
            version=lines[1],
            start_time=lines[2],
        )
    except (FileNotFoundError, ValueError, IndexError):
        return None


def is_alive(info: DaemonInfo | None) -> bool:
    """Check if the daemon process is still running.

    Uses os.kill(pid, 0) for basic liveness. The start_time in the PID file
    helps detect PID recycling (a different process reusing the same PID).
    """
    if info is None:
        return False
    try:
        os.kill(info.pid, 0)
        return True
    except OSError:
        return False


def write_pid(pid: int | None = None) -> None:
    """Write PID file atomically (tempfile + rename).

    Args:
        pid: Process ID to write. Defaults to current process.
    """
    if pid is None:
        pid = os.getpid()

    version = read_version()
    start_time = datetime.now(timezone.utc).isoformat()

    PIDFILE.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file, then rename
    fd, tmp_path = tempfile.mkstemp(dir=PIDFILE.parent, prefix=".claudicle-pid-")
    try:
        os.write(fd, f"{pid}\n{version}\n{start_time}\n".encode())
        os.close(fd)
        os.rename(tmp_path, PIDFILE)
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def remove_pid() -> None:
    """Remove the PID file. Called as the LAST cleanup step on shutdown."""
    try:
        PIDFILE.unlink()
    except FileNotFoundError:
        pass


def stop_daemon(info: DaemonInfo | None = None) -> bool:
    """Stop a running daemon by sending SIGTERM and waiting for PID file removal.

    Returns True if the daemon was stopped, False if it wasn't running.
    """
    if info is None:
        info = read_pid()
    if not is_alive(info):
        remove_pid()  # Clean up stale PID file
        return False

    # Send SIGTERM
    try:
        os.kill(info.pid, signal.SIGTERM)
    except OSError:
        remove_pid()
        return False

    # Wait for PID file removal (the daemon's completion signal)
    for _ in range(50):  # 5 seconds max
        if not PIDFILE.exists():
            return True
        time.sleep(0.1)

    # PID file still exists — check if process actually died
    if not is_alive(info):
        remove_pid()
        return True

    # Last resort: SIGKILL
    log.warning("Daemon did not stop gracefully, sending SIGKILL")
    try:
        os.kill(info.pid, signal.SIGKILL)
    except OSError:
        pass
    time.sleep(0.2)
    remove_pid()
    return True


def daemon_health(base_url: str | None = None) -> dict | None:
    """Fetch daemon health from the orchestrator API.

    Returns the parsed JSON response or None if unreachable.
    """
    if base_url is None:
        base_url = os.environ.get(
            "CLAUDICLE_API_URL", "http://claudicle-api.localhost:1355"
        )

    try:
        import urllib.request
        req = urllib.request.Request(
            f"{base_url}/api/health",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            import json
            return json.loads(resp.read())
    except Exception:
        return None


def daemon_version(base_url: str | None = None) -> str | None:
    """Fetch the running daemon's version from /api/health."""
    health = daemon_health(base_url)
    if health:
        return health.get("version")
    return None


def ensure_daemon() -> bool:
    """Auto-start the daemon if not running. Returns True if daemon is available.

    Uses fcntl.flock on the PID file for atomic startup — prevents concurrent
    hooks from starting multiple daemons.

    This is fire-and-forget: spawns the daemon as a detached background process
    and returns immediately. The daemon will be available by the next hook
    invocation or adapter connection.
    """
    info = read_pid()

    if is_alive(info):
        # Daemon running — check version
        installed = read_version()
        if info.version != installed:
            log.info(
                "Version mismatch: running=%s installed=%s, restarting",
                info.version, installed,
            )
            stop_daemon(info)
        else:
            return True  # Daemon healthy and current version

    # Acquire startup lock (non-blocking)
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = PIDFILE.parent / ".claudicle-start.lock"
    try:
        lock_fd = open(lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # Another process holds the lock — daemon is being started
        log.info("Another process is starting the daemon, skipping")
        return False

    try:
        # Double-check after acquiring lock
        info = read_pid()
        if is_alive(info):
            return True

        # Start daemon as detached background process
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(LOG_FILE, "a")

        subprocess.Popen(
            [sys.executable, "-m", "claudicle", "--daemon"],
            cwd=str(DAEMON_DIR),
            start_new_session=True,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
        log.info("Daemon started (fire-and-forget)")
        return False  # Not yet available, will be on next check

    except Exception as e:
        log.error("Failed to start daemon: %s", e)
        return False
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
