"""
ApexEstateHub Database Reset Utility
====================================

WARNING:
    This script DESTROYS all data in the database.

Usage:
    python3 database/reset_database.py
    python3 database/reset_database.py --yes
    python3 database/reset_database.py --sql dashestatehub.sql
    python3 database/reset_database.py --yes --after seed   # non-interactive

Steps:
    1. Connect to PostgreSQL
    2. Drop and recreate the public schema (the actual "reset")
    3. Ask what to do next:
         1) Run Schema only
         2) Run Schema & seed
         3) None — leave blank database
    4. (unless "None") Execute estatehub.sql, optionally seed, then verify
       tables/functions/views

estatehub.sql declares no IF NOT EXISTS / DROP IF EXISTS guards, so it is
written to install onto the empty schema created in step 2 and nowhere else.
That is what makes this script the from-scratch path:

    python3 database/reset_database.py --yes --after seed
"""

import os
import sys
import argparse
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv, dotenv_values

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import connection_params, describe_target  # noqa: E402


# ------------------------------------------------------------------
# Load .env
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# Resolved once, here, and reused everywhere below (schema install, seed
# handoff, validation) so all three provably hit the same database. The
# precedence rules live in db_config.
_P = connection_params()
DB_HOST = _P.get("host")
DB_PORT = _P.get("port")
DB_NAME = _P.get("dbname")
DB_USER = _P.get("user")
DB_PASSWORD = _P.get("password")
SSL_MODE = _P.get("sslmode")
SSL_ROOT_CERT = _P.get("sslrootcert")

if DB_HOST is None:
    # DATABASE_URL-only configuration: fall back to the individual values for
    # the psql subprocess, which cannot take a URL in place of these flags.
    _u = dotenv_values(BASE_DIR / ".env")
    DB_HOST = _u.get("PGHOST")
    DB_PORT = int(_u.get("PGPORT") or 5432)
    DB_NAME = _u.get("PGDATABASE")
    DB_USER = _u.get("PGUSER")
    DB_PASSWORD = _u.get("PGPASSWORD")
    SSL_MODE = _u.get("PGSSLMODE") or "require"
    SSL_ROOT_CERT = _u.get("PGSSLROOTCERT")


# ------------------------------------------------------------------
# Connect
# ------------------------------------------------------------------

def connect():
    """Plain cursor connection — validate() below uses positional access."""
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER,
        password=DB_PASSWORD, sslmode=SSL_MODE,
        **({"sslrootcert": SSL_ROOT_CERT}
           if SSL_ROOT_CERT and SSL_MODE != "disable" else {}),
    )


# ------------------------------------------------------------------
# Execute SQL Script
# ------------------------------------------------------------------

def execute_sql_file(conn, sql_file):
    if not os.path.isfile(sql_file):
        raise FileNotFoundError(f"Schema file not found: {sql_file}")

    print("\nRunning schema file via psql...")
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
        conn.commit()

    import subprocess
    env = os.environ.copy()
    if DB_PASSWORD:
        env["PGPASSWORD"] = DB_PASSWORD
    
    cmd = [
        "psql",
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-U", DB_USER,
        "-d", DB_NAME,
        "-v", "ON_ERROR_STOP=1",
        "-q",
        "-f", str(sql_file)
    ]
    
    try:
        res = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        print("✓ DDL executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\nFAILED to execute schema:\n{e.stderr}")
        raise


# ------------------------------------------------------------------
# Post-reset action: schema only / schema + seed / leave blank
# ------------------------------------------------------------------

_ACTION_LABELS = {
    "schema": "Run Schema only",
    "seed":   "Run Schema & seed",
    "none":   "None — leave blank database",
}


def prompt_post_reset_action(args) -> str:
    """Returns 'schema', 'seed', or 'none'. Non-interactive via --after;
    otherwise prompts, same as reset's own --yes/RESET confirmation does
    for the destructive step itself."""
    if args.after:
        return args.after

    print()
    print("  What would you like to do next?")
    print("    1) Run Schema only")
    print("    2) Run Schema & seed")
    print("    3) None — leave blank database")
    print()
    try:
        choice = input("  Choice [1-3, default 1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "1"
    return {"1": "schema", "2": "seed", "3": "none", "": "schema"}.get(choice, "schema")


def seed_connect():
    """Opens the seed connection against THIS script's target database.

    Deliberately not seed.py's get_conn(): the two resolved their targets
    independently, so with a DATABASE_URL in .env this script dropped the
    schema from the PG* database while the seed wrote to the DATABASE_URL one
    (observed as a fresh local reset followed by every seed step reporting
    "already exists" against the remote). Both now go through db_config, so the
    reset and the seed provably hit one database.

    RealDictCursor is required: every function in seed.py reads rows by column
    name (row["id"], row["linked_id"], ...).
    """
    return psycopg2.connect(
        **connection_params(),
        cursor_factory=psycopg2.extras.RealDictCursor,
        connect_timeout=20,
        options="-c lock_timeout=15000 -c statement_timeout=180000",
    )


def run_seed_demo_data(conn):
    """Delegates to database/seed.py's run_seed(conn), which commits and
    closes `conn` itself (same contract migrate.py's --seed flow relies
    on) — the caller must not touch `conn` again after this returns.

    Does not reuse the `conn` passed in: validate() below needs plain
    positional/tuple access, whereas every function in seed.py needs
    named-column access, which only works on a connection opened with
    cursor_factory=RealDictCursor. So this closes the first connection and
    opens a fresh one via seed_connect(), which targets the same database.
    """
    conn.close()

    try:
        from seed import run_seed
    except ImportError:
        from database.seed import run_seed

    seed_conn = seed_connect()

    try:
        run_seed(seed_conn)
    except psycopg2.errors.LockNotAvailable:
        print()
        print("  ❌  Seeding stopped: timed out waiting for a database lock.")
        print("      Something else is holding a lock on a table this script")
        print("      needs — most likely another connection to the same DB")
        print("      (e.g. the live app, or a previous migrate.py/seed.py run")
        print("      that was interrupted mid-transaction and left idle).")
        print("      Run this in psql / Aiven console to find and end it:")
        print()
        print("        SELECT pid, state, query_start, state_change, query")
        print("        FROM pg_stat_activity")
        print("        WHERE datname = current_database() AND pid <> pg_backend_pid()")
        print("          AND state <> 'idle'")
        print("        ORDER BY query_start;")
        print()
        print("      Idle-in-transaction sessions are the usual culprit —")
        print("      SELECT pg_terminate_backend(<pid>) to clear one, then re-run.")
        seed_conn.rollback()
        seed_conn.close()
        sys.exit(1)
    except psycopg2.errors.QueryCanceled:
        print()
        print("  ❌  Seeding stopped: a statement exceeded its timeout.")
        print("      This is a slower failure than a lock wait — check whether")
        print("      the DB itself is under load, or a single statement is")
        print("      doing far more work than expected.")
        seed_conn.rollback()
        seed_conn.close()
        sys.exit(1)


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

def validate(cursor):

    print("\nValidating installation...")

    cursor.execute("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema='public'
    """)
    table_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM information_schema.views
        WHERE table_schema='public'
    """)
    view_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM pg_proc p
        JOIN pg_namespace n
            ON n.oid = p.pronamespace
        WHERE n.nspname='public'
    """)
    function_count = cursor.fetchone()[0]

    print(f"✓ Tables    : {table_count}")
    print(f"✓ Views     : {view_count}")
    print(f"✓ Functions : {function_count}")

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY table_name
    """)

    print("\nTables:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--sql",
        default="database/estatehub.sql",
        help="Schema file"
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the RESET confirmation prompt"
    )

    parser.add_argument(
        "--after",
        choices=["schema", "seed", "none"],
        default=None,
        help="Skip the post-reset prompt: 'schema' (schema only), "
             "'seed' (schema + demo data), or 'none' (leave blank)."
    )

    args = parser.parse_args()

    sql_file = Path(args.sql)

    if not sql_file.exists():
        print(f"ERROR: SQL file not found: {sql_file}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("ApexEstateHub Database Reset")
    print("=" * 70)

    print(f"Host     : {DB_HOST}:{DB_PORT}")
    print(f"Database : {DB_NAME}")
    print(f"User     : {DB_USER}")
    print(f"Schema   : {sql_file}")

    if not args.yes:
        confirm = input(
            "\nWARNING: ALL DATA WILL BE DELETED.\n"
            "Type RESET to continue: "
        )

        if confirm != "RESET":
            print("Cancelled.")
            sys.exit(0)

    conn = None

    try:
        conn = connect()
        conn.autocommit = False

        cur = conn.cursor()

        print("\n✓ Connected")

        print("\nDropping public schema objects...")

        cur.execute("DROP SCHEMA public CASCADE;")
        conn.commit()

        cur.execute("CREATE SCHEMA public AUTHORIZATION CURRENT_USER;")
        conn.commit()

        print("✓ Fresh public schema created")

        action = prompt_post_reset_action(args)
        print(f"\n→ {_ACTION_LABELS[action]}")

        if action == "none":
            conn.close()
            conn = None
            print("\n" + "=" * 70)
            print("DATABASE RESET SUCCESSFUL — blank database (no schema installed)")
            print("=" * 70)
            print("Run this script again (or database/migrate.py) when you're")
            print("ready to install the schema.")
            return

        execute_sql_file(conn, sql_file)

        if action == "seed":
            # run_seed_demo_data() commits and closes `conn` itself (same
            # contract migrate.py's --seed flow relies on) — do not reuse
            # `conn`/`cur` after this call. validate() below reconnects
            # with a fresh connection specifically because of this.
            run_seed_demo_data(conn)
            conn = None

        # Reconnect for validation regardless of path taken above, since
        # a 'seed' action already closed the original connection and a
        # fresh one keeps this step uniform across both remaining actions
        # rather than conditionally reusing a maybe-closed cursor.
        conn = connect()
        cur = conn.cursor()
        validate(cur)

        print("\n" + "=" * 70)
        print("DATABASE RESET SUCCESSFUL")
        print("=" * 70)

    except Exception as e:

        if conn:
            # run_seed_demo_data() closes `conn` itself, so by the time a seed
            # failure reaches here the rollback raised InterfaceError and
            # replaced the real traceback with "connection already closed".
            try:
                conn.rollback()
            except psycopg2.Error:
                pass

        print("\nERROR")
        print("-" * 70)
        print(str(e))
        print("-" * 70)

        sys.exit(1)

    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
