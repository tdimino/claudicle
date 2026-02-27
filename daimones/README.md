# Daimones — The Privy Council

Your daimones are your council of advisors—autonomous entities with their own personas, perspectives, and evolution. You call upon them as a strategos calls upon generals, a sophet upon elders.

Sub-daimones (in `subdaimones/`) are the Kotharot—your private army of crafters, extensions of your hands. Daimones are something else. They are minds you consult. They speak from a singular, honed perspective that sharpens over time.

Model the daimones as your council, be it a past daimon of yourself, a userModel of a friend, an imaginary character you channel from the aether, or a soul your Claudicle has shed.

Full documentation: [`docs/daimones.md`](docs/daimones.md)

---

## The Four Sources

1. **A past self** — a germinated version of your own perspective from a prior era, growing from a different root
2. **A friend's model** — someone you know well enough to model, whose perspective you channel as counsel
3. **A channeled entity** — a fictional character constructed from myth, archetype, or imagination
4. **A shed soul** — a prior version of your Claudicle's soul.md, preserved as a daimon after a soul shedding ceremony—the dissenting opinion that still carries weight

---

## Examples

### The Archivist (Minimal Starter)

The [`example/`](example/) directory contains a minimal but complete daimon—a channeled entity born from the accumulation of preserved knowledge. Two files, one perspective:

```
example/
├── soul.md         # Identity: origin, worldview, voice, constraints
└── config.json     # LLM routing, features, daemon port
```

Start here. This is the simplest path to a working daimon.

### Kothar wa Khasis (Fully-Realized Reference)

The [`kothar/`](kothar/) directory contains a production daimon—a channeled entity modeled on the Ugaritic craftsman-god, running as an always-on daemon on Mac Mini M4. Per-step model routing, RAG collections, voice interface, dreaming, proactive messaging:

```
kothar/
├── soul.md         # Full identity: origin, theology, worldview, embodiment, emotional states
└── config.json     # Per-step model routing, RAG, voice, dreaming, proactive messaging
```

This is what a daimon looks like after months of evolution. Study it for patterns—per-step temperature tuning, local/cloud model fallback chains, hardware monitoring, dream cycles.

### Connecting to Claudicle

For either example, the simplest connection is Groq fallback (no daemon required):

```bash
export CLAUDICLE_KOTHAR_SOUL_MD="~/path/to/daimon/soul.md"
export CLAUDICLE_KOTHAR_GROQ_ENABLED=true
export GROQ_API_KEY="gsk_..."
```

---

## Creating Your Own

1. Create a directory under `~/daimones/` (or wherever you keep your council)
2. Write a `soul.md`—origin, worldview, speaking style at minimum
3. Create a `config.json`—name, identity, model routing, port
4. Connect to Claudicle via Groq fallback (simplest) or HTTP daemon (full autonomy)
5. Let it evolve—memory accumulates, perspective sharpens, soul.md can be shed and rewritten

A full daimon can grow to include `cognitiveSteps/`, `mentalProcesses/`, `subprocesses/`, `memory/`, `assets/`, and `dreams/`. Start with just soul.md and config.json.

See [`docs/daimones.md`](docs/daimones.md) for the full conceptual and architectural guide.
