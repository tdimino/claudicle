---
title: "Adapters"
directory: daemon/adapters/
files: 5
created: 2026-02-19
description: "Channel I/O adapters connecting the cognitive pipeline to external interfaces"
adapters:
  - slack_adapter (Socket Mode WebSocket)
  - slack_listen (background listener)
  - inbox_watcher (file polling auto-responder)
  - slack_log (event JSONL stream)
  - terminal_ui (stdin/stdout)
---

# Adapters

Channel I/O adapters connecting the cognitive pipeline to external interfaces.

---

| Adapter | File | Protocol | Purpose |
|---------|------|----------|---------|
| Slack Socket Mode | `slack_adapter.py` | WebSocket | Receives @mentions and DMs, routes to async callback |
| Slack Listener | `slack_listen.py` | WebSocket | Background process—writes incoming messages to `inbox.jsonl` |
| Inbox Watcher | `inbox_watcher.py` | File polling | Auto-responds to `inbox.jsonl` messages via configurable provider |
| Slack Event Log | `slack_log.py` | JSONL stream | Append-only log of all Slack events (tail-able, thread-safe) |
| Terminal UI | `terminal_ui.py` | stdin/stdout | Async input loop and activity log for the unified launcher |

## Data Flow

```
Slack → slack_adapter.py → soul_engine → slack_post
     → slack_listen.py  → inbox.jsonl → inbox_watcher.py → soul_engine → slack_post
     → slack_log.py     → events.jsonl (observability)
```
