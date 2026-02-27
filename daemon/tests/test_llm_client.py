"""Sanity tests for engine.llm_client exports and imports."""

import importlib


def test_import_no_circular():
    compression = importlib.import_module("memory.compression")
    reflect = importlib.import_module("engine.reflect")

    assert compression is not None
    assert reflect is not None


def test_providers_dict_exists():
    from engine.llm_client import PROVIDERS

    assert "groq" in PROVIDERS
    assert "openrouter" in PROVIDERS


def test_call_llm_function_exists():
    from engine.llm_client import call_llm

    assert callable(call_llm)
