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
from urllib.parse import quote

import psycopg2
import psycopg2.extras
from psycopg2 import pool

log = logging.getLogger(__name__)

# Load .env early so this module can be imported directly in scripts
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    # dotenv is optional at runtime; if unavailable, environment must be set externally
    pass


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

        # Additional SSL CA env var names used across the codebase
        ssl_ca_env = os.getenv('PGSSLROOTCERT') or os.getenv('PGSSL_CA') or os.getenv('PGSSLROOTCA')

        if not all([host, dbname, user, pw]):
            raise RuntimeError(
                "Database env vars missing: PGHOST / PGDATABASE / PGUSER / PGPASSWORD"
            )

        dsn = f"postgresql://{user}:{quote(pw)}@{host}:{port}/{dbname}?sslmode={ssl}"

        # If an SSL root cert is provided as a file path, expand and append it to the DSN
        if ssl_ca_env:
            ca_path = os.path.expanduser(ssl_ca_env)
            ca_path = os.path.abspath(ca_path)
            if os.path.isfile(ca_path):
                # Only append if not already present
                if 'sslrootcert=' not in dsn:
                    dsn = dsn + f"&sslrootcert={ca_path}"

        return dsn

    def _init_pool(self):
        try:
            dsn = self._dsn()
            self._pool = pool.ThreadedConnectionPool(
                minconn=5,
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

        _t_get0 = time.monotonic()
        conn = self._pool.getconn()
        _get_elapsed = time.monotonic() - _t_get0
        if _get_elapsed > 0.5:
            print(f"    ↳ getconn() took {_get_elapsed:.2f}s (new/blocked connection)")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    # ── public execute ────────────────────────────────────────────────────────

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
            _t0 = time.monotonic()
            try:
                with self._conn() as conn:
                    _t_exec0 = time.monotonic()
                    cur = conn.cursor()
                    cur.execute(converted_sql, converted_params)
                    _exec_elapsed = time.monotonic() - _t_exec0

                    if fetch_one:
                        row = cur.fetchone()
                        print(f"  ⏱ DB query ok (attempt {attempt + 1}) total={time.monotonic() - _t0:.2f}s exec={_exec_elapsed:.2f}s")
                        return dict(row) if row else None

                    if fetch_all:
                        rows = cur.fetchall()
                        print(f"  ⏱ DB query ok (attempt {attempt + 1}) total={time.monotonic() - _t0:.2f}s exec={_exec_elapsed:.2f}s")
                        return [dict(r) for r in rows] if rows else []

                    print(f"  ⏱ DB query ok (attempt {attempt + 1}) total={time.monotonic() - _t0:.2f}s exec={_exec_elapsed:.2f}s")
                    return None          # DML with no fetch

            except psycopg2.OperationalError as exc:
                _elapsed = time.monotonic() - _t0
                # Stale pooled connection — rebuild pool once
                if attempt < retries:
                    print(f"  ⚠️  DB operational error (attempt {attempt + 1}, {_elapsed:.2f}s elapsed): {exc}")
                    self._pool = None
                    self._init_pool()
                    time.sleep(0.5)
                else:
                    print(f"  ❌ DB query failed after {retries} retries ({_elapsed:.2f}s on final attempt): {exc}")
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
