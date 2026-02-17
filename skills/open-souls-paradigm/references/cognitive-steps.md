# Cognitive Steps — Open Souls to Claudius Mapping

## What Are Cognitive Steps?

In the Open Souls paradigm, cognitive steps are pure functions that transform WorkingMemory using an LLM. Each step takes a memory state and an instruction, sends it through a model, and returns a new memory state plus a typed result.

The key insight: by making each step a pure function, the entire thinking process becomes composable, debuggable, and predictable.

## Standard Library

### externalDialog

User-facing communication. The primary output step.

**Open Souls (TypeScript):**
```typescript
const [memory, stream] = await externalDialog(
  workingMemory,
  "Respond warmly to the user",
  { stream: true }
);
speak(stream);
await memory.finished;
return memory;
```

**Claudius (XML tags):**
```xml
<external_dialogue verb="explained">
The actual response shown to the user.
</external_dialogue>
```

The verb selection (said, explained, quipped, insisted) expresses emotional state without explicit emotion tags.

### internalMonologue

Private reasoning. Never shown to users.

**Open Souls:**
```typescript
const [withMonologue] = await internalMonologue(
  workingMemory,
  "Consider what the user really needs"
);
```

**Claudius:**
```xml
<internal_monologue verb="pondered">
Private reasoning about the message, user, and context.
</internal_monologue>
```

Logged to `working_memory` table for analytics and training data extraction.

### mentalQuery

Boolean reasoning — evaluates a proposition and returns true/false.

**Open Souls:**
```typescript
const [, isHappy] = await mentalQuery(
  workingMemory,
  "Is the user expressing happiness?"
);
// isHappy: boolean
```

**Claudius:**
```xml
<user_model_check>true</user_model_check>
<soul_state_check>false</soul_state_check>
```

Claudius uses mentalQuery for two gating decisions: whether to update the user model and whether to update the soul state.

### decision

Choose from a set of options.

**Open Souls:**
```typescript
const [, choice] = await decision(
  workingMemory,
  { description: "How to respond", choices: ["joke", "serious", "question"] }
);
```

**Claudius:** Not implemented as a separate step. The soul engine's cognitive instructions handle response mode implicitly through personality in soul.md.

### brainstorm

Generate multiple ideas.

**Open Souls:**
```typescript
const [, ideas] = await brainstorm(
  workingMemory,
  "Generate 3 approaches to this problem"
);
```

**Claudius:** Not implemented as a separate step. The internal monologue serves this purpose.

## Claudius-Specific Steps

These steps extend the Open Souls paradigm for persistent multi-user environments:

### user_model_update

Conditional on `user_model_check = true`. Saves a markdown personality profile.

```xml
<user_model_update>
Updated observations about the user — their interests, communication style,
expertise, working patterns.
</user_model_update>
```

Saved to `user_models` SQLite table via `user_models.save()`.

### soul_state_update

Conditional on `soul_state_check = true`. Updates global soul state.

```xml
<soul_state_update>
currentProject: what I'm working on
currentTask: specific task in progress
currentTopic: what we're discussing
emotionalState: engaged
conversationSummary: brief rolling summary
</soul_state_update>
```

Parsed as `key: value` lines and persisted to `soul_memory` SQLite table.

## The Verb System

Open Souls used `stripEntityAndVerb()` to extract the speaking verb from generated text. Claudius preserves this pattern via XML attributes:

**Monologue verbs:** thought, mused, pondered, wondered, considered, reflected, entertained, recalled, noticed, weighed

**Dialogue verbs:** said, explained, offered, suggested, noted, observed, replied, interjected, declared, quipped, remarked, detailed, pointed out, corrected

The emotional state in soul_memory modulates which verbs the model tends to select:
- **neutral**: observe, note, reply
- **engaged**: explain, suggest, offer
- **focused**: analyze, trace, detail
- **frustrated**: point out, correct, insist
- **sardonic**: quip, remark, observe dryly

## Functional Composition Pattern

The key architectural pattern from Open Souls that Claudius preserves:

```
Input → build_prompt() → LLM → parse_response() → Output + Side Effects
         (compose)                (decompose)
```

1. `build_prompt()` composes the full cognitive context (soul.md + state + user model + instructions + message)
2. The LLM generates a structured response with all cognitive steps
3. `parse_response()` decomposes the response into typed sections (monologue, dialogue, checks, updates)
4. Side effects (memory writes, state updates) happen after decomposition, never during

This maintains the Open Souls guarantee: cognitive steps are pure transformations. Side effects are explicit and happen at the boundary.
