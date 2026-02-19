"""
Direct Anthropic API provider — uses httpx for minimal dependencies.

Requires ANTHROPIC_API_KEY environment variable.
Cheapest Claude path (no CLI overhead).
"""

import json
import logging
import os

log = logging.getLogger("claudicle.providers.anthropic")

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicAPI:
    name = "anthropic"

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def generate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(
            _API_URL, headers=self._headers(),
            json=body, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return _extract_text(data)

    async def agenerate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _API_URL, headers=self._headers(),
                json=body, timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return _extract_text(data)


def _extract_text(data: dict) -> str:
    """Extract text from Anthropic Messages API response."""
    parts = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "".join(parts)
