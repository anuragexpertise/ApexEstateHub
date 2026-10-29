#!/usr/bin/env python3
"""
Phase 5 release gate and assurance status (Gold-Standard Plan v4, tasks 5.4 and the 'audit-grade' rule).

    python scripts/release_check.py gate v2026.11.0 [--max-age 30]   # exit 1 unless 5.4 is recorded for this release
    python scripts/release_check.py status                           # where 5.1 to 5.3 stand; what may be claimed
    python scripts/release_check.py worklist                         # rules and decision types with no opinion (5.2)

The gate needs BOTH checks recorded for the tag: the Income-tax Act 2025 transition and the July 2026 IFMS amendment,
dated within --max-age days. A record with no adviser reference passes but is printed as PROVISIONAL.
Record checks with app.services.assurance.record_release_verification (master only).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import assurance  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("tag")
    g.add_argument("--max-age", type=int, default=30)
    sub.add_parser("status")
    sub.add_parser("worklist")
    a = p.parse_args(argv)

    if a.cmd == "gate":
        res = assurance.release_gate(a.tag, a.max_age)
        for r in res["items"]:
            flag = "OK  " if r["ok"] else "FAIL"
            prov = " [PROVISIONAL: no adviser reference]" if r["provisional"] and r["checked_on"] else ""
            print(f"{flag} {r['item']}: {r['outcome'] or '-'} on {r['checked_on'] or '-'}{prov}" + (f" ({r['reason']})" if r["reason"] else ""))
        print("release gate:", "PASS" if res["ok"] else "FAIL", "(provisional)" if res["ok"] and res["provisional"] else "")
        return 0 if res["ok"] else 1
    if a.cmd == "status":
        s = assurance.status()
        print(s["label"])
        for t in s["tasks"]:
            print(f"  {t['task']} {'done' if t['satisfied'] else 'OUTSTANDING'}: {t['label']}")
        print("  rules/decision types without an opinion:", s["rules_without_opinion"])
        return 0 if s["audit_grade_allowed"] else 1
    for r in assurance.rules_without_opinion():
        print(f"{r['subject_kind']:13} {r['regime_code'] or '-':14} {r['subject_key']:34} {r['assurance_state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
