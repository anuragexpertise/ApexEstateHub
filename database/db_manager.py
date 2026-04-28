# database/db_manager.py
"""
Singleton psycopg2 connection manager — Aiven PostgreSQL edition.

The DSN is built on the FIRST actual connect() call, not at import time.
This guarantees python-dotenv has already loaded .env before we read env vars.
"""
import os
import psycopg2
import psycopg2.extras
from threading import Lock


class DatabaseManager:
    """Thread-safe PostgreSQL manager with lazy DSN + auto-reconnect."""

    def __init__(self):
        self._conn = None
        self._lock = Lock()
        self._dsn  = None          # built lazily on first _get_conn()

    # ── DSN builder (called once, lazily) ────────────────────────────────────
    @staticmethod
    def _build_dsn() -> str:
        from dotenv import load_dotenv
        load_dotenv(override=False)   # safe no-op if already loaded

        # 1. Full DATABASE_URL
        raw = os.getenv('DATABASE_URL', '').strip()
        if raw:
            return raw.replace('postgres://', 'postgresql://', 1)

        # 2. Individual Aiven vars
        host     = os.getenv('PGHOST',     '').strip().strip("'\"")
        port     = os.getenv('PGPORT',     '').strip().strip("'\"") or '5432'
        dbname   = os.getenv('PGDATABASE', '').strip().strip("'\"")
        user     = os.getenv('PGUSER',     '').strip().strip("'\"")
        password = os.getenv('PGPASSWORD', '').strip().strip("'\"")
        sslmode  = os.getenv('PGSSLMODE',  'require').strip().strip("'\"")

        if not all([host, dbname, user, password]):
            raise EnvironmentError(
                "\n\n  ❌  Database not configured.\n"
                "  Set DATABASE_URL  or  PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD\n"
                "  in your .env file or environment.\n"
            )

        # Sanitise port — must be an integer
        try:
            port = str(int(port))
        except ValueError:
            port = '5432'

        dsn = (
            f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
            f"?sslmode={sslmode}"
        )

        # Optional: Aiven CA cert for verify-full SSL
        ssl_ca = os.getenv('PGSSL_CA', '').strip()
        if ssl_ca and os.path.isfile(ssl_ca):
            dsn += f"&sslrootcert={ssl_ca}"

        return dsn

    # ── Extra psycopg2 kwargs for SSL ─────────────────────────────────────────
    @staticmethod
    def _connect_kwargs() -> dict:
        """Return sslrootcert kwarg when CA cert is available."""
        ssl_ca = os.getenv('PGSSL_CA', '').strip()
        if ssl_ca and os.path.isfile(ssl_ca):
            return {'sslrootcert': ssl_ca}
        return {}

    # ── Connection management ─────────────────────────────────────────────────
    def _get_conn(self):
        """Return an open connection; build DSN and connect if needed."""
        if self._dsn is None:
            self._dsn = self._build_dsn()

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                self._dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
                connect_timeout=15,
                **self._connect_kwargs(),
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
        with self._lock:
            try:
                return self._run(query, params, fetch_one, fetch_all)

            except psycopg2.OperationalError as err:
                # Aiven idle timeout or network blip → reset and retry once
                print(f"⚠  DB reconnecting after OperationalError: {err}")
                try:
                    self._conn = None
                    return self._run(query, params, fetch_one, fetch_all)
                except Exception as retry_err:
                    self._safe_rollback()
                    raise retry_err

            except Exception as e:
                self._safe_rollback()
                raise e

    def _run(self, query, params, fetch_one, fetch_all):
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

    def _safe_rollback(self):
        try:
            if self._conn and not self._conn.closed:
                self._conn.rollback()
        except Exception:
            pass

    # ── Health check ──────────────────────────────────────────────────────────
    def test_connection(self) -> bool:
        try:
            row = self.execute_query("SELECT 1 AS ok", fetch_one=True)
            return bool(row and row.get('ok') == 1)
        except Exception as e:
            print(f"DB connection test failed: {e}")
            return False

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
        self._conn = None


# ── Singleton ─────────────────────────────────────────────────────────────────
db = DatabaseManager()
