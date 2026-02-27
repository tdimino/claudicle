"""Shared SQLite connection pool with per-thread isolation.

Replaces the duplicate threading.local() + _get_conn() pattern that was
independently implemented in working_memory.py, soul_memory.py,
user_models.py, and session_store.py.

Two pools are instantiated at module level:
- memory_pool  → memory.db (working_memory, soul_memory, user_models)
- session_pool → sessions.db (session_store)

Each pool manages its own thread-local connections and runs migrations
before first use. Migrations can be SQL strings or callables (for complex
migrations like soul_memory's soul_id column addition).

Thread-safe: each thread gets its own SQLite connection via threading.local().
"""

import logging
import os
import sqlite3
import threading
from collections.abc import Sequence
from typing import Callable

log = logging.getLogger(__name__)

Migration = str | Callable[[sqlite3.Connection], None]

_MEMORY_DB = os.path.join(os.path.dirname(__file__), "memory.db")
_SESSIONS_DB = os.path.join(os.path.dirname(__file__), "sessions.db")


class ConnectionPool:
    """Thread-local SQLite connection pool with automatic migration.

    Each thread that calls get_conn() gets its own connection. Migrations
    are applied when a thread first opens a connection, and also whenever
    new migrations are registered later (use add_migrations()).

    Args:
        db_path: Path to the SQLite database file.
        migrations: Ordered list of migrations to run before first use.
            Each migration is either a SQL string (executed via conn.execute,
            duplicate/already-exists OperationalError ignored for idempotency)
            or a callable taking a sqlite3.Connection (for complex multi-step
            migrations).
        row_factory: Optional row factory for connections. Defaults to
            sqlite3.Row for dict-like access.
    """

    def __init__(
        self,
        db_path: str,
        migrations: list[Migration] | None = None,
        row_factory: type | None = sqlite3.Row,
    ):
        self._db_path = db_path
        self._migrations: list[Migration] = list(migrations or [])
        self._row_factory = row_factory
        self._migrations_lock = threading.Lock()
        self._local = threading.local()

    @property
    def db_path(self) -> str:
        return self._db_path

    @db_path.setter
    def db_path(self, value: str) -> None:
        self._db_path = value

    def get_conn(self) -> sqlite3.Connection:
        """Get or create the thread-local connection (migrated)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            if self._row_factory is not None:
                self._local.conn.row_factory = self._row_factory
            self._local.migrations_applied = 0

        self._apply_pending_migrations(self._local.conn)
        return self._local.conn

    def add_migrations(self, migrations: Sequence[Migration]) -> None:
        """Register additional migrations.

        Safe to call at import-time from multiple modules sharing the same
        pool. If the current thread already has an open connection, any newly
        registered migrations will be applied on the next get_conn() call.
        """
        if not migrations:
            return
        with self._migrations_lock:
            self._migrations.extend(migrations)

    def add_migration(self, migration: Migration) -> None:
        self.add_migrations([migration])

    def _apply_pending_migrations(self, conn: sqlite3.Connection) -> None:
        applied = getattr(self._local, "migrations_applied", 0)
        if applied < 0:
            applied = 0

        with self._migrations_lock:
            pending = self._migrations[applied:]
            target = len(self._migrations)  # snapshot total under lock

            if not pending:
                return

            for migration in pending:
                if callable(migration):
                    migration(conn)
                    continue

                try:
                    conn.execute(migration)
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if "duplicate column name" in msg or "already exists" in msg:
                        continue
                    raise

            conn.commit()
            self._local.migrations_applied = target

    def close(self) -> None:
        """Close the thread-local connection if open."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
            self._local.migrations_applied = 0

    def reset_local(self) -> None:
        """Reset thread-local state for test isolation.

        Creates a fresh threading.local() so the next get_conn() call
        in any thread opens a new connection.
        """
        self.close()
        self._local = threading.local()


# ---------------------------------------------------------------------------
# Pool instances — importable singletons
# ---------------------------------------------------------------------------

memory_pool = ConnectionPool(_MEMORY_DB)
session_pool = ConnectionPool(_SESSIONS_DB, row_factory=None)
