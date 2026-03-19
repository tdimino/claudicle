# claude -p Subprocess Usage

Claudicle invokes Claude Code as a subprocess via `claude -p` (print mode). This is the backbone of the Legacy Daemon (`bot.py`) and the `claude_cli` provider, and serves as an escalation path in bridge mode when full tool access is needed.

## What `claude -p` Is

`claude -p` / `claude --print` is a built-in Claude Code CLI flag — not part of the Agent SDK. It runs a single prompt through Claude Code with full tool access, outputs the response to stdout, and exits. It supports all standard CLI flags:

```bash
claude -p "Your prompt here"
claude -p "Prompt" --output-format json
claude -p "Prompt" --resume SESSION_ID
claude -p "Prompt" --allowed-tools "Read,Glob,Grep,Bash"
claude -p "Prompt" --model sonnet
claude -p "Prompt" --max-budget-usd 0.50
```

This is a standard feature of the Claude Code CLI. No SDK, no additional dependencies.

## Nesting Guard

Claude Code prevents nested sessions by default. If you try to run `claude -p` from inside a running Claude Code session (e.g., via the Bash tool), you get:

```
Error: Claude Code cannot be launched inside another Claude Code session.
Nested sessions share runtime resources and will crash all active sessions.
To bypass this check, unset the CLAUDECODE environment variable.
```

The guard detects nesting via the `CLAUDECODE` environment variable, which Claude Code sets automatically in its child process environment. Any `CLAUDE_CODE_*` prefixed variables also indicate a parent session.

## How Claudicle Handles This

Every code path that invokes `claude -p` strips the nesting guard variables from the subprocess environment:

```python
env = os.environ.copy()
for key in list(env):
    if key.startswith("CLAUDE_CODE_") or key == "CLAUDECODE":
        env.pop(key)

result = subprocess.run(
    ["claude", "-p", prompt, "--output-format", "json"],
    capture_output=True, text=True,
    timeout=120, env=env,
)
```

This is implemented in:
- `daemon/providers/claude_cli.py` — the `claude_cli` provider (lines 32-34)
- `daemon/claude_handler.py` — the `process()` function (lines 146-148)
- `daemon/claude_handler.py` — the `async_process()` SDK path (lines 357-360)
- `adapters/sms/sms_respond.py` — SMS channel adapter (line 352)

## When Nesting Matters

The nesting guard is only relevant when `claude -p` is called **from inside** a Claude Code session — e.g., during development/testing from your terminal. In production deployment (launchd daemon, Slack bot), the parent process is Python, not Claude Code, so the guard variables aren't present and no stripping is needed.

However, Claudicle always strips them defensively. This is correct — the daemon could theoretically be launched from within a Claude Code session during development, and the code should work regardless of how it was started.

## claude -p vs Agent SDK

Claudicle supports both invocation methods:

| | `claude -p` (subprocess) | Agent SDK (`query()`) |
|---|---|---|
| **Function** | `claude_handler.process()` | `claude_handler.async_process()` |
| **Used by** | `bot.py` (Legacy Daemon) | `claudicle.py` (Unified Launcher) |
| **Provider** | `providers/claude_cli.py` | `providers/claude_sdk.py` |
| **I/O** | stdin/stdout, synchronous | Async generator, streaming |
| **Session resume** | `--resume SESSION_ID` flag | `resume=SESSION_ID` parameter |
| **Dependencies** | Claude Code CLI in PATH | `claude-code-sdk` Python package |
| **Nesting guard** | Strip `CLAUDECODE` env var | Set `CLAUDECODE=""` in env |

Both spawn full Claude Code sessions with tool access and session continuity. The subprocess approach is simpler and has no Python dependency beyond `subprocess`. The SDK approach is async-native and supports streaming.

## claude -p vs Bridge Mode Providers

Bridge mode (split pipeline, inbox watcher) routes cognitive steps through LLM providers **directly** — Groq, Ollama, OpenRouter, Anthropic API — without spawning a Claude Code session. These providers are lighter and cheaper but have **no tool access** (no Bash, Read, Edit, etc.).

`claude -p` remains available as an escalation path when bridge mode needs full Claude Code capabilities:

| Provider | Tool Access | Cost | Use Case |
|---|---|---|---|
| `ollama` | No | Free | Monologue, dreams, system queries |
| `groq` | No | Cheap | Classification, structured output, scholarly |
| `openai_compat` | No | Varies | OpenRouter, custom endpoints |
| `anthropic_api` | No | API rate | Direct Anthropic calls |
| `claude_cli` | **Yes** | API rate | Complex reasoning, file ops, multi-tool tasks |
| `claude_sdk` | **Yes** | API rate | Same as above, async/streaming |

## PATH Considerations

When invoked via launchd, the `PATH` may not include Homebrew or user-local binaries. `claude_cli.py` prepends standard paths:

```python
env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
```

Ensure `claude` is accessible at one of these paths, or symlink it (e.g., `ln -sf $(which claude) /usr/local/bin/claude`).

## Testing

The nesting guard stripping is covered by `daemon/tests/test_claude_handler.py`:

```python
def test_env_vars_stripped(self):
    """CLAUDE_CODE_* env vars are stripped to prevent nested sessions."""
```

To test `claude -p` manually from inside a Claude Code session:

```bash
# This fails (nesting guard):
claude -p "Hello"

# This works (env var stripped):
env -u CLAUDECODE claude -p "Hello"
```
