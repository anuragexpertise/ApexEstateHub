"""
Phase 1 leftovers (Gold-Standard Plan v3): task 1.5 disputed / under-protest bills, task 1.8 Sec 44AB flag,
task 1.9 interest wording and "no resolved rate = no interest".

Real Postgres only (same convention as the other *_live.py suites): load database/estatehub.sql, run
database/seed.py, set PG* and ESTATEHUB_LIVE_TESTS=1. Every test runs in one connection that is rolled back.
"""
import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
RATE = 2          # % per month
REF = "GBM-2026/04"


@pytest.fixture()
def cur():
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    c = conn.cursor(cursor_factory=RealDictCursor)
    yield c
    conn.rollback()
    conn.close()


def q1(cur, sql, params=()):
    cur.execute(sql, params)
    r = cur.fetchone()
    return r


def refused(cur, sql, params=()):
    """Run a statement that must be refused; return the message and keep the test transaction usable."""
    cur.execute("SAVEPOINT refusal")
    try:
        cur.execute(sql, params)
    except psycopg2.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT refusal")
        return str(e)
    cur.execute("RELEASE SAVEPOINT refusal")
    pytest.fail("expected the database to refuse: " + sql)


def admin(cur):
    return q1(cur, "SELECT id FROM users WHERE role='admin' AND society_id=%s LIMIT 1", (SOC,))["id"]


def flat(cur):
    apt = q1(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))["id"]
    cur.execute("DELETE FROM receivables WHERE entity_id=%s AND role='apartment'", (apt,))
    return apt


def acc(cur, name):
    return q1(cur, "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE %s ORDER BY id LIMIT 1", (SOC, name))["id"]


def set_interest_rule(cur, rate=RATE, ref=REF):
    """The society-wide charges row is the resolved rate (bye-law 46(a)); open it from the beginning of time."""
    cur.execute("""UPDATE apt_charges_fines_basis SET apt_interest_pct=%s, interest_resolution_ref=%s, charges_interest=TRUE,
                          apt_status=TRUE, start_date=DATE '2000-01-01', end_date=NULL
                    WHERE society_id=%s AND apt_id IS NULL""", (rate, ref, SOC))
    assert cur.rowcount == 1


def bill(cur, apt, amount=1000, days_overdue=95, accrue=True):
    income = acc(cur, "Society Maintenance Charge")
    due = date.today() - timedelta(days=days_overdue)
    rid = q1(cur, """INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount, interest_amount,
                                              amount, due_date, status, charge_kind)
                     VALUES (%s,%s,'apartment',%s,'Maintenance',%s,0,%s,%s,'pending','common_expense') RETURNING id""",
             (SOC, apt, income, amount, amount, due))["id"]
    if accrue:
        cur.execute("SELECT fn_post_receivable_accrual(%s,%s,%s,'apartment',%s,%s,'Maintenance')", (SOC, rid, apt, income, amount))
    return rid


def rec(cur, rid):
    return q1(cur, "SELECT * FROM receivables WHERE id=%s", (rid,))


def raise_dispute(cur, rid, reason="Charged for a flat that was vacant", ref="MC-2026/11"):
    return q1(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,%s,%s) AS id", (SOC, rid, admin(cur), reason, ref))["id"]


def decide(cur, did, outcome, reason="Committee decided", ref="MC-2026/12"):
    return q1(cur, "SELECT fn_decide_receivable_dispute(%s,%s,%s,%s,%s,%s) AS msg", (SOC, did, outcome, admin(cur), reason, ref))["msg"]


# ══════════════════════ task 1.9: interest wording, and no resolved rate = no interest ══════════════════════════
@pytest.mark.parametrize("rate, shown", [(1.75, "1.75"), (2, "2"), (2.5, "2.5"), (10, "10")])
def test_interest_basis_text_uses_the_agreed_wording(cur, rate, shown):
    t = q1(cur, "SELECT fn_interest_basis_text(%s::numeric, %s) AS t", (rate, "GBM-7"))["t"]
    assert t == f"Simple Interest - Bye-law 46(a) - Rate {shown}% via Resolution GBM-7 by GBM"


def test_interest_accrues_at_the_resolved_rate_and_carries_the_wording(cur):
    apt = flat(cur)
    set_interest_rule(cur)
    rid = bill(cur, apt, amount=1000, days_overdue=95)
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    r = rec(cur, rid)
    assert r["interest_amount"] > 0
    assert r["amount"] == r["base_amount"] + r["interest_amount"]
    cur.execute("SELECT acc_particulars FROM transactions WHERE source_table='receivables' AND source_id=%s AND acc_particulars LIKE 'Interest on%%'", (rid,))
    texts = {x["acc_particulars"] for x in cur.fetchall()}
    assert texts and all(f"Rate {RATE}% via Resolution {REF} by GBM" in t for t in texts), texts


@pytest.mark.parametrize("rate, ref", [(None, REF), (RATE, None), (RATE, "   "), (0, REF)])
def test_no_resolved_rate_or_no_resolution_number_means_no_interest(cur, rate, ref):
    apt = flat(cur)
    set_interest_rule(cur, rate, ref)
    rid = bill(cur, apt)
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    assert rec(cur, rid)["interest_amount"] == 0


# ══════════════════════ task 1.5: disputed / under-protest bills ══════════════════════════════════════════════
def test_a_disputed_bill_stops_accruing_interest_and_is_not_in_default(cur):
    apt = flat(cur)
    set_interest_rule(cur)
    rid = bill(cur, apt)
    before = q1(cur, "SELECT dues_outstanding, dues_overdue, arrears_bye_law7 FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, apt))
    assert before["dues_overdue"] == 1000 and before["arrears_bye_law7"] == 1000

    did = raise_dispute(cur, rid)
    assert q1(cur, "SELECT fn_receivable_disputed_asof(%s, CURRENT_DATE) AS x", (rid,))["x"] is True
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    held = rec(cur, rid)
    assert held["interest_amount"] == 0 and held["interest_months_applied"] == 0       # the interest clock did not move

    s = q1(cur, "SELECT dues_outstanding, dues_overdue, arrears_bye_law7 FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, apt))
    assert s["dues_outstanding"] == 1000                                               # still owed, still in the books
    assert s["dues_overdue"] == 0 and s["arrears_bye_law7"] == 0                       # but not in default
    assert q1(cur, "SELECT fn_apartment_overdue_outstanding(%s) AS x", (apt,))["x"] == 0
    assert q1(cur, "SELECT arrears FROM fn_common_expense_arrears_asof(%s,%s,CURRENT_DATE,60)", (SOC, apt))["arrears"] == 0
    assert q1(cur, "SELECT amount_held FROM receivable_disputes WHERE id=%s", (did,))["amount_held"] == 1000


def test_the_hold_is_dated_so_a_past_as_at_test_sees_the_bill_as_it_stood(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    raise_dispute(cur, rid)
    yesterday = date.today() - timedelta(days=1)
    assert q1(cur, "SELECT fn_receivable_disputed_asof(%s,%s) AS x", (rid, yesterday))["x"] is False   # not yet raised then
    assert q1(cur, "SELECT arrears FROM fn_common_expense_arrears_asof(%s,%s,%s,60)", (SOC, apt, yesterday))["arrears"] == 1000


def test_dismissing_the_dispute_ends_the_hold_and_interest_catches_up(cur):
    apt = flat(cur)
    set_interest_rule(cur)
    rid = bill(cur, apt)
    did = raise_dispute(cur, rid)
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    assert rec(cur, rid)["interest_amount"] == 0
    assert "dismissed" in decide(cur, did, "dismissed")
    assert rec(cur, rid)["status"] == "pending"
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    assert rec(cur, rid)["interest_amount"] > 0                                        # the held months are charged
    assert q1(cur, "SELECT dues_overdue FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, apt))["dues_overdue"] > 0
    d = q1(cur, "SELECT status, decided_on, decision_resolution_ref FROM receivable_disputes WHERE id=%s", (did,))
    assert d["status"] == "dismissed" and d["decided_on"] == date.today() and d["decision_resolution_ref"] == "MC-2026/12"


def test_withdrawing_also_ends_the_hold(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    did = raise_dispute(cur, rid)
    assert "withdrawn" in decide(cur, did, "withdrawn")
    assert q1(cur, "SELECT fn_receivable_disputed_asof(%s, CURRENT_DATE) AS x", (rid,))["x"] is False


def test_upholding_reverses_the_accrual_and_cancels_the_bill(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    sdr = acc(cur, "Sundry Debtors")
    net = lambda: q1(cur, """SELECT COALESCE(SUM(CASE entry_side WHEN 'Dr' THEN amount ELSE -amount END),0) AS n
                               FROM transactions WHERE source_table='receivables' AND source_id=%s AND acc_id=%s""", (rid, sdr))["n"]
    assert net() == 1000
    did = raise_dispute(cur, rid)
    msg = decide(cur, did, "upheld", reason="Flat was vacant; charge withdrawn")
    assert "upheld" in msg and "1 journal" in msg
    assert net() == 0                                                                  # the receivable control account nets to nil
    assert rec(cur, rid)["status"] == "cancelled"
    d = q1(cur, "SELECT status, reversal_journal_ids FROM receivable_disputes WHERE id=%s", (did,))
    assert d["status"] == "upheld" and len(d["reversal_journal_ids"]) == 1
    cur.execute("SELECT is_reversal, reversal_reason FROM transactions WHERE journal_id = ANY(%s)", (d["reversal_journal_ids"],))
    legs = cur.fetchall()
    assert legs and all(l["is_reversal"] and "Dispute upheld" in l["reversal_reason"] for l in legs)
    assert q1(cur, "SELECT dues_outstanding FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, apt))["dues_outstanding"] == 0


def test_upholding_reverses_interest_that_accrued_before_the_dispute_too(cur):
    apt = flat(cur)
    set_interest_rule(cur)
    rid = bill(cur, apt)
    cur.execute("SELECT fn_apply_receivable_interest(%s)", (SOC,))
    assert rec(cur, rid)["interest_amount"] > 0
    did = raise_dispute(cur, rid)
    assert "2 journal" in decide(cur, did, "upheld", reason="Charge was wrong")


def test_a_part_paid_bill_can_be_held_but_not_upheld(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    cur.execute("UPDATE receivables SET paid_amount=400, paid_principal=400, status='partial' WHERE id=%s", (rid,))
    did = raise_dispute(cur, rid)
    assert q1(cur, "SELECT amount_held FROM receivable_disputes WHERE id=%s", (did,))["amount_held"] == 600
    assert "refund" in refused(cur, "SELECT fn_decide_receivable_dispute(%s,%s,'upheld',%s,'x','y')", (SOC, did, admin(cur)))
    assert "dismissed" in decide(cur, did, "dismissed")                                # the other outcomes still work


def test_raising_and_deciding_are_refused_when_incomplete_or_wrong(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    uid = admin(cur)
    assert "reason" in refused(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,'short','MC-1')", (SOC, rid, uid))
    assert "resolution" in refused(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,'a proper reason here','  ')", (SOC, rid, uid))
    assert "not found" in refused(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,'a proper reason here','MC-1')", (SOC + 99, rid, uid))
    did = raise_dispute(cur, rid)
    assert "already under dispute" in refused(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,'a proper reason here','MC-1')", (SOC, rid, uid))
    assert "upheld, dismissed or withdrawn" in refused(cur, "SELECT fn_decide_receivable_dispute(%s,%s,'maybe',%s,'r','x')", (SOC, did, uid))
    assert "why" in refused(cur, "SELECT fn_decide_receivable_dispute(%s,%s,'dismissed',%s,'  ','x')", (SOC, did, uid))
    assert "resolution" in refused(cur, "SELECT fn_decide_receivable_dispute(%s,%s,'dismissed',%s,'r','')", (SOC, did, uid))
    assert "open dispute" in refused(cur, "SELECT fn_decide_receivable_dispute(%s,%s,'dismissed',%s,'r','x')", (SOC + 99, did, uid))


def test_only_an_unpaid_apartment_bill_can_be_held(cur):
    apt = flat(cur)
    rid = bill(cur, apt, accrue=False)
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount, paid_principal=amount WHERE id=%s", (rid,))
    assert "unpaid" in refused(cur, "SELECT fn_raise_receivable_dispute(%s,%s,%s,'a proper reason here','MC-1')", (SOC, rid, admin(cur)))


def test_a_decided_bill_can_be_disputed_again_but_only_one_dispute_is_open(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    did = raise_dispute(cur, rid)
    decide(cur, did, "dismissed")
    assert raise_dispute(cur, rid, reason="A new ground, found later") != did
    assert q1(cur, "SELECT COUNT(*) AS n FROM receivable_disputes WHERE receivable_id=%s AND status='open'", (rid,))["n"] == 1


def test_dispute_records_are_append_only(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    did = raise_dispute(cur, rid)
    assert "cannot be edited" in refused(cur, "UPDATE receivable_disputes SET reason='rewritten reason text' WHERE id=%s", (did,))
    assert "cannot be edited" in refused(cur, "UPDATE receivable_disputes SET amount_held=1 WHERE id=%s", (did,))
    assert "cannot be deleted" in refused(cur, "DELETE FROM receivable_disputes WHERE id=%s", (did,))
    assert "truncate" in refused(cur, "TRUNCATE receivable_disputes CASCADE").lower()
    decide(cur, did, "dismissed")
    assert "decided dispute cannot be changed" in refused(cur, "UPDATE receivable_disputes SET status='open', decided_on=NULL WHERE id=%s", (did,))
    assert "cannot be deleted" in refused(cur, "DELETE FROM receivable_disputes WHERE id=%s", (did,))


def test_a_decision_must_carry_its_reason_and_resolution_in_the_table_itself(cur):
    apt = flat(cur)
    rid = bill(cur, apt)
    did = raise_dispute(cur, rid)
    assert "ck_receivable_dispute_decision" in refused(cur, "UPDATE receivable_disputes SET status='dismissed', decided_on=CURRENT_DATE WHERE id=%s", (did,))


# ══════════════════════ task 1.8: Sec 44AB flag turns on at the threshold ═════════════════════════════════════
def _fy_now():
    t = date.today()
    return t.year if t.month >= 4 else t.year - 1


def _flag(cur, fy):
    return q1(cur, "SELECT * FROM fn_tax_audit_flag(%s,%s)", (SOC, fy))


def test_44ab_flag_is_ok_warn_then_flag_as_receipts_cross_80_percent_and_the_limit(cur):
    fy = _fy_now()
    base = _flag(cur, fy)
    income = float(base["total_income"])
    assert base["status"] == "provisional" and base["flag"] == "ok"
    # Put the threshold at exactly the income already in the books plus 1000, then add receipts across each line.
    limit = round(income + 1000, 2)
    cur.execute("UPDATE tax_audit_thresholds SET amount=%s WHERE threshold_key='business_turnover'", (limit,))
    assert _flag(cur, fy)["flag"] in ("ok", "warn")
    apt, inc = flat(cur), acc(cur, "Society Maintenance Charge")
    rid = bill(cur, apt, amount=1, accrue=False)
    cur.execute("SELECT fn_post_receivable_accrual(%s,%s,%s,'apartment',%s,%s,'t')", (SOC, rid, apt, inc, 999))
    assert _flag(cur, fy)["flag"] == "warn"                                            # 1000 short of the limit... at or above 80%
    cur.execute("SELECT fn_post_receivable_accrual(%s,%s,%s,'apartment',%s,%s,'t')", (SOC, rid, apt, inc, 1))
    f = _flag(cur, fy)
    assert f["flag"] == "flag" and float(f["total_income"]) >= limit                    # at the limit is flagged
    assert float(f["pct_of_threshold"]) >= 100 and "Ask your CA" in f["note"]


def test_44ab_threshold_is_effective_dated(cur):
    cur.execute("""INSERT INTO tax_audit_thresholds (threshold_key, amount, effective_from, note)
                   VALUES ('business_turnover', 5000000, DATE '2099-04-01', 'test')""")
    assert float(_flag(cur, 2098)["threshold"]) == 10000000                            # year ends 31 Mar 2099: before the new row
    assert float(_flag(cur, 2099)["threshold"]) == 5000000                             # year ends 31 Mar 2100: the new row applies
    assert float(_flag(cur, 2030)["threshold"]) == 10000000
