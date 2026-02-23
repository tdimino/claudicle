# Recommended Skill Pairings

Claudicle ships with zero skills. Pair it with [claude-code-minoan](https://github.com/tdimino/claude-code-minoan) or bring your own.

```bash
git clone https://github.com/tdimino/claude-code-minoan
cp -r claude-code-minoan/skills/* ~/.claude/skills/
cd claudicle && ./setup.sh --personal  # regenerate manifest
```

## Essential (core agent capabilities)

- **Firecrawl** — Web scraping to markdown (Claudicle can research for you)
- **exa-search** — Neural web search with AI-powered research mode
- **rlama** — Local RAG for semantic search over document collections

## Recommended (enhances the experience)

- **minoan-swarm** — Multi-agent teams with shared task lists and parallel workstreams
- **skill-optimizer** — Create and review skills that extend your agent's capabilities
- **codex-orchestrator** — Delegate tasks to OpenAI Codex subagents (code review, debugging, security)
- **twitter** — Twitter/X integration via bird CLI, x-search API, and Smaug archival
- **claude-tracker-suite** — Session management: search, resume, alive detection
- **claude-md-manager** — Maintain your CLAUDE.md

## Nice-to-have (specialized)

- **nano-banana-pro** — Image generation (soul avatars via Gemini)
- **gemini-claude-resonance** — Cross-model dialogue
- **agent-browser** — Headless browser automation
- **llama-cpp** / **smolvlm** / **parakeet** — Local ML inference
- **academic-research** — Paper search and literature review
