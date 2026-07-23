"""
ApexEstateHub Database Reset Utility
====================================

WARNING:
    This script DESTROYS all data in the database.

Usage:
    python3 database/reset_database.py
    python3 database/reset_database.py --yes
    python3 database/reset_database.py --sql dashestatehub.sql

Steps:
    1. Connect to PostgreSQL
    2. Execute estatehub.sql (idempotent)
    3. Verify tables/functions/views
"""

import os
import sys
import argparse
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


# ------------------------------------------------------------------
# Load .env
# ------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("PGHOST")
DB_PORT = int(os.getenv("PGPORT", "5432"))
DB_NAME = os.getenv("PGDATABASE")
DB_USER = os.getenv("PGUSER")
DB_PASSWORD = os.getenv("PGPASSWORD")

SSL_MODE = os.getenv("PGSSLMODE", "require")
SSL_ROOT_CERT = os.getenv("PGSSLROOTCERT")


# ------------------------------------------------------------------
# Connect
# ------------------------------------------------------------------

def connect():
    params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "sslmode": SSL_MODE,
    }

    if SSL_ROOT_CERT:
        params["sslrootcert"] = SSL_ROOT_CERT

    return psycopg2.connect(**params)


# ------------------------------------------------------------------
# Execute SQL Script
# ------------------------------------------------------------------

def execute_sql_file(cursor, sql_file):
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    print("\nRunning schema file...")
    cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    cursor.execute(sql)
    print("✓ Schema executed")


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
        help="Skip confirmation"
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

        cur.execute("""
            DROP SCHEMA public CASCADE;
        """)

        cur.execute("""
            CREATE SCHEMA public AUTHORIZATION CURRENT_USER;
        """)

        print("✓ Fresh public schema created")

        execute_sql_file(cur, sql_file)

        validate(cur)

        conn.commit()

        print("\n" + "=" * 70)
        print("DATABASE RESET SUCCESSFUL")
        print("=" * 70)

    except Exception as e:

        if conn:
            conn.rollback()

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
