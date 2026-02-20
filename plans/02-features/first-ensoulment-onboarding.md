---
title: "First Ensoulment: Stimulus Verb Toggle + Onboarding + Primary User"
date: 2026-02-19
status: implemented
implemented_in:
  - "Uncommitted — stimulus verb toggle, 4-stage onboarding, primary user designation"
changes_from_plan:
  - "Originally planned as 3-stage onboarding; expanded to 4 stages mid-implementation"
  - "Stage 1 (Primary User) added after initial plan was approved"
  - "PRIMARY_USER_ID config added (not in original plan scope)"
  - "role field added to user model frontmatter"
  - "soul_engine.py stage guards changed from < 3 to < 4"
  - "Onboarding guide rewritten from scratch (was manual interview, now automated)"
tests_added: 5
total_tests: 319
---

# First Ensoulment: Stimulus Verb Toggle + Onboarding + Primary User

**Date**: 2026-02-19

## Summary

Three interconnected features implemented in one session:

### 1. Stimulus Verb Toggle (`STIMULUS_VERB_ENABLED`)
- When disabled, skips the `stimulus_verb` cognitive step entirely
- Working memory defaults to verb "said"
- Reduces LLM output overhead for deployments that don't need verb narration

### 2. First Ensoulment Onboarding (`ONBOARDING_ENABLED`)
- 4-stage automated interview for unknown users:
  - Stage 0: Greeting — learn name (`<user_name>`, `<onboarding_greeting>`)
  - Stage 1: Primary — are you the owner? (`<is_primary>`, `<onboarding_dialogue>`)
  - Stage 2: Persona — define personality (`<persona_notes>`, `<onboarding_dialogue>`)
  - Stage 3: Skills — select tools (`<selected_skills>`, `<onboarding_dialogue>`)
- State machine in `onboarding.py`, prompts in `skills/interview/prompts.py`
- Intercepted at `build_prompt()` and `parse_response()` in soul_engine.py

### 3. Primary User Designation
- `role` field in user model frontmatter (`"primary"` / `"standard"`)
- `PRIMARY_USER_ID` config (defaults to `DEFAULT_SLACK_USER_ID`)
- Auto-assigned by `ensure_exists()` for known Slack users
- Set via onboarding stage 1 for unknown users

## Files Modified

| File | Changes |
|------|---------|
| `daemon/config.py` | `STIMULUS_VERB_ENABLED`, `ONBOARDING_ENABLED`, `PRIMARY_USER_ID` |
| `daemon/engine/soul_engine.py` | Verb toggle, onboarding interception, stage guards |
| `daemon/engine/onboarding.py` | New file — 4-stage state machine (238 LOC) |
| `daemon/memory/user_models.py` | `role` in template, `ensure_exists()` role logic |
| `daemon/skills/interview/prompts.py` | `greeting()`, `primary_check()`, `persona()`, `skills_selection()` |
| `daemon/skills/interview/catalog.py` | Skills catalog discovery |
| `daemon/tests/test_onboarding.py` | 21 tests covering all stages + role assignment |
| `daemon/tests/conftest.py` | `ONBOARDING_ENABLED=False` autouse fixture |
| `docs/onboarding-guide.md` | Full rewrite documenting automated First Ensoulment |
