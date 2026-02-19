# Multi-Provider Model Selection — Extension Pattern

## Open Souls Pattern

The Open Souls Engine supports **per-step model selection**: each cognitive step can specify its own LLM provider and model. This enables cost optimization (cheap models for gates, expensive models for generation) and capability matching (vision models for image analysis, fast models for boolean checks).

### Per-Step Model Override

```typescript
// Fast gate check — cheap model
const [mem1, shouldRespond] = await mentalQuery(
  workingMemory,
  "Should I respond to this message?",
  { model: "gemini-flash" }
);

// Complex reasoning — expensive model
const [mem2, analysis] = await internalMonologue(
  mem1,
  "Deeply analyze the philosophical implications",
  { model: "gpt-4o" }
);

// User-facing response — balanced model
const [mem3, stream] = await externalDialog(
  mem2,
  "Respond thoughtfully",
  { stream: true, model: "kimi-k2" }
);
```

### Strategy: Cost-Optimized Pipeline

```typescript
// Gate: cheap model (0.1x cost)
const [mem, isAngry] = await mentalQuery(workingMemory, "Is user angry?", { model: "gemini-flash" });

// Decision: cheap model (0.1x cost)
const [mem2, approach] = await decision(mem, {
  description: "Response strategy?",
  choices: ["empathize", "redirect", "humor"]
}, { model: "gemini-flash" });

// Generation: expensive model (1x cost)
const [mem3, stream] = await externalDialog(
  mem2, `Respond with ${approach} approach`,
  { stream: true, model: "gpt-4o" }
);
```

**Cost savings**: In a typical pipeline with 3 gate checks + 1 generation, per-step model selection reduces cost by ~60% versus running everything through the expensive model.

### Strategy: Capability Matching

```typescript
// Vision analysis — multimodal model
const [mem, description] = await internalMonologue(
  memoryWithImage,
  "Describe what you see",
  { model: "gpt-4-vision-preview" }
);

// Structured extraction — schema-focused model
const [mem2, data] = await instruction(
  mem,
  "Extract key entities as JSON",
  { model: "gpt-4o" }
);

// Creative writing — creative model
const [mem3, story] = await externalDialog(
  mem2,
  "Tell a story incorporating these elements",
  { model: "claude-sonnet-4-5-20250929" }
);
```

### Error Fallback Pattern

```typescript
try {
  const [mem, response] = await externalDialog(
    workingMemory, "Respond", { stream: true, model: "gpt-4o" }
  );
  speak(response);
  await mem.finished;
} catch (error) {
  log("Primary model failed, falling back");
  const [mem, response] = await externalDialog(
    workingMemory, "Apologize and respond simply",
    { model: "gpt-3.5-turbo" }  // Cheaper, more reliable fallback
  );
  speak(response);
}
```

---

## Current Claudicle Implementation

Claudicle uses a **single model per invocation**. All cognitive steps run in one LLM call:

```
build_prompt() → single Claude call → parse_response()
```

The model is determined by the invocation method:
- **Session Bridge** (`bot.py`, `slack_listen.py`): Uses whatever `claude -p` resolves to (user's default model)
- **Unified Launcher** (`claudicle.py`): Uses the Agent SDK with whatever model the SDK defaults to
- **`/ensoul`**: Uses the session's current model (set via `/model`)

There is **no per-step model routing**. The single-call architecture means all 6 cognitive steps (monologue, dialogue, user model check/update, soul state check/update) are processed by the same model in one pass.

### Where the Model Is Set

- `claude_handler.py:35-55` — `process()` invokes `claude -p` (subprocess, model from CLI default)
- `claude_handler.py:75-139` — `async_process()` invokes `query()` (SDK, model from SDK config)
- `config.py` — No model configuration currently exists

---

## Extension Blueprint

### Goal

Enable per-step model selection so different cognitive steps can use different models. Two approaches:

### Approach 1: Multi-Call Pipeline (Full Flexibility)

Split the single LLM call into separate calls per cognitive step, each with its own model:

```python
# daemon/multi_model.py
"""Per-step model routing for the cognitive pipeline."""

from config import _env

# Per-step model configuration
STEP_MODELS = {
    "internal_monologue": _env("MODEL_MONOLOGUE", "sonnet"),
    "external_dialogue": _env("MODEL_DIALOGUE", "sonnet"),
    "user_model_check": _env("MODEL_GATE", "haiku"),       # Cheap for boolean
    "user_model_update": _env("MODEL_UPDATE", "haiku"),     # Cheap for structured
    "soul_state_check": _env("MODEL_GATE", "haiku"),        # Cheap for boolean
    "soul_state_update": _env("MODEL_UPDATE", "haiku"),     # Cheap for structured
}

async def run_step(step_name: str, prompt: str, invoke_llm: callable) -> str:
    """Run a single cognitive step with its configured model."""
    model = STEP_MODELS.get(step_name, "sonnet")
    return await invoke_llm(prompt, model=model)
```

**Trade-off**: More LLM calls (higher latency, more API round-trips) but enables model specialization and cost optimization. Best for when different steps genuinely need different capabilities.

### Approach 2: Single-Call with Model Override (Pragmatic)

Keep the single-call architecture but allow overriding the model for the entire pipeline:

```python
# config.py additions
CLAUDE_MODEL = _env("MODEL", "sonnet")          # Default model
CLAUDE_MODEL_FAST = _env("MODEL_FAST", "haiku")  # For quick responses

# claude_handler.py — model selection per message context
def _select_model(text: str, channel: str, is_first: bool) -> str:
    """Select model based on message context."""
    if is_first:
        return config.CLAUDE_MODEL  # Full model for first message
    if len(text) < 20:
        return config.CLAUDE_MODEL_FAST  # Fast model for short messages
    return config.CLAUDE_MODEL
```

**Trade-off**: No per-step flexibility, but zero latency increase. Good enough for most use cases.

### Configuration

```python
# config.py additions
CLAUDE_MODEL = _env("MODEL", "sonnet")
CLAUDE_MODEL_FAST = _env("MODEL_FAST", "haiku")
MULTI_MODEL_ENABLED = _env("MULTI_MODEL", "false").lower() == "true"

# Per-step overrides (only used when MULTI_MODEL_ENABLED=true)
STEP_MODELS = {
    "internal_monologue": _env("MODEL_MONOLOGUE", CLAUDE_MODEL),
    "external_dialogue": _env("MODEL_DIALOGUE", CLAUDE_MODEL),
    "user_model_check": _env("MODEL_GATE", CLAUDE_MODEL_FAST),
    "soul_state_check": _env("MODEL_GATE", CLAUDE_MODEL_FAST),
}
```

### Estimated Effort

- **Approach 1**: ~150 LOC new (`multi_model.py`), ~80 LOC modified (`soul_engine.py` split into per-step prompts, `claude_handler.py` multi-call loop)
- **Approach 2**: ~20 LOC modified (`config.py` + `claude_handler.py` model selection)
- Tests: ~40 LOC for model routing logic
