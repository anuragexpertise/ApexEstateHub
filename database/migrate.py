#!/usr/bin/env python3
# database/migrate.py
"""
EstateHub — Aiven PostgreSQL migration + seed script.

Usage:
    python3 database/migrate.py            # normal
    python3 database/migrate.py --force    # re-run DDL even if tables exist
    python3 database/migrate.py --seed     # skip prompt, always seed
    python3 database/migrate.py --no-seed  # skip prompt, never seed
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

import logging
logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)


def _dsn() -> str:
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
        print("❌  Set DATABASE_URL  or  PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
        sys.exit(1)
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"


def get_conn():
    try:
        conn = psycopg2.connect(
            _dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=20,
            options="-c lock_timeout=15000 -c statement_timeout=180000",
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


from pathlib import Path
import sqlparse

def load_schema_sql():
    sql_file = Path(__file__).with_name("estatehub.sql")
    if not sql_file.exists():
        raise FileNotFoundError(f"Schema file not found: {sql_file}")
    return sql_file.read_text(encoding="utf-8")

SCHEMA_SQL = load_schema_sql()

def run_schema(conn):
    stmts = sqlparse.split(SCHEMA_SQL)
    ok = 0
    err = 0
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for stmt in stmts:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
                ok += 1
            except Exception as exc:
                conn.rollback()
                snippet = stmt[:120].replace("\n", " ")
                print(f"\nFAILED:\n{snippet}")
                print(exc)
                err += 1
    return ok, err


def main():
    parser = argparse.ArgumentParser(description="EstateHub DB migration + seed")
    parser.add_argument("--force",   action="store_true", help="Re-run DDL even if tables already exist")
    parser.add_argument("--seed",    action="store_true", help="Always seed demo data without prompting")
    parser.add_argument("--no-seed", action="store_true", help="Skip demo data seeding")
    args = parser.parse_args()

    print()
    print("═" * 62)
    print("  EstateHub — Database Migration")
    print("═" * 62)
    print(f"  Host : {os.getenv('PGHOST','(from DATABASE_URL)')}")
    print(f"  DB   : {os.getenv('PGDATABASE','')}")
    print()

    conn = get_conn()
    print("  ✓ Connected to Aiven PostgreSQL")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='societies') AS ex"
        )
        tables_exist = cur.fetchone()["ex"]

    if tables_exist and not args.force:
        print("  ✓ Schema present — running safe ALTER/CREATE IF NOT EXISTS pass…")
    else:
        print("  ⟳ Creating schema…")

    ok, err = run_schema(conn)
    print(f"  ✓ DDL: {ok} ok, {err} skipped")

    if args.no_seed:
        print("  Seed skipped (--no-seed).")
        conn.close()
        return

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM societies")
        has_societies = cur.fetchone()["c"] > 0

    if has_societies and not args.seed:
        print("  ✓ Societies exist — skipping demo seed. Use --seed to force.")
        conn.close()
        return

    if args.seed:
        do_seed = True
    else:
        print()
        print("  First run — no societies found.")
        print("  Seed demo data? (1 society, 39 users, 50 accounts,")
        print("  12 events, 12 concerns, 2 gate logs, 2 assets)")
        print()
        try:
            ans = input("  Seed demo data? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        do_seed = ans != "n"

    if do_seed:
        try:
            from seed import run_seed
        except ImportError:
            from database.seed import run_seed
        try:
            run_seed(conn)
        except psycopg2.errors.LockNotAvailable:
            print()
            print("  ❌  Seeding stopped: timed out waiting for a database lock.")
            print("      Another connection is holding a lock — run in psql/Aiven console to find and end it:")
            print("        SELECT pid, state, query FROM pg_stat_activity")
            print("        WHERE datname = current_database() AND pid <> pg_backend_pid()")
            print("          AND state <> 'idle' ORDER BY query_start;")
            conn.rollback()
            conn.close()
            sys.exit(1)
        except psycopg2.errors.QueryCanceled:
            print()
            print("  ❌  Seeding stopped: a statement exceeded the 3-minute timeout.")
            conn.rollback()
            conn.close()
            sys.exit(1)
        conn = None  # run_seed() closes the connection itself
    else:
        print("  Seed skipped.  Log in as master admin to create a society.")

    if conn is not None:
        conn.close()
    print()
    print("═" * 62)
    print("✅ Migration complete")
    print("═" * 62)


if __name__ == "__main__":
    main()