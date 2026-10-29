"""
Plan v4, C.2 -- the seeded demo society passes its own checks.

A fresh seeded database must not fail the tie-out or the compliance certificate. Two things used to make them fail:
the 12 asset / instrument / deposit expenses were posted to the ledger under the asset or deposit (so the expense
tie-out found "no ledger line"), and the seed recorded no ledger anchor.

Live tests against a REAL Postgres, read-only.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_seed_selfcheck_live.py
"""
import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

SOC = 1


def _db():
    from database.db_manager import db
    return db


def test_every_tieout_comparison_passes():
    from app.services import auditor_checks as ac
    r = ac.run("tieout", SOC)
    bad = [row for row in r["rows"] if not row[4] in (True, "True")]
    assert r["status"] == "pass", f"{r['note']} {bad}"


def test_expense_tieout_reads_purchases_not_later_sales():
    """The tie-out compares an asset purchase with its debit only: a sale of the asset (a credit to the same
    account) must neither hide a missing purchase nor make a correct one differ."""
    rows = _db()._execute(
        "SELECT ok, detail FROM fn_tieout_report(%s, %s) WHERE check_key = 'expenses_vs_ledger'", (SOC, 2026), fetch_all=True)
    assert rows and rows[0]["ok"], rows
    sold = _db()._execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE society_id = %s AND source_table = 'assets' AND entry_side = 'Cr' "
        "AND acc_particulars ILIKE 'Asset disposed%%'", (SOC,), fetch_one=True)["n"]
    assert sold >= 1, "the seed should include at least one disposed asset for this to prove anything"


def test_seed_records_a_signed_anchor_that_verifies():
    from app.security import ledger_anchor
    anchors = _db()._execute(
        "SELECT signature FROM ledger_chain_anchors WHERE society_id = %s", (SOC,), fetch_all=True)
    assert anchors, "the seed must record a ledger anchor"
    assert all(a["signature"] for a in anchors)
    assert ledger_anchor.verify_signatures(SOC) == []


def test_certificate_has_no_failing_check_on_a_fresh_seed():
    from app.services import compliance_certificate as cc
    c = cc.collect(SOC)
    failing = [x for x in c["checks"] if x["result"] == "fail"]
    assert not failing, failing
    assert c["overall"] in ("pass", "exceptions")
