#!/usr/bin/env python3
# database/migrate.py
"""
EstateHub — apply database/estatehub.sql to PostgreSQL, then optionally seed.

estatehub.sql is the single source of truth for the schema. Every column,
constraint and index is declared inline on its CREATE TABLE, so this script has
no DDL of its own to keep in step with the file. Two constraints cannot be
inlined and are the only ALTER TABLE statements, both pointing at a table
declared later in the file (societies -> accounts, society_policy_settings ->
resolutions).

The schema carries no IF NOT EXISTS / DROP IF EXISTS guards: the database is
not in production, so the only supported way to install it is onto an empty
schema. `database/reset_database.py --yes --after seed` drops and recreates the
public schema and then runs this file, which is the from-scratch path.

This script still executes statement-by-statement and reports rather than
aborts on a failing statement, so on a database that already has the schema it
will print one "already exists" error per object. That is expected and harmless
— it is not a signal that anything needs fixing. To actually reinstall, use
reset_database.py.

Usage:
    python3 database/migrate.py            # normal
    python3 database/migrate.py --force    # same DDL pass, ignore existing tables
    python3 database/migrate.py --seed     # skip prompt, always seed
    python3 database/migrate.py --no-seed  # skip prompt, never seed
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
import sqlparse

logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).with_name("estatehub.sql")


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


def run_schema(conn) -> tuple[int, int]:
    if not SCHEMA_FILE.exists():
        print(f"❌  Schema file not found: {SCHEMA_FILE}")
        sys.exit(1)

    ok = err = 0
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        for stmt in sqlparse.split(SCHEMA_FILE.read_text(encoding="utf-8")):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
                ok += 1
            except Exception as exc:
                conn.rollback()
                print(f"\nFAILED:\n{stmt[:120].replace(chr(10), ' ')}\n{exc}")
                err += 1
    return ok, err


def schema_present(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='societies') AS ex"
        )
        return cur.fetchone()["ex"]


def society_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM societies")
        return cur.fetchone()["c"]


def seed(conn):
    try:
        from seed import run_seed
    except ImportError:
        from database.seed import run_seed
    run_seed(conn)   # run_seed() closes the connection itself


def main():
    parser = argparse.ArgumentParser(description="EstateHub schema + seed")
    parser.add_argument("--force",   action="store_true", help="Run the DDL pass even if tables already exist")
    parser.add_argument("--seed",    action="store_true", help="Always seed demo data without prompting")
    parser.add_argument("--no-seed", action="store_true", help="Skip demo data seeding")
    args = parser.parse_args()

    print()
    print("═" * 62)
    print("  EstateHub — Database Migration")
    print("═" * 62)
    print(f"  Schema: {SCHEMA_FILE.name}")
    print(f"  Host   : {os.getenv('PGHOST', '(from DATABASE_URL)')}")
    print(f"  DB     : {os.getenv('PGDATABASE', '')}")
    print()

    conn = get_conn()
    print("  ✓ Connected to PostgreSQL")

    if schema_present(conn) and not args.force:
        print("  ✓ Schema present — re-running estatehub.sql (idempotent pass)…")
    else:
        print("  ⟳ Creating schema…")

    ok, err = run_schema(conn)
    print(f"  ✓ DDL: {ok} applied, {err} failed/skipped")
    if err:
        print("  ⚠  Failed statements above are usually objects that already exist;")
        print("     anything else needs fixing in estatehub.sql before this DB is usable.")

    if args.no_seed:
        print("  Seed skipped (--no-seed).")
        conn.close()
        return

    if society_count(conn) > 0 and not args.seed:
        print("  ✓ Societies exist — skipping demo seed. Use --seed to force.")
        conn.close()
        return

    if args.seed:
        do_seed = True
    else:
        print()
        print("  First run — no societies found.")
        print("  Seed demo data?")
        print()
        try:
            ans = input("  Seed demo data? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        do_seed = ans != "n"

    if do_seed:
        try:
            seed(conn)
        except psycopg2.errors.LockNotAvailable:
            print()
            print("  ❌  Seeding stopped: timed out waiting for a database lock.")
            print("      Find the holder with:")
            print("        SELECT pid, state, query FROM pg_stat_activity")
            print("        WHERE datname = current_database() AND pid <> pg_backend_pid()")
            print("          AND state <> 'idle' ORDER BY query_start;")
            sys.exit(1)
        except psycopg2.errors.QueryCanceled:
            print()
            print("  ❌  Seeding stopped: a statement exceeded the 3-minute timeout.")
            sys.exit(1)
        conn = None   # run_seed() closed it
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
