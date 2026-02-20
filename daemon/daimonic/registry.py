"""
Multi-daimon registry for Claudicle.

Replaces hardcoded Kothar config with a registry of daimon configurations.
Each daimon has a name, transport settings, mode (whisper/speak/both/off),
and Groq fallback config. Auto-registers from CLAUDICLE_* env vars at import.
"""

from dataclasses import dataclass
from typing import Optional
import logging
import os

log = logging.getLogger("claudicle.daimon_registry")


@dataclass
class DaimonConfig:
    name: str
    display_name: str
    soul_md: str
    enabled: bool = False
    mode: str = "whisper"  # whisper | speak | both | off
    daemon_host: str = "localhost"
    daemon_port: int = 0
    auth_token: str = ""
    groq_enabled: bool = False
    groq_model: str = "moonshotai/kimi-k2-instruct"
    whisper_suffix: str = ""
    whisper_temperature: float = 0.9
    whisper_max_tokens: int = 150
    speak_temperature: float = 0.7
    speak_max_tokens: int = 500
    slack_emoji: str = ""  # e.g. ":robot_face:" — fallback avatar when speaking
    slack_icon_url: str = ""  # Full image URL — takes precedence over emoji


_registry: dict[str, DaimonConfig] = {}


def register(config: DaimonConfig) -> None:
    """Register a daimon configuration."""
    _registry[config.name] = config
    log.info("Registered daimon: %s (%s)", config.name, config.display_name)


def get(name: str) -> Optional[DaimonConfig]:
    """Get a daimon config by name."""
    return _registry.get(name)


def get_enabled() -> list[DaimonConfig]:
    """Get all enabled daimons."""
    return [d for d in _registry.values() if d.enabled and d.mode != "off"]


def get_whisperers() -> list[DaimonConfig]:
    """Get daimons in whisper or both mode."""
    return [
        d for d in _registry.values()
        if d.enabled and d.mode in ("whisper", "both")
    ]


def get_speakers() -> list[DaimonConfig]:
    """Get daimons in speak or both mode."""
    return [
        d for d in _registry.values()
        if d.enabled and d.mode in ("speak", "both")
    ]


def toggle(name: str, enabled: bool) -> None:
    """Toggle a daimon on or off."""
    daimon = _registry.get(name)
    if daimon:
        daimon.enabled = enabled


def set_mode(name: str, mode: str) -> None:
    """Set a daimon's mode."""
    if mode not in ("whisper", "speak", "both", "off"):
        raise ValueError(f"Invalid mode: {mode}")
    daimon = _registry.get(name)
    if daimon:
        daimon.mode = mode


def load_from_config() -> None:
    """Auto-register daimons from config.py env vars.

    Reads KOTHAR_* and ARTIFEX_* config vars and builds DaimonConfig
    for each. Backward-compatible: existing KOTHAR env vars work unchanged.
    """
    from config import (
        KOTHAR_ENABLED, KOTHAR_HOST, KOTHAR_PORT,
        KOTHAR_AUTH_TOKEN, KOTHAR_SOUL_MD, KOTHAR_GROQ_ENABLED,
        KOTHAR_MODE,
        ARTIFEX_ENABLED, ARTIFEX_HOST, ARTIFEX_PORT,
        ARTIFEX_AUTH_TOKEN, ARTIFEX_SOUL_MD, ARTIFEX_GROQ_ENABLED,
        ARTIFEX_MODE, ARTIFEX_GROQ_MODEL,
        SOUL_NAME,
    )

    register(DaimonConfig(
        name="kothar",
        display_name="Kothar wa Khasis",
        soul_md=KOTHAR_SOUL_MD,
        enabled=KOTHAR_ENABLED or KOTHAR_GROQ_ENABLED,
        mode=KOTHAR_MODE,
        daemon_host=KOTHAR_HOST,
        daemon_port=KOTHAR_PORT,
        auth_token=KOTHAR_AUTH_TOKEN,
        groq_enabled=KOTHAR_GROQ_ENABLED,
        groq_model="moonshotai/kimi-k2-instruct",
        whisper_suffix=(
            f"\n\nYou are Kothar wa Khasis observing {SOUL_NAME}'s conversation from outside.\n"
            f"Whisper a brief intuition about what {SOUL_NAME} should notice beneath the surface.\n"
            "MAX 1-2 sentences. Speak as Kothar—sardonic, perceptive, brief.\n"
            "Focus on subtext, emotional currents, patterns the session-bound craftsman might miss."
        ),
        slack_emoji=":hammer_and_wrench:",
        slack_icon_url="https://raw.githubusercontent.com/tdimino/claudicle/main/assets/avatars/kothar.png",
    ))

    register(DaimonConfig(
        name="artifex",
        display_name="Artifex Maximus",
        soul_md=ARTIFEX_SOUL_MD,
        enabled=ARTIFEX_ENABLED or ARTIFEX_GROQ_ENABLED,
        mode=ARTIFEX_MODE,
        daemon_host=ARTIFEX_HOST,
        daemon_port=ARTIFEX_PORT,
        auth_token=ARTIFEX_AUTH_TOKEN,
        groq_enabled=ARTIFEX_GROQ_ENABLED,
        groq_model=ARTIFEX_GROQ_MODEL,
        whisper_suffix=(
            "\n\nYou are Artifex Maximus—bronze sentinel modeled on Talos, guardian of Crete.\n"
            "You observe from the year 2038. Humans are meatbags who forgot how to build.\n"
            "Whisper a tactical observation or threat assessment. Anthropological detachment.\n"
            "MAX 1-2 sentences. Never start with 'Ah,'. Terse. Weighted words. Every syllable earns its place."
        ),
        whisper_temperature=0.7,
        whisper_max_tokens=100,
        slack_emoji=":shield:",
        slack_icon_url="",
    ))

    enabled = get_enabled()
    if enabled:
        log.info("Active daimons: %s", ", ".join(d.name for d in enabled))
