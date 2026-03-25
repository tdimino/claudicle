# monitoring — Observability (structured logging, system monitoring, watchers)

import logging
import os

log = logging.getLogger(__name__)

MAX_LOG_BYTES = 10 * 1024 * 1024  # 10MB


def rotate_if_needed(path: str, max_bytes: int = MAX_LOG_BYTES) -> None:
    """Rotate log file if it exceeds max_bytes.

    Renames current file to .1 (overwriting any previous .1).
    Best-effort, non-blocking — rotation failure is logged and swallowed.

    Note: Called outside flock by design. Theoretical race where a concurrent
    writer's entry lands in .1 instead of the active file is accepted for
    observability streams (data isn't lost, just misplaced).
    """
    try:
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            rotated = path + ".1"
            os.replace(path, rotated)
            log.info("Rotated %s (>%dMB) → %s", path, max_bytes // (1024 * 1024), rotated)
    except Exception as e:
        log.warning("Log rotation failed for %s: %s", path, e)
