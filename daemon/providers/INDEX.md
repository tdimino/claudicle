---
title: "Providers"
directory: daemon/providers/
files: 6
created: 2026-02-19
description: "LLM provider abstraction layer — 6 providers with registry and fallback chains"
providers:
  - claude_cli (default)
  - anthropic_api
  - claude_sdk
  - groq
  - ollama
  - openai_compat
---

# Providers

LLM provider abstraction layer. Each provider implements the same interface; the registry in `__init__.py` handles selection and fallback chains.

---

| Provider | File | Cost | Requires |
|----------|------|------|----------|
| Claude CLI | `claude_cli.py` | Per-use | `claude` in PATH |
| Anthropic API | `anthropic_api.py` | Per-token | `ANTHROPIC_API_KEY` |
| Claude Agent SDK | `claude_sdk.py` | Per-token | `claude-agent-sdk` package |
| Groq | `groq_provider.py` | Near-free | `GROQ_API_KEY` |
| Ollama | `ollama_provider.py` | Free | Local Ollama server |
| OpenAI-Compatible | `openai_compat.py` | Varies | `OPENAI_COMPAT_BASE_URL` |

All providers are stateless per-call (no `--resume`). Provider selection is configured via `CLAUDICLE_PROVIDER` with per-cognitive-step overrides in `CognitiveStep`.
