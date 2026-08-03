#!/usr/bin/env python3
# database/apply_migration_concerns_declined_status.py
"""
ApexEstateHub — apply/rollback the concerns_assigns 'declined' status migration.

Usage
-----
    python3 database/apply_migration_concerns_declined_status.py            # apply
    python3 database/apply_migration_concerns_declined_status.py --rollback # revert
    python3 database/apply_migration_concerns_declined_status.py --dry-run  # print only
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATION_SQL = os.path.join(HERE, "migration_concerns_assigns_declined_status.sql")
ROLLBACK_SQL = os.path.join(HERE, "rollback_concerns_assigns_declined_status.sql")


def _dsn() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        return raw.replace("postgres://", "postgresql://", 1)
    host = os.getenv("PGHOST", "").strip()
    port = os.getenv("PGPORT", "5432").strip() or "5432"
    dbname = os.getenv("PGDATABASE", "").strip()
    user = os.getenv("PGUSER", "").strip()
    pw = os.getenv("PGPASSWORD", "").strip()
    if not (host and dbname and user):
        print("❌ No DATABASE_URL and no PGHOST/PGDATABASE/PGUSER set.")
        sys.exit(1)
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}"


def main():
    parser = argparse.ArgumentParser(description="Apply/rollback concerns_assigns 'declined' status migration")
    parser.add_argument("--rollback", action="store_true", help="revert to the pre-'declined' constraint")
    parser.add_argument("--dry-run", action="store_true", help="print the SQL, don't execute")
    args = parser.parse_args()

    path = ROLLBACK_SQL if args.rollback else MIGRATION_SQL
    label = "ROLLBACK" if args.rollback else "MIGRATION"

    if not os.path.exists(path):
        print(f"❌ {path} not found — place it next to this script.")
        sys.exit(1)

    with open(path, "r") as f:
        sql = f.read()

    if args.dry_run:
        print(f"── {label} ({path}) ──")
        print(sql)
        return

    print("→ Connecting…")
    conn = psycopg2.connect(_dsn())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print(f"→ Applying {label}: {os.path.basename(path)}")
            cur.execute(sql)
        conn.commit()
        print(f"✅ {label} applied successfully.")
    except Exception as e:
        conn.rollback()
        print(f"❌ {label} failed, rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
