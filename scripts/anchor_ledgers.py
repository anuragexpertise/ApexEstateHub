#!/usr/bin/env python3
"""
Anchor and sign every society's ledger hash chain (see app/security/ledger_anchor.py).

Run it on a schedule (daily or monthly), as the restricted application login (see database/app_role.py). Each anchor is signed with the society's
SIGNING_LEDGER key (needs SECRET_VAULT_KEY in the environment):

    python scripts/anchor_ledgers.py            # anchor all societies
    python scripts/anchor_ledgers.py --verify   # also verify every stored anchor's signature

Exit status is non-zero if any society failed to anchor (a chain that does not verify is never anchored) or
any signature fails to verify, so the scheduler raises the alarm.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.security import ledger_anchor  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true", help="also verify every stored anchor's signature")
    args = ap.parse_args()
    bad = 0
    for r in ledger_anchor.anchor_all():
        if r["ok"]:
            a = r["anchor"]
            print(f"society {r['society_id']}: anchored seq {a['ledger_seq']} ({a['row_count']} entries) head {a['head_hash'][:16]}...")
        else:
            bad += 1
            print(f"society {r['society_id']}: FAILED - {r['error']}", file=sys.stderr)
    if args.verify:
        for p in ledger_anchor.verify_signatures():
            bad += 1
            print(f"anchor {p['anchor_id']} (society {p['society_id']}): {p['problem']}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
