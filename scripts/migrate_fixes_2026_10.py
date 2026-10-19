#!/usr/bin/env python3
"""
One-off, idempotent upgrade for a database installed BEFORE these two SQL fixes (database/estatehub.sql already
carries them for new installs):

  1. fn_verify_receipt_chain - "column reference receipt_number is ambiguous" (broke Auditor checks 5 / 5b).
  2. fn_entrance_fee_due     - referenced an undefined alias `o` (the alias is `oa`).

The function bodies are read from estatehub.sql itself, so there is one definition. CREATE OR REPLACE keeps the
signatures, so nothing that calls them needs to change. Safe to run twice; one transaction, any error rolls back.

    python3 scripts/migrate_fixes_2026_10.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SCHEMA = Path(__file__).resolve().parent.parent / "database" / "estatehub.sql"
FUNCTIONS = ("fn_verify_receipt_chain", "fn_entrance_fee_due")


def function_sql(sql_text: str, name: str) -> str:
    """The CREATE OR REPLACE FUNCTION statement for `name`, from its header to the closing $$;."""
    m = re.search(rf"CREATE OR REPLACE FUNCTION {name}\(.*?\n\$\$;", sql_text, flags=re.S)
    if not m:
        raise SystemExit(f"{name} not found in {SCHEMA}")
    return m.group(0)


def main() -> None:
    text = SCHEMA.read_text(encoding="utf-8")
    statements = [function_sql(text, n) for n in FUNCTIONS]
    from database.db_manager import db
    with db._conn() as conn:
        cur = conn.cursor()
        for stmt in statements:
            cur.execute(stmt)
    print("Replaced: " + ", ".join(FUNCTIONS))


if __name__ == "__main__":
    main()
