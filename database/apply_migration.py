#!/usr/bin/env python3
# database/apply_migration.py
"""
Apply the incremental migrations in database/migrations/ to an EXISTING database.

database/migrate.py only does fresh installs on an empty database. The files here are written idempotently
(IF NOT EXISTS / guarded UPDATEs), so running them twice is safe. Each file runs in its own transaction.

    python3 database/apply_migration.py                 # every file in database/migrations/, in name order
    python3 database/apply_migration.py 002             # only files whose name starts with 002
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from dotenv import load_dotenv

load_dotenv(override=False)
from db_config import connection_params, describe_target  # noqa: E402

MIGRATIONS = Path(__file__).with_name("migrations")


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply idempotent SQL migrations to an existing EstateHub database")
    ap.add_argument("prefix", nargs="?", default="", help="only files whose name starts with this (e.g. 002)")
    args = ap.parse_args()
    files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.name.startswith(args.prefix))
    if not files:
        sys.exit(f"No migration files match '{args.prefix}' in {MIGRATIONS}")
    print(f"Target: {describe_target()}")
    conn = psycopg2.connect(**connection_params())
    try:
        for f in files:
            try:
                with conn.cursor() as cur:
                    cur.execute(f.read_text(encoding="utf-8"))
                conn.commit()
                print(f"applied  {f.name}")
            except Exception as exc:                      # noqa: BLE001
                conn.rollback()
                sys.exit(f"FAILED   {f.name}: {exc}\n(rolled back; later files were not run)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
