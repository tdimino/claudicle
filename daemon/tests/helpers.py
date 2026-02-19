"""Shared test constants and utilities."""

import json


SAMPLE_SOUL_MD = """# Claudicle — Test Soul

You are Claudicle, a test soul agent.

## Personality
Helpful and concise.

## Guidelines
Answer questions directly.
"""

SAMPLE_SKILLS_MD = """## Skills

- **Read**: Read files
- **Search**: Search the web
"""


class MockProvider:
    """Fake LLM provider that returns configurable responses and records calls."""

    def __init__(self, name="mock", response=""):
        self.name = name
        self.response = response
        self.calls: list[dict] = []

    def generate(self, prompt: str, model: str = "") -> str:
        self.calls.append({"prompt": prompt, "model": model})
        return self.response

    async def agenerate(self, prompt: str, model: str = "") -> str:
        self.calls.append({"prompt": prompt, "model": model})
        return self.response


def make_inbox_entry(
    text="Hello",
    user_id="U123",
    channel="C456",
    thread_ts="1234567890.000001",
    display_name="TestUser",
    handled=False,
    **extra,
):
    """Build a standard inbox entry dict."""
    entry = {
        "text": text,
        "user_id": user_id,
        "channel": channel,
        "thread_ts": thread_ts,
        "display_name": display_name,
        "handled": handled,
    }
    entry.update(extra)
    return entry


def write_inbox_entry(path, entry):
    """Append a single JSON line to an inbox file."""
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
