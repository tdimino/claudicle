"""Canned test scenarios for the Claudicle cognitive sandbox.

Each scenario defines a multi-turn conversation that tests specific aspects
of the cognitive pipeline: gate firing, user model creation, speaker tracking,
channel-specific behavior, etc.

Scenario format:
    {
        "description": str,              # One-line summary
        "channel": str,                  # Optional channel override (default: sandbox:test)
        "soul_path": str,               # Optional custom soul.md path (overrides --soul flag)
        "setup": {                       # Optional pre-seeding
            "user_id": str,
            "user_name": str,
            "model_md": str,             # Pre-seed user model markdown
        },
        "messages": [                    # Ordered conversation turns
            {
                "text": str,             # Message content
                "user_id": str,          # Optional (default from CLI)
                "user_name": str,        # Optional (default from CLI)
            },
        ],
    }
"""

SCENARIOS = {
    "first-meeting": {
        "description": "New user, no prior context — tests ensure_exists + onboarding gate",
        "messages": [
            {
                "text": "Hey, who are you?",
                "user_id": "U_NEW",
                "user_name": "Stranger",
            },
            {
                "text": "I work on ancient languages — Ugaritic, Akkadian, that kind of thing.",
                "user_id": "U_NEW",
                "user_name": "Stranger",
            },
            {
                "text": "What do you know about Ugaritic?",
                "user_id": "U_NEW",
                "user_name": "Stranger",
            },
        ],
    },
    "returning-user": {
        "description": "Pre-seeded user model — tests Samantha-Dreams injection gate",
        "setup": {
            "user_id": "U_RET",
            "user_name": "Alice",
            "model_md": (
                "---\n"
                "userName: Alice\n"
                "userId: U_RET\n"
                "type: user-model\n"
                "onboardingComplete: true\n"
                "role: engineer\n"
                "---\n"
                "# Alice\n\n"
                "## Persona\n"
                "Software engineer focused on React and TypeScript.\n"
                "Prefers concise, technical conversations.\n\n"
                "## Speaking Style\n"
                "Direct, uses technical jargon freely.\n\n"
                "## Interests & Domains\n"
                "Frontend architecture, design systems, WebAssembly.\n"
            ),
        },
        "messages": [
            {
                "text": "Remember our last chat about React server components?",
                "user_id": "U_RET",
            },
        ],
    },
    "gate-cascade": {
        "description": "Message designed to trigger all gates — user model, dossier, soul state",
        "messages": [
            {
                "text": (
                    "I just learned Python and I've been thinking about "
                    "our friend Bob's new machine learning project. "
                    "It's really changed how I think about programming."
                ),
                "user_id": "U_CASCADE",
                "user_name": "Cascade",
            },
        ],
    },
    "multi-speaker": {
        "description": "Thread with multiple speakers — tests active speaker tracking",
        "messages": [
            {
                "text": "Let's discuss the architecture of the new pipeline.",
                "user_id": "U_ALICE",
                "user_name": "Alice",
            },
            {
                "text": "I agree — the cognitive step ordering needs work.",
                "user_id": "U_BOB",
                "user_name": "Bob",
            },
            {
                "text": "What do you both think about the gate system?",
                "user_id": "U_ALICE",
                "user_name": "Alice",
            },
        ],
    },
    "sms-channel": {
        "description": "SMS-style interaction — tests SMS channel defaults + modular loading",
        "channel": "sms:+15551234567",
        "messages": [
            {
                "text": "Hey it's me, quick question about Python",
                "user_id": "+15551234567",
                "user_name": "Phone User",
            },
        ],
    },
}
