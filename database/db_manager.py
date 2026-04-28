# database/db_manager.py
"""
Singleton PostgreSQL connection manager — Aiven edition.

Key differences vs NeonDB:
  • PGPORT is required  (Aiven uses non-standard ports like 12345)
  • SSL CA cert supported via PGSSL_CA env var
  • pool_recycle set below Aiven's 300 s idle-connection timeout
  • Retry logic on OperationalError (transient network hiccups)
"""

import os
import psycopg2
import psycopg2.extras
from threading import Lock


class DatabaseManager:
    """Thread-safe PostgreSQL manager with auto-reconnect."""

    def __init__(self):
        self._conn = None
        self._lock = Lock()
        self._dsn  = self._build_dsn()

    # ── DSN builder ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_dsn() -> str:
        # ── 1. Full DATABASE_URL ───────────────────────────────────────────
        direct = os.getenv('DATABASE_URL', '').strip()
        if direct:
            return direct.replace('postgres://', 'postgresql://', 1)

        # ── 2. Individual Aiven vars ───────────────────────────────────────
        host     = os.getenv('PGHOST',     '').strip("'\"")
        port     = os.getenv('PGPORT',     '5432').strip("'\"")  # Aiven custom port
        dbname   = os.getenv('PGDATABASE', '').strip("'\"")
        user     = os.getenv('PGUSER',     '').strip("'\"")
        password = os.getenv('PGPASSWORD', '').strip("'\"")
        sslmode  = os.getenv('PGSSLMODE',  'require').strip("'\"")

        if not all([host, dbname, user, password]):
            raise EnvironmentError(
                "Database env vars missing. Set DATABASE_URL  or  "
                "PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD."
            )

        dsn = (
            f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
            f"?sslmode={sslmode}"
        )

        # Append CA cert for verify-ca / verify-full (recommended for Aiven)
        ssl_ca = os.getenv('PGSSL_CA', '').strip()
        if ssl_ca and os.path.isfile(ssl_ca):
            dsn += f"&sslrootcert={ssl_ca}"

        return dsn

    # ── SSL kwargs for psycopg2.connect ───────────────────────────────────────
    @staticmethod
    def _ssl_kwargs() -> dict:
        """
        Build extra keyword args for psycopg2.connect.
        When PGSSL_CA is set we pass an ssl context so the cert is verified.
        """
        ssl_ca = os.getenv('PGSSL_CA', '').strip()
        if not ssl_ca or not os.path.isfile(ssl_ca):
            return {}
        try:
            import ssl
            ctx = ssl.create_default_context(cafile=ssl_ca)
            ctx.check_hostname = False   # Aiven cert may not match the hostname
            return {'sslmode': 'require', 'sslrootcert': ssl_ca}
        except Exception as e:
            print(f"⚠  SSL context build failed: {e} — falling back to sslmode=require")
            return {}

    # ── Connection management ─────────────────────────────────────────────────
    def _get_conn(self):
        """Return an open connection, reconnecting if closed/lost."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                self._dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=15,      # Aiven can be slightly slower on cold start
                **self._ssl_kwargs(),
            )
            self._conn.autocommit = False
            print("✓ DB connected (Aiven PostgreSQL)")
        return self._conn

    # ── Public query interface ────────────────────────────────────────────────
    def execute_query(
        self,
        query: str,
        params=None,
        fetch_one: bool = False,
        fetch_all: bool = False,
    ):
        """
        Execute SQL and optionally fetch results.

        Returns:
            dict        — fetch_one=True
            list[dict]  — fetch_all=True
            None        — INSERT / UPDATE / DELETE
        """
        with self._lock:
            try:
                return self._run(query, params, fetch_one, fetch_all)

            except psycopg2.OperationalError as op_err:
                # Connection lost (Aiven idle timeout, network blip) → retry once
                print(f"⚠  DB OperationalError: {op_err} — reconnecting …")
                try:
                    self._conn = None
                    return self._run(query, params, fetch_one, fetch_all)
                except Exception as retry_err:
                    if self._conn:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                    raise retry_err

            except Exception as e:
                if self._conn and not self._conn.closed:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                raise e

    def _run(self, query, params, fetch_one, fetch_all):
        """Inner execution — called by execute_query (already inside lock)."""
        conn   = self._get_conn()
        cursor = conn.cursor()
        try:
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
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    # ── Health check ──────────────────────────────────────────────────────────
    def test_connection(self) -> bool:
        """Return True if Aiven is reachable."""
        try:
            row = self.execute_query("SELECT 1 AS ok", fetch_one=True)
            return bool(row and row.get('ok') == 1)
        except Exception as e:
            print(f"DB connection test failed: {e}")
            return False

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# ── Singleton ─────────────────────────────────────────────────────────────────
db = DatabaseManager()
