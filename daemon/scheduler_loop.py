"""Scheduler loop — background async polling for due events.

Runs in the unified launcher (claudicle.py) and inbox watcher.
Polls for due events, creates Perception objects, and routes them
through the process router. Daemon-only — terminal sessions don't
use this.
"""

import asyncio
import logging

import config
from engine.perception import Perception
import scheduler

log = logging.getLogger("claudicle.scheduler_loop")


async def run_scheduler(interval: int | None = None):
    """Background loop that polls for due scheduled events.

    interval: seconds between polls (default: config.SCHEDULER_INTERVAL)
    """
    if not config.SCHEDULER_ENABLED:
        log.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    poll_interval = interval or config.SCHEDULER_INTERVAL
    log.info("Scheduler started (interval=%ds)", poll_interval)

    while True:
        try:
            due = scheduler.get_due_events(
                max_batch=5,
                max_overdue_ratio=config.SCHEDULER_MAX_OVERDUE_RATIO,
            )

            for event in due:
                perception = Perception(
                    action=event["perception_action"],
                    content=event.get("perception_content", ""),
                    user_id="system",
                    channel=event.get("channel") or "scheduler",
                    thread_ts=event.get("thread_ts") or "scheduled",
                    internal=True,
                    metadata=event.get("metadata", {}),
                )

                try:
                    # Import here to avoid circular imports
                    from engine import process_router
                    from memory.snapshot import load_snapshot

                    snapshot = load_snapshot(
                        perception.channel,
                        perception.thread_ts,
                    )

                    result = await process_router.route(
                        text=perception.content,
                        user_id=perception.user_id,
                        channel=perception.channel,
                        thread_ts=perception.thread_ts,
                        snapshot=snapshot,
                        internal=True,
                        target_process=event.get("target_process", ""),
                    )

                    scheduler.mark_fired(event["id"])
                    log.info(
                        "Fired scheduled event %s: action=%s, dialogue=%s",
                        event["id"], event["perception_action"],
                        result.dialogue[:80] if result.dialogue else "(empty)",
                    )

                except Exception as e:
                    log.error("Scheduled event %s failed: %s", event["id"], e)

        except Exception as e:
            log.error("Scheduler poll error: %s", e)

        await asyncio.sleep(poll_interval)
