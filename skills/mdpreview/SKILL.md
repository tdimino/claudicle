---
name: mdpreview
description: "Catppuccin-themed live-reloading Markdown viewer with multi-tab support, margin annotations, bookmarks, file tagging, command palette, sidebar TOC, and Chrome --app mode. Use when previewing .md files, adding annotations, or running document review sessions."
argument-hint: <file.md> [file2.md ...] [--port PORT] [--author NAME]
allowed-tools: Bash(python3*), Read, Glob, Write
---

# mdpreview — Markdown Preview & Annotate

Catppuccin Mocha/Latte live-reloading Markdown viewer with multi-tab support and Google Docs-style margin annotations.

> **Canonical repo**: [github.com/tdimino/md-preview-and-annotate](https://github.com/tdimino/md-preview-and-annotate)

## Install

```bash
git clone https://github.com/tdimino/md-preview-and-annotate.git ~/tools/md-preview-and-annotate
```

Zero dependencies — pure Python stdlib.

## Quick Start

```bash
# Preview one or more files
python3 -m md_preview_and_annotate file.md [file2.md ...]

# Add a file to a running server (tab reuse)
python3 -m md_preview_and_annotate --add another.md

# Add an annotation from CLI (no server needed)
python3 -m md_preview_and_annotate --annotate file.md \
  --text "selected passage" --author "Claude" --comment "Needs revision"
```

Opens in Chrome `--app` mode (falls back to default browser). No install, no build step, no dependencies.

## Features

| Feature | Details |
|---------|---------|
| **Live reload** | 500ms polling, auto-refreshes on file save |
| **Multi-tab** | Open multiple .md files, switch tabs, add/close at runtime |
| **Tab reuse** | Launching a new file while server is running adds it as a tab |
| **5 annotation types** | Comment, Question, Suggestion, Important, Bookmark |
| **Threaded replies** | Reply to any annotation inline |
| **Bookmarks** | Global persistence to `~/.claude/bookmarks/` with INDEX.md |
| **File tagging** | 7 predefined + custom tags via command palette `#` prefix |
| **Command palette** | `Cmd+K` / `Ctrl+K` for commands, tabs, and recent files |
| **Sidecar JSON** | Annotations in `file.md.annotations.json` — source markdown never modified |
| **Catppuccin** | Mocha (dark) / Latte (light) themes |
| **Typography** | Cormorant Garamond headings, DM Sans body, Victor Mono code |
| **Sidebar TOC** | Resizable table of contents with scroll-spy |
| **Chrome --app** | Frameless Chrome window for native feel |
| **Cross-file links** | Local `.md` links open in new tabs |

## Annotation System

Select text in the viewer -> floating carousel appears -> pick type -> fill in comment in the gutter.

Programmatic annotations via `--annotate` CLI flag write directly to sidecar JSON (no running server needed).

- **Human authors** — blue name badge
- **AI authors** — mauve name badge with robot icon
- **Resolve/archive** — resolved annotations move to `file.md.annotations.resolved.json`
- **Orphan cleanup** — annotations for deleted text auto-removed on next load

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/content?tab=<id>` | GET | Markdown content for a tab |
| `/api/tabs` | GET | List open tabs |
| `/api/annotations?tab=<id>` | GET | Annotations for a tab |
| `/api/tags?tab=<id>` | GET | Tags for a tab |
| `/api/add` | POST | Open a new file tab |
| `/api/close` | POST | Close a tab |
| `/api/annotate` | POST | Create an annotation |
| `/api/resolve` | POST | Toggle resolved state |
| `/api/reply` | POST | Add a threaded reply |
| `/api/delete-annotation` | POST | Delete an annotation |
| `/api/tags` | POST | Add/remove a tag |
