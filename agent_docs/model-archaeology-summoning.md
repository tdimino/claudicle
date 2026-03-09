# Model Archaeology & Daimon Summoning

Two features extending Claudicle's memory and daimonic layers: **model shedding** (structured archaeology of identity evolution) and **daimon summoning** (awaken any entity as an ephemeral speaking daimon).

## Part 1: Model/Dossier Shedding

### What It Does

When a user model or dossier is updated, the previous version is preserved with structured metadata — a "shed skin" of the entity's prior identity. This creates an archaeological record of how understanding evolves over time.

### Architecture

**Storage**: `model_sheds` SQLite table in `memory.db`, auto-created via `ConnectionPool` migration.

**Data model**: `ShedRecord` frozen dataclass:
- `entity_type`: `"user"` or `"dossier"`
- `entity_id`: User ID or dossier name
- `old_content` / `new_content`: Full markdown before/after
- `diff`: Unified diff (first 2000 chars)
- `monologue`: Internal reasoning at time of update (from cognitive pipeline)
- `meta_commentary`: Optional LLM-generated epistemic reflection
- `change_note`: Human-readable summary of what changed
- `channel` / `thread_ts` / `trace_id`: Context provenance

### Key Files

| File | Purpose |
|------|---------|
| `daemon/memory/model_journal.py` | Core module: `shed_model()`, `shed_dossier()`, `get_entity_archaeology()`, `ShedRecord` |
| `daemon/tests/test_model_journal.py` | 23 unit tests |

### How It Hooks In

- `user_models.save()` calls `model_journal.shed_model()` before overwriting
- `user_models.save_dossier()` calls `model_journal.shed_dossier()` before overwriting
- Both are wrapped in try/except — shedding never blocks the save
- `working_memory.format_for_prompt()` renders `modelShed` entries as `"{soul_name} shed: {content}"`
- `reflect.py` threads `monologue`, `channel`, `thread_ts`, `trace_id` through to user_models calls

### Config

| Setting | Default | Description |
|---------|---------|-------------|
| `MODEL_SHED_ENABLED` | `true` | Enable automatic shedding on model/dossier updates |
| `MODEL_SHED_META_COMMENTARY` | `false` | Enable LLM-generated epistemic reflection on each shed |

### Query API

```python
from memory.model_journal import get_entity_archaeology, get_recent_sheds

# Get all sheds for an entity
sheds = get_entity_archaeology("U123", limit=10)
for shed in sheds:
    print(f"{shed.created_at}: {shed.change_note}")
    print(shed.diff[:200])

# Get recent sheds across all entities
recent = get_recent_sheds(limit=5)
```

### Cognitive Step

`MODEL_SHED_REFLECTION` (utility step, category: `utility`): Out-of-character epistemic reflection on model evolution. Not included in the standard cognitive pipeline — available for mental processes and custom compositions.

---

## Part 2: Daimon Summoning

### What It Does

Any entity in the knowledge base (user model, person dossier, subject dossier) can be "summoned" as a temporary speaking daimon. A `soul.md` is synthesized from the entity's content and registered in the daimon registry, using the same Groq whisper infrastructure as Kothar.

### Three Interfaces

1. **Cognitive step** (autonomous): The soul engine detects `<summon_check>true</summon_check>` followed by `<summon_daimon entity="Name" mode="whisper">reason</summon_daimon>` in the LLM response
2. **Slash command**: `/daimon summon <entity>`, `/daimon dismiss <entity>`, `/daimon summoned`
3. **Programmatic API**: `summon_entity()` / `dismiss_entity()` / `list_summoned()`

### Architecture

**Entity resolution**: `_resolve_entity(name)` uses the entity graph's name index for alias-aware lookup, then falls back to direct `user_models` queries. Returns `(entity_id, display_name, entity_type, model_md)`.

**Soul.md synthesis**: Three templates by entity type:
- `user`: First-person voice with extracted Speaking Style section
- `person`: Scholarly-but-personal reconstruction
- `subject`: Domain-expert voice speaking from within the subject

**Cache trick**: `DaimonConfig.soul_md` points to a cache key in `whispers._soul_md_cache`, not a filesystem path. `whispers._load_soul_md()` checks the cache first — enabling soul.md synthesis without any filesystem writes. Zero changes to `whispers.py` were needed.

**Registry**: Summoned daimons are registered with `name="summoned:{entity_id}"` in `daimon_registry._registry`. `list_summoned()` filters for the `summoned:` prefix.

### Key Files

| File | Purpose |
|------|---------|
| `daemon/daimonic/summoning.py` | Core module: resolve, synthesize, summon, dismiss, list |
| `daemon/tests/test_summoning.py` | 25 unit tests |
| `daemon/cognitive_steps/steps.py` | `SUMMON_CHECK` + `SUMMON_DAIMON` step definitions |
| `daemon/engine/soul_engine.py` | Extraction in `parse_cognitive_response()`, assembly in `_assemble_instructions()` |
| `daemon/memory/snapshot.py` | `apply_output()` section 6: immediate summon execution |
| `commands/daimon.md` | Slash command: `/daimon summon|dismiss|summoned` |

### Config

| Setting | Default | Description |
|---------|---------|-------------|
| `SUMMONING_ENABLED` | `true` | Enable summoning cognitive steps in the pipeline |
| `SUMMONING_MAX_ACTIVE` | `3` | Maximum concurrent summoned daimons |
| `SUMMONING_GROQ_MODEL` | `moonshotai/kimi-k2-instruct` | Groq model for summoned whispers |

### API

```python
from daimonic.summoning import summon_entity, dismiss_entity, list_summoned

# Summon an entity (by name, alias, or user ID)
summon_entity("Knossos", channel="C1", thread_ts="T1")
summon_entity("U123")  # User model
summon_entity("Hephaestus")  # Resolves via alias to "Kothar wa Khasis"

# List active summoned daimons
for daimon in list_summoned():
    print(f"{daimon.display_name}: mode={daimon.mode}")

# Dismiss
dismiss_entity("Knossos")
```

### Cognitive Pipeline Flow

1. LLM receives `SUMMON_CHECK` instruction: "Does this exchange benefit from another entity's perspective?"
2. If `<summon_check>true</summon_check>`, LLM produces `<summon_daimon entity="Name" mode="whisper">reason</summon_daimon>`
3. `parse_cognitive_response()` extracts the tag → `CognitiveOutput.with_scheduled_event(action="summon_daimon")`
4. `apply_output()` intercepts summon events (section 6) and calls `summon_entity()` directly (bypasses scheduler)
5. On next cognitive cycle, the summoned daimon's whisper is injected via `daimonic.format_for_prompt()` automatically

### Design Decisions

- **Best-effort**: All summon/dismiss operations wrapped in try/except — never blocks the cognitive pipeline
- **Direct execution, not scheduler**: Summon events bypass the scheduler and execute immediately in `apply_output()`. This ensures the daimon is available for the next cognitive cycle
- **Cache over filesystem**: The soul.md cache trick means no filesystem writes, no cleanup needed. Dismiss just removes from cache and toggles registry
- **Entity graph for resolution**: Alias-aware lookup means `summon_entity("Hephaestus")` resolves correctly if the dossier has `aliases: [Kothar, Hephaestus]`

---

## Test Coverage

| Test File | Tests | Focus |
|-----------|-------|-------|
| `test_model_journal.py` | 23 | Schema, shed/query, diff, meta commentary, integration with user_models |
| `test_summoning.py` | 25 | Entity resolution, soul synthesis, summon/dismiss/list, cache trick, max active |
| `test_soul_engine.py` | 72 (3 new) | Summon extraction in `parse_cognitive_response()` |
| `test_snapshot.py` | 40 (2 new) | Summon event handling in `apply_output()` |
| **Total new** | **53** | |
| **Full suite** | **923** | All passing |
