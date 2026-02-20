"""Tests for daemon/session_store.py — save/get/touch, TTL expiry, cleanup."""

import time

from memory import session_store


class TestSaveGetTouch:
    """Tests for the session lifecycle."""

    def test_save_and_get(self):
        session_store.save("C1", "T1", "session-abc-123")
        assert session_store.get("C1", "T1") == "session-abc-123"

    def test_get_nonexistent(self):
        assert session_store.get("C1", "NOPE") is None

    def test_save_updates_existing(self):
        session_store.save("C1", "T1", "v1")
        session_store.save("C1", "T1", "v2")
        assert session_store.get("C1", "T1") == "v2"

    def test_touch_refreshes(self):
        session_store.save("C1", "T1", "s1")
        # Backdate last_used
        conn = session_store._get_conn()
        conn.execute(
            "UPDATE sessions SET last_used = ? WHERE channel = ? AND thread_ts = ?",
            (time.time() - 100, "C1", "T1"),
        )
        conn.commit()
        session_store.touch("C1", "T1")
        # Should still be valid
        assert session_store.get("C1", "T1") == "s1"


class TestTTLExpiry:
    """Tests for TTL-based session expiration."""

    def test_expired_session_returns_none(self):
        session_store.save("C1", "T1", "s1")
        # Backdate past TTL
        conn = session_store._get_conn()
        conn.execute(
            "UPDATE sessions SET last_used = ? WHERE channel = ? AND thread_ts = ?",
            (time.time() - 999999, "C1", "T1"),
        )
        conn.commit()
        assert session_store.get("C1", "T1") is None

    def test_expired_session_deleted_on_get(self):
        session_store.save("C1", "T1", "s1")
        conn = session_store._get_conn()
        conn.execute(
            "UPDATE sessions SET last_used = ? WHERE channel = ? AND thread_ts = ?",
            (time.time() - 999999, "C1", "T1"),
        )
        conn.commit()
        session_store.get("C1", "T1")  # triggers delete
        row = conn.execute(
            "SELECT * FROM sessions WHERE channel = ? AND thread_ts = ?", ("C1", "T1")
        ).fetchone()
        assert row is None


class TestCleanup:
    """Tests for cleanup()."""

    def test_removes_expired(self):
        session_store.save("C1", "T1", "s1")
        conn = session_store._get_conn()
        conn.execute(
            "UPDATE sessions SET last_used = ? WHERE channel = ? AND thread_ts = ?",
            (time.time() - 999999, "C1", "T1"),
        )
        conn.commit()
        deleted = session_store.cleanup()
        assert deleted == 1

    def test_preserves_active(self):
        session_store.save("C1", "T1", "s1")
        deleted = session_store.cleanup()
        assert deleted == 0
        assert session_store.get("C1", "T1") == "s1"
