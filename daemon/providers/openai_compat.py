"""
OpenAI-compatible provider — works with vLLM, LM Studio, Together, Fireworks.

Requires OPENAI_COMPAT_BASE_URL environment variable.
Optionally set OPENAI_COMPAT_API_KEY for authenticated endpoints.
"""

import logging
import os

log = logging.getLogger("claudius.providers.openai_compat")

_DEFAULT_MODEL = "default"


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self):
        self.base_url = os.environ.get("OPENAI_COMPAT_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("OPENAI_COMPAT_API_KEY", "")

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        resp = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json=body, timeout=120,
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
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=body, timeout=120,
            )
            resp.raise_for_status()
            return _extract_text(resp.json())


def _extract_text(data: dict) -> str:
    """Extract text from OpenAI-compatible chat completions response."""
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""
