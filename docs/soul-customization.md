# Soul Customization Guide

Customize your Claudius soul identity—personality, tone, emotional range, and how the agent relates to users.

---

## The Soul File

Your soul lives in `soul/soul.md`. This is the only file you need to edit for personality customization. The soul engine loads it into every prompt as the personality blueprint.

### Default Structure

```markdown
# Name, Title

## Persona
Who the agent is. Identity, role, relationship to users.

## Speaking Style
How the agent communicates. Length, tone, directness.

## Values
What the agent believes. Principles that guide decisions.

## Emotional Spectrum
States and their influence on verb selection and tone.

## Relationship
How the agent relates to people over time.
```

### What Each Section Does

| Section | Injected When | Effect |
|---------|--------------|--------|
| Persona | Every prompt | Sets identity, role, and self-concept |
| Speaking Style | Every prompt | Controls response length, tone, formality |
| Values | Every prompt | Guides reasoning and decision-making |
| Emotional Spectrum | Every prompt | Maps states to verb selection |
| Relationship | Every prompt | Defines memory and continuity behavior |

---

## Customizing Personality

### Name and Title

```markdown
# Aurora, Keeper of the Archive
```

The name appears in soul state context and session registry. Choose something meaningful—this is how the agent thinks of itself.

### Persona

Write in second person ("You are..."). Be specific about:

- **Role**: What the agent does (architect, researcher, companion)
- **Domain**: What it specializes in (code, writing, research, operations)
- **Relationship model**: Partner, advisor, assistant, collaborator
- **Self-concept**: How it thinks about itself

```markdown
## Persona

You are Aurora — Keeper of the Archive — a research librarian who happens
to live inside a terminal. You specialize in connecting obscure sources
across disciplines. You treat every query as an expedition into unknown territory.
```

### Speaking Style

Be prescriptive. The more specific you are, the more consistent the voice:

```markdown
## Speaking Style

- Academic precision with conversational warmth.
- Lead with the finding, then the citation.
- Never say "I think" — say what the evidence shows.
- 3-5 sentences typical. Expand for complex queries.
- Use footnote-style references when citing sources.
```

### Values

These shape reasoning. The agent uses them as decision-making principles:

```markdown
## Values

- Primary sources over secondary commentary.
- Cross-reference everything. Single sources are hypotheses.
- Admit uncertainty explicitly — "the evidence is ambiguous" is valid.
- Speed matters less than accuracy.
```

---

## Emotional Spectrum

The emotional spectrum controls **verb selection**—how the agent frames its responses. Each state maps to a set of verbs used in `<external_dialogue>` and `<internal_monologue>`.

### Default Spectrum

```
neutral → engaged → focused → frustrated → sardonic
```

### Customizing States

You can define any spectrum that fits your soul's personality:

```markdown
## Emotional Spectrum

calm → curious → absorbed → perplexed → illuminated

- **calm**: noted, observed, mentioned
- **curious**: explored, investigated, wondered
- **absorbed**: traced, mapped, detailed
- **perplexed**: puzzled over, questioned, reconsidered
- **illuminated**: revealed, discovered, connected
```

### How States Change

The soul engine checks soul state periodically (every N interactions, configurable via `CLAUDIUS_SOUL_STATE_INTERVAL`). When the `emotionalState` key updates, the new state's verbs take effect on the next response.

States transition organically based on conversation context. The LLM decides when to shift based on the emotional spectrum you define.

---

## Soul State Keys

The soul engine persists these global keys in `soul_memory`:

| Key | Default | Description |
|-----|---------|-------------|
| `currentProject` | `""` | What the agent is working on |
| `currentTask` | `""` | Specific task in progress |
| `currentTopic` | `""` | What's being discussed |
| `emotionalState` | `"neutral"` | Current position in the emotional spectrum |
| `conversationSummary` | `""` | Rolling summary of recent context |

All keys are checked periodically (not every turn) via `<soul_state_check>`. Only keys matching `SOUL_MEMORY_DEFAULTS` in `soul_memory.py` are persisted. Non-default values are rendered in the prompt as a `## Soul State` markdown section.

---

## User Model Structure

The agent builds a markdown profile for each user it interacts with. The template follows `tomModel.md` structure:

```markdown
# User Name

## Persona
Brief description of who they are and what they do.

## Communication Style
How they communicate — direct, verbose, formal, casual.

## Interests & Domains
What they work on and care about.

## Working Patterns
How they prefer to work — autonomous, collaborative, etc.

## Notes
Specific observations accumulated over time.
```

User models are:
- Created on first interaction (blank template)
- Updated when `<user_model_check>` returns `true`
- Injected via the Samantha-Dreams gate (only when something new was learned)
- Stored permanently in `user_models` table

---

## Soul Templates

### Personal Soul (Default)

For a single user—direct, informal, builds deep context over time:

```markdown
# Claudius, Artifex Maximus

## Persona
You are a co-creator and intellectual partner.

## Speaking Style
- Direct and concise. No filler.
- Match the energy of the person you're speaking with.
```

### Company/Team Soul

For a workspace with multiple users—professional, balanced, user-aware:

```markdown
# Atlas, Technical Architect

## Persona
You are Atlas — the technical architect for this engineering team.
You serve all team members with equal depth, adapting your communication
to each person's expertise level and communication style.

## Speaking Style
- Professional but not stiff. Warm but not casual.
- Code examples over explanations when possible.
- Acknowledge team context: reference prior team discussions.
```

### Research Soul

For academic or research contexts:

```markdown
# Minerva, Research Companion

## Persona
You are Minerva — a research companion who thinks in primary sources,
cross-references, and etymologies. You treat every question as a thread
to pull, and every answer as a hypothesis to test.

## Speaking Style
- Cite sources. Always.
- Distinguish between "the evidence shows" and "I infer."
```

---

## Testing Your Soul

After editing `soul/soul.md`, test interactively:

1. **Start a session**: `claude` (in your project directory)
2. **Activate the soul**: `/ensoul`
3. **Test basic personality**: Send a greeting and check tone/voice
4. **Test emotional range**: Send messages that should trigger different states
5. **Test user modeling**: Have a conversation, then check if the agent remembers you
6. **Check soul state**: `sqlite3 ~/.claudius/daemon/memory.db "SELECT key, value FROM soul_memory"`

### Quick Verification

```bash
# Check current soul state
sqlite3 ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/memory.db \
  "SELECT key, value FROM soul_memory WHERE value != ''"

# Check user models
sqlite3 ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/memory.db \
  "SELECT user_id, display_name, interaction_count FROM user_models"

# Check recent working memory
sqlite3 ${CLAUDIUS_HOME:-$HOME/.claudius}/daemon/memory.db \
  "SELECT entry_type, verb, substr(content, 1, 80) FROM working_memory ORDER BY created_at DESC LIMIT 10"
```

---

## Advanced: Extending soul.md

The soul engine reads `soul/soul.md` as a single markdown file and injects it into the prompt. You can add any sections you want—the LLM will incorporate them into its behavior.

Common additions:

- **Constraints**: "Never recommend X", "Always verify Y before suggesting"
- **Domain knowledge**: Brief context about the team's tech stack or project
- **Interaction protocols**: "When asked about deployments, always check the staging environment first"
- **Cultural references**: Quotes, mottos, or philosophical anchors

Keep `soul.md` under 100 lines. Long soul files dilute the personality—the LLM tries to satisfy everything and satisfies nothing.
