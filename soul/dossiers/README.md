# Dossiers — Deep Knowledge for Your Soul

Dossiers are structured markdown files that give your soul agent deep
pre-authored knowledge. Unlike `soul.md` (which is injected into every
prompt), dossiers are **reference material** — available when needed,
not loaded by default.

## Quick Start

1. Copy a template from `templates/`
2. Fill in the YAML frontmatter tags and all sections (be specific — vague dossiers are useless)
3. Save it in this directory (any name, `.md` extension)
4. Reference it when relevant: "Read my self-portrait in soul/dossiers/"

## Templates

| Template | Use When |
|----------|----------|
| `self-portrait.md` | You want the soul to deeply understand YOU |
| `research-subject.md` | You have a topic the soul should be expert in |
| `person.md` | Someone the soul should know about |
| `domain-knowledge.md` | Technical/professional context |

## Principles

- **Specificity over length.** A 20-line dossier with sharp details beats
  a 200-line one with generalities.
- **Update, don't accumulate.** Edit existing dossiers rather than adding new ones.
- **RAG tags matter.** 20-30 tags per dossier enable semantic retrieval
  if you wire up a vector store.
- **Honest uncertainty.** Mark speculation as speculation. The soul trusts
  what you write here.

## How Dossiers Are Used

Dossiers live on disk as reference material. They can be:

- **Read on demand** — "Read my self-portrait dossier" or "What do you know about [topic]?"
- **Loaded into RAG** — If you have a vector store, dossiers are chunked for retrieval
- **Referenced in soul.md** — Point soul.md to specific dossiers: "For my background, see soul/dossiers/self-portrait.md"
- **Loaded via hooks** — A SessionStart hook can inject specific dossiers as `additionalContext`

They are NOT automatically injected into every prompt. This keeps prompts
lean while making deep knowledge available when the soul needs it.

## Self-Dossier vs Auto-Generated User Model

Claudicle auto-generates user models from conversations (the Samantha-Dreams
pattern). Your self-portrait dossier is different:

| Aspect | Auto User Model | Self-Portrait Dossier |
|--------|----------------|----------------------|
| Author | The soul engine | You |
| Updates | Automatic | Manual |
| Depth | Shallow (observed) | Deep (self-authored) |
| Available | After N interactions | Day one |

They complement each other. The self-portrait provides ground truth;
the auto model captures how you actually behave in practice.

## Examples

See `examples/` for filled-in dossiers showing what good looks like:

- `self-portrait-example.md` — A fictional developer's self-dossier
- `research-subject-example.md` — A research topic dossier
