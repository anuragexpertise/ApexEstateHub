"""
UP financial-compliance patch: bye-law 7 tested AS AT the cutoff date, s.22 sequencing, transfer types,
transferor-borne fee kept out of common-expense arrears, reserve % read from the society's rule.

Real Postgres only (same convention as test_owner_loan_dues_live.py); every test rolls back.
"""
import os
from datetime import date

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
ELECTION = date(2026, 10, 1)      # FY basis -> cut-off 31 Mar 2026; bills due on/before 30 Jan 2026 are >60 days old
CUTOFF = date(2026, 3, 31)
OLD_DUE = date(2026, 1, 15)


@pytest.fixture()
def cur():
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    c = conn.cursor(cursor_factory=RealDictCursor)
    yield c
    conn.rollback()
    conn.close()


def q1(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchone()


def clean_flat(cur):
    """A flat with no receivables at all, so the test controls every rupee."""
    row = q1(cur, """SELECT a.id FROM apartments a WHERE a.society_id=%s AND a.active
                      AND NOT EXISTS (SELECT 1 FROM receivables r WHERE r.entity_id=a.id AND r.role='apartment')
                    ORDER BY a.id LIMIT 1""", (SOC,))
    if row:
        return row["id"]
    row = q1(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))
    cur.execute("DELETE FROM receivables WHERE entity_id=%s AND role='apartment'", (row["id"],))
    return row["id"]


def bill(cur, apt, amount=1000, due=OLD_DUE, kind="common_expense"):
    acc = q1(cur, "SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,))["id"]
    return q1(cur, """INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount,
                                               interest_amount, amount, due_date, status, charge_kind)
                      VALUES (%s,%s,'apartment',%s,'test bill',%s,0,%s,%s,'pending',%s) RETURNING id""",
              (SOC, apt, acc, amount, amount, due, kind))["id"]


def pay(cur, rec, on, amount=None):
    """Settle a receivable the way the app does (paid_amount + paid_principal), dated `on`."""
    cur.execute("SELECT set_config('app.payment_date', %s, true)", (on.isoformat(),))
    cur.execute("""UPDATE receivables SET paid_amount = amount, paid_principal = amount - interest_amount, status='paid'
                    WHERE id=%s""", (rec,))
    cur.execute("SELECT set_config('app.payment_date', '', true)")


def b7(cur, apt):
    return q1(cur, "SELECT * FROM fn_bye_law7_eligibility(%s,%s) WHERE apartment_id=%s", (SOC, ELECTION, apt))


# ── bye-law 7 is tested as at the cutoff, not today ─────────────────────────────
def test_payment_after_the_cutoff_does_not_cure_the_arrears(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt)
    pay(cur, rec, date(2026, 5, 10))                       # settled AFTER 31 Mar 2026
    row = b7(cur, apt)
    assert row["eligible"] is False and row["overdue_amount"] == 1000   # arrears stood on the cut-off date


def test_payment_before_the_cutoff_clears_it(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt)
    pay(cur, rec, date(2026, 3, 20))
    row = b7(cur, apt)
    assert row["eligible"] is True and row["overdue_amount"] == 0


def test_partial_payment_before_cutoff_leaves_the_remainder(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt, 1000)
    cur.execute("SELECT set_config('app.payment_date', '2026-03-01', true)")
    cur.execute("UPDATE receivables SET paid_amount=400, paid_principal=400, status='partial' WHERE id=%s", (rec,))
    assert b7(cur, apt)["overdue_amount"] == 600


def test_bill_not_yet_60_days_old_at_cutoff_is_ignored(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2026, 3, 1))                   # only 30 days old on 31 Mar
    assert b7(cur, apt)["eligible"] is True


def test_transfer_fee_is_not_a_common_expense_arrear(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 5000, kind="transfer_fee")
    assert b7(cur, apt)["eligible"] is True


def test_payment_log_records_every_settlement_path(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt, 1000)
    cur.execute("UPDATE receivables SET paid_amount=300, paid_principal=300 WHERE id=%s", (rec,))
    cur.execute("UPDATE receivables SET paid_amount=1000 WHERE id=%s", (rec,))     # hand-written: paid_principal untouched
    rows = q1(cur, "SELECT COUNT(*) AS n, SUM(principal_delta) AS p, SUM(total_delta) AS t FROM receivable_payment_log WHERE receivable_id=%s", (rec,))
    assert rows["n"] == 2 and rows["p"] == 1000 and rows["t"] == 1000


# ── standing: transfer fee does not feed the s.22 six-month test ────────────────
def test_unpaid_transfer_fee_alone_does_not_trigger_s22(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 5000, due=date(2025, 1, 1), kind="transfer_fee")
    assert q1(cur, "SELECT s22_blocked FROM fn_get_standing(%s,%s,%s)", (SOC, apt, date(2026, 9, 1)))["s22_blocked"] is True


# ── s.22 sequencing ────────────────────────────────────────────────────────────
def _proceeding(cur, apt, **steps):
    cols = ["society_id", "apartment_id", "service_type", "default_since"] + list(steps)
    vals = [SOC, apt, "water", date(2025, 1, 1)] + list(steps.values())
    ph = ",".join(["%s"] * len(cols))
    return q1(cur, f"INSERT INTO service_cutoff_proceedings ({','.join(cols)}) VALUES ({ph}) RETURNING id", vals)["id"]


def _check(cur, pid, asof=date(2026, 9, 1)):
    return q1(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, asof))


def _full(**over):
    steps = dict(notice_served_on=date(2026, 3, 1), gb_resolution_on=date(2026, 3, 10),
                 copy_sent_to_authority_on=date(2026, 3, 12), copy_sent_to_owner_on=date(2026, 3, 12),
                 display_notice_on=date(2026, 3, 12))
    steps.update(over)
    return steps


def test_s22_clean_sequence_passes(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2025, 1, 10))
    r = _check(cur, _proceeding(cur, apt, **_full()))
    assert r["can_cut_off"] is True, r["blockers"]


def test_s22_resolution_before_notice_period_ends_is_blocked(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2025, 1, 10))
    r = _check(cur, _proceeding(cur, apt, **_full(gb_resolution_on=date(2026, 3, 4))))   # notice 1 Mar + 7d = 8 Mar
    assert r["can_cut_off"] is False and any("precedes the end of the 7-day notice" in b for b in r["blockers"])


def test_s22_copies_dated_before_the_resolution_are_blocked(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2025, 1, 10))
    r = _check(cur, _proceeding(cur, apt, **_full(copy_sent_to_authority_on=date(2026, 3, 9),
                                                  copy_sent_to_owner_on=date(2026, 3, 9), display_notice_on=date(2026, 3, 9))))
    msgs = " | ".join(r["blockers"])
    assert r["can_cut_off"] is False
    assert "competent authority is dated" in msgs and "owner is dated" in msgs and "display is dated" in msgs


def test_s22_appeal_window_runs_from_receipt_when_recorded(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2025, 1, 10))
    pid = _proceeding(cur, apt, **_full(copy_received_by_owner_on=date(2026, 8, 25)))     # arrived late
    r = _check(cur, pid, date(2026, 9, 1))
    assert r["can_cut_off"] is False and any("appeal window open until 2026-09-09" in b for b in r["blockers"])


def test_s22_default_clock_cannot_start_earlier_than_the_books_show(cur):
    apt = clean_flat(cur)
    bill(cur, apt, due=date(2026, 6, 1))                   # oldest unpaid bill is only ~3 months old
    r = _check(cur, _proceeding(cur, apt, **_full()), date(2026, 9, 1))   # typed default_since is 1 Jan 2025
    assert r["can_cut_off"] is False and any("default must exceed 6 months" in b for b in r["blockers"])


# ── transfers ──────────────────────────────────────────────────────────────────
def _transfer(cur, apt, ttype="sale", value=1000000):
    return q1(cur, "SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,'Seller','Buyer',NULL,%s)",
              (SOC, apt, date(2026, 9, 1), value, ttype))


def test_sale_levies_half_percent_as_transfer_fee_kind(cur):
    apt = clean_flat(cur)
    r = _transfer(cur, apt)
    assert r["msg"] == "OK" and r["fee_amount"] == 5000
    assert q1(cur, "SELECT charge_kind FROM receivables WHERE id=%s", (r["receivable_id"],))["charge_kind"] == "transfer_fee"


@pytest.mark.parametrize("ttype", ["gift", "succession"])
def test_gift_and_succession_carry_no_fee(cur, ttype):
    apt = clean_flat(cur)
    r = _transfer(cur, apt, ttype, value=0)
    assert r["msg"].startswith("OK") and r["fee_amount"] == 0 and r["receivable_id"] is None
    assert q1(cur, "SELECT transfer_type FROM apartment_transfers WHERE id=%s", (r["transfer_id"],))["transfer_type"] == ttype


def test_unknown_transfer_type_is_rejected(cur):
    apt = clean_flat(cur)
    assert _transfer(cur, apt, "barter")["msg"].startswith("Error")


# ── reserve % comes from the society's rule ───────────────────────────────────────
def test_reserve_pct_follows_the_regime_parameter(cur):
    cur.execute("UPDATE regime_rule_parameters SET value=10 WHERE regime_code='UP_AOA_2010' AND rule_key='reserve_appropriation_pct'")
    assert cur.rowcount == 1
    r = q1(cur, "SELECT * FROM fn_fy_close_preview(%s,%s)", (SOC, 2025))
    assert float(r["reserve_pct"]) == 10.0
    assert float(q1(cur, "SELECT reserve_pct FROM fn_fy_close_preview(%s,%s,%s)", (SOC, 2025, 40))["reserve_pct"]) == 40.0   # explicit wins
