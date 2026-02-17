"""
Claude Agent SDK provider — wraps SDK query().

Requires claude-agent-sdk package. Stateless per-call (no --resume).
"""

import logging

log = logging.getLogger("claudius.providers.claude_sdk")


class ClaudeSDK:
    name = "claude_sdk"

    def generate(self, prompt: str, model: str = "") -> str:
        import asyncio
        try:
            asyncio.get_running_loop()
            # Already inside an event loop — run in a thread to avoid deadlock
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.agenerate(prompt, model=model)).result()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(self.agenerate(prompt, model=model))

    async def agenerate(self, prompt: str, model: str = "") -> str:
        import os
        from claude_agent_sdk import (
            query,
            ClaudeAgentOptions,
            AssistantMessage,
            ResultMessage,
            TextBlock,
        )

        env_overrides = {
            "CLAUDECODE": "",
            "CLAUDE_CODE_SSE_PORT": "",
            "CLAUDE_CODE_ENTRYPOINT": "",
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""),
        }

        options = ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash", "WebFetch"],
            permission_mode="bypassPermissions",
            env=env_overrides,
        )

        full_response = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        full_response += block.text
            elif isinstance(message, ResultMessage):
                if message.is_error:
                    raise RuntimeError(f"SDK error: {message.result}")
                if message.result and not full_response:
                    full_response = message.result

        return full_response
