# Config

Configuration files that control Claude Code hook behavior. Versioned and reviewable -- `git diff` shows exactly what changed.

## Files

### `auto-approve-whitelist.json`

Permission whitelist/denylist for the `smart-auto-approve.py` hook (PermissionRequest event, Bash matcher). Controls which Bash commands are auto-approved, hard-denied, or passed through to manual approval.

**Three-tier decision matrix:**
1. **Shell chaining guard** -- commands with `;`, `|`, `&&`, backticks, `$(`, `>` bypass both lists and go to manual approval
2. **Deny** -- matched commands are blocked silently (no prompt, no execution)
3. **Allow** -- matched commands execute without prompting
4. Everything else passes through to the normal approve/deny dialog (interactive) or auto-approves (bypassPermissions)

**Structure:**
```json
{
  "version": "2026-03-17",
  "reviewed_by": "tom",
  "allow": [
    {"pattern": "^git\\s+status", "category": "git-read"}
  ],
  "deny": [
    {"pattern": "sudo\\b", "category": "privilege-escalation", "reason": "Never run as root"}
  ]
}
```

**Categories (deny):**

| Category | What it blocks | Why |
|----------|---------------|-----|
| `privilege-escalation` | `sudo`, `su -` | Never run as root |
| `destructive` | `rm -r`, `rm *`, `chmod -R`, `chown`, glob deletes | Irreversible file/permission changes |
| `arbitrary-exec` | `eval`, `dd`, `python -c`, `ruby -e`, `node -e`, `perl -e` | Arbitrary code execution |
| `network-exec` | `curl\|sh`, `wget\|sh`, `curl\|python`, `curl\|node`, `curl\|ruby` | Remote code execution |
| `fork-bomb` | `:(){ :\|: & }` | System denial-of-service |
| `git-destructive` | `push --force`, `push main/master`, `reset --hard`, `clean -f`, `checkout -- .`, `branch -D` | Irreversible git state changes |
| `git-bypass` | `--no-verify`, `--no-gpg-sign` | Skips safety hooks |
| `process-kill` | `kill -9`, `killall`, `pkill` | Ungraceful process termination |
| `system-config` | `launchctl`, `defaults write`, `networksetup`, `scutil`, `dscl`, `systemsetup` | macOS system configuration |
| `sensitive-write` | Redirects to `/etc/`, `~/.ssh/`, `~/.claude/settings` | Write to sensitive paths |
| `publish` | `npm publish`, `cargo publish`, `gem push`, `twine upload` | Package registry publish -- never headless |
| `db-destructive` | `DROP TABLE/DATABASE`, `TRUNCATE`, `DELETE` without WHERE, `ALTER TABLE ... DROP` | Irreversible database changes |

**Categories (allow):**

| Category | What it allows |
|----------|---------------|
| `git-read` | `git status/diff/log/show/branch/tag/blame/ls-files` |
| `file-inspect` | `ls`, `stat`, `find`, `grep`, `rg`, `cat`, `head`, `tail`, `wc` |
| `test-runners` | `npm test`, `pytest`, `vitest`, `jest` |
| `package-info` | `npm list/outdated`, `pip list/show/freeze` |
| `process-inspect` | `lsof -i`, `ps aux`, `which` |
| `system-info` | `pwd`, `whoami`, `uname`, `date`, `sw_vers` |
| `version-checks` | `node -v`, `python --version`, `cargo --version`, etc. |

**Critical for daemon-spawned sessions:** When Kothar's orchestrator spawns Claude Code with `bypassPermissions`, this deny list is the only safety boundary. Commands not explicitly denied are permitted without human approval.

**Review cadence:** Update `version` and `reviewed_by` fields before major Claude Code updates. `git log -p ~/.claude/config/auto-approve-whitelist.json` shows the full audit trail.

**Consumed by:** `~/.claude/hooks/smart-auto-approve.py` (falls back to hardcoded patterns if this file is missing or malformed).
