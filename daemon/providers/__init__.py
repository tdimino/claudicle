"""
Provider abstraction for Claudicle LLM calls.

Defines a Provider protocol and a registry for pluggable LLM backends.
Providers are auto-registered on import based on available credentials.

Usage:
    from providers import get_provider, list_providers

    provider = get_provider("anthropic")
    response = provider.generate(prompt, model="claude-haiku-4-5-20251001")

    # Or async:
    response = await provider.agenerate(prompt)

    # With fallback chain:
    response = await generate_with_fallback(prompt, ["groq", "ollama", "claude_cli"])
"""

import asyncio
import logging
from typing import Optional, Protocol, runtime_checkable

log = logging.getLogger("claudicle.providers")


@runtime_checkable
class Provider(Protocol):
    """LLM provider interface. All providers implement generate() and agenerate()."""

    name: str

    def generate(self, prompt: str, model: str = "") -> str:
        """Synchronous generation. Blocks until complete."""
        ...

    async def agenerate(self, prompt: str, model: str = "") -> str:
        """Async generation. Default implementation wraps generate()."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_registry: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    """Register a provider instance by name."""
    _registry[provider.name] = provider
    log.debug("Registered provider: %s", provider.name)


def get_provider(name: str = "") -> Provider:
    """Get a provider by name. Empty string returns the default (claude_cli)."""
    if not name:
        name = "claude_cli"
    if name not in _registry:
        # Lazy fallback: register claude_cli if it wasn't auto-registered
        if name == "claude_cli":
            from . import claude_cli
            register(claude_cli.ClaudeCLI())
        else:
            raise KeyError(
                f"Provider '{name}' not registered. "
                f"Available: {', '.join(_registry) or 'none'}"
            )
    return _registry[name]


def list_providers() -> list[str]:
    """List all registered provider names."""
    return list(_registry.keys())


# Called by inbox_watcher when WATCHER_FALLBACK_PROVIDERS is configured (future)
async def generate_with_fallback(
    prompt: str,
    providers: list[str],
    model: str = "",
) -> str:
    """Try providers in order, falling back on failure.

    Returns the first successful response. Raises RuntimeError if all fail.
    """
    errors = []
    for name in providers:
        try:
            p = get_provider(name)
            return await p.agenerate(prompt, model=model)
        except Exception as e:
            log.warning("Provider %s failed: %s", name, e)
            errors.append((name, str(e)))

    raise RuntimeError(
        f"All providers failed: {'; '.join(f'{n}: {e}' for n, e in errors)}"
    )


# ---------------------------------------------------------------------------
# Auto-registration: import available providers
# ---------------------------------------------------------------------------

def _auto_register():
    """Import and register providers based on available credentials/tools."""
    import os
    import shutil

    # claude_cli: always available if `claude` is in PATH
    if shutil.which("claude"):
        try:
            from . import claude_cli
            register(claude_cli.ClaudeCLI())
        except Exception as e:
            log.debug("claude_cli not available: %s", e)

    # claude_sdk: available if claude-agent-sdk is installed
    try:
        from . import claude_sdk
        register(claude_sdk.ClaudeSDK())
    except Exception as e:
        log.debug("claude_sdk not available: %s", e)

    # anthropic: available if ANTHROPIC_API_KEY is set
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from . import anthropic_api
            register(anthropic_api.AnthropicAPI())
        except Exception as e:
            log.debug("anthropic not available: %s", e)

    # groq: available if GROQ_API_KEY is set
    if os.environ.get("GROQ_API_KEY"):
        try:
            from . import groq_provider
            register(groq_provider.GroqProvider())
        except Exception as e:
            log.debug("groq not available: %s", e)

    # ollama: available if localhost:11434 is reachable (lazy check on first use)
    try:
        from . import ollama_provider
        register(ollama_provider.OllamaProvider())
    except Exception as e:
        log.debug("ollama not available: %s", e)

    # openai_compat: available if OPENAI_COMPAT_BASE_URL is set
    if os.environ.get("OPENAI_COMPAT_BASE_URL"):
        try:
            from . import openai_compat
            register(openai_compat.OpenAICompatProvider())
        except Exception as e:
            log.debug("openai_compat not available: %s", e)


_auto_register()
