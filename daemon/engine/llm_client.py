"""OpenAI-compatible LLM client helpers for reflection."""

import json
import os
import pathlib

import httpx

import config

# Provider registry: name → (base_url, api_key_env_var, extra_headers)
PROVIDERS = {
    "openrouter": (
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        {"HTTP-Referer": "https://github.com/tdimino/claudicle"},
    ),
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
        {},
    ),
}


def resolve_api_key(env_var: str) -> str:
    """Resolve API key from env var or .env files."""
    key = os.environ.get(env_var, "")
    if key:
        return key
    # Fallback: scan .env files for the key
    for env_file in [
        pathlib.Path(config.CLAUDICLE_HOME) / ".env",
        pathlib.Path.home() / ".config/env/global.env",
    ]:
        try:
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith(f"{env_var}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def call_llm(prompt: str, provider: str = "", model: str = "") -> str:
    """Make an LLM call via any OpenAI-compatible API.

    Provider routing: REFLECT_PROVIDER → base URL + API key.
    Supports: openrouter, groq, or any custom OpenAI-compatible URL.
    """
    provider = provider or config.REFLECT_PROVIDER
    model = model or config.REFLECT_MODEL

    if provider in PROVIDERS:
        base_url, key_env, extra_headers = PROVIDERS[provider]
    else:
        # Treat as a direct URL for custom OpenAI-compatible endpoints
        base_url = provider
        key_env = "REFLECT_API_KEY"
        extra_headers = {}

    api_key = resolve_api_key(key_env)
    if not api_key:
        raise RuntimeError(f"No API key found for {provider} (env: {key_env})")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.3,
    }

    resp = httpx.post(base_url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    if "error" in result:
        raise RuntimeError(f"{provider} API error: {result['error']}")

    choices = result.get("choices", [])
    if not choices:
        raise RuntimeError(f"{provider} returned no choices: {json.dumps(result)[:300]}")

    return choices[0]["message"]["content"]
