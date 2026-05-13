#!/usr/bin/env python3
# database/migrate.py
"""
Run dashestatehub.sql against Aiven PostgreSQL.

Usage:
    python3 database/migrate.py            # normal run
    python3 database/migrate.py --force    # re-run even if tables exist
"""
import os, sys, re, argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(override=False)


# ── Connection ────────────────────────────────────────────────────────────────

def get_conn():
    import psycopg2, psycopg2.extras

    raw = os.getenv('DATABASE_URL', '').strip()
    if raw:
        dsn = raw.replace('postgres://', 'postgresql://', 1)
    else:
        host   = os.getenv('PGHOST',     '').strip().strip("'\"")
        port   = os.getenv('PGPORT',     '5432').strip().strip("'\"") or '5432'
        dbname = os.getenv('PGDATABASE', '').strip().strip("'\"")
        user   = os.getenv('PGUSER',     '').strip().strip("'\"")
        pw     = os.getenv('PGPASSWORD', '').strip().strip("'\"")
        ssl    = os.getenv('PGSSLMODE',  'require').strip().strip("'\"")

        if not all([host, dbname, user, pw]):
            print("❌  Missing: PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD")
            sys.exit(1)
        try:
            port = str(int(port))
        except ValueError:
            port = '5432'

        dsn = f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"

    try:
        conn = psycopg2.connect(dsn,
                                cursor_factory=psycopg2.extras.RealDictCursor,
                                connect_timeout=15)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌  Cannot connect to Aiven: {e}")
        sys.exit(1)


# ── SQL parser ────────────────────────────────────────────────────────────────

def _strip_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    # Block comments first
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Line comments
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql


def split_statements(raw_sql: str) -> list:
    """
    Split SQL on semicolons, skip statements that are
    empty or comment-only after stripping.
    """
    stmts = []
    for raw in raw_sql.split(';'):
        # Check if there's any real SQL after stripping comments
        cleaned = _strip_comments(raw).strip()
        if cleaned:
            stmts.append(raw.strip())
    return stmts


# ── Migration runner ──────────────────────────────────────────────────────────

def already_migrated(conn) -> bool:
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'societies'
        )
    """)
    exists = cur.fetchone()['exists']
    cur.close()
    return exists


def run_migration(conn, sql_path: str) -> tuple:
    raw_sql  = open(sql_path, encoding='utf-8').read()
    stmts    = split_statements(raw_sql)
    ok = err = 0

    cur = conn.cursor()
    for stmt in stmts:
        try:
            cur.execute(stmt)
            conn.commit()
            ok += 1
        except Exception as e:
            conn.rollback()
            snippet = _strip_comments(stmt)[:80].replace('\n', ' ').strip()
            print(f"  ⚠  Skipped ({e.__class__.__name__}): {snippet}…")
            err += 1
    cur.close()
    return ok, err


# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true',
                        help='Re-run even if tables already exist')
    parser.add_argument('--sql', default=None)
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path     = args.sql or os.path.join(project_root, 'dashestatehub.sql')

    if not os.path.isfile(sql_path):
        print(f"❌  SQL file not found: {sql_path}")
        sys.exit(1)

    print("=" * 55)
    print("  ApexEstateHub — Aiven Database Migration")
    print("=" * 55)
    print(f"  SQL file : {sql_path}")
    print(f"  Host     : {os.getenv('PGHOST','?')}:{os.getenv('PGPORT','?')}")
    print(f"  Database : {os.getenv('PGDATABASE','?')}")
    print()

    conn = get_conn()
    print("✓ Connected to Aiven PostgreSQL")

    if already_migrated(conn) and not args.force:
        print("✓ Tables already exist — running additive patches only.")
        conn.close()
        # Even on existing DBs, always run the full SQL so the additive
        # ALTER TABLE / DO $$ blocks at the bottom apply safely.
        conn = get_conn()
        print("  Applying additive patches from main SQL …")
        ok, err = run_migration(conn, sql_path)
        conn.close()
        print(f"  ✓ {ok} statements OK", end="")
        print(f"  ({err} skipped)" if err else "")
    else:
        print("  Parsing and running SQL statements …")
        ok, err = run_migration(conn, sql_path)
        conn.close()
        print()
        print(f"  ✓ {ok} statements OK")
        if err:
            print(f"  ⚠  {err} skipped (see above — usually safe)")

    # Always run auth_enhanced.sql as a supplemental patch (all ADD COLUMN IF
    # NOT EXISTS — completely safe to re-run on any existing database).
    auth_sql = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auth_enhanced.sql')
    if os.path.isfile(auth_sql):
        print()
        print("  Applying auth_enhanced.sql patch …")
        conn2 = get_conn()
        ok2, err2 = run_migration(conn2, auth_sql)
        conn2.close()
        print(f"  ✓ {ok2} statements OK", end="")
        print(f"  ({err2} skipped)" if err2 else "")

    print()
    print("=" * 55)
    print("  Running seed check …")
    print("=" * 55)

    # Re-import db singleton so it gets a fresh connection
    import importlib, database.db_manager as dbmod
    importlib.reload(dbmod)

    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seed.py')
    if os.path.isfile(seed_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location('seed', seed_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run()
    else:
        print("  seed.py not found — skipping.")


if __name__ == '__main__':
    main()
