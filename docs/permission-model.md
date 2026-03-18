# Permission Model

How Claudicle controls what Claude Code sessions can do, especially when spawned headlessly by daimones.

## Three-Tier Decision Matrix

Every Bash command in a Claude Code session goes through `smart-auto-approve.py` (PermissionRequest hook):

```
Command arrives
  │
  ├─ Shell chaining? (;  |  &&  `  $(  >  >>)
  │   └─ YES → pass through to manual approval dialog
  │
  ├─ Matches deny pattern?
  │   └─ YES → BLOCKED (no prompt, no execution)
  │
  ├─ Matches allow pattern?
  │   └─ YES → auto-approved (no prompt)
  │
  └─ Neither → pass through to manual approval dialog
```

In interactive sessions, "pass through" means the user sees an approve/deny prompt. In `bypassPermissions` sessions (daemon-spawned), "pass through" means auto-approved. This makes the **deny list the only safety boundary** for headless sessions.

## Configuration

Patterns are loaded from `~/.claude/config/auto-approve-whitelist.json`. If the file is missing or malformed, hardcoded fallbacks in `smart-auto-approve.py` take effect.

Install the template:
```bash
cp config/auto-approve-whitelist.template.json ~/.claude/config/auto-approve-whitelist.json
```

### Deny Categories (12)

| Category | Examples | Why |
|----------|---------|-----|
| `privilege-escalation` | `sudo`, `su -` | Never run as root |
| `destructive` | `rm -rf /`, `rm -rf ~`, `chmod -R`, `chown` | Irreversible file/permission changes |
| `arbitrary-exec` | `eval`, `dd`, `python -c`, `node -e`, `ruby -e` | Arbitrary code execution |
| `network-exec` | `curl\|sh`, `wget\|sh`, `curl\|python` | Remote code execution |
| `fork-bomb` | `:(){ :\|: & }` | System denial-of-service |
| `git-destructive` | `push --force`, `push main`, `reset --hard`, `clean -f`, `branch -D` | Irreversible git state |
| `git-bypass` | `--no-verify`, `--no-gpg-sign` | Skips safety hooks |
| `process-kill` | `kill -9`, `killall`, `pkill` | Ungraceful termination |
| `system-config` | `launchctl`, `defaults write`, `networksetup` | macOS system changes |
| `sensitive-write` | Redirects to `/etc/`, `~/.ssh/`, `~/.claude/settings` | Sensitive path writes |
| `publish` | `npm publish`, `cargo publish`, `gem push` | Package registry publish |
| `db-destructive` | `DROP TABLE`, `TRUNCATE`, `DELETE` without WHERE | Irreversible database changes |

### Allow Categories (7)

| Category | Examples |
|----------|---------|
| `git-read` | `git status`, `diff`, `log`, `show`, `branch`, `blame` |
| `file-inspect` | `ls`, `find`, `grep`, `cat`, `head`, `tail`, `wc` |
| `test-runners` | `npm test`, `pytest`, `vitest`, `jest` |
| `package-info` | `npm list`, `pip show`, `pip freeze` |
| `process-inspect` | `lsof -i`, `ps aux`, `which` |
| `system-info` | `pwd`, `whoami`, `uname`, `date` |
| `version-checks` | `node -v`, `python --version`, `cargo --version` |

## Bypass Permissions

Two paths to `bypassPermissions`:

1. **Claude Agent SDK** (`claude_handler.async_process`): sets `permission_mode="bypassPermissions"` in `ClaudeAgentOptions`. Used by the unified launcher and orchestrator API.

2. **Legacy subprocess** (`claude_handler.process`): passes `--dangerously-skip-permissions` as a CLI flag. Used by `bot.py`.

Both paths still fire the `smart-auto-approve.py` hook. Deny patterns block even with permissions bypassed.

## Subdaimone File Access Permissions

Subdaimones run as non-interactive subagents via the Agent tool. When a subagent's tool call would normally trigger a user approval prompt (e.g., reading a file outside the project directory), the call is **silently blocked** — the subagent cannot prompt the user interactively.

This means subdaimones that read soul files, CLAUDE.md, or run boot scripts at `~/.claude/` or `~/.claudicle/` will fail unless those paths are explicitly allowed in `settings.local.json`.

### Required Permissions

Add these to your **global** `~/.claude/settings.local.json` (not project-level) so subdaimones can access soul infrastructure from any project:

```json
{
  "permissions": {
    "allow": [
      "Read(//Users/<you>/.claude/**)",
      "Read(//Users/<you>/.claudicle/**)",
      "Read(//Users/<you>/daimones/**)",
      "Glob(//Users/<you>/.claude/**)",
      "Glob(//Users/<you>/.claudicle/**)",
      "Glob(//Users/<you>/daimones/**)",
      "Grep(//Users/<you>/.claude/**)",
      "Grep(//Users/<you>/.claudicle/**)",
      "Grep(//Users/<you>/daimones/**)"
    ]
  }
}
```

Without these, every subdaimone's boot sequence fails silently — `soul-context.py` runs (covered by `Bash(python3:*)`), but subsequent Read/Glob/Grep calls to soul files are blocked.

### Symptoms of Missing Permissions

- Subdaimones report "blocked by permissions" or return incomplete results
- Boot sequence partially executes (Bash works, Read fails)
- Soul identity not loaded — subdaimone responds as a generic agent

## Review Cadence

Before major Claude Code updates:
1. Review `~/.claude/config/auto-approve-whitelist.json`
2. Update the `version` and `reviewed_by` fields
3. Run the test suite: `echo '{"tool_name":"Bash","tool_input":{"command":"sudo rm -rf /"}}' | python3 ~/.claude/hooks/smart-auto-approve.py`
4. Check `git log -p ~/.claude/config/auto-approve-whitelist.json` for audit trail

## Shell Chaining Guard

The first check in the hook rejects commands containing shell chaining operators before either the allow or deny list is consulted. This prevents bypass attacks like:

```bash
git status ; rm -rf ~     # chaining guard catches ';'
git log | cat             # chaining guard catches '|'
git status && sudo rm -rf # chaining guard catches '&&'
```

These commands fall through to manual approval (interactive) or auto-approve (bypassPermissions). The deny list then catches the dangerous portion only if the command isn't chained.
