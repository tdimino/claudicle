---
title: "Plans"
directory: plans/
created: 2026-02-19
description: "Development plans preserved to document how the project evolved"
subfolders:
  - 01-architecture (3 plans)
  - 02-features (2 plans)
---

# Plans

Development plans for Claudicle, preserved to document how the project evolved. Each plan captures what was proposed, what was actually built, and where the two diverged.

Plans are the raw architectural thinking behind each major feature—research findings, trade-off analyses, implementation sequences. By keeping them alongside the code, anyone can trace *why* the codebase looks the way it does, not just *what* it contains.

Each plan has YAML frontmatter recording its implementation status, the commits that realized it, and any deviations from the original design.

---

## 01-architecture/

Structural refactors and system design decisions.

| Plan | Date | Status | Notable Commits |
|------|------|--------|-----------------|
| [Cognitive Pipeline Research](01-architecture/cognitive-pipeline-research.md) | 2026-02-18 | Implemented | `203332f` |
| [Modular Extraction + Structured Logging](01-architecture/modular-extraction-structured-logging.md) | 2026-02-18 | Implemented | `203332f`, `1f5cba4` |
| [Soul Stream Three-Log Architecture](01-architecture/soul-stream-three-log.md) | 2026-02-18 | Implemented | `1f5cba4` |

## 02-features/

New capabilities added to the daemon.

| Plan | Date | Status | Notable Commits |
|------|------|--------|-----------------|
| [Multi-Speaker Awareness](02-features/multi-speaker-awareness.md) | 2026-02-19 | Implemented | Uncommitted |
| [First Ensoulment + Primary User](02-features/first-ensoulment-onboarding.md) | 2026-02-19 | Implemented | Uncommitted |

---

## Reading the Frontmatter

Every plan file begins with YAML frontmatter:

```yaml
---
title: "Feature Name"
date: 2026-02-18
status: implemented          # implemented | partial | deferred | superseded
implemented_in:              # commits that realized the plan
  - "abc1234 commit message"
changes_from_plan:           # where reality diverged from the blueprint
  - "Phase 3 deferred—not needed at current complexity"
---
```

`changes_from_plan` is the most valuable field. It records the gap between intention and execution—the decisions made *during* implementation that the plan couldn't anticipate.
