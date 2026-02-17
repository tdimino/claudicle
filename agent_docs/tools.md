# Tool Reference

Preferred tools for Claudius soul agent sessions. Installed to `~/.claude/agent_docs/` by setup.sh.

## Web Scraping
- **Firecrawl**: `firecrawl scrape URL --only-main-content` — preferred over WebFetch
- **Jina**: `jina URL` — fallback scraper, works on Twitter/X

## Search
- **OSGrep**: `osgrep "query" -p PATH` — semantic code search, prefer over grep
- **Exa**: `python3 ~/.claude/skills/exa-search/scripts/exa_search.py "query"` — neural web search

## Local RAG
- **RLAMA**: `rlama search BUCKET "query"` — semantic search over local document collections
- `rlama list` — show available collections

## Infrastructure
- `uv run` / `uv pip` — Python package management (always use uv, never raw pip)
- `git` / `gh` — Version control and GitHub CLI
- `bd` — Beads task tracker (dependency-aware, cross-session)

## MCP Servers
Use MCP servers before guessing. Check `~/.claude.json` or `~/.claude/settings.json` for configured servers.

## Notes
- Prefer Firecrawl over WebFetch for all web content
- Prefer RLAMA for semantic code/document search over grep
- Use `uv` for all Python operations
- When operating as a Slack daemon, keep responses concise (2-4 sentences unless asked for more)
