# Open Souls — Official Project Reference

**Source:** [github.com/opensouls/opensouls](https://github.com/opensouls/opensouls) (MIT License)

## Soul Engine

The Soul Engine is built on a core belief: LLMs are incredible reasoning machines—similar to the prefrontal cortex of the brain—but they lack *the rest of the mind*. The engine is designed to model everything else: agency, memory, emotion, drive, and goal setting. Think "NextJS + Vercel for the minds of digital beings." It's run locally and containerized for cloud deployment.

At its heart are two abstractions: **WorkingMemory** (an immutable collection of memories) and **cognitiveSteps** (functions that transform WorkingMemory and return typed responses). This functional, append-only approach made AI thought processes debuggable and predictable. Souls are orchestrated by **MentalProcesses**—a state machine where each process defined a behavioral mode (e.g., "introduction", "guessing", "frustrated") that can transition to another, giving souls dynamic, context-aware behavior. The engine supports multiple models (OpenAI, Anthropic, etc), offered resumable conversations with fully persistent state, integrated vector stores with atomic change tracking, and background processes for long-running computations.

The goal is not to build better chatbots—it is to create "AI Souls": agentic, embodied digital beings with personality, drive, and ego that interact with humans (and each other) in genuinely humane ways. Developers use it to bring IP characters to life, build Discord companions, create AR presences, educational tutors, game NPCs, and more. The philosophy prioritized interaction quality over accuracy, drawing inspiration from neuroscience and psychology to model minds realistically.

## Repository Structure

```
opensouls/
├── library/          # Core Soul Engine library
├── packages/         # SDK packages and integrations
├── souls/examples/   # Example soul implementations
├── plans/            # Development plans
├── scripts/          # Build and development scripts
└── logos/            # Project branding
```

## Key Concepts

- **WorkingMemory** — Immutable collection of memories (conversation context + cognitive state)
- **cognitiveSteps** — Pure functions: WorkingMemory + instruction → new WorkingMemory + typed result
- **MentalProcesses** — State machine: each process is a behavioral mode that can transition to another
- **Subprocesses** — Background processes that run between perception cycles
- **MemoryIntegrator** — Handles integration of incoming perceptions into WorkingMemory
- **Hooks** — Capability providers: `useActions`, `useSoulMemory`, `useProcessMemory`, etc.

## Links

- Repository: [github.com/opensouls/opensouls](https://github.com/opensouls/opensouls)
- Website: [opensouls.org](https://opensouls.org)
- License: MIT
