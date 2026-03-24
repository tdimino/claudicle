---
title: "Documentation"
directory: docs/
files: 37
created: 2026-02-19
updated: 2026-03-24
description: "Guides and reference material for Claudicle"
categories:
  - getting-started (4)
  - architecture (10)
  - channel-setup (5)
  - identity (3)
  - daimonic-intelligence (2)
  - operations (5)
  - philosophy (2)
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
| [Skill Pairings](skill-pairings.md) | Recommended skills by tier (Essential, Recommended, Nice-to-have) |

## Architecture

| Guide | Description |
|-------|-------------|
| [claude -p Subprocess](claude-p-subprocess.md) | Nesting guard, env var stripping, claude -p vs Agent SDK vs bridge providers |
| [Daemon Architecture](daemon-architecture.md) | High-level system design and module map |
| [Cognitive Pipeline](cognitive-pipeline.md) | Deep dive into the XML-tagged cognitive step system |
| [Unified Launcher](unified-launcher-architecture.md) | How `claudicle.py` orchestrates terminal + Slack + Discord + Telegram |
| [Runtime Modes Comparison](runtime-modes-comparison.md) | `/ensoul`, Session Bridge, Unified Launcher, Legacy, Inbox Watcher |
| [Soul Stream](soul-stream.md) | Structured JSONL cognitive cycle log (`soul_log.py`) |
| [Open Souls Alignment](open-souls-alignment.md) | Paradigm mapping, intentional adaptations, roadmap |
| [Daimon Summoning](daimon-summoning.md) | Awaken any entity (user model, dossier) as an ephemeral speaking daimon—Open Souls alignment, lifecycle, cache trick |
| [Channel Adapters](channel-adapters.md) | Slack, Discord, Telegram, SMS, WhatsApp, terminal |
| [Session Bridge](session-bridge.md) | Thread-to-session mapping for multi-turn conversations |
| [Session Management](session-management.md) | Session lifecycle, TTLs, cleanup |
| [Hooks](hooks.md) | Claude Code lifecycle hooks—soul activation, session registry, reflection |
| [Orchestrator API](orchestrator-api.md) | HTTP gateway for daimon→Claude Code delegation, portless registration, Bearer auth |
| [Permission Model](permission-model.md) | Three-tier Bash command gating, deny/allow categories, bypassPermissions, review cadence |

## Channel Setup

| Guide | Description |
|-------|-------------|
| [SMS Setup](sms-setup.md) | Telnyx + Twilio, webhooks, message batching, memory integration |
| [Telegram Setup](telegram-setup.md) | BotFather, polling mode, daimon identity |
| [Discord Setup](discord-setup.md) | Developer Portal, Message Content Intent, webhook daimon identity |
| [WhatsApp Setup](whatsapp-setup.md) | Baileys gateway, QR pairing, security (beta) |
| [Channel Comparison](channel-comparison.md) | Side-by-side feature matrix for all channels |

## Identity & Customization

| Guide | Description |
|-------|-------------|
| [Backstory](backstory.md) | The Cuticle—Claudicle's narrative identity |
| [Soul Customization](soul-customization.md) | Configuring soul.md, personality, dossier templates |
| [Daimones](daimones.md) | The privy council—autonomous advisors with four sources, strategos pattern, evolution |
| [Daimonic Intercession](daimonic-intercession.md) | Whisper protocol, security, Groq fallback, configuration |

## Operations

| Guide | Description |
|-------|-------------|
| [Inbox Watcher](inbox-watcher.md) | Always-on autonomous Slack responder |
| [Rate Limits](rate-limits.md) | Slack API rate limit handling |
| [Commands Reference](commands-reference.md) | All slash commands (`/ensoul`, `/activate`, etc.) |
| [Scripts Reference](scripts-reference.md) | Slack utility scripts catalog |
| [Environment Variables](environment-variables.md) | All `CLAUDICLE_` config variables with defaults |

## Daimonic Intelligence

| Guide | Description |
|-------|-------------|
| [Sub-Daimones](sub-daimones.md) | Cognitive agent architecture—12 sub-daimones, persistent memory, invocation, precedents, dry-run testing |
| [Mental Processes](mental-processes.md) | Kothar's 9 mental processes—reference implementation for daimon behavioral architecture (Open Souls paradigm) |

## Philosophy

| Guide | Description |
|-------|-------------|
| [How Claudicle Differs](how-claudicle-differs.md) | What changes when you give an LLM persistent memory, an internal monologue, and a soul |
| [Mystical Vocabulary](mystical-vocabulary.md) | Why ancient terms for consciousness produce better AI systems than the engineering lexicon |

## Development

| Guide | Description |
|-------|-------------|
| [Extending Claudicle](extending-claudicle.md) | Developer guide for adding providers, adapters, skills |
| [Testing](testing.md) | Test suite structure and conventions (927 tests) |
| [Cognitive Sandbox](sandbox.md) | Isolated pipeline runner for observing cognitive steps, gates, and memory formation |
