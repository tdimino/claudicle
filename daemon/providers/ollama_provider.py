"""
Ollama local provider — zero cost, zero latency, full sovereignty.

No API key required. Talks to localhost:11434 by default.
Override with OLLAMA_HOST environment variable.
"""

import logging
import os

log = logging.getLogger("claudius.providers.ollama")

_DEFAULT_MODEL = "hermes3:8b"


class OllamaProvider:
    name = "ollama"

    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def generate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "prompt": prompt,
            "stream": False,
        }
        resp = httpx.post(
            f"{self.base_url}/api/generate",
            json=body, timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def agenerate(self, prompt: str, model: str = "") -> str:
        import httpx

        body = {
            "model": model or _DEFAULT_MODEL,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=body, timeout=300,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
