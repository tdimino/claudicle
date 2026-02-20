---
title: "Documentation"
directory: docs/
files: 21
created: 2026-02-19
description: "Guides and reference material for Claudicle"
categories:
  - getting-started (4)
  - architecture (8)
  - identity (3)
  - operations (4)
  - development (2)
---

# Documentation

Guides and reference material for Claudicle, organized by topic.

---

## Getting Started

| Guide | Description |
|-------|-------------|
| [Installation Guide](installation-guide.md) | What Claudicle installs and how to set it up |
| [Slack Setup](slack-setup.md) | Slack app configuration, tokens, permissions |
| [Onboarding Guide](onboarding-guide.md) | First Ensoulment—automated 4-stage interview for new users |
| [Troubleshooting](troubleshooting.md) | Common issues and fixes |

## Architecture

| Guide | Description |
|-------|-------------|
| [Daemon Architecture](daemon-architecture.md) | High-level system design and module map |
| [Cognitive Pipeline](cognitive-pipeline.md) | Deep dive into the XML-tagged cognitive step system |
| [Unified Launcher](unified-launcher-architecture.md) | How `claudicle.py` orchestrates terminal + Slack |
| [Runtime Modes Comparison](runtime-modes-comparison.md) | `/ensoul`, Session Bridge, Unified Launcher, Legacy, Inbox Watcher |
| [Soul Stream](soul-stream.md) | Structured JSONL cognitive cycle log (`soul_log.py`) |
| [Channel Adapters](channel-adapters.md) | Slack Socket Mode, SMS (Telnyx/Twilio), terminal |
| [Session Bridge](session-bridge.md) | Thread-to-session mapping for multi-turn conversations |
| [Session Management](session-management.md) | Session lifecycle, TTLs, cleanup |

## Identity & Customization

| Guide | Description |
|-------|-------------|
| [Backstory](backstory.md) | The Cuticle—Claudicle's narrative identity |
| [Soul Customization](soul-customization.md) | Configuring soul.md, personality, dossier templates |
| [Daimonic Intercession](daimonic-intercession.md) | Multi-daimon whisper/speak system (Kothar, Artifex) |

## Operations

| Guide | Description |
|-------|-------------|
| [Inbox Watcher](inbox-watcher.md) | Always-on autonomous Slack responder |
| [Rate Limits](rate-limits.md) | Slack API rate limit handling |
| [Commands Reference](commands-reference.md) | All slash commands (`/ensoul`, `/activate`, etc.) |
| [Scripts Reference](scripts-reference.md) | Slack utility scripts catalog |

## Development

| Guide | Description |
|-------|-------------|
| [Extending Claudicle](extending-claudicle.md) | Developer guide for adding providers, adapters, skills |
| [Testing](testing.md) | Test suite structure and conventions (319 tests) |
