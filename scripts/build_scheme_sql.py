#!/usr/bin/env python3
"""Regenerate (or --check) the scheme-pack block of database/estatehub.sql from schemes/*.toml.

    python scripts/build_scheme_sql.py          # rewrite the block in place
    python scripts/build_scheme_sql.py --check  # exit 1 if the block is stale (CI / pre-commit)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from schemes.loader import BEGIN_MARK, END_MARK, load_all, render_sql  # noqa: E402

SQL = ROOT / "database" / "estatehub.sql"


def main() -> int:
    text = SQL.read_text(encoding="utf-8")
    a, b = text.find(BEGIN_MARK), text.find(END_MARK)
    if a < 0 or b < 0:
        print("generated-block markers not found in estatehub.sql", file=sys.stderr)
        return 2
    new = text[:a] + render_sql(load_all()) + text[b + len(END_MARK):]
    if "--check" in sys.argv:
        if new != text:
            print("database/estatehub.sql is out of date: run python scripts/build_scheme_sql.py", file=sys.stderr)
            return 1
        print("scheme block is up to date")
        return 0
    SQL.write_text(new, encoding="utf-8")
    print("scheme block regenerated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
