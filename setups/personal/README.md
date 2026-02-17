# Claudius — Personal Setup

Your own soul agent in 5 minutes.

## What You Get

- A Claude Code session with persistent personality via `/ensoul`
- Three-tier memory: remembers you across conversations
- Optional Slack integration: respond to DMs as your soul agent
- Optional SMS integration: text your agent via Telnyx/Twilio

## Quick Start

```bash
git clone https://github.com/tdimino/claudius
cd claudius
./setup.sh --personal
```

## Customize Your Soul

Edit `~/.claudius/soul/soul.md` to change:
- Name and persona
- Speaking style and tone
- Values and principles
- Emotional spectrum

## Add Skills

Claudius ships with zero skills — pair it with any skill repo:

```bash
# Example: add 40+ skills from claude-code-minoan
git clone https://github.com/tdimino/claude-code-minoan
cp -r claude-code-minoan/skills/* ~/.claude/skills/
cd ~/.claudius && ./setup.sh --personal  # regenerates skills manifest
```

## Environment Variables

Copy `env.example` to your shell profile and fill in your tokens.
