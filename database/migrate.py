#!/usr/bin/env python3
# database/migrate.py
"""
Install the schema: database/estatehub.sql is the ONLY schema file and every install is a fresh one.

There is no upgrade path and no backward compatibility. The file is applied as ONE transaction onto an EMPTY
database (any error rolls everything back); a database that already has tables is refused. To start over:

    python3 database/reset_database.py --yes --after seed

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


def main() -> None:
    ap = argparse.ArgumentParser(description="Fresh EstateHub install (+ optional demo seed)")
    ap.add_argument("--seed", action="store_true", help="also load the demo data")
    args = ap.parse_args()

    print(f"Target: {describe_target()}")
    conn = psycopg2.connect(**connection_params(), cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = 'public'")
            if cur.fetchone()["n"]:
                sys.exit("Database is not empty. Installs are always fresh: run "
                         "`python3 database/reset_database.py --yes --after seed`.")
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
