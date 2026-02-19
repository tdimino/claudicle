# Scheduled Events — Extension Pattern

## Open Souls Pattern

The `scheduleEvent` action enables proactive behavior by scheduling future perceptions. Instead of only responding to user messages, the soul can initiate contact, send follow-ups, check in periodically, and manage time-based state transitions.

### Core API

```typescript
const { scheduleEvent } = useActions();

// Schedule event after delay (seconds)
const eventId = await scheduleEvent({
  in: 10,                          // 10 seconds from now
  process: pokesSpeaker,           // Mental process to handle it
  perception: {
    action: "poked",               // Perception action type
    content: "I poked.",           // Perception content
    name: "Samantha",              // Soul name
  },
});

// Schedule event at specific date
const eventId = await scheduleEvent({
  when: new Date(2026, 2, 1),      // March 1, 2026
  perception: {
    action: "reminder",
    content: "Monthly check-in",
  },
  process: reminderProcess,
});

// Cancel scheduled event
const { cancelScheduledEvent } = useProcessManager();
cancelScheduledEvent(eventId);
```

### Preventing Infinite Loops

Scheduled events create perceptions that trigger mental processes—which could schedule more events. Always check if the current perception is internal (scheduled):

```typescript
// ✅ CORRECT: Guard against re-scheduling
if (!invokingPerception?.internal) {
  scheduleEvent({
    in: 3600,
    process: checkInProcess,
    perception: { action: "checkIn", content: "Hourly check" },
  });
}

// ❌ WRONG: Creates infinite loop
scheduleEvent({ in: 3600, process: checkInProcess, ... });
```

### Use Cases

**Follow-Up System**: Schedule check-ins after problem resolution:

```typescript
const [, severity] = await decision(memory, {
  description: "How soon should we follow up?",
  choices: ["24 hours (crisis)", "48 hours (typical)", "72 hours (preventive)"]
});

scheduleEvent({
  in: hoursMap[severity] * 3600,
  process: followUpCheck,
  perception: {
    action: "followUpDue",
    content: `Check in about ${topic}`,
    metadata: { severity, tools: toolsPresented.current }
  }
});
```

**Periodic Check-Ins**: Daily/hourly recurring behavior:

```typescript
if (invokingPerception?.action === "dailyCheckIn") {
  // Do check-in work...

  // Schedule next one (self-referencing, guarded)
  if (!invokingPerception?.internal) {
    scheduleEvent({
      in: 86400,  // 24 hours
      process: checkInProcess,
      perception: { action: "dailyCheckIn", content: "Daily check-in", internal: true }
    });
  }
}
```

**Inactivity Timeout**: Transition to dormant state after silence:

```typescript
scheduleEvent({
  in: 1800,  // 30 minutes
  process: dormantProcess,
  perception: { action: "inactivityTimeout", content: "User has been inactive" }
});
```

**Delayed Reactions**: Give "thinking time" before responding:

```typescript
scheduleEvent({
  in: 5,  // 5 seconds
  process: thoughtfulResponse,
  perception: { action: "finishedThinking", content: userQuestion }
});
```

### Pending Events Management

```typescript
const { pendingScheduledEvents, cancelScheduledEvent } = useProcessManager();

// View pending events (sorted soonest-to-latest)
for (const event of pendingScheduledEvents) {
  console.log(`${event.id}: ${event.perception.action} at ${event.when}`);
}

// Cancel specific event
cancelScheduledEvent(eventId);

// Cancel all of a certain type
for (const event of pendingScheduledEvents) {
  if (event.perception.action === "reminder") {
    cancelScheduledEvent(event.id);
  }
}
```

---

## Current Claudicle Implementation

Claudicle has **no scheduling capability**. The soul only responds to incoming messages—it cannot initiate contact, send follow-ups, or perform time-based actions.

### Closest Equivalent

The Session Bridge listener (`slack_listen.py`) runs continuously, but it only watches for incoming messages. There's no mechanism for the soul to schedule future actions.

The `UserPromptSubmit` hook (`slack_inbox_hook.py`) fires at the start of every Claude Code turn, but this is user-initiated (requires the user to type something), not time-based.

---

## Extension Blueprint

### Goal

Add a scheduler so Claudicle can initiate proactive behavior—follow-ups, check-ins, reminders, and time-based state transitions.

### New Module: `daemon/scheduler.py`

```python
"""Event scheduler for proactive soul behavior."""

import json
import sqlite3
import time
import asyncio
import logging
from datetime import datetime, timedelta

log = logging.getLogger("claudicle.scheduler")

_DB_PATH = "memory.db"

def _init():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_events (
            id TEXT PRIMARY KEY,
            fire_at REAL NOT NULL,
            perception_action TEXT NOT NULL,
            perception_content TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',
            channel TEXT,
            thread_ts TEXT,
            created_at REAL DEFAULT (strftime('%s', 'now')),
            fired INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fire_at ON scheduled_events(fire_at)")
    conn.commit()
    conn.close()

def schedule(perception_action: str, content: str, delay_seconds: int,
             channel: str = None, thread_ts: str = None,
             metadata: dict = None) -> str:
    """Schedule a future perception."""
    import uuid
    event_id = str(uuid.uuid4())[:8]
    fire_at = time.time() + delay_seconds

    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """INSERT INTO scheduled_events
           (id, fire_at, perception_action, perception_content, metadata, channel, thread_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (event_id, fire_at, perception_action, content,
         json.dumps(metadata or {}), channel, thread_ts)
    )
    conn.commit()
    conn.close()

    log.info(f"Scheduled {perception_action} ({event_id}) for {delay_seconds}s from now")
    return event_id

def cancel(event_id: str):
    """Cancel a scheduled event."""
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("DELETE FROM scheduled_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()

def get_due_events() -> list[dict]:
    """Get events whose fire_at time has passed."""
    conn = sqlite3.connect(_DB_PATH)
    rows = conn.execute(
        """SELECT id, perception_action, perception_content, metadata, channel, thread_ts
           FROM scheduled_events
           WHERE fire_at <= ? AND fired = 0
           ORDER BY fire_at""",
        (time.time(),)
    ).fetchall()
    conn.close()

    return [
        {"id": r[0], "action": r[1], "content": r[2],
         "metadata": json.loads(r[3]), "channel": r[4], "thread_ts": r[5]}
        for r in rows
    ]

def mark_fired(event_id: str):
    """Mark event as fired."""
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("UPDATE scheduled_events SET fired = 1 WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()

def pending(channel: str = None) -> list[dict]:
    """List unfired events, optionally filtered by channel."""
    conn = sqlite3.connect(_DB_PATH)
    if channel:
        rows = conn.execute(
            "SELECT id, perception_action, fire_at FROM scheduled_events WHERE fired = 0 AND channel = ? ORDER BY fire_at",
            (channel,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, perception_action, fire_at FROM scheduled_events WHERE fired = 0 ORDER BY fire_at"
        ).fetchall()
    conn.close()
    return [{"id": r[0], "action": r[1], "fire_at": r[2]} for r in rows]
```

### Scheduler Loop

```python
# daemon/scheduler_loop.py
"""Background loop that checks for due events and processes them."""

import asyncio
import scheduler
import claude_handler

async def run_scheduler(interval: int = 30):
    """Check for due events every `interval` seconds."""
    while True:
        due = scheduler.get_due_events()
        for event in due:
            try:
                await _process_event(event)
                scheduler.mark_fired(event["id"])
            except Exception as e:
                log.error(f"Failed to process event {event['id']}: {e}")
        await asyncio.sleep(interval)

async def _process_event(event: dict):
    """Process a scheduled event through the cognitive pipeline."""
    text = f"[Scheduled: {event['action']}] {event['content']}"
    channel = event.get("channel", "scheduler")
    thread_ts = event.get("thread_ts", "scheduled")

    response = await claude_handler.async_process(
        text, "system", channel, thread_ts
    )

    # Post response to channel if applicable
    if event.get("channel"):
        await _post_to_channel(channel, response, thread_ts)
```

### Cognitive Step for Scheduling

Add a new XML tag so the soul can schedule events from within a response:

```python
# soul_engine.py — new cognitive instruction
_SCHEDULE_INSTRUCTION = """
<schedule_event action="followUpDue" delay_seconds="3600">
Optional content describing the scheduled action.
</schedule_event>
"""

# parse_response() — extract and queue scheduled events
schedule_match = re.search(
    r'<schedule_event\s+action="([^"]+)"\s+delay_seconds="(\d+)">(.*?)</schedule_event>',
    raw, re.DOTALL
)
if schedule_match:
    scheduler.schedule(
        perception_action=schedule_match.group(1),
        content=schedule_match.group(3).strip(),
        delay_seconds=int(schedule_match.group(2)),
        channel=channel,
        thread_ts=thread_ts,
    )
```

### Integration with Unified Launcher

```python
# claudicle.py — start scheduler alongside message processing
async def main():
    # ... existing setup ...

    # Start scheduler loop as background task
    if config.SCHEDULER_ENABLED:
        asyncio.create_task(scheduler_loop.run_scheduler(interval=30))

    # ... existing message processing loop ...
```

### Configuration

```python
# config.py additions
SCHEDULER_ENABLED = _env("SCHEDULER_ENABLED", "false").lower() == "true"
SCHEDULER_INTERVAL = int(_env("SCHEDULER_INTERVAL", "30"))  # seconds
SCHEDULER_MAX_EVENTS = int(_env("SCHEDULER_MAX_EVENTS", "100"))
```

### Estimated Effort

- `daemon/scheduler.py`: ~100 LOC (SQLite event store)
- `daemon/scheduler_loop.py`: ~50 LOC (background event checker)
- Modified `soul_engine.py`: ~20 lines (schedule_event XML tag + extraction)
- Modified `claudicle.py`: ~5 lines (start scheduler task)
- Modified `config.py`: ~4 lines (scheduler settings)
- Tests: ~80 LOC (schedule, cancel, due detection, loop)
