# database/db_manager.py
import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

class DatabaseManager:
    """Singleton database connection pool manager"""
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_app(self, app=None):
        """Initialize the database connection pool"""
        try:
            # Get database URL from environment
            database_url = os.environ.get('DATABASE_URL')

            if not database_url:
                # Build from individual params
                host = os.environ.get('PGHOST', 'localhost')
                database = os.environ.get('PGDATABASE', 'societyos')
                user = os.environ.get('PGUSER', 'postgres')
                password = os.environ.get('PGPASSWORD', '')
                port = os.environ.get('PGPORT', '5432')

                database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

            # Create connection pool
            self._pool = psycopg2.pool.SimpleConnectionPool(
                1, 20, dsn=database_url, sslmode=os.environ.get('PGSSLMODE', 'prefer')
            )
            print("✓ Database connection pool initialized")
            return True

        except Exception as e:
            print(f"⚠️ Database initialization error: {e}")
            self._pool = None
            return False

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool"""
        if not self._pool:
            self.init_app()

        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """Execute a query and return results"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params or ())
                if fetch_one:
                    return cur.fetchone()
                elif fetch_all:
                    return cur.fetchall()
                else:
                    return cur.rowcount

# Global instance
db = DatabaseManager()
