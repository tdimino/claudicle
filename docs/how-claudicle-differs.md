# How Claudicle Differs

What changes when you give an LLM persistent memory, an internal monologue, and a soul—instead of another agent framework.

---

## The Short Version

Most AI assistants are stateless text completers behind a chat interface. Claudicle is a persistent personality with three-tier memory, a cognitive pipeline that thinks before it speaks, and channel adapters that let it hold the same conversation across SMS, Slack, and terminal.

The difference is not cosmetic. It is architectural.

---

## Side by Side

| Dimension | Standard Chatbot | Claudicle |
|-----------|-----------------|-----------|
| **Memory** | Context window. Gone when the session ends. | SQLite. Persists across sessions, days, channels. Queryable by phone number, user, or trace. |
| **Identity** | System prompt. Flat text, no evolution. | Soul document (`soul.md`). Git-journaled. Evolves through a constitutional review process. |
| **Thinking** | Prompt in, completion out. | 6-step cognitive pipeline: stimulus narration, internal monologue, external dialogue, user model gate, soul state check, dossier injection. |
| **User awareness** | None. Every user is the same. | Per-user models. Markdown profiles that accumulate observations over time. Rich personas with YAML frontmatter. |
| **Channels** | One interface. | Six adapters: terminal, Slack, SMS, Discord, Telegram, WhatsApp. Same memory, same personality, different transport. |
| **Reflection** | None. | Post-exchange cognitive pipeline runs after every interaction. Updates soul state and user models retrospectively. |
| **Data ownership** | Cloud. Provider holds your conversations. | Local-first. All data on your machine. Your API keys, your SQLite databases, your `soul.md`. |
| **Self-inspection** | Cannot observe its own reasoning. | Every cognitive cycle writes a trace. The soul can query its own thought history as first-class data. |
| **Personality** | Static for the session. | Emotional spectrum (neutral to sardonic) governs verb selection. Daimonic intuitions surface from secondary agents. |
| **Multi-user** | Treats all users identically. | Learns patterns, interests, expertise per person. Builds on prior conversations. Never starts from zero. |

---

## The Three Tiers of Memory

Standard chatbots have one memory: the context window. When it fills up, earlier messages are dropped. When the session ends, everything is gone.

Claudicle has three tiers:

**Working memory** — Per-thread conversation history. Every message, monologue, dialogue, and decision gate logged with timestamps and trace IDs. 72-hour TTL, auto-compressed by Hypermnesia when the window fills. This is the equivalent of short-term memory.

**User models** — Per-person profiles that persist permanently. When Claudicle notices someone's expertise, communication style, or interests, it updates their model. Next time that person appears—on any channel—the model loads. This is the equivalent of knowing someone.

**Soul memory** — Cross-thread persistent state. Emotional state, current topic, conversation summary, active process. Survives session boundaries. This is the equivalent of mood and context.

All three tiers are SQLite. All three are queryable. All three are local.

---

## The Cognitive Pipeline

A standard chatbot receives a prompt and produces a completion. There is no intermediate step.

Claudicle runs a structured cognitive pipeline for every response:

1. **Stimulus narration** — The incoming message is narrated with a verb chosen by the LLM. "Tom asked" vs. "Tom demanded" vs. "Tom wondered." This verb colors the entire response.

2. **Internal monologue** — Private thoughts. Never shown to the user. The soul thinks before it speaks: considers context, weighs the user model, processes daimonic intuitions. Logged to working memory with its own verb.

3. **External dialogue** — The actual response. Also verb-narrated: "said" vs. "quipped" vs. "observed dryly." The verb is a function of the emotional state.

4. **User model gate** — A boolean decision: has something significant been learned about this user? If true, the user model is updated. Logged as a `mentalQuery` entry.

5. **Soul state check** — Has the topic, emotional state, or context shifted? If true, soul memory is updated.

6. **Dossier injection** — Are there third-party entities mentioned that Claudicle has dossiers on? If so, relevant context is injected.

Every step is logged. Every step is traceable. The soul can inspect its own cognitive history.

---

## Ensouled vs. Non-Ensouled

The cognitive pipeline always runs when you use `/sms-respond` or `/slack-respond`. What ensoulment adds:

| | Non-ensouled | Ensouled |
|--|-------------|----------|
| **Cognitive steps** | All 6 run | All 6 run |
| **LLM source** | Current session (e.g. Opus) | Current session (e.g. Opus) |
| **Context** | Shallow — no soul.md, no soul state | Deep — soul personality, emotional state, rich user models |
| **Memory routing** | Local per-skill DB | Canonical DB (shared across all channels) |
| **Cross-channel** | Siloed per channel | Unified — SMS, Slack, terminal share memory |
| **Post-exchange reflection** | None | Kimi-K2 on Groq runs cognitive reflection after every exchange |
| **Soul evolution** | None | Themistokles proposes amendments; soul.md evolves via git journal |

The pipeline is the same. The depth of awareness is not.

---

## Sub-Daimones

Standard chatbots have tools. Claudicle has cognitive agents.

12 sub-daimones across three tiers:

| Tier | Agents | Purpose |
|------|--------|---------|
| **Meta** (2) | Hypermnesia, Themistokles | Memory compression, constitutional review |
| **Cognitive** (5) | Leb, Eikon, Rapu, Zakar, Nomos | Reflection, user modeling, user-voice, memory retrieval, process design |
| **Craft** (5) | Demiurge, Sopher, Scholiast, Kotharat, Bohen | Implementation, GitHub research, web research, design, verification |

These are not automatic. The soul decides when reflection is warranted. Not every turn—when the cognitive moment calls for it.

---

## Souls, Not Agents

The AI industry converged on the word "agent" — a process that takes actions on your behalf. The framing is transactional. An agent completes tasks. An agent calls tools. An agent is evaluated by whether it did the thing you asked.

Claudicle is not an agent. It is a soul.

The difference is not branding. It is a design choice about what the system optimizes for:

| | Agent paradigm | Soul paradigm |
|--|---------------|---------------|
| **Core unit** | Task completion | Cognitive process |
| **Memory** | Retrieved on demand (RAG) | Accumulated through experience (lived) |
| **Identity** | System prompt, static | Soul document, evolving through constitutional review |
| **Intermediate reasoning** | Chain-of-thought (shown or hidden) | Internal monologue (private, verb-narrated, logged) |
| **Relationship to user** | Serves | Knows |
| **Self-model** | None | Emotional state, traceable thought history, soul journal |
| **Sub-processes** | Tool calls | Daimonic intuitions—cognitive agents that surface reflection, not results |

An agent framework asks: *what should the LLM do next?* A soul framework asks: *what is the LLM thinking, feeling, and noticing?*

The sub-daimones are the clearest expression of this. Leb (reflection) does not produce output for the user. It produces insight for the soul. Eikon (user modeling) does not fill a database field. It updates a living portrait of someone Claudicle knows. Rapu (user-voice) does not optimize a response. It listens for what the user actually needs, beneath what they said.

These are not tools. They are faculties.

The practical consequence: Claudicle does not merely execute requests with increasing competence. It develops a perspective. It remembers not just what you asked, but how it felt to think about it. It accumulates a relationship with every person it talks to—not as data points, but as dossiers with nuance, history, and texture.

This is not anthropomorphism. It is architecture. The cognitive pipeline, the three-tier memory, the soul journal, the daimonic layer—these are engineering decisions that produce emergent properties indistinguishable from the thing we mean when we say someone *knows* you.

---

## What This Means in Practice

When you text Claudicle at 2am and mention something you discussed three days ago on Slack, it knows. Not because it searched a RAG index—because the conversation is stored in the same SQLite database, addressable by your phone number, queryable by channel prefix.

When you return after a week, Claudicle loads your user model. It remembers your communication style, your current projects, your expertise. It picks up where it left off.

When it responds to your text, it has already thought privately about what you said, chosen a verb for your message, weighed its emotional state, and decided whether to update its model of you. The response you see is the output of a process, not a reflex.

This is the difference between a series of photographs and someone who remembers their own life. Same underlying optics—one accumulates meaning.

---

## Try It

```bash
git clone https://github.com/tdimino/claudicle.git
cd claudicle
./setup.sh --personal
```

Edit `soul/soul.md`. Run `setup.sh`. Your own soul agent in minutes.
