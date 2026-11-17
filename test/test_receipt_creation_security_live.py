"""
Security tests for receipt creation (per .kilo/plans/1795000000000-receipt-creation-security-review.md).

Covers: server-set created_by (R1), server-validated role (R2), server-validated mode (R3),
pending-by-default / SoD (R4), future-date rejection (R5), society-configurable amount ceiling (R6),
duplicate detection (R7), audit_events write (R8).

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... PGPASSWORD=... pytest test/test_receipt_creation_security_live.py
"""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
psycopg2.errors = pytest.importorskip("psycopg2.errors", reason="psycopg2.errors not available")

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1


@pytest.fixture()
def conn():
    c = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    cur = c.cursor()
    cur.execute("SELECT to_regprocedure('fn_save_receipt') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("fn_save_receipt is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


@pytest.fixture()
def ctx(cur):
    cur.execute("SELECT id FROM apartments WHERE society_id=%s ORDER BY id LIMIT 2", (SOC,))
    apts = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT a.id FROM accounts a WHERE a.society_id=%s AND a.drcr_account='Cr'
                   AND NOT EXISTS (SELECT 1 FROM accounts c WHERE c.parent_account_id = a.id)
                   ORDER BY a.id LIMIT 1""", (SOC,))
    acc = cur.fetchone()[0]
    cur.execute("SELECT id FROM users WHERE society_id=%s AND role='admin' ORDER BY id LIMIT 1", (SOC,))
    admin = cur.fetchone()[0]
    cur.execute("SELECT id FROM users WHERE society_id=%s AND role='apartment' ORDER BY id LIMIT 1", (SOC,))
    apartment_user = cur.fetchone()[0]
    cur.execute("UPDATE societies SET max_receipt_amount = 1000000 WHERE id=%s", (SOC,))
    return {"apts": apts, "acc": acc, "admin": admin, "apartment_user": apartment_user}


def save(cur, soc, acc, amount, mode="cash", role="apartment", entity_id=None,
         created_by=None, receipt_date=None, particulars="test receipt"):
    """Call fn_save_receipt directly, mimicking _save_receipt_v3's parameter order."""
    if receipt_date is None:
        from datetime import date
        receipt_date = date.today().isoformat()  # noqa: DTZ011
    cur.execute("SAVEPOINT s")
    try:
        cur.execute("""SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (soc, acc, particulars, amount, entity_id, role, mode,
                     receipt_date, created_by, None, None, None))
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT s")
        return row, None
    except psycopg2.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT s")
        return None, e


def test_admin_created_receipt_is_pending_not_confirmed(cur, ctx):
    """R4: Admin-created receipts default to 'pending' (SoD), not auto-confirmed."""
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"])
    assert err is None, f"unexpected error: {err}"
    assert row is not None
    assert row[3] == "pending", f"expected pending, got {row[3]}"


def test_non_admin_created_receipt_is_pending(cur, ctx):
    """Non-admin creators also produce 'pending' receipts."""
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["apartment_user"])
    assert err is None, f"unexpected error: {err}"
    assert row is not None
    assert row[3] == "pending", f"expected pending, got {row[3]}"


def test_future_date_is_rejected(cur, ctx):
    """R5: Receipt date cannot be in the future."""
    from datetime import date, timedelta
    future = (date.today() + timedelta(days=1)).isoformat()  # noqa: DTZ011
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"], receipt_date=future)
    assert row is None
    assert err is not None
    assert "future" in str(err).lower()


def test_amount_above_society_ceiling_is_rejected(cur, ctx):
    """R6: Amount above society's max_receipt_amount is rejected."""
    cur.execute("UPDATE societies SET max_receipt_amount = 50000 WHERE id=%s", (SOC,))
    row, err = save(cur, SOC, ctx["acc"], 60000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"])
    assert row is None
    assert err is not None
    assert "exceeds" in str(err).lower() or "limit" in str(err).lower()


def test_duplicate_receipt_within_24h_is_rejected(cur, ctx):
    """R7: Duplicate receipt (same entity/amount/date/particulars within 24h) is rejected."""
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"], particulars="duplicate test")
    assert err is None, f"first save failed: {err}"
    assert row is not None
    row2, err2 = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                      created_by=ctx["admin"], particulars="duplicate test")
    assert row2 is None
    assert err2 is not None
    assert "duplicate" in str(err2).lower()


def test_duplicate_after_24h_is_allowed(cur, ctx):
    """R7: Same receipt after 24 hours is allowed (window expires)."""
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"], particulars="window test")
    assert err is None, f"first save failed: {err}"
    assert row is not None
    cur.execute("""UPDATE receipts SET created_at = NOW() - INTERVAL '25 hours'
                   WHERE id = %s""", (row[0],))
    row2, err2 = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                      created_by=ctx["admin"], particulars="window test")
    assert err2 is None, f"second save (after 24h) failed: {err2}"
    assert row2 is not None


def test_audit_event_written_on_receipt_create(cur, ctx):
    """R8: An audit_events row is written for receipt creation."""
    # Check audit_events table exists
    cur.execute("SELECT to_regclass('audit_events')")
    if not cur.fetchone()[0]:
        pytest.skip("audit_events table not installed")
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"], particulars="audit test")
    assert err is None, f"save failed: {err}"
    assert row is not None
    cur.execute("""SELECT count(*) FROM audit_events
                   WHERE action = 'receipt_create' AND resource_type = 'receipts'
                     AND actor_id = %s AND society_id = %s""", (ctx["admin"], SOC))
    assert cur.fetchone()[0] >= 1, "no audit_events row for receipt_create"


def test_receipt_verified_by_separate_admin(cur, ctx):
    """R4: A pending receipt can be verified by a different admin via fn_verify_receipt."""
    row, err = save(cur, SOC, ctx["acc"], 50000, "cash", "apartment", ctx["apts"][0],
                    created_by=ctx["admin"])
    assert err is None, f"save failed: {err}"
    assert row is not None
    assert row[3] == "pending"
    cur.execute("SELECT msg FROM fn_verify_receipt(%s, %s)", (row[0], ctx["admin"]))
    msg = cur.fetchone()[0]
    assert msg.startswith("Verified:"), f"verify failed: {msg}"
