"""Tests for multi-soul architecture — soul_path, soul-scoped memory, dynamic SOUL_NAME."""

import os
import threading

import pytest

from engine import soul_path
from memory import soul_memory


class TestResolveSoulPath:
    def test_default_returns_soul_md(self, tmp_path):
        """Without profiles or env vars, returns soul/soul.md."""
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul.md").write_text("# Default")
        result = soul_path.resolve_soul_path(str(tmp_path))
        assert result.endswith("soul/soul.md")

    def test_env_override(self, tmp_path, monkeypatch):
        """CLAUDICLE_SOUL_PROFILE env var takes precedence."""
        profiles = tmp_path / "soul" / "profiles"
        profiles.mkdir(parents=True)
        (profiles / "minerva.md").write_text("# Minerva")
        monkeypatch.setenv("CLAUDICLE_SOUL_PROFILE", "minerva")
        result = soul_path.resolve_soul_path(str(tmp_path))
        assert result.endswith("profiles/minerva.md")

    def test_env_override_missing_profile_falls_through(self, tmp_path, monkeypatch):
        """Env var pointing to nonexistent profile falls back to default."""
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul.md").write_text("# Default")
        monkeypatch.setenv("CLAUDICLE_SOUL_PROFILE", "nonexistent")
        result = soul_path.resolve_soul_path(str(tmp_path))
        assert result.endswith("soul/soul.md")

    def test_symlink_resolution(self, tmp_path):
        """soul/active symlink resolves to the target profile."""
        profiles = tmp_path / "soul" / "profiles"
        profiles.mkdir(parents=True)
        target = profiles / "atlas.md"
        target.write_text("# Atlas")
        link = tmp_path / "soul" / "active"
        os.symlink(str(target), str(link))
        result = soul_path.resolve_soul_path(str(tmp_path))
        assert result.endswith("atlas.md")

    def test_broken_symlink_falls_back(self, tmp_path):
        """Broken symlink falls back to soul.md."""
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul.md").write_text("# Default")
        link = soul_dir / "active"
        os.symlink("/nonexistent/path.md", str(link))
        result = soul_path.resolve_soul_path(str(tmp_path))
        assert result.endswith("soul/soul.md")


class TestGetActiveSoulName:
    def test_default_name(self, tmp_path):
        """Default soul returns 'default'."""
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul.md").write_text("# Default")
        assert soul_path.get_active_soul_name(str(tmp_path)) == "default"

    def test_profile_name(self, tmp_path, monkeypatch):
        """Profile soul returns the profile name."""
        profiles = tmp_path / "soul" / "profiles"
        profiles.mkdir(parents=True)
        (profiles / "forge.md").write_text("# Forge")
        monkeypatch.setenv("CLAUDICLE_SOUL_PROFILE", "forge")
        assert soul_path.get_active_soul_name(str(tmp_path)) == "forge"


class TestSoulScopedMemory:
    def test_different_souls_independent(self):
        """Different soul_id values store independently."""
        soul_memory.set("currentProject", "Project Alpha", soul_id="claudius")
        soul_memory.set("currentProject", "Project Beta", soul_id="minerva")
        assert soul_memory.get("currentProject", soul_id="claudius") == "Project Alpha"
        assert soul_memory.get("currentProject", soul_id="minerva") == "Project Beta"

    def test_get_all_scoped(self):
        """get_all returns only the specified soul's data."""
        soul_memory.set("emotionalState", "focused", soul_id="claudius")
        soul_memory.set("emotionalState", "engaged", soul_id="atlas")
        all_claudius = soul_memory.get_all(soul_id="claudius")
        assert all_claudius["emotionalState"] == "focused"
        all_atlas = soul_memory.get_all(soul_id="atlas")
        assert all_atlas["emotionalState"] == "engaged"

    def test_format_for_prompt_scoped(self):
        """format_for_prompt respects soul_id."""
        soul_memory.set("currentProject", "Minoan Research", soul_id="claudius")
        prompt = soul_memory.format_for_prompt(soul_id="claudius")
        assert "Minoan Research" in prompt
        # Other soul has no project
        prompt2 = soul_memory.format_for_prompt(soul_id="other")
        assert "Minoan Research" not in prompt2

    def test_default_soul_id(self, monkeypatch):
        """Default soul_id comes from config.SOUL_NAME."""
        import config
        monkeypatch.setattr(config, "SOUL_NAME", "TestSoul")
        soul_memory.set("emotionalState", "sardonic")
        assert soul_memory.get("emotionalState", soul_id="testsoul") == "sardonic"


class TestDynamicSoulName:
    def test_set_active_soul(self):
        """config.set_active_soul() changes SOUL_NAME at runtime."""
        import config
        original = config.SOUL_NAME
        config.set_active_soul("Minerva")
        assert config.SOUL_NAME == "Minerva"
        # Restore
        config.set_active_soul(original)

    def test_dynamic_soul_name_in_memory(self, monkeypatch):
        """Changing SOUL_NAME at runtime scopes memory operations."""
        import config
        monkeypatch.setattr(config, "SOUL_NAME", "Alpha")
        soul_memory.set("currentTopic", "Topic A")
        monkeypatch.setattr(config, "SOUL_NAME", "Beta")
        soul_memory.set("currentTopic", "Topic B")
        assert soul_memory.get("currentTopic", soul_id="alpha") == "Topic A"
        assert soul_memory.get("currentTopic", soul_id="beta") == "Topic B"


class TestContextCacheInvalidation:
    def test_invalidate_clears_cache(self):
        """invalidate_soul_cache clears the cached soul content."""
        from engine import context
        context._soul_cache = "old cached value"
        context.invalidate_soul_cache()
        assert context._soul_cache is None

    def test_reload_soul_path(self, tmp_path, monkeypatch):
        """reload_soul_path re-resolves and clears cache."""
        from engine import context
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul.md").write_text("# Default")
        monkeypatch.setattr(context, "_CLAUDICLE_HOME", str(tmp_path))
        context._soul_cache = "stale"
        context.reload_soul_path()
        assert context._soul_cache is None
        assert context._SOUL_MD_PATH.endswith("soul/soul.md")
