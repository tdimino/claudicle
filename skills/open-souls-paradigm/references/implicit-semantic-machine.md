# Implicit Semantic Machine (ISM) — Extension Pattern

## Open Souls Pattern

While cognitive steps handle individual tasks and mental processes provide state-machine control, **Implicit Semantic Machines (ISMs)** give the soul autonomy in decision-making. Instead of a developer-defined sequence of cognitive steps, the soul receives a **playbook** of possible actions and **chooses which to execute**. The loop recurses until the goal is satisfied, max iterations are reached, or an action transitions to a new mental process.

### Mental Processes vs ISMs

| Aspect | Mental Processes | ISMs |
|--------|------------------|------|
| Control | Developer defines exact flow | Soul chooses actions |
| Flexibility | Fixed cognitive step sequence | Dynamic action selection |
| Execution | Predictable, minimal LLM calls | More LLM calls, potentially slower |
| Use case | Precise control needed | Complex autonomous behavior |

### ISM Execution Flow

```
Start → Check Pending Perceptions → (has perception?) → Return
                                   → (no) → Max Loop? → (yes) → Return
                                                       → (no) → Process Playbook
                                                                → Pick Action(s)
                                                                → Execute Handler(s)
                                                                → Recurse → Start
```

### Three Components

1. **Goal** — What the soul is trying to achieve (clear, concise)
2. **Playbook** — Guidelines to ground and guide decisions
3. **Actions** — Discrete choices the soul can make

### Implementation

```typescript
const result = await implicitSemanticMachine({
  workingMemory,
  internalMemory: workingMemory,
  goal: "Understand the problem the user has, and help solve it",
  actions: [
    {
      name: "Think",
      description: "Think about the problem and access necessary knowledge",
      handleActionUse: async (workingMemory, internalMemory, recurse) => {
        const [withThought] = await internalMonologue(
          workingMemory,
          "Think about the problem deeply"
        );
        return recurse({ workingMemory: withThought, internalMemory: withThought });
      }
    },
    {
      name: "Respond",
      description: "Share findings with the user",
      handleActionUse: async (workingMemory, internalMemory, recurse) => {
        const [mem, stream] = await externalDialog(
          workingMemory, "Respond to the user", { stream: true }
        );
        speak(stream);
        await mem.finished;
        return mem;  // Returning memory (not recurse) ends the loop
      }
    },
    {
      name: "Escalate",
      description: "Problem requires specialist — escalate",
      handleActionUse: async (workingMemory, internalMemory, recurse) => {
        return [workingMemory, expertProcess, { executeNow: true }];
      }
    }
  ],
  playbook: "Solve the user's problem step by step",
});
```

### Key Behaviors

- Creates a memory region with the playbook
- Maintains internal memory to track decisions (prevents action loops)
- Recursively runs until goal satisfied, max loops, or action returns new process
- Actions can call `recurse()` to continue the loop, or return memory to end it

### Hybrid Architecture

ISMs and mental processes work together — structured phases (greeting, closing) use mental processes, while open-ended phases (problem-solving, exploration) use ISMs:

```
Mental Process (structured) → ISM (autonomous) → Mental Process (structured)
```

---

## Current Claudius Implementation

Claudius has **no ISM equivalent**. The cognitive pipeline is a fixed sequence: `build_prompt() → LLM → parse_response()`. The soul has no autonomy in choosing which cognitive steps to execute — the developer defines the exact sequence in `_COGNITIVE_INSTRUCTIONS`.

The closest analog is the `emotionalState` modulating verb selection, but this doesn't change the step sequence or give the soul decision-making authority over its own cognitive process.

---

## Extension Blueprint

### Goal

Add an ISM module that can be invoked from a mental process when autonomous behavior is needed. This is the most ambitious extension — it requires multiple LLM calls per turn and a recursive execution loop.

### New Module: `daemon/ism.py`

```python
"""Implicit Semantic Machine — autonomous action selection loop."""

import json
import logging
from typing import Callable, Optional

log = logging.getLogger("slack-daemon.ism")

class Action:
    def __init__(self, name: str, description: str,
                 handler: Callable):
        self.name = name
        self.description = description
        self.handler = handler

class ISMResult:
    def __init__(self, response: Optional[str] = None,
                 next_process: Optional[str] = None):
        self.response = response
        self.next_process = next_process

async def run_ism(
    prompt_context: str,
    goal: str,
    playbook: str,
    actions: list[Action],
    invoke_llm: Callable,
    max_loops: int = 5,
    check_interrupt: Optional[Callable] = None,
) -> ISMResult:
    """Run ISM loop until goal met, max loops, or interrupt."""
    internal_log = []
    result = ISMResult()

    for loop_idx in range(max_loops):
        # Check for interruption (new perception)
        if check_interrupt and check_interrupt():
            log.info(f"ISM interrupted at loop {loop_idx}")
            break

        # Build action selection prompt
        action_list = "\n".join(
            f"- **{a.name}**: {a.description}"
            for a in actions
        )
        selection_prompt = f"""
{prompt_context}

## Goal
{goal}

## Playbook
{playbook}

## Available Actions
{action_list}

## Internal Log
{chr(10).join(internal_log) if internal_log else "(first iteration)"}

Choose one or more actions to take. Respond with JSON:
{{"actions": ["ActionName1", "ActionName2"], "reasoning": "why"}}

If the goal is satisfied, respond with:
{{"actions": ["DONE"], "reasoning": "goal achieved because..."}}
"""
        # Ask LLM to pick actions
        raw = await invoke_llm(selection_prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"ISM: Failed to parse action selection: {raw[:200]}")
            break

        chosen = parsed.get("actions", [])
        reasoning = parsed.get("reasoning", "")
        internal_log.append(f"Loop {loop_idx}: chose {chosen} — {reasoning}")

        if "DONE" in chosen:
            log.info(f"ISM: Goal satisfied at loop {loop_idx}")
            break

        # Execute chosen actions
        action_map = {a.name: a for a in actions}
        for action_name in chosen:
            action = action_map.get(action_name)
            if not action:
                log.warning(f"ISM: Unknown action '{action_name}'")
                continue

            handler_result = await action.handler(prompt_context, internal_log)
            if isinstance(handler_result, ISMResult):
                result = handler_result
                if result.next_process:
                    return result  # Process transition ends ISM

    return result
```

### Usage from a Mental Process

```python
# daemon/processes/problem_solving.py
from ism import run_ism, Action, ISMResult

COGNITIVE_STEPS = ["internal_monologue", "external_dialogue"]

async def run_ism_phase(prompt_context, invoke_llm, check_interrupt):
    """ISM for autonomous problem-solving."""
    actions = [
        Action(
            "Think",
            "Reason about the problem internally",
            handler=_think_handler,
        ),
        Action(
            "Research",
            "Search codebase or documentation for relevant information",
            handler=_research_handler,
        ),
        Action(
            "Respond",
            "Share findings with the user",
            handler=_respond_handler,
        ),
    ]

    return await run_ism(
        prompt_context=prompt_context,
        goal="Understand and help solve the user's problem",
        playbook="Ask clarifying questions if needed, research before responding, be thorough",
        actions=actions,
        invoke_llm=invoke_llm,
        max_loops=5,
        check_interrupt=check_interrupt,
    )
```

### When to Use ISMs vs Fixed Pipeline

**Use the fixed pipeline (default)** when:
- Response time matters (1 LLM call vs N)
- The cognitive sequence is well-defined
- API cost is a concern

**Use ISMs** when:
- The soul needs to decide its own approach
- Complex multi-step tasks with branching logic
- Goal-oriented behavior where steps are unknown upfront
- Research and exploration tasks

### Configuration

```python
# config.py
ISM_MAX_LOOPS = int(_env("ISM_MAX_LOOPS", "5"))
ISM_ENABLED = _env("ISM_ENABLED", "false").lower() == "true"
```

### Estimated Effort

- New file: `daemon/ism.py` (~120 LOC)
- New process: `daemon/processes/problem_solving.py` (~80 LOC)
- Modified: `claude_handler.py` — add ISM invocation path (~20 lines)
- Modified: `config.py` — add ISM settings
- Tests: ~100 LOC (loop termination, action selection, interrupt)
