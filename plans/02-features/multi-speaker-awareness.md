---
title: "Multi-Speaker Awareness"
date: 2026-02-19
status: implemented
implemented_in:
  - "Uncommitted — implemented in same session as onboarding features"
changes_from_plan:
  - "DEFAULT_USER_NAME set to 'Human' (not 'User') for onboarding detection"
  - "parse_frontmatter() uses simple string parsing instead of PyYAML import"
  - "onboardingComplete field added to frontmatter (not in original plan)"
  - "get_display_name() renamed to get_user_name() for clarity"
---

# Claudicle Daemon: Multi-Speaker Awareness

**Date**: 2026-02-19

## Summary

Made Claudicle aware of all speakers in a thread—each message attributed to the correct display name, user models for active participants available in context, YAML frontmatter in user model templates.

## Key Changes

1. `display_name` column in working memory (per-speaker attribution)
2. `format_for_prompt()` shows "Tom said:" instead of "User said:"
3. Multi-speaker user model injection in `context.py`
4. YAML frontmatter in `_USER_MODEL_TEMPLATE` (userName, userId, type, onboardingComplete)
5. `parse_frontmatter()` and `get_user_name()` in `user_models.py`
6. `DEFAULT_USER_NAME` and `DEFAULT_USER_ID` in `config.py`
7. `store_user_message()` passes display_name through to working memory
