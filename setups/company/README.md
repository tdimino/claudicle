# Claudicle — Company Setup

A soul agent for your team.

## What You Get

Everything in personal mode, plus:
- Professional team soul template
- Multi-channel Slack bindings (map channels to purposes)
- Shared user models (remembers every team member)
- Team-specific soul personality

## Quick Start

```bash
git clone https://github.com/tdimino/claudicle
cd claudicle
./setup.sh --company
```

The installer will prompt for your company name and configure the soul template.

## Channel Mapping

Edit `channel-map.example.json` to pre-bind Slack channels:

```json
{
  "channels": {
    "#general": "Team-wide announcements and questions",
    "#engineering": "Technical discussions and code review",
    "#support": "Customer support escalations"
  }
}
```

## Team Onboarding

Each team member can interact with Claudicle and build their own user model:
1. DM Claudicle on Slack
2. Claudicle automatically creates a user model after a few interactions
3. The model persists and improves over time

## Environment Variables

Copy `env.example` to your deployment environment.
