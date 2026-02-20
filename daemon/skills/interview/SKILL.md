---
name: interview
description: Multi-turn onboarding interview for first ensoulment.
category: core
---

# Interview Skill

First ensoulment interview—when Claudicle meets a new user for the
first time, this skill conducts a warm, conversational interview to:

1. Learn the user's name
2. Build a preliminary user model
3. Let the user define Claudicle's persona for them
4. Select which skills/tools to activate

## Architecture

Follows the Open Souls mental process pattern (state machine):
- Stage 0: Greeting → name extraction
- Stage 1: Persona definition
- Stage 2: Skills selection
- Complete: transition to normal cognitive pipeline

State is tracked in working_memory (entry_type: "onboardingStep")
and user model frontmatter (onboardingComplete: true/false).
