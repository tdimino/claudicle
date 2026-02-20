---
title: "Scripts"
directory: scripts/
files: 16
created: 2026-02-19
description: "Slack integration utilities and daemon support scripts"
shared_utils: "_slack_utils.py"
categories:
  - slack-operations (10)
  - daemon-support (4)
  - activation (2)
---

# Scripts

Slack integration utilities and daemon support scripts. All Slack scripts share `_slack_utils.py` for auth, rate limiting, and API helpers.

---

## Slack Operations

| Script | Purpose |
|--------|---------|
| `slack_post.py` | Send, reply, schedule, update, delete messages |
| `slack_read.py` | Read channel history and thread replies |
| `slack_search.py` | Search messages and files across the workspace |
| `slack_delete.py` | Delete messages—single, batch, or thread cleanup |
| `slack_react.py` | Add, remove, or list reactions |
| `slack_upload.py` | Upload files (2-step external upload API) |
| `slack_channels.py` | List, inspect, and join channels |
| `slack_users.py` | List and lookup workspace users |
| `slack_check.py` | Read and manage unhandled inbox messages |
| `slack_app_home.py` | Build and publish the App Home tab via Block Kit |

## Daemon Support

| Script | Purpose |
|--------|---------|
| `slack_memory.py` | CLI for three-tier memory (user models, soul, working) |
| `slack_format.py` | Soul-aware formatter for Slack bridge responses |
| `slack_inbox_hook.py` | `UserPromptSubmit` hook—silently checks inbox each turn |
| `_slack_utils.py` | Shared utilities: auth, rate limiting, API calls, formatters |

## Activation

| Script | Purpose |
|--------|---------|
| `activate_sequence.py` | Boot sequence terminal visual effects (Matrix/Tron aesthetic) |
| `situational_awareness.py` | Gathers workspace, soul state, channels, users into a readout |
