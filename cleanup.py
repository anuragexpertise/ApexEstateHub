#!/usr/bin/env python3
# cleanup.py
"""
Remove redundant, backup and superseded files from the EstateHub project.

Run from project root:
    python3 cleanup.py [--dry-run]
"""

import os
import sys
import argparse
from pathlib import Path

# ── Files to delete unconditionally ──────────────────────────────────────────
REDUNDANT_FILES = [
    # Old login system
    "app/dash_apps/pages/login_systemOLD.py",
    "app/dash_apps/pages/login_system_old.py",
    "app/dash_apps/pages/society_select.py",
    "app/dash_apps/pages/login_page.py",

    # Backup / temp files
    "app/dash_apps/app_shell.py.bak",
    "app/dash_apps/__init__.py.bak",
    "app/dash_apps/callbacks/__init__.py.bak",
    "app/dash_apps/callbacks/shell_callbacks.py.bak",
    "app/dash_apps/callbacks/login_callbacks.py.bak",

    # Old / fixed KPI cards
    "app/dash_apps/pages/kpi_cards_FIXED.py",
    "app/dash_apps/pages/kpi_cards_old.py",
    "app/dash_apps/pages/card_catalogue_old.py",

    # Old portal pages (replaced by portal_pages.py)
    "app/dash_apps/pages/admin_portal.py",
    "app/dash_apps/pages/owner_portal.py",
    "app/dash_apps/pages/vendor_portal.py",
    "app/dash_apps/pages/security_portal.py",
    "app/dash_apps/pages/master_portal.py",
    "app/dash_apps/pages/master_admin.py",

    # Old / duplicate callback files
    "app/dash_apps/callbacks/card_catalogue_callbacks_FIXED.py",
    "app/dash_apps/callbacks/card_catalogue_callbacks_old.py",

    # Old seed
    "database/seed.py",        # replaced by migrate.py --seed

    # Pycache / pyc handled separately via glob
]

# ── Patterns to delete recursively ───────────────────────────────────────────
REDUNDANT_PATTERNS = [
    "**/__pycache__",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.py.bak",
    "**/*.py.orig",
    "**/*.py.old",
]


def _delete(path: Path, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if dry_run:
        print(f"  [dry] would delete: {path}")
        return True
    try:
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"  ✓ deleted: {path}")
        return True
    except Exception as exc:
        print(f"  ✗ error deleting {path}: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without deleting")
    args = parser.parse_args()

    root = Path(__file__).parent
    deleted = 0

    print()
    print("EstateHub — cleanup redundant files")
    print("=" * 42)

    # Explicit files
    for rel in REDUNDANT_FILES:
        p = root / rel
        if _delete(p, args.dry_run):
            deleted += 1

    # Pattern matches
    for pat in REDUNDANT_PATTERNS:
        for p in sorted(root.glob(pat)):
            if _delete(p, args.dry_run):
                deleted += 1

    print()
    action = "would delete" if args.dry_run else "deleted"
    print(f"  {action} {deleted} file(s)/dir(s)")
    if args.dry_run:
        print("  Run without --dry-run to actually delete.")
    print()


if __name__ == "__main__":
    main()
