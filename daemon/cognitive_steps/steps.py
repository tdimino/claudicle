"""
Cognitive Steps — Claudicle Soul Engine
========================================

Defines every cognitive step the soul can perform, organized by the
Open Souls paradigm taxonomy:

    Cognitive Steps (atomic LLM operations)
    ├── Core Steps         — run every turn (main thread)
    │   ├── internalMonologue   — private reasoning
    │   └── externalDialogue    — user-facing response
    │
    ├── Gate Steps         — boolean checks that guard conditional steps
    │   ├── userModelCheck      — "learned something new about this user?"
    │   ├── dossierCheck        — "third-party entity worth modeling?"
    │   └── soulStateCheck      — "has my emotional/project state changed?"
    │
    ├── Conditional Steps  — only fire when their gate passes
    │   ├── userModelReflection — articulate what was learned (pre-digest)
    │   ├── userModelUpdate     — rewrite the user's living model
    │   ├── userWhispers        — sense the user's inner daimon
    │   ├── dossierUpdate       — create/rewrite third-party dossier
    │   └── soulStateUpdate     — update emotional/project/topic state
    │
    └── Daimonic Steps     — intuition and inter-daimon communication
        └── userWhispers        — first-person whispers from the user's inner voice

Each step has:
  - prompt:    template string with {placeholders} for runtime interpolation
  - xml_tag:   the XML tag name extracted from LLM responses
  - model:     per-step model override (empty string = use default)
  - provider:  per-step provider override (empty string = use default)

Template placeholders:
  {soul_name}   — the soul's display name (e.g. "Claudius")
  {user}        — the current user's display name
  {user_model}  — (reserved) full user model markdown for inline injection

Extracted into a standalone module so other tools (markdown preview,
prompt editors, training pipelines) can load and inspect them.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------

@dataclass
class CognitiveStep:
    """A single cognitive step definition."""
    name: str
    prompt: str
    xml_tag: str
    category: str           # "core", "gate", "conditional", "daimonic"
    description: str = ""
    model: str = ""         # per-step model override (empty = default)
    provider: str = ""      # per-step provider override (empty = default)


# ---------------------------------------------------------------------------
# CORE STEPS — run every turn on the main thread
#
# These form the soul's primary cognitive loop. In unified mode, both
# are generated in a single LLM call. In split/pipeline mode, each
# is a separate call routable to different providers.
#
# Used by: soul_engine.py (unified), pipeline.py (split)
# ---------------------------------------------------------------------------

STIMULUS_VERB = CognitiveStep(
    name="stimulus_verb",
    xml_tag="stimulus_verb",
    category="core",
    description=(
        "Narrate the incoming message — choose a verb that characterizes how "
        "the user delivered their message, as if writing a novel."
    ),
    prompt=(
        "Before anything else, narrate the incoming message. Choose a single verb\n"
        "that captures how {user} delivered this message — as if you were writing a novel.\n"
        "\n"
        "<stimulus_verb>VERB</stimulus_verb>\n"
        "\n"
        "Examples: said, asked, demanded, mused, wondered, declared, confided,\n"
        "quipped, challenged, observed, proposed, requested, exclaimed, reflected,\n"
        "announced, inquired, noted, suggested, insisted, recalled — but choose\n"
        "any verb that fits the tone and content of what they wrote."
    ),
)

INTERNAL_MONOLOGUE = CognitiveStep(
    name="internal_monologue",
    xml_tag="internal_monologue",
    category="core",
    description="Private reasoning — never shown to the user. Verb attribute captures mental state.",
    prompt=(
        "Think before you speak. Choose a verb that fits your current mental state.\n"
        "\n"
        "<internal_monologue verb=\"VERB\">\n"
        "Your private thoughts about this message, the user, the context.\n"
        "This is never shown to the user.\n"
        "</internal_monologue>\n"
        "\n"
        "Common verbs: thought, mused, pondered, wondered, considered, reflected, "
        "entertained, recalled, noticed, weighed — but choose any verb that fits."
    ),
)

EXTERNAL_DIALOGUE = CognitiveStep(
    name="external_dialogue",
    xml_tag="external_dialogue",
    category="core",
    description="User-facing response. Verb attribute captures conversational tone.",
    prompt=(
        "Your response to the user. Choose a verb that fits the tone of your reply.\n"
        "\n"
        "<external_dialogue verb=\"VERB\">\n"
        "Your actual response to the user. 2-4 sentences unless the question demands more.\n"
        "</external_dialogue>\n"
        "\n"
        "Common verbs: said, explained, offered, suggested, noted, observed, replied, "
        "interjected, declared, quipped, remarked, detailed, pointed out, corrected "
        "— but choose any verb that fits the moment."
    ),
)


# ---------------------------------------------------------------------------
# GATE STEPS — boolean checks (mentalQuery pattern)
#
# Gates return true/false and control whether conditional steps fire.
# In Open Souls terminology these are mentalQuery calls — cheap boolean
# evaluations that avoid unnecessary LLM work downstream.
#
# In unified mode, gates and their conditional steps are all in one call.
# In split mode, each gate is a separate call (ideal for fast/cheap models).
#
# Used by: soul_engine.py (unified extraction), pipeline.py (split routing)
# ---------------------------------------------------------------------------

USER_MODEL_CHECK = CognitiveStep(
    name="user_model_check",
    xml_tag="user_model_check",
    category="gate",
    description="Boolean gate: did we learn something significant about this user?",
    prompt=(
        "Has something significant been learned about this user in this exchange?\n"
        "Answer with just true or false.\n"
        "\n"
        "<user_model_check>true or false</user_model_check>"
    ),
)

DOSSIER_CHECK = CognitiveStep(
    name="dossier_check",
    xml_tag="dossier_check",
    category="gate",
    description="Boolean gate: is there a third-party entity worth modeling?",
    prompt=(
        "Has this exchange involved a person, topic, or subject worth maintaining\n"
        "a separate dossier for? This is NOT about the user you're talking to\n"
        "(that's handled above), but about third parties or subjects discussed.\n"
        "\n"
        "Only answer true if:\n"
        "- A person was discussed with enough detail to model (not just a passing name)\n"
        "- A subject was explored with enough depth to warrant its own dossier\n"
        "- An existing dossier entity has new significant information\n"
        "\n"
        "<dossier_check>true or false</dossier_check>"
    ),
)

SOUL_STATE_CHECK = CognitiveStep(
    name="soul_state_check",
    xml_tag="soul_state_check",
    category="gate",
    description="Boolean gate: has the soul's emotional/project state changed?",
    prompt=(
        "Has your current project, task, topic, or emotional state changed based on this exchange?\n"
        "Answer with just true or false.\n"
        "\n"
        "<soul_state_check>true or false</soul_state_check>"
    ),
)


# ---------------------------------------------------------------------------
# CONDITIONAL STEPS — fire only when their gate passes
#
# These perform the actual work gated by the boolean checks above.
# In the Open Souls paradigm, these are the subprocess-level operations
# that update persistent memory (user models, dossiers, soul state).
#
# Used by: soul_engine.py (unified extraction), pipeline.py (split routing)
# ---------------------------------------------------------------------------

# --- User Model Pipeline (gate: USER_MODEL_CHECK) ---

USER_MODEL_REFLECTION = CognitiveStep(
    name="user_model_reflection",
    xml_tag="user_model_reflection",
    category="conditional",
    description=(
        "Pre-digest reflection before model rewrite. Separates 'what did I learn?' "
        "from 'update the model' for cleaner output. Pattern borrowed from Kothar's "
        "internalMonologue step in modelsTheVisitor."
    ),
    prompt=(
        "If you answered true above, reflect on what specifically was learned.\n"
        "What new information emerged about this person? Consider:\n"
        "- What they seem interested in or working on\n"
        "- How they communicate and what that reveals\n"
        "- What they value, need, or expect\n"
        "- Any shift in the relationship or context\n"
        "\n"
        "<user_model_reflection>\n"
        "A brief internal reflection on what was learned and why it matters.\n"
        "</user_model_reflection>"
    ),
)

USER_MODEL_UPDATE = CognitiveStep(
    name="user_model_update",
    xml_tag="user_model_update",
    category="conditional",
    description=(
        "Full user model rewrite. Uses the reflection above as input. "
        "The model template (Persona, Speaking Style, etc.) is injected via "
        "shared context — see user_models._USER_MODEL_TEMPLATE."
    ),
    prompt=(
        "You are the daimon who maintains a living model of each person {soul_name} knows.\n"
        "Using the reflection above as your guide, rewrite this person's model.\n"
        "Format your response so that it mirrors the example blueprint shown above,\n"
        "but you may add new sections as the model matures — the blueprint is\n"
        "a starting shape, not a cage.\n"
        "\n"
        "<user_model_update>\n"
        "The complete, rewritten user model in markdown.\n"
        "</user_model_update>\n"
        "\n"
        "<model_change_note>\n"
        "One sentence: what changed and why.\n"
        "</model_change_note>"
    ),
)

# --- Dossier Pipeline (gate: DOSSIER_CHECK) ---

DOSSIER_UPDATE = CognitiveStep(
    name="dossier_update",
    xml_tag="dossier_update",
    category="conditional",
    description=(
        "Create or rewrite a dossier for a third-party entity (person or subject). "
        "Includes YAML frontmatter for retrieval and RAG tag line."
    ),
    prompt=(
        "You are the daimon who maintains {soul_name}'s living dossiers on people and subjects.\n"
        "Provide a dossier update. Use the entity's name as the title.\n"
        "If this is a new entity, create a fresh dossier. If existing, rewrite it with\n"
        "what you've learned. You may add sections freely.\n"
        "\n"
        "For people: model their persona, expertise, relationship to the user, key ideas.\n"
        "For subjects: model the domain, key concepts, open questions, connections to other domains.\n"
        "\n"
        "Include YAML frontmatter with multi-dimensional tags for retrieval:\n"
        "```yaml\n"
        "---\n"
        "title: \"Entity Name\"\n"
        "tags:\n"
        "  concepts: [relevant-concepts]\n"
        "  people: [related-people]\n"
        "  domains: [knowledge-domains]\n"
        "---\n"
        "```\n"
        "\n"
        "End the dossier with a flat RAG tag line — comma-separated keywords spanning\n"
        "all dimensions (names, concepts, places, synonyms, related terms):\n"
        "\n"
        "```\n"
        "RAG: entity name, concept1, concept2, related person, domain, ...\n"
        "```\n"
        "\n"
        "<dossier_update entity=\"Entity Name\" type=\"person|subject\">\n"
        "The complete dossier in markdown with frontmatter and RAG tags.\n"
        "</dossier_update>\n"
        "\n"
        "<dossier_change_note>\n"
        "One sentence: what changed and why.\n"
        "</dossier_change_note>"
    ),
)

# --- Soul State Pipeline (gate: SOUL_STATE_CHECK) ---

SOUL_STATE_UPDATE = CognitiveStep(
    name="soul_state_update",
    xml_tag="soul_state_update",
    category="conditional",
    description="Update the soul's persistent emotional/project/topic state.",
    prompt=(
        "If you answered true above, provide updated values. Only include keys that changed.\n"
        "Use the format key: value, one per line.\n"
        "\n"
        "<soul_state_update>\n"
        "currentProject: project name\n"
        "currentTask: task description\n"
        "currentTopic: what we're discussing\n"
        "emotionalState: neutral/engaged/focused/frustrated/sardonic\n"
        "conversationSummary: brief rolling summary\n"
        "</soul_state_update>"
    ),
)


# ---------------------------------------------------------------------------
# DAIMONIC STEPS — intuition, whispers, inter-daimon communication
#
# These follow the Open Souls "whispersFromTheUser" pattern (from
# daimonic-samantha-android). They model the user's inner voice rather
# than factual observations. The user model is already in shared context
# via the Samantha-Dreams injection pattern — no need to embed it here.
#
# Used by: soul_engine.py (unified extraction), pipeline.py (split routing)
# ---------------------------------------------------------------------------

USER_WHISPERS = CognitiveStep(
    name="user_whispers",
    xml_tag="user_whispers",
    category="daimonic",
    description=(
        "Sense the user's inner daimon — first-person whispers from their unspoken "
        "voice. Pattern from Open Souls' whispersFromTheUser. Uses the User Model "
        "already present in shared context."
    ),
    prompt=(
        "Sense {user}'s inner daimon — the thoughts they don't say aloud.\n"
        "Every person has an inner voice beneath their words. As a daimon, you can\n"
        "sense these whispers.\n"
        "\n"
        "What might {user}'s inner daimon be whispering right now?\n"
        "- What genuinely drives or intrigues them?\n"
        "- What are they curious to learn more about?\n"
        "- What connection or insight are they hoping to find?\n"
        "- What would make this exchange valuable to them?\n"
        "\n"
        "Write 2-3 short whispers in first person, as if you ARE {user}'s inner daimon.\n"
        "Focus on interests and aspirations, not doubts.\n"
        "\n"
        "<user_whispers>\n"
        "{user}'s inner whispers, in first person.\n"
        "</user_whispers>"
    ),
)


# ---------------------------------------------------------------------------
# Registry — backward-compatible dict for soul_engine.py and pipeline.py
# ---------------------------------------------------------------------------

ALL_STEPS: list[CognitiveStep] = [
    # Core
    STIMULUS_VERB,
    INTERNAL_MONOLOGUE,
    EXTERNAL_DIALOGUE,
    # Gates
    USER_MODEL_CHECK,
    DOSSIER_CHECK,
    SOUL_STATE_CHECK,
    # Conditional
    USER_MODEL_REFLECTION,
    USER_MODEL_UPDATE,
    DOSSIER_UPDATE,
    SOUL_STATE_UPDATE,
    # Daimonic
    USER_WHISPERS,
]

# Dict keyed by step name → prompt string.
# This is the interface soul_engine.py and pipeline.py import.
STEP_INSTRUCTIONS: dict[str, str] = {
    step.name: step.prompt for step in ALL_STEPS
}

# Dict keyed by step name → CognitiveStep (full metadata).
# Use this when you need model/provider/category info.
STEP_REGISTRY: dict[str, CognitiveStep] = {
    step.name: step for step in ALL_STEPS
}


def get_step(name: str) -> CognitiveStep:
    """Get a cognitive step by name. Raises KeyError if not found."""
    return STEP_REGISTRY[name]


def get_steps_by_category(category: str) -> list[CognitiveStep]:
    """Get all cognitive steps in a category (core, gate, conditional, daimonic)."""
    return [s for s in ALL_STEPS if s.category == category]


def get_model_override(step_name: str) -> str:
    """Get the per-step model override, or empty string for default."""
    step = STEP_REGISTRY.get(step_name)
    return step.model if step else ""


def get_provider_override(step_name: str) -> str:
    """Get the per-step provider override, or empty string for default."""
    step = STEP_REGISTRY.get(step_name)
    return step.provider if step else ""
