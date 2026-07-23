#!/usr/bin/env python3
# database/migrate.py
"""
EstateHub — Aiven PostgreSQL migration + seed script.

What it does
============
1. Connects to Aiven PostgreSQL (DATABASE_URL or PG* env vars).
2. Creates / updates the full schema (idempotent — uses IF NOT EXISTS).
3. On first run (no societies), asks whether to seed demo data:
     • 1 master admin
     • 1 society  (Sunrise Residency)
     • 50 Chart-of-Accounts entries
     • 1 admin, 2 apartment owners, 2 vendors, 2 security staff
     • 2 concerns, 2 events, 2 gate-log entries, 2 assets

All passwords stored with werkzeug generate_password_hash so
auth_service.check_password_hash() can verify them.

Usage
-----
    python3 database/migrate.py            # normal
    python3 database/migrate.py --force    # re-run DDL even if tables exist
    python3 database/migrate.py --seed     # skip prompt, always seed
    python3 database/migrate.py --no-seed  # skip prompt, never seed
"""

import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ═════════════════════════════════════════════════════════════════════════════

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
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
# SCHEMA  (idempotent DDL)
# ═════════════════════════════════════════════════════════════════════════════

from pathlib import Path

def load_schema_sql():
    sql_file = Path(__file__).with_name("estatehub.sql")

    if not sql_file.exists():
        raise FileNotFoundError(
            f"Schema file not found: {sql_file}"
        )

    return sql_file.read_text(encoding="utf-8")

SCHEMA_SQL = load_schema_sql()

def run_schema(conn):
    import sqlparse
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


# ═════════════════════════════════════════════════════════════════════════════
# DEMO / SEED DATA — moved to database/seed.py (see --seed below).
# ACCOUNTS, SOCIETY, USERS, EVENTS, CONCERNS, ASSETS and all idempotent
# demo-data seeding now live in seed.run_seed(conn), using the same
# society_id=1 identity and the same hardcoded accounts/users migrate.py
# used to seed.
# ═════════════════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="EstateHub DB migration + seed")
    parser.add_argument("--force",   action="store_true",
                        help="Re-run DDL even if tables already exist")
    parser.add_argument("--seed",    action="store_true",
                        help="Always seed demo data without prompting")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip demo data seeding")
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

    # ── Schema ────────────────────────────────────────────────────────────
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

    # ── Seed decision ────────────────────────────────────────────────────
    if args.no_seed:
        print("  Seed skipped (--no-seed).")
        conn.close()
        _summary()
        return

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM societies")
        has_societies = cur.fetchone()["c"] > 0

    if has_societies and not args.seed:
        print(f"  ✓ Societies exist — skipping demo seed.")
        print("    Use --seed to force-add demo data anyway.")
        conn.close()
        _summary()
        return

    if args.seed:
        do_seed = True
    else:
        print()
        print("  First run — no societies found.")
        print("  Seed demo data?  (1 society, 7 users, 50 accounts,")
        print("  2 events, 2 concerns, 2 gate logs, 2 assets)")
        print()
        try:
            ans = input("  Seed demo data? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        do_seed = ans != "n"

    if do_seed:
        try:
            from seed import run_seed  # when run as `python3 database/migrate.py`
        except ImportError:
            from database.seed import run_seed  # when imported as a package
        run_seed(conn)
        conn = None  # run_seed() closes the connection itself
    else:
        print("  Seed skipped.  Log in as master admin to create a society.")

    if conn is not None:
        conn.close()
    _summary()


def _summary():
    print()
    print("═" * 62)
    print("  ✅ Migration complete")
    print("═" * 62)
    print()


if __name__ == "__main__":
    main()
