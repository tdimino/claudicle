# Hooks

Claudicle wires Claude Code hooks for soul identity, session continuity, and Slack notifications. All are non-destructive—`setup.sh` merges them into your existing `settings.json`.

## Hook Chain

| Event | Hook | What It Does |
|-------|------|-------------|
| `SessionStart` | `soul-activate.py` | Registers session. If ensouled, injects soul personality + state into `additionalContext`. |
| `SessionEnd` / `Stop` | `soul-deregister.py` | Deregisters session from the soul registry. |
| `Stop` / `PreCompact` | `claudicle-handoff.py` | Heartbeat + session handoff for context recovery. |
| `Stop` | `soul-reflect.py` | Retrospective cognitive reflection via configurable LLM (60s cooldown). |
| `UserPromptSubmit` | `slack_inbox_hook.py` | *(Optional)* Notifies you of unhandled Slack messages each turn. |

## Injection Layers

When soul is active, `soul-activate.py` builds `additionalContext` from five layers:

1. **Soul personality** — `soul/soul.md` (or active profile)
2. **Soul state** — emotional state, current topic from `memory.db`
3. **Working memory** — recent terminal channel entries from `memory.db`
4. **User model** — primary user's living model from `memory.db`
5. **Active sessions** — sibling session awareness from registry

## Details

See [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the full hook chain design and file map.
