"""
Groq cloud provider — fast inference, near-free.

Requires GROQ_API_KEY environment variable.
Uses OpenAI-compatible chat completions endpoint.
"""

import logging
import os

log = logging.getLogger("claudicle.providers.groq")

_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider:
    name = "groq"

    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        resp = httpx.post(
            _API_URL, headers=self._headers(),
            json=body, timeout=60,
        )
        resp.raise_for_status()
        return _extract_text(resp.json())

    async def agenerate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _API_URL, headers=self._headers(),
                json=body, timeout=60,
            )
            resp.raise_for_status()
            return _extract_text(resp.json())


def _extract_text(data: dict) -> str:
    """Extract text from OpenAI-compatible chat completions response."""
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""
