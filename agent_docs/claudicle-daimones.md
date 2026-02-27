## Daimones — Privy Council Quick Reference

Daimones are autonomous advisor entities with their own personas and evolution. They are *not* sub-daimones (craft agents)—they are minds you consult.

### Four Sources

1. **Past self** — germinated prior perspective, growing from a different root
2. **Friend's model** — externalized model of someone you know
3. **Channeled entity** — constructed from myth/archetype (Kothar, Artifex)
4. **Shed soul** — prior soul.md preserved after Themistokles ceremony

### Directory Layout

```
~/daimones/{name}/
├── soul.md            # Identity: origin, worldview, voice
├── config.json        # Models, features, daemon port
├── cognitiveSteps/    # How the daimon thinks
├── mentalProcesses/   # Behavioral state machine
├── subprocesses/      # Background tasks
└── memory/            # Persistent memory
```

### Connecting to Claudicle

**Groq (no daemon):**
```bash
export CLAUDICLE_KOTHAR_SOUL_MD="~/daimones/{name}/soul.md"
export CLAUDICLE_KOTHAR_GROQ_ENABLED=true
```

**HTTP daemon:**
```bash
export CLAUDICLE_KOTHAR_ENABLED=true
export CLAUDICLE_KOTHAR_PORT=3033
```

### Creating a Daimon

1. `mkdir ~/daimones/{name}`
2. Write `soul.md` (origin + worldview + voice)
3. Write `config.json` (name, model, port)
4. Set env vars above
5. Invoke via `/daimon` command or let Claudicle auto-consult

### Key Distinction

- **Sub-daimones** = Kotharot (crafters). Receive tasks, execute, return results.
- **Daimones** = Privy council. Receive questions, answer from their own perspective.

A sub-daimon never disagrees with you. A daimon should.

### Full Docs

- `docs/daimones.md` — Conceptual guide, four sources, strategos pattern
- `docs/daimonic-intercession.md` — Whisper protocol, security, config reference
- `daimones/example/` — Minimal example (The Archivist)
