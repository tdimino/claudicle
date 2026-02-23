"""Tests for soul_journal — git-journaled soul shedding."""

import subprocess

import pytest

from memory import soul_journal


@pytest.fixture
def soul_md(tmp_path):
    """Create a minimal soul.md in a temp directory."""
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    p = soul_dir / "soul.md"
    p.write_text("# Original Soul\n\nOriginal content.\n")
    return str(p)


@pytest.fixture(autouse=True)
def reset_repo_cache():
    """Clear the repo initialization cache between tests."""
    soul_journal._repo_initialized.clear()
    yield
    soul_journal._repo_initialized.clear()


class TestEnsureRepo:
    def test_initializes_git_repo(self, soul_md):
        """_ensure_repo creates .git/ in the soul directory."""
        from pathlib import Path
        soul_dir = Path(soul_md).parent
        assert soul_journal._ensure_repo(soul_dir)
        assert (soul_dir / ".git").exists()

    def test_idempotent(self, soul_md):
        """Second call returns True without re-initializing."""
        from pathlib import Path
        soul_dir = Path(soul_md).parent
        assert soul_journal._ensure_repo(soul_dir)
        assert soul_journal._ensure_repo(soul_dir)

    def test_handles_missing_git(self, monkeypatch, soul_md):
        """Returns False gracefully if git binary not found."""
        from pathlib import Path
        soul_dir = Path(soul_md).parent
        original_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if cmd[0] == "git":
                raise FileNotFoundError("git")
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert not soul_journal._ensure_repo(soul_dir)


class TestShed:
    def test_shed_creates_two_commits(self, soul_md):
        """A full shed produces a pre-shed snapshot + rationale commit."""
        ok = soul_journal.shed(
            soul_md,
            "# Evolved Soul\n\nNew content.\n",
            "Themistokles: soul evolved to match new patterns",
            description="test shed",
        )
        assert ok

        from pathlib import Path
        soul_dir = Path(soul_md).parent

        # Verify file content changed
        assert Path(soul_md).read_text() == "# Evolved Soul\n\nNew content.\n"

        # Verify git log has at least 2 entries
        result = subprocess.run(
            ["git", "log", "--oneline", "--", "soul.md"],
            cwd=soul_dir, capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.strip().splitlines() if l]
        assert len(lines) >= 2
        # Most recent commit is the rationale
        assert "Themistokles" in lines[0]
        # Previous is the pre-shed snapshot
        assert "pre-shed" in lines[1]

    def test_shed_invalidates_cache(self, soul_md):
        """Shed clears the soul cache in context.py."""
        from engine import context
        context._soul_cache = "old cached value"
        soul_journal.shed(soul_md, "new", "rationale")
        assert context._soul_cache is None


class TestCommit:
    def test_commit_creates_one_commit(self, soul_md):
        """commit() journals a pre-existing change (single commit)."""
        from pathlib import Path

        # Initialize the repo first
        soul_dir = Path(soul_md).parent
        soul_journal._ensure_repo(soul_dir)
        # Initial commit so git has a baseline
        soul_journal._git_commit(soul_dir, Path(soul_md), "initial")

        # Simulate an Edit tool modifying soul.md
        Path(soul_md).write_text("# Modified by Edit tool\n")

        ok = soul_journal.commit(soul_md, "Themistokles: refined speaking style")
        assert ok

        result = subprocess.run(
            ["git", "log", "--oneline", "--", "soul.md"],
            cwd=soul_dir, capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.strip().splitlines() if l]
        assert len(lines) >= 2
        assert "Themistokles" in lines[0]

    def test_commit_invalidates_cache(self, soul_md):
        """commit() also clears the soul cache."""
        from engine import context
        context._soul_cache = "stale"
        soul_journal.commit(soul_md, "rationale")
        assert context._soul_cache is None


class TestGetJournal:
    def test_returns_log(self, soul_md):
        """get_journal returns readable git log output."""
        soul_journal.shed(soul_md, "v2", "shed: v2")
        journal = soul_journal.get_journal(soul_md)
        assert "shed: v2" in journal

    def test_respects_limit(self, soul_md):
        """get_journal limits entries."""
        soul_journal.shed(soul_md, "v2", "shed: v2")
        soul_journal.shed(soul_md, "v3", "shed: v3")
        journal = soul_journal.get_journal(soul_md, limit=1)
        lines = [l for l in journal.strip().splitlines() if l]
        assert len(lines) == 1

    def test_nonexistent_returns_placeholder(self, tmp_path):
        """get_journal on nonexistent file returns placeholder."""
        fake = str(tmp_path / "soul" / "soul.md")
        journal = soul_journal.get_journal(fake)
        assert "No journal" in journal


class TestGetLastShed:
    def test_returns_dict(self, soul_md):
        """get_last_shed returns hash, rationale, timestamp."""
        soul_journal.shed(soul_md, "v2", "shed: latest change")
        last = soul_journal.get_last_shed(soul_md)
        assert last["rationale"] == "shed: latest change"
        assert "hash" in last
        assert "timestamp" in last

    def test_empty_when_no_history(self, tmp_path):
        """get_last_shed returns {} when no history exists."""
        fake = str(tmp_path / "soul" / "soul.md")
        assert soul_journal.get_last_shed(fake) == {}


class TestTimeout:
    def test_timeout_returns_false(self, monkeypatch, soul_md):
        """Git timeout returns False from _git_commit."""
        from pathlib import Path
        soul_dir = Path(soul_md).parent
        soul_journal._ensure_repo(soul_dir)

        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 10)

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert not soul_journal._git_commit(soul_dir, Path(soul_md), "test")
