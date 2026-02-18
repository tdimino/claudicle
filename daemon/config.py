"""
Claudius daemon configuration.

All settings can be overridden via environment variables prefixed with CLAUDIUS_.
Legacy SLACK_DAEMON_ prefix also supported for backward compatibility.
"""

import os


def _env(key, default):
    """Read env var with CLAUDIUS_ prefix, falling back to SLACK_DAEMON_."""
    return os.environ.get(f"CLAUDIUS_{key}",
           os.environ.get(f"SLACK_DAEMON_{key}", default))


# Claudius home directory
CLAUDIUS_HOME = os.environ.get("CLAUDIUS_HOME", os.path.expanduser("~/.claudius"))

# Channel filtering
ALLOWED_CHANNELS = None  # None = all channels bot is in
BLOCKED_CHANNELS: set = set()  # Channel IDs to never respond in

# Response limits
MAX_RESPONSE_LENGTH = 3000  # Slack message limit ~4000 chars; leave headroom

# Claude Code invocation
CLAUDE_TIMEOUT = int(_env("TIMEOUT", "120"))
CLAUDE_CWD = os.path.expanduser(_env("CWD", "~"))
CLAUDE_ALLOWED_TOOLS = _env("TOOLS", "Read,Glob,Grep,Bash,WebFetch")

# Session expiry
SESSION_TTL_HOURS = int(_env("SESSION_TTL", "24"))

# Soul engine
SOUL_ENGINE_ENABLED = _env("SOUL_ENGINE", "true").lower() == "true"
WORKING_MEMORY_WINDOW = int(_env("MEMORY_WINDOW", "20"))
USER_MODEL_UPDATE_INTERVAL = int(_env("USER_MODEL_INTERVAL", "5"))
WORKING_MEMORY_TTL_HOURS = int(_env("MEMORY_TTL", "72"))
SOUL_STATE_UPDATE_INTERVAL = int(_env("SOUL_STATE_INTERVAL", "3"))

# Terminal session (unified launcher)
TERMINAL_SESSION_TOOLS = _env(
    "TERMINAL_TOOLS", "Read,Glob,Grep,Bash,WebFetch,Edit,Write"
)
TERMINAL_SOUL_ENABLED = _env("TERMINAL_SOUL", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------
DEFAULT_PROVIDER = _env("PROVIDER", "claude_cli")
DEFAULT_MODEL = _env("MODEL", "")
PIPELINE_MODE = _env("PIPELINE_MODE", "unified")  # "unified" | "split"

# Per-step overrides (only when PIPELINE_MODE=split)
STEP_PROVIDER = {
    "internal_monologue": _env("PROVIDER_MONOLOGUE", ""),
    "external_dialogue":  _env("PROVIDER_DIALOGUE", ""),
    "user_model_check":   _env("PROVIDER_GATE", ""),
    "soul_state_check":   _env("PROVIDER_GATE", ""),
    "user_model_update":  _env("PROVIDER_UPDATE", ""),
    "soul_state_update":  _env("PROVIDER_UPDATE", ""),
}
STEP_MODEL = {
    "internal_monologue": _env("MODEL_MONOLOGUE", ""),
    "external_dialogue":  _env("MODEL_DIALOGUE", ""),
    "user_model_check":   _env("MODEL_GATE", ""),
    "soul_state_check":   _env("MODEL_GATE", ""),
    "user_model_update":  _env("MODEL_UPDATE", ""),
    "soul_state_update":  _env("MODEL_UPDATE", ""),
}

# Inbox watcher
WATCHER_PROVIDER = _env("WATCHER_PROVIDER", "")  # empty = DEFAULT_PROVIDER
WATCHER_MODEL = _env("WATCHER_MODEL", "")
WATCHER_POLL_INTERVAL = int(_env("WATCHER_POLL", "3"))

# WhatsApp adapter
WHATSAPP_GATEWAY_URL = _env("WHATSAPP_GATEWAY_URL", "http://localhost:3847")
WHATSAPP_GATEWAY_PORT = int(_env("WHATSAPP_GATEWAY_PORT", "3847"))
WHATSAPP_ALLOWED_SENDERS = _env("WHATSAPP_ALLOWED_SENDERS", "")
WHATSAPP_RATE_LIMIT = int(_env("WHATSAPP_RATE_LIMIT", "10"))

# Daimonic intercession — Kothar
KOTHAR_ENABLED = _env("KOTHAR_ENABLED", "false").lower() == "true"
KOTHAR_HOST = _env("KOTHAR_HOST", "localhost")
KOTHAR_PORT = int(_env("KOTHAR_PORT", "3033"))
KOTHAR_AUTH_TOKEN = _env("KOTHAR_AUTH_TOKEN", "")
KOTHAR_SOUL_MD = _env("KOTHAR_SOUL_MD", "~/souls/kothar/soul.md")  # expanduser deferred to daimonic.py
KOTHAR_GROQ_ENABLED = _env("KOTHAR_GROQ_ENABLED", "false").lower() == "true"
KOTHAR_MODE = _env("KOTHAR_MODE", "whisper")  # whisper | speak | both | off

# Daimonic intercession — Artifex
ARTIFEX_ENABLED = _env("ARTIFEX_ENABLED", "false").lower() == "true"
ARTIFEX_HOST = _env("ARTIFEX_HOST", "localhost")
ARTIFEX_PORT = int(_env("ARTIFEX_PORT", "3034"))
ARTIFEX_AUTH_TOKEN = _env("ARTIFEX_AUTH_TOKEN", "")
ARTIFEX_SOUL_MD = _env("ARTIFEX_SOUL_MD", "~/souls/artifex/soul.md")
ARTIFEX_GROQ_ENABLED = _env("ARTIFEX_GROQ_ENABLED", "false").lower() == "true"
ARTIFEX_MODE = _env("ARTIFEX_MODE", "whisper")  # whisper | speak | both | off
ARTIFEX_GROQ_MODEL = _env("ARTIFEX_GROQ_MODEL", "moonshotai/kimi-k2-instruct")

# Shared Groq key
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# Memory versioning (git-tracked evolution of user models and soul state)
MEMORY_GIT_ENABLED = _env("MEMORY_GIT_ENABLED", "true").lower() == "true"

# Autonomous dossiers (people, subjects, topics encountered in conversation)
DOSSIER_ENABLED = _env("DOSSIER_ENABLED", "true").lower() == "true"
MAX_DOSSIER_INJECTION = int(_env("MAX_DOSSIER_INJECTION", "3"))

# Logging
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
