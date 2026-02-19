"""
Claude CLI provider — wraps `claude -p` subprocess.

Default provider. Always available when `claude` is in PATH.
Does NOT use --resume (providers are stateless per-call).
Session continuity is handled by claude_handler.py for unified mode,
or by the caller for split/watcher mode.
"""

import asyncio
import json
import logging
import os
import subprocess

log = logging.getLogger("claudicle.providers.claude_cli")


class ClaudeCLI:
    name = "claude_cli"

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    def generate(self, prompt: str, model: str = "") -> str:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])

        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
        for key in list(env):
            if key.startswith("CLAUDE_CODE_") or key == "CLAUDECODE":
                env.pop(key)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout, env=env,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"claude -p timed out after {self.timeout}s")

        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            if result.returncode != 0:
                raise RuntimeError(f"claude -p failed (rc={result.returncode}): {result.stderr[:200]}")
            return result.stdout.strip()

        if data.get("is_error"):
            raise RuntimeError(f"Claude error: {data.get('result', 'unknown')}")
        if result.returncode != 0:
            raise RuntimeError(f"claude -p failed (rc={result.returncode})")

        return data.get("result", "")

    async def agenerate(self, prompt: str, model: str = "") -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate, prompt, model)
