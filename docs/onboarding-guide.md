# Onboarding Guide — First Ensoulment

When Claudicle encounters a new user whose identity is unknown, it conducts an automated 4-stage interview called **First Ensoulment**. This bootstraps a personalized user model before entering the normal cognitive pipeline.

---

## When Onboarding Triggers

Onboarding activates when ALL of these are true:

1. `ONBOARDING_ENABLED` is `true` (default)
2. The user's model has `onboardingComplete: false` in its YAML frontmatter
3. The user's display name is the default (`"Human"`)

**Users who skip onboarding automatically:**
- Slack users with known display names (e.g. from the Slack API). Their models are created with `onboardingComplete: true` and an auto-assigned `role` via `ensure_exists()`.
- Any user whose `onboardingComplete` is already `true`.

---

## The 4 Stages

Each stage uses XML tags for structured LLM output. The soul engine intercepts the normal cognitive pipeline and delegates to `onboarding.build_instructions()` and `onboarding.parse_response()`.

### Stage 0: Greeting — Learn the User's Name

The soul introduces itself and asks for the user's name.

**LLM tags:** `<user_name>`, `<onboarding_greeting>`

**Side effects:**
- Updates `userName` in user model frontmatter
- Updates the model's `# Title` heading
- Records `onboardingStep` with `metadata.stage: 0`

### Stage 1: Primary User — Are You the Owner?

Asks whether this person is the soul's primary user—the one who set it up and shapes its personality over time.

**LLM tags:** `<is_primary>`, `<onboarding_dialogue>`

**Side effects:**
- Sets `role: "primary"` or `role: "standard"` in user model frontmatter
- Records `onboardingStep` with `metadata.stage: 1, metadata.role: "primary"|"standard"`

There is exactly one primary user per soul. The primary user gets deeper model tracking and serves as the soul's anchor relationship.

### Stage 2: Persona — Define the Soul's Personality

Asks what kind of soul the user wants—communication style, expertise, personality traits.

**LLM tags:** `<persona_notes>`, `<onboarding_dialogue>`

**Side effects:**
- Replaces the default `## Persona` section in the user model with LLM-generated notes
- Records `onboardingStep` with `metadata.stage: 2`

### Stage 3: Skills — Select Active Tools

Presents the available skills catalog and asks which ones to activate.

**LLM tags:** `<selected_skills>`, `<onboarding_dialogue>`

**Side effects:**
- Records `onboardingStep` with `metadata.stage: 3`
- Sets `onboardingComplete: true` in user model frontmatter
- Subsequent messages enter the normal cognitive pipeline

---

## Primary User Designation

Every user model has a `role` field in its YAML frontmatter:

| Role | Meaning |
|------|---------|
| `"primary"` | The soul's owner. Matches `PRIMARY_USER_ID` config. |
| `"standard"` | All other users. |

### How Role Is Set

**Automatic (known Slack users):** When `ensure_exists()` creates a user model for a Slack user with a known display name, it checks `user_id == PRIMARY_USER_ID`. If they match, `role: "primary"` is set; otherwise `role: "standard"`.

**Via onboarding (unknown users):** Stage 1 of the interview asks the user directly. The LLM extracts `<is_primary>yes</is_primary>` or `no`, and `_set_role()` updates the frontmatter.

### Configuration

```bash
# Defaults to DEFAULT_SLACK_USER_ID (Tom's Slack ID)
export CLAUDICLE_PRIMARY_USER_ID="U08V7U4MR8B"
```

---

## User Model Frontmatter

After onboarding, a user model's YAML frontmatter looks like:

```yaml
---
userName: "Alice"
userId: "U12345678"
title: "Alice"
createdAt: "2026-02-19"
onboardingComplete: true
role: "primary"
---
```

Key fields:

| Field | Values | Set By |
|-------|--------|--------|
| `onboardingComplete` | `true` / `false` | `ensure_exists()` or onboarding stage 3 |
| `role` | `"primary"` / `"standard"` | `ensure_exists()` or onboarding stage 1 |
| `userName` | display name | `ensure_exists()` or onboarding stage 0 |

---

## State Tracking

Stage progress is tracked via `entry_type="onboardingStep"` entries in working memory:

```json
{
  "entry_type": "onboardingStep",
  "content": "Completed onboarding stage 0",
  "metadata": {"stage": 0, "name": "Alice"}
}
```

`get_stage()` counts completed stages and returns the next one (0–3), or 4 when all are done.

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDICLE_ONBOARDING_ENABLED` | `true` | Master toggle for First Ensoulment |
| `CLAUDICLE_PRIMARY_USER_ID` | `DEFAULT_SLACK_USER_ID` | Soul owner's user ID |

---

## Manual Overrides

**Skip onboarding for a user:**

```sql
-- Set onboardingComplete directly in the database
UPDATE user_models SET model_md = REPLACE(model_md, 'onboardingComplete: false', 'onboardingComplete: true')
WHERE user_id = 'U12345678';
```

**Re-trigger onboarding:**

```sql
UPDATE user_models SET model_md = REPLACE(model_md, 'onboardingComplete: true', 'onboardingComplete: false')
WHERE user_id = 'U12345678';
```

**Disable onboarding entirely:**

```bash
export CLAUDICLE_ONBOARDING_ENABLED=false
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `daemon/engine/onboarding.py` | State machine: `needs_onboarding()`, `get_stage()`, `build_instructions()`, `parse_response()` |
| `daemon/skills/interview/prompts.py` | Per-stage LLM prompts: `greeting()`, `primary_check()`, `persona()`, `skills_selection()` |
| `daemon/skills/interview/catalog.py` | Skills catalog discovery for stage 3 |
| `daemon/engine/soul_engine.py` | Interception points in `build_prompt()` and `parse_response()` |
| `daemon/memory/user_models.py` | User model template with `role` field, `ensure_exists()` |
| `daemon/config.py` | `ONBOARDING_ENABLED`, `PRIMARY_USER_ID` |

---

## Advanced: Manual User Model Interview

Beyond the automated First Ensoulment, you can deepen a user model through a manual interview via Slack DM:

> "Interview me so you can build a detailed model of who I am, how I work, and what I care about. Ask me about my role, technical domains, communication style, working patterns, and interests. Keep going until you have a thorough picture."

The soul engine's user model system will update the profile over time, but an explicit interview accelerates this. After the interview, export the model for use as a persistent userModel:

```bash
# View what Claudicle learned
sqlite3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon/memory.db \
  "SELECT model_md FROM user_models WHERE user_id = 'U12345678'"

# Save as a userModel file for Claude Code
sqlite3 ${CLAUDICLE_HOME:-$HOME/.claudicle}/daemon/memory.db \
  -noheader "SELECT model_md FROM user_models WHERE user_id = 'U12345678'" \
  > ~/.claude/userModels/yourName/yourNameModel.md
```
