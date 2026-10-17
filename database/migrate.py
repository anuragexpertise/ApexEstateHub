#!/usr/bin/env python3
# database/migrate.py
"""
Install database/estatehub.sql (the single source of truth for the schema) and
optionally the demo seed.

The file is applied as ONE transaction onto an EMPTY database: any error rolls
everything back and nothing is half-installed. To start over use
`database/reset_database.py --yes --after seed`.

    python3 database/migrate.py            # schema only
    python3 database/migrate.py --seed     # schema + demo data
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(override=False)
from db_config import connection_params, describe_target  # noqa: E402

SCHEMA_FILE = Path(__file__).with_name("estatehub.sql")


def connect():
    return psycopg2.connect(**connection_params(), cursor_factory=psycopg2.extras.RealDictCursor)


def main() -> None:
    parser = argparse.ArgumentParser(description="EstateHub schema (+ optional demo seed)")
    parser.add_argument("--seed", action="store_true", help="also load the demo data")
    args = parser.parse_args()

    print(f"Target: {describe_target()}")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        sys.exit(f"Schema install failed and was rolled back: {exc}")
    print("Schema installed.")

    if args.seed:
        from seed import run_seed
        run_seed(conn)          # commits and closes the connection itself
        return
    conn.close()


if __name__ == "__main__":
    main()
