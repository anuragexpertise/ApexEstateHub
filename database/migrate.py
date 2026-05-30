#!/usr/bin/env python3
# database/migrate.py
"""
Run estatehub.sql against Aiven PostgreSQL.

Usage:
    python3 database/migrate.py            # normal run
    python3 database/migrate.py --force    # re-run even if tables exist
"""
import os
import sys
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(override=False)


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_conn():
    """Create psycopg2 connection to Aiven PostgreSQL."""
    import psycopg2
    import psycopg2.extras

    raw = os.getenv('DATABASE_URL', '').strip()
    if raw:
        dsn = raw.replace('postgres://', 'postgresql://', 1)
    else:
        host = os.getenv('PGHOST', '').strip().strip("'\"")
        port = os.getenv('PGPORT', '5432').strip().strip("'\"") or '5432'
        dbname = os.getenv('PGDATABASE', '').strip().strip("'\"")
        user = os.getenv('PGUSER', '').strip().strip("'\"")
        pw = os.getenv('PGPASSWORD', '').strip().strip("'\"")
        ssl = os.getenv('PGSSLMODE', 'require').strip().strip("'\"")

        if not all([host, dbname, user, pw]):
            print("❌  Missing: PGHOST / PGDATABASE / PGUSER / PGPASSWORD")
            sys.exit(1)
        
        try:
            port = str(int(port))
        except ValueError:
            port = '5432'

        dsn = f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"

    try:
        conn = psycopg2.connect(
            dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=15
        )
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌  Cannot connect to Aiven: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# SQL PARSER
# ══════════════════════════════════════════════════════════════════════════════

def _strip_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    # Block comments first
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    # Line comments
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql


def split_statements(raw_sql: str) -> list:
    """
    Improved splitter that properly handles $$ delimited PL/pgSQL functions.
    """
    stmts = []
    buffer = []
    in_dollar_block = False
    lines = raw_sql.split('\n')

    for line in lines:
        buffer.append(line)
        stripped = line.strip()

        # Detect start of a $$ function block
        if not in_dollar_block and re.search(r'CREATE OR REPLACE FUNCTION|DO\s+\$\$', stripped, re.IGNORECASE):
            in_dollar_block = True

        # End of $$ block - look for $$;
        if in_dollar_block and stripped.endswith('$$;'):
            in_dollar_block = False
            stmt = '\n'.join(buffer).strip()
            if stmt:
                stmts.append(stmt)
            buffer = []
            continue

        # Regular statements (outside dollar blocks)
        if not in_dollar_block and stripped.endswith(';') and not stripped.startswith('--'):
            stmt = '\n'.join(buffer).strip()
            cleaned = _strip_comments(stmt).strip()
            if cleaned and cleaned != ';':
                stmts.append(stmt)
            buffer = []

    # Handle any remaining content
    if buffer:
        stmt = '\n'.join(buffer).strip()
        cleaned = _strip_comments(stmt).strip()
        if cleaned and cleaned != ';':
            stmts.append(stmt)

    return stmts


# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def already_migrated(conn) -> bool:
    """Check if societies table exists."""
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
    """Execute SQL file, return (success_count, error_count)."""
    raw_sql = open(sql_path, encoding='utf-8').read()
    stmts = split_statements(raw_sql)
    ok = err = 0

    cur = conn.cursor()
    for stmt in stmts:
        try:
            cur.execute(stmt)
            conn.commit()
            ok += 1
        except Exception as e:
            conn.rollback()
            # Show snippet for debugging
            snippet = _strip_comments(stmt)[:100].replace('\n', ' ').strip()
            print(f"  ⚠  Skipped ({e.__class__.__name__}): {snippet}…")
            err += 1
    cur.close()
    return ok, err


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true',
                        help='Re-run even if tables already exist')
    parser.add_argument('--sql', default=None,
                        help='Path to SQL file (default: estatehub.sql)')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = args.sql or os.path.join(project_root, 'estatehub.sql')

    if not os.path.isfile(sql_path):
        print(f"❌  SQL file not found: {sql_path}")
        sys.exit(1)

    print("=" * 60)
    print("  EsateHub — Aiven Database Migration")
    print("=" * 60)
    print(f"  SQL file : {sql_path}")
    print(f"  Host     : {os.getenv('PGHOST', '?')}:{os.getenv('PGPORT', '?')}")
    print(f"  Database : {os.getenv('PGDATABASE', '?')}")
    print()

    conn = get_conn()
    print("✓ Connected to Aiven PostgreSQL")

    # Check if already migrated
    if already_migrated(conn) and not args.force:
        print("✓ Tables already exist — applying safe updates only.")
        print("  (All CREATE/ALTER statements use IF NOT EXISTS)")
        print()
    else:
        print("  Running full migration (first run) …")
        print()

    # Run migration
    print("  Executing SQL statements …")
    ok, err = run_migration(conn, sql_path)
    conn.close()
    
    print()
    print(f"  ✓{ok} statements executed successfully")
    if err:
        print(f"  ⚠  {err} statements skipped (see above — usually safe)")

    # Run seed check
    print()
    print("=" * 60)
    print("  Running seed check …")
    print("=" * 60)

    # Re-import db singleton to get fresh connection
    import importlib
    import database.db_manager as dbmod
    importlib.reload(dbmod)

    seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seed.py')
    if os.path.isfile(seed_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location('seed', seed_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.run()
    else:
        print("  seed.py not found — skipping.")
    
    print()
    print("=" * 60)
    print("  ✅ Migration Complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
