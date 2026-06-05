# database/db_manager.py
"""
Database manager for Aiven PostgreSQL.

Uses psycopg2 under the hood but accepts SQLAlchemy-style named
parameters (:name) in all queries — they are converted to %(name)s
before execution so every caller can use the same syntax.

Usage:
    from database.db_manager import db

    row  = db._execute("SELECT * FROM societies WHERE id = :id",
                       {"id": 1}, fetch_one=True)
    rows = db._execute("SELECT * FROM societies", fetch_all=True)
    db._execute("INSERT INTO societies (name) VALUES (:name)",
               {"name": "Test"})
"""

import os
import re
import time
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool

log = logging.getLogger(__name__)


# ── Named-param conversion ────────────────────────────────────────────────────

_NAMED_RE = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")


def _to_pyformat(sql: str, params: dict | None) -> tuple[str, tuple | None]:
    """
    Convert :name → %(name)s so psycopg2 can handle SQLAlchemy-style params.
    Positional %s queries with a tuple/list pass through unchanged.
    """
    if params is None:
        return sql, None

    if isinstance(params, dict):
        converted = _NAMED_RE.sub(r"%(\1)s", sql)
        return converted, params          # psycopg2 accepts dict with %(name)s

    # Already a tuple/list — positional style, leave as-is
    return sql, params


# ── Connection pool wrapper ───────────────────────────────────────────────────

class DatabaseManager:
    """Thread-safe Aiven PostgreSQL connection pool."""

    def __init__(self):
        self._pool: pool.ThreadedConnectionPool | None = None
        self._init_pool()

    # ── Pool init ─────────────────────────────────────────────────────────────

    def _dsn(self) -> str:
        raw = os.getenv("DATABASE_URL", "").strip()
        if raw:
            return raw.replace("postgres://", "postgresql://", 1)

        host   = os.getenv("PGHOST",     "").strip()
        port   = os.getenv("PGPORT",     "5432").strip() or "5432"
        dbname = os.getenv("PGDATABASE", "").strip()
        user   = os.getenv("PGUSER",     "").strip()
        pw     = os.getenv("PGPASSWORD", "").strip()
        ssl    = os.getenv("PGSSLMODE",  "require").strip()

        if not all([host, dbname, user, pw]):
            raise RuntimeError(
                "Database env vars missing: PGHOST / PGDATABASE / PGUSER / PGPASSWORD"
            )
        return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"

    def _init_pool(self):
        try:
            dsn = self._dsn()
            self._pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=15,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            log.info("✅ DB pool initialised (Aiven PostgreSQL)")
        except Exception as exc:
            log.error("❌ DB pool init failed: %s", exc)
            self._pool = None

    # ── Connection context manager ────────────────────────────────────────────

    @contextmanager
    def _conn(self):
        if self._pool is None:
            self._init_pool()
        if self._pool is None:
            raise RuntimeError("Database connection pool unavailable")

        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ── Public execute ────────────────────────────────────────────────────────

    def execute(
        self,
        sql: str,
        params=None,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ):
        """
        Execute a query and optionally return rows.

        Args:
            sql:       Query string with :name placeholders (or bare %s).
            params:    dict for named params, tuple/list for positional, None for no params.
            fetch_one: Return the first row as a dict (or None).
            fetch_all: Return all rows as a list of dicts.

        Returns:
            dict | list[dict] | None depending on fetch_* flags.
        """
        converted_sql, converted_params = _to_pyformat(sql, params)

        retries = 2
        for attempt in range(retries + 1):
            try:
                with self._conn() as conn:
                    cur = conn.cursor()
                    cur.execute(converted_sql, converted_params)

                    if fetch_one:
                        row = cur.fetchone()
                        return dict(row) if row else None

                    if fetch_all:
                        rows = cur.fetchall()
                        return [dict(r) for r in rows] if rows else []

                    return None          # DML with no fetch

            except psycopg2.OperationalError as exc:
                # Stale pooled connection — rebuild pool once
                if attempt < retries:
                    log.warning("DB operational error (attempt %d): %s", attempt + 1, exc)
                    self._pool = None
                    self._init_pool()
                    time.sleep(0.5)
                else:
                    log.error("DB query failed after %d retries: %s", retries, exc)
                    raise

    # Alias so existing code that calls db._execute() still works
    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        return self.execute(sql, params, fetch_one=fetch_one, fetch_all=fetch_all)

    # ── Health check ──────────────────────────────────────────────────────────

    def is_healthy(self) -> bool:
        try:
            self.execute("SELECT 1", fetch_one=True)
            return True
        except Exception:
            return False

    def close(self):
        if self._pool:
            self._pool.closeall()
            self._pool = None


# ── Singleton ─────────────────────────────────────────────────────────────────
db = DatabaseManager()
