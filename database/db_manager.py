# database/db_manager.py
"""
Singleton PostgreSQL connection manager.
Uses psycopg2 with a simple connection pool pattern safe for
multi-threaded gunicorn (--threads flag).
"""

import os
import psycopg2
import psycopg2.extras
from threading import Lock


class DatabaseManager:
    """Thread-safe PostgreSQL manager with auto-reconnect."""

    def __init__(self):
        self._conn   = None
        self._lock   = Lock()
        self._dsn    = self._build_dsn()

    # ── DSN builder ───────────────────────────────────────────────
    @staticmethod
    def _build_dsn() -> str:
        direct = os.getenv('DATABASE_URL')
        if direct:
            # Neon returns postgres:// — psycopg2 needs postgresql://
            return direct.replace('postgres://', 'postgresql://', 1)

        host     = os.getenv('PGHOST',     '').strip("'\"")
        dbname   = os.getenv('PGDATABASE', '').strip("'\"")
        user     = os.getenv('PGUSER',     '').strip("'\"")
        password = os.getenv('PGPASSWORD', '').strip("'\"")
        sslmode  = os.getenv('PGSSLMODE',  'require').strip("'\"")

        if not all([host, dbname, user, password]):
            raise EnvironmentError(
                "Database env vars missing. Set DATABASE_URL or "
                "PGHOST / PGDATABASE / PGUSER / PGPASSWORD."
            )
        return (
            f"postgresql://{user}:{password}@{host}/{dbname}"
            f"?sslmode={sslmode}"
        )

    # ── Connection management ─────────────────────────────────────
    def _get_conn(self):
        """Return an open connection, reconnecting if needed."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                self._dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=10,
            )
            self._conn.autocommit = False
        return self._conn

    # ── Public query interface ────────────────────────────────────
    def execute_query(
        self,
        query: str,
        params=None,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ):
        """
        Execute a SQL statement and optionally fetch results.

        Returns:
            dict          — when fetch_one=True
            list[dict]    — when fetch_all=True
            None          — for INSERT / UPDATE / DELETE
        """
        with self._lock:
            try:
                conn   = self._get_conn()
                cursor = conn.cursor()
                cursor.execute(query, params or ())

                if fetch_one:
                    row = cursor.fetchone()
                    conn.commit()
                    return dict(row) if row else None

                if fetch_all:
                    rows = cursor.fetchall()
                    conn.commit()
                    return [dict(r) for r in rows] if rows else []

                conn.commit()
                return None

            except psycopg2.OperationalError:
                # Connection lost — reset and retry once
                try:
                    self._conn = None
                    conn   = self._get_conn()
                    cursor = conn.cursor()
                    cursor.execute(query, params or ())
                    if fetch_one:
                        row = cursor.fetchone()
                        conn.commit()
                        return dict(row) if row else None
                    if fetch_all:
                        rows = cursor.fetchall()
                        conn.commit()
                        return [dict(r) for r in rows] if rows else []
                    conn.commit()
                    return None
                except Exception as retry_err:
                    if self._conn:
                        self._conn.rollback()
                    raise retry_err

            except Exception as e:
                if self._conn and not self._conn.closed:
                    self._conn.rollback()
                raise e

            finally:
                try:
                    cursor.close()
                except Exception:
                    pass

    def test_connection(self) -> bool:
        """Return True if the database is reachable."""
        try:
            result = self.execute_query("SELECT 1 AS ok", fetch_one=True)
            return bool(result and result.get('ok') == 1)
        except Exception as e:
            print(f"DB connection test failed: {e}")
            return False

    def close(self):
        """Close the underlying connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# ── Singleton ─────────────────────────────────────────────────────────────────
db = DatabaseManager()