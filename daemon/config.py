"""
Claudicle daemon configuration.

All settings can be overridden via environment variables prefixed with CLAUDICLE_.
Legacy SLACK_DAEMON_ prefix also supported for backward compatibility.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


def _env(key: str, default: Any) -> Any:
    """Read env var with CLAUDICLE_ prefix, falling back to SLACK_DAEMON_."""
    return os.environ.get(f"CLAUDICLE_{key}", os.environ.get(f"SLACK_DAEMON_{key}", default))


_FIELD_ENV_KEYS: dict[str, str] = {
    "CLAUDE_TIMEOUT": "TIMEOUT",
    "CLAUDE_CWD": "CWD",
    "CLAUDE_ALLOWED_TOOLS": "TOOLS",
    "SESSION_TTL_HOURS": "SESSION_TTL",
    "SOUL_NAME": "SOUL_NAME",
    "DEFAULT_USER_NAME": "DEFAULT_USER_NAME",
    "DEFAULT_SLACK_USER_ID": "DEFAULT_SLACK_USER_ID",
    "PRIMARY_USER_ID": "PRIMARY_USER_ID",
    "SOUL_ENGINE_ENABLED": "SOUL_ENGINE",
    "USER_MODEL_UPDATE_INTERVAL": "USER_MODEL_INTERVAL",
    "WORKING_MEMORY_TTL_HOURS": "MEMORY_TTL",
    "SOUL_STATE_UPDATE_INTERVAL": "SOUL_STATE_INTERVAL",
    "COMPRESSION_ENABLED": "COMPRESSION",
    "COMPRESSION_THRESHOLD": "COMPRESSION_THRESHOLD",
    "COMPRESSION_KEEP_RECENT": "COMPRESSION_KEEP",
    "COMPRESSION_REFLECT_INTERVAL": "COMPRESSION_INTERVAL",
    "COMPRESSION_USE_LLM": "COMPRESSION_LLM",
    "COMPRESSION_MODEL": "COMPRESSION_MODEL",
    "COMPRESSION_PROVIDER": "COMPRESSION_PROVIDER",
    "COMPRESSION_ARCHIVE": "COMPRESSION_ARCHIVE",
    "WORKING_MEMORY_PROMPT_INJECT": "WM_PROMPT_INJECT",
    "WORKING_MEMORY_WINDOW": "WM_WINDOW",
    "STIMULUS_VERB_ENABLED": "STIMULUS_VERB",
    "ONBOARDING_ENABLED": "ONBOARDING",
    "SOUL_LOG_ENABLED": "SOUL_LOG",
    "TERMINAL_SESSION_TOOLS": "TERMINAL_TOOLS",
    "TERMINAL_SOUL_ENABLED": "TERMINAL_SOUL",
    "TERMINAL_REFLECT_ENABLED": "TERMINAL_REFLECT",
    "REFLECT_PROVIDER": "REFLECT_PROVIDER",
    "REFLECT_MODEL": "REFLECT_MODEL",
    "REFLECT_COOLDOWN": "REFLECT_COOLDOWN",
    "WM_STREAM_ENABLED": "WM_STREAM",
    "DEFAULT_PROVIDER": "PROVIDER",
    "DEFAULT_MODEL": "MODEL",
    "PIPELINE_MODE": "PIPELINE_MODE",
    "WATCHER_PROVIDER": "WATCHER_PROVIDER",
    "WATCHER_MODEL": "WATCHER_MODEL",
    "WATCHER_POLL_INTERVAL": "WATCHER_POLL",
    "WHATSAPP_GATEWAY_URL": "WHATSAPP_GATEWAY_URL",
    "WHATSAPP_GATEWAY_PORT": "WHATSAPP_GATEWAY_PORT",
    "WHATSAPP_ALLOWED_SENDERS": "WHATSAPP_ALLOWED_SENDERS",
    "WHATSAPP_RATE_LIMIT": "WHATSAPP_RATE_LIMIT",
    "KOTHAR_ENABLED": "KOTHAR_ENABLED",
    "KOTHAR_HOST": "KOTHAR_HOST",
    "KOTHAR_PORT": "KOTHAR_PORT",
    "KOTHAR_AUTH_TOKEN": "KOTHAR_AUTH_TOKEN",
    "KOTHAR_SOUL_MD": "KOTHAR_SOUL_MD",
    "KOTHAR_GROQ_ENABLED": "KOTHAR_GROQ_ENABLED",
    "KOTHAR_MODE": "KOTHAR_MODE",
    "ARTIFEX_ENABLED": "ARTIFEX_ENABLED",
    "ARTIFEX_HOST": "ARTIFEX_HOST",
    "ARTIFEX_PORT": "ARTIFEX_PORT",
    "ARTIFEX_AUTH_TOKEN": "ARTIFEX_AUTH_TOKEN",
    "ARTIFEX_SOUL_MD": "ARTIFEX_SOUL_MD",
    "ARTIFEX_GROQ_ENABLED": "ARTIFEX_GROQ_ENABLED",
    "ARTIFEX_MODE": "ARTIFEX_MODE",
    "ARTIFEX_GROQ_MODEL": "ARTIFEX_GROQ_MODEL",
    "MEMORY_GIT_ENABLED": "MEMORY_GIT_ENABLED",
    "SCHEDULER_ENABLED": "SCHEDULER_ENABLED",
    "SCHEDULER_INTERVAL": "SCHEDULER_INTERVAL",
    "SCHEDULER_MAX_EVENTS": "SCHEDULER_MAX_EVENTS",
    "SCHEDULER_MAX_OVERDUE_RATIO": "SCHEDULER_MAX_OVERDUE_RATIO",
    "COMPACTION_ENABLED": "COMPACTION",
    "MODEL_SHED_ENABLED": "MODEL_SHED_ENABLED",
    "MODEL_SHED_META_COMMENTARY": "MODEL_SHED_META_COMMENTARY",
    "SUMMONING_ENABLED": "SUMMONING_ENABLED",
    "SUMMONING_MAX_ACTIVE": "SUMMONING_MAX_ACTIVE",
    "SUMMONING_GROQ_MODEL": "SUMMONING_GROQ_MODEL",
    "DOSSIER_ENABLED": "DOSSIER_ENABLED",
    "MAX_DOSSIER_INJECTION": "MAX_DOSSIER_INJECTION",
    "EDITORIAL_DOSSIER_ENABLED": "EDITORIAL_DOSSIER_ENABLED",
    "EDITORIAL_DOSSIER_BASE": "EDITORIAL_DOSSIER_BASE",
    "CHANNEL_DOMAIN_MAP": "CHANNEL_DOMAIN_MAP",
    "TOOL_AUGMENTED_STEPS_ENABLED": "TOOL_AUGMENTED_STEPS_ENABLED",
    "TOOL_MAX_ROUNDS": "TOOL_MAX_ROUNDS",
    "TOOL_TIMEOUT_SECONDS": "TOOL_TIMEOUT_SECONDS",
    # Daemon lifecycle
    "DAEMON_AUTO_START": "DAEMON_AUTO_START",
    "DAEMON_HEALTH_TIMEOUT": "DAEMON_HEALTH_TIMEOUT",
    "SOUL_PROFILE": "SOUL_PROFILE",
    # Discord adapter
    "DISCORD_ALLOWED_CHANNELS": "DISCORD_ALLOWED_CHANNELS",
    "DISCORD_RESPOND_TO_MENTIONS": "DISCORD_RESPOND_TO_MENTIONS",
    "DISCORD_RESPOND_TO_DMS": "DISCORD_RESPOND_TO_DMS",
    # Telegram adapter
    "TELEGRAM_ALLOWED_CHATS": "TELEGRAM_ALLOWED_CHATS",
    "TELEGRAM_RESPOND_TO_MENTIONS": "TELEGRAM_RESPOND_TO_MENTIONS",
    "TELEGRAM_RESPOND_TO_DMS": "TELEGRAM_RESPOND_TO_DMS",
}

_STEP_PROVIDER_ENV_KEYS = (
    "PROVIDER_MONOLOGUE",
    "PROVIDER_DIALOGUE",
    "PROVIDER_GATE",
    "PROVIDER_UPDATE",
)
_STEP_MODEL_ENV_KEYS = (
    "MODEL_MONOLOGUE",
    "MODEL_DIALOGUE",
    "MODEL_GATE",
    "MODEL_UPDATE",
)


def _default_step_provider() -> dict[str, str]:
    return {
        "internal_monologue": "",
        "external_dialogue": "",
        "user_model_check": "",
        "soul_state_check": "",
        "dossier_check": "",
        "user_model_update": "",
        "soul_state_update": "",
        "dossier_update": "",
        "editorial_dossier_check": "",
        "editorial_dossier_update": "",
    }


def _default_step_model() -> dict[str, str]:
    return {
        "internal_monologue": "",
        "external_dialogue": "",
        "user_model_check": "",
        "soul_state_check": "",
        "dossier_check": "",
        "user_model_update": "",
        "soul_state_update": "",
        "dossier_update": "",
        "editorial_dossier_check": "",
        "editorial_dossier_update": "",
    }


def _build_step_provider() -> dict[str, str]:
    return {
        "internal_monologue": _env("PROVIDER_MONOLOGUE", ""),
        "external_dialogue": _env("PROVIDER_DIALOGUE", ""),
        "user_model_check": _env("PROVIDER_GATE", ""),
        "soul_state_check": _env("PROVIDER_GATE", ""),
        "dossier_check": _env("PROVIDER_GATE", ""),
        "user_model_update": _env("PROVIDER_UPDATE", ""),
        "soul_state_update": _env("PROVIDER_UPDATE", ""),
        "dossier_update": _env("PROVIDER_UPDATE", ""),
        "editorial_dossier_check": _env("PROVIDER_GATE", ""),
        "editorial_dossier_update": _env("PROVIDER_UPDATE", ""),
    }


def _build_step_model() -> dict[str, str]:
    return {
        "internal_monologue": _env("MODEL_MONOLOGUE", ""),
        "external_dialogue": _env("MODEL_DIALOGUE", ""),
        "user_model_check": _env("MODEL_GATE", ""),
        "soul_state_check": _env("MODEL_GATE", ""),
        "dossier_check": _env("MODEL_GATE", ""),
        "user_model_update": _env("MODEL_UPDATE", ""),
        "soul_state_update": _env("MODEL_UPDATE", ""),
        "dossier_update": _env("MODEL_UPDATE", ""),
        "editorial_dossier_check": _env("MODEL_GATE", ""),
        "editorial_dossier_update": _env("MODEL_UPDATE", ""),
    }


def _has_prefixed_env(key: str) -> bool:
    return f"CLAUDICLE_{key}" in os.environ or f"SLACK_DAEMON_{key}" in os.environ


class LegacyPrefixedEnvSource(PydanticBaseSettingsSource):
    """Load env vars with CLAUDICLE_ first, then SLACK_DAEMON_ fallback.

    Only __call__ is overridden — pydantic-settings calls it once for the
    full batch of fields. No per-field get_field_value needed.
    """

    def get_field_value(self, field, field_name: str) -> tuple[Any, str, bool]:
        # Required by the abstract base class but never called when __call__
        # returns the full dict. Satisfy the interface contract.
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        data: dict[str, Any] = {}

        for field_name, env_key in _FIELD_ENV_KEYS.items():
            value = _env(env_key, None)
            if value is not None:
                data[field_name] = value

        if "CLAUDICLE_HOME" in os.environ:
            data["CLAUDICLE_HOME"] = os.environ["CLAUDICLE_HOME"]
        if "GROQ_API_KEY" in os.environ:
            data["GROQ_API_KEY"] = os.environ["GROQ_API_KEY"]

        if any(_has_prefixed_env(key) for key in _STEP_PROVIDER_ENV_KEYS):
            data["STEP_PROVIDER"] = _build_step_provider()
        if any(_has_prefixed_env(key) for key in _STEP_MODEL_ENV_KEYS):
            data["STEP_MODEL"] = _build_step_model()

        return data


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # Claudicle home directory
    CLAUDICLE_HOME: str = os.path.expanduser("~/.claudicle")

    # Channel filtering
    ALLOWED_CHANNELS: str | None = None  # None = all channels bot is in
    BLOCKED_CHANNELS: set[str] = Field(default_factory=set)  # Channel IDs to never respond in

    # Response limits
    MAX_RESPONSE_LENGTH: int = 3000  # Slack message limit ~4000 chars; leave headroom

    # Claude Code invocation
    CLAUDE_TIMEOUT: int = 120
    CLAUDE_CWD: str = "~"
    CLAUDE_ALLOWED_TOOLS: str = "Read,Glob,Grep,Bash,WebFetch"

    # Session expiry
    SESSION_TTL_HOURS: int = 24

    # Soul identity
    SOUL_NAME: str = "Claudius"

    # Default user identity (for non-Slack contexts: terminal, inbox, etc.)
    # In Slack, user_id comes from the Slack API (e.g. "U04ABCD1234").
    # For terminal/inbox use, these defaults apply when no Slack identity exists.
    DEFAULT_USER_NAME: str = "Human"
    DEFAULT_SLACK_USER_ID: str = "U08V7U4MR8B"

    # Primary user — the soul's owner. Gets role: "primary" in their user model.
    PRIMARY_USER_ID: str | None = None

    # Soul engine
    SOUL_ENGINE_ENABLED: bool = True
    USER_MODEL_UPDATE_INTERVAL: int = 5
    WORKING_MEMORY_TTL_HOURS: int = 72
    SOUL_STATE_UPDATE_INTERVAL: int = 3
    COMPRESSION_ENABLED: bool = True
    COMPRESSION_THRESHOLD: int = 50
    COMPRESSION_KEEP_RECENT: int = 20
    COMPRESSION_REFLECT_INTERVAL: int = 5
    COMPRESSION_USE_LLM: bool = False
    COMPRESSION_MODEL: str = ""
    COMPRESSION_PROVIDER: str = ""
    COMPRESSION_ARCHIVE: bool = True
    WORKING_MEMORY_PROMPT_INJECT: bool = False
    WORKING_MEMORY_WINDOW: int = 40

    # Subdaimon memory TTL (longer than conversation memory — 30 days default)
    DAIMON_MEMORY_TTL_HOURS: int = 720

    # Stimulus verb narration (LLM chooses verb for incoming messages; disable for "said" default)
    STIMULUS_VERB_ENABLED: bool = True

    # First ensoulment onboarding (interview new users whose name is DEFAULT_USER_NAME)
    ONBOARDING_ENABLED: bool = True

    # Soul log (structured cognitive cycle JSONL stream)
    SOUL_LOG_ENABLED: bool = True

    # Terminal session (unified launcher)
    TERMINAL_SESSION_TOOLS: str = "Read,Glob,Grep,Bash,WebFetch,Edit,Write"
    TERMINAL_SOUL_ENABLED: bool = False

    # Terminal reflection (post-response cognitive pipeline for Claude Code sessions)
    TERMINAL_REFLECT_ENABLED: bool = True
    REFLECT_PROVIDER: str = "groq"
    REFLECT_MODEL: str = "moonshotai/kimi-k2-instruct"
    REFLECT_COOLDOWN: int = 60

    # Working memory stream (tail-able JSONL of all cognitive entries)
    WM_STREAM_ENABLED: bool = True

    # ---------------------------------------------------------------------------
    # Provider routing
    # ---------------------------------------------------------------------------
    DEFAULT_PROVIDER: str = "claude_cli"
    DEFAULT_MODEL: str = ""
    PIPELINE_MODE: str = "unified"  # "unified" | "split"

    # Per-step overrides (only when PIPELINE_MODE=split)
    STEP_PROVIDER: dict[str, str] = Field(default_factory=_default_step_provider)
    STEP_MODEL: dict[str, str] = Field(default_factory=_default_step_model)

    # Inbox watcher
    WATCHER_PROVIDER: str = ""  # empty = DEFAULT_PROVIDER
    WATCHER_MODEL: str = ""
    WATCHER_POLL_INTERVAL: int = 3

    # WhatsApp adapter
    WHATSAPP_GATEWAY_URL: str = "http://localhost:3847"
    WHATSAPP_GATEWAY_PORT: int = 3847
    WHATSAPP_ALLOWED_SENDERS: str = ""
    WHATSAPP_RATE_LIMIT: int = 10

    # Daimonic intercession — Kothar
    KOTHAR_ENABLED: bool = False
    KOTHAR_HOST: str = "localhost"
    KOTHAR_PORT: int = 3033
    KOTHAR_AUTH_TOKEN: str = ""
    KOTHAR_SOUL_MD: str = "~/souls/kothar/soul.md"  # expanduser deferred to daimonic.py
    KOTHAR_GROQ_ENABLED: bool = False
    KOTHAR_MODE: str = "whisper"  # whisper | speak | both | off

    # Daimonic intercession — Artifex
    ARTIFEX_ENABLED: bool = False
    ARTIFEX_HOST: str = "localhost"
    ARTIFEX_PORT: int = 3034
    ARTIFEX_AUTH_TOKEN: str = ""
    ARTIFEX_SOUL_MD: str = "~/souls/artifex/soul.md"
    ARTIFEX_GROQ_ENABLED: bool = False
    ARTIFEX_MODE: str = "whisper"  # whisper | speak | both | off
    ARTIFEX_GROQ_MODEL: str = "moonshotai/kimi-k2-instruct"

    # Shared Groq key
    GROQ_API_KEY: str = ""

    # Memory versioning (git-tracked evolution of user models and soul state)
    MEMORY_GIT_ENABLED: bool = True

    # Scheduled events (daemon-only background event loop)
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL: int = 30              # seconds between polls
    SCHEDULER_MAX_EVENTS: int = 100           # cap total pending events
    SCHEDULER_MAX_OVERDUE_RATIO: float = 2.0  # auto-expire ratio

    # Context compaction (token-budget-aware context assembly)
    COMPACTION_ENABLED: bool = False

    # Model/dossier shedding (archaeology of identity evolution)
    MODEL_SHED_ENABLED: bool = True
    MODEL_SHED_META_COMMENTARY: bool = False  # LLM-generated epistemic reflection on each shed

    # Daimon summoning (awaken any entity as an ephemeral speaking daimon)
    SUMMONING_ENABLED: bool = True
    SUMMONING_MAX_ACTIVE: int = 3
    SUMMONING_GROQ_MODEL: str = "moonshotai/kimi-k2-instruct"

    # Autonomous dossiers (people, subjects, topics encountered in conversation)
    DOSSIER_ENABLED: bool = True
    MAX_DOSSIER_INJECTION: int = 3

    # Editorial dossiers — domain-scoped living records maintained by daimons
    # Convention: {EDITORIAL_DOSSIER_BASE}/{domain}-editorial-record.md
    EDITORIAL_DOSSIER_ENABLED: bool = False
    EDITORIAL_DOSSIER_BASE: str = ""
    CHANNEL_DOMAIN_MAP: dict[str, str] = Field(default_factory=dict)

    # Tool-augmented cognitive steps (split mode only)
    TOOL_AUGMENTED_STEPS_ENABLED: bool = False
    TOOL_MAX_ROUNDS: int = 3
    TOOL_TIMEOUT_SECONDS: int = 15

    # Discord adapter
    DISCORD_ALLOWED_CHANNELS: str = ""           # Comma-separated channel IDs (empty = all)
    DISCORD_RESPOND_TO_MENTIONS: bool = True
    DISCORD_RESPOND_TO_DMS: bool = True

    # Telegram adapter
    TELEGRAM_ALLOWED_CHATS: str = ""             # Comma-separated chat IDs (empty = all)
    TELEGRAM_RESPOND_TO_MENTIONS: bool = True
    TELEGRAM_RESPOND_TO_DMS: bool = True

    # Daemon lifecycle
    DAEMON_AUTO_START: bool = True           # Auto-start daemon from hooks
    DAEMON_HEALTH_TIMEOUT: int = 3           # Seconds to wait for /api/health

    # Logging
    LOG_DIR: str = os.path.join(os.path.dirname(__file__), "logs")

    # Soul profile (for multi-soul support)
    SOUL_PROFILE: str = ""

    @property
    def global_config_hash(self) -> str:
        """Hash of config values that require daemon restart when changed.

        Global-tier settings (soul identity, provider list, home dir) are baked
        into daemon state at startup. Per-operation settings (compression thresholds,
        watcher params, stimulus verb) are read fresh and don't require restart.
        """
        global_vals = sorted([
            ("SOUL_NAME", self.SOUL_NAME),
            ("SOUL_PROFILE", self.SOUL_PROFILE),
            ("CLAUDICLE_HOME", str(self.CLAUDICLE_HOME)),
            ("DEFAULT_PROVIDER", self.DEFAULT_PROVIDER),
            ("DEFAULT_MODEL", self.DEFAULT_MODEL),
            ("PIPELINE_MODE", self.PIPELINE_MODE),
            ("SOUL_ENGINE_ENABLED", str(self.SOUL_ENGINE_ENABLED)),
        ])
        return hashlib.sha256(str(global_vals).encode()).hexdigest()[:8]

    @field_validator("CLAUDE_CWD", mode="after")
    @classmethod
    def _expand_claude_cwd(cls, value: str) -> str:
        return os.path.expanduser(value)

    @model_validator(mode="after")
    def _set_primary_user_id(self) -> "Settings":
        if self.PRIMARY_USER_ID is None:
            self.PRIMARY_USER_ID = self.DEFAULT_SLACK_USER_ID
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            LegacyPrefixedEnvSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


settings = Settings()
globals().update(settings.model_dump())


def set_active_soul(name: str) -> None:
    """Update SOUL_NAME at runtime for soul profile switching.

    Only the module global is updated — settings singleton is read-only
    after construction. All consumers access config.SOUL_NAME, not
    settings.SOUL_NAME.
    """
    global SOUL_NAME
    SOUL_NAME = name
