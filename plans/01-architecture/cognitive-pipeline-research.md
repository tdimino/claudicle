---
title: "Cognitive Pipeline Refactoring: Research & Recommendations"
date: 2026-02-18
status: implemented
implemented_in:
  - "203332f feat: extract context.py, add trace_id system"
changes_from_plan:
  - "CognitiveStep dataclass moved to cognitive_steps/steps.py instead of soul_engine.py"
  - "STEP_INSTRUCTIONS re-exported from cognitive_steps module"
  - "Interaction counter unified in context.py via user_models.increment_interaction()"
---

# Claudius Cognitive Pipeline Refactoring: Research & Architectural Recommendations

**Date**: 2026-02-18
**Scope**: Refactoring `daemon/soul_engine.py` (560 LOC) and `daemon/pipeline.py` (359 LOC)---~920 LOC across 2 files with significant duplication in context assembly, instruction strings, and XML parsing.

## Summary

External research across Open Souls Engine, LangGraph, CrewAI, and Confucius SDK (Meta/Harvard) to determine the right refactoring approach for our cognitive pipeline at ~920 LOC scale.

## Key Findings

1. **Every mature framework separates prompt templates, pipeline logic, and response parsing**
2. At our scale (~1K LOC), inline instruction strings + utility functions is correct---over-engineering hurts
3. The Confucius SDK pattern (single orchestrator + thin adapter layer for unified/split modes) maps directly to our problem
4. `context.py` extraction is highest-priority: eliminates duplication, fixes missing daimonic whispers in split mode

## Recommendations Adopted

- **Phase 1**: Extract `daemon/context.py` (~140 LOC shared context assembly)
- **Phase 2**: Consolidate instruction strings into `STEP_INSTRUCTIONS` dict
- **Phase 3**: Decompose `parse_response()` into named handlers
- **Phase 4**: Add `trace_id` system and structured cognitive logging
- **Phase 5**: Unify interaction counters

## References

- Open Souls Engine (TypeScript, 294 stars)
- Confucius SDK (Meta/Harvard, Dec 2025, 54.3% SWE-Bench)
- arXiv 2602.10479 "Evolution of Agentic AI Software Architecture" (Feb 2026)
- arXiv 2509.08182 "XML Prompting as Grammar-Constrained Interaction" (Sep 2025)
