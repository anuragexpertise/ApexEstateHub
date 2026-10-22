#!/usr/bin/env python3
"""
One-off, idempotent upgrade for a database installed BEFORE the Team Logins screen.

  users.active BOOLEAN NOT NULL DEFAULT TRUE  - FALSE switches a login off (cannot sign in; an open session ends).

database/estatehub.sql already carries the column for new installs. The Python code runs without it (it just cannot
disable a login yet), so deploy order does not matter, but run this once to turn the feature on. Also fixes the
Accountant / Supervisor / Staff lists and KPI cards, which read users.active.

    python3 scripts/migrate_team_logins_2026_10.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main() -> None:
    from database.db_manager import db
    with db._conn() as conn:
        conn.cursor().execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
    print("users.active is in place.")


if __name__ == "__main__":
    main()
