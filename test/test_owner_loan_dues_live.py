"""
Owner loans in the dues checks: No Dues issuing, bye-law 7 and s.22 (database/estatehub.sql,
section "OWNER LOANS IN THE DUES CHECKS" + the edited fn_bye_law7_eligibility / fn_service_cutoff_check).

Real Postgres only (same convention as test_up_aoa_compliance_live.py): load estatehub.sql, run seed.py,
set PGHOST/PGDATABASE/PGUSER/PGPASSWORD (PGSSLMODE for non-TLS). Every test runs in one connection that is
rolled back, including the actions-layer tests, which are pointed at that same connection.
"""
import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled
from test.loan_fixtures import approved_loan_resolution, cur_runner, disburse

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
ELECTION = date(2026, 10, 1)          # financial-year basis -> cut-off 31 Mar 2026; 60-day rule -> due on/before 30 Jan 2026
OLD_DUE = date(2026, 1, 15)           # overdue by the bye-law 7 test
LOAN_DATE = date(2025, 12, 1)


@pytest.fixture()
def cur():
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    c = conn.cursor(cursor_factory=RealDictCursor)
    yield c
    conn.rollback()
    conn.close()


@pytest.fixture()
def actions(cur, monkeypatch):
    """up_aoa_actions pointed at the test transaction."""
    from app.services import up_aoa_actions

    class _Shim:
        def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
            cur.execute(sql, params)
            if fetch_one:
                r = cur.fetchone()
                return dict(r) if r else None
            if fetch_all:
                return [dict(r) for r in cur.fetchall()]
            return None
    monkeypatch.setattr(up_aoa_actions, "db", _Shim())
    return up_aoa_actions


def q1(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchone()


def apartment(cur, clean=False):
    """An active flat; clean=True -> one with no pending receivables (so s.22 'dues remain' starts false)."""
    extra = ("AND NOT EXISTS (SELECT 1 FROM receivables r WHERE r.entity_id = a.id AND r.role='apartment' "
             "AND r.status IN ('pending','partial'))") if clean else ""
    row = q1(cur, f"SELECT a.id FROM apartments a WHERE a.society_id=%s AND a.active {extra} ORDER BY a.id LIMIT 1", (SOC,))
    if not row:
        pytest.skip("no suitable apartment in the seeded data")
    return row["id"]


def admin(cur):
    return q1(cur, "SELECT id FROM users WHERE role='admin' LIMIT 1")["id"]


def make_loan(cur, apt, principal=50000, due=OLD_DUE, loan_date=LOAN_DATE):
    """A lawful loan: UP loans need a passed General Body resolution, a purpose and a short-term repayment date."""
    row = disburse(cur_runner(cur), apt, loan_date, principal, 0, "bank", "test", admin(cur), due=due)
    assert row["msg"] == "OK", row
    if not due:                      # tests of the "no repayment date yet" state clear the date the rule insists on
        cur.execute("UPDATE owner_loans SET due_date = NULL WHERE id = %s", (row["loan_id"],))
    return row["loan_id"]


def set_rule(cur, key, value):
    cur.execute("UPDATE regime_rule_parameters SET value=%s WHERE regime_code='UP_AOA_2010' AND rule_key=%s", (value, key))
    assert cur.rowcount == 1


def b7(cur, apt, election=ELECTION):
    return q1(cur, "SELECT * FROM fn_bye_law7_eligibility(%s,%s) WHERE apartment_id=%s", (SOC, election, apt))


def repay_all(cur, loan, on=date(2026, 9, 1)):
    out = q1(cur, "SELECT principal - repaid_amount AS o FROM owner_loans WHERE id=%s", (loan,))["o"]
    assert q1(cur, "SELECT msg FROM fn_repay_owner_loan(%s,%s,%s,0,'bank',%s)", (loan, on, out, admin(cur)))["msg"] == "OK"


def transfer(cur, apt):
    row = q1(cur, "SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,'A','B',%s)",
             (SOC, apt, date(2026, 9, 1), 5000000, admin(cur)))
    assert row["msg"] == "OK", row
    return row["transfer_id"]


# ── due dates and the dues position ──────────────────────────────────────────
def test_due_date_rules(cur):
    apt = apartment(cur)
    loan = make_loan(cur, apt, due=None)
    assert q1(cur, "SELECT fn_set_owner_loan_due_date(%s,%s) AS m", (loan, LOAN_DATE - timedelta(days=1)))["m"].startswith("Error")
    assert q1(cur, "SELECT fn_set_owner_loan_due_date(%s,%s) AS m", (loan, OLD_DUE))["m"] == "OK"
    assert q1(cur, "SELECT fn_set_owner_loan_due_date(%s,NULL) AS m", (loan,))["m"] == "OK"            # clearing is allowed
    assert q1(cur, "SELECT fn_set_owner_loan_due_date(999999,%s) AS m", (OLD_DUE,))["m"].startswith("Error")


def test_dues_position_separates_receivables_and_loans(cur):
    apt = apartment(cur)
    before = q1(cur, "SELECT * FROM fn_apartment_dues_position(%s, %s)", (apt, date(2026, 9, 1)))
    make_loan(cur, apt, 50000, due=OLD_DUE)
    after = q1(cur, "SELECT * FROM fn_apartment_dues_position(%s, %s)", (apt, date(2026, 9, 1)))
    assert after["receivables_outstanding"] == before["receivables_outstanding"]
    assert after["loan_outstanding"] - before["loan_outstanding"] == 50000
    assert after["loan_overdue"] - before["loan_overdue"] == 50000
    assert after["total_outstanding"] - before["total_outstanding"] == 50000
    # the receivable-only helper that NOC and the deactivation guard use is unchanged
    assert q1(cur, "SELECT fn_apartment_outstanding(%s) AS v", (apt,))["v"] == before["receivables_outstanding"]


# ── No Dues ──────────────────────────────────────────────────────────────────
def test_outstanding_loan_blocks_issuing_nodues_until_repaid(cur):
    apt = apartment(cur)
    tr = transfer(cur, apt)
    assert q1(cur, "SELECT can_issue FROM fn_nodues_issue_check(%s)", (tr,))["can_issue"] is True
    loan = make_loan(cur, apt, 50000, due=None)                       # no due date: still blocks No Dues
    chk = q1(cur, "SELECT * FROM fn_nodues_issue_check(%s)", (tr,))
    assert chk["can_issue"] is False and chk["loan_outstanding"] >= 50000 and "refused" in chk["reason"]
    repay_all(cur, loan)
    assert q1(cur, "SELECT can_issue FROM fn_nodues_issue_check(%s)", (tr,))["can_issue"] is True


def test_nodues_block_is_switchable_and_refusal_always_allowed(cur, actions):
    apt = apartment(cur)
    tr = transfer(cur, apt)
    make_loan(cur, apt, 50000, due=None)
    ok, msg = actions.set_nodues(SOC, tr, "nodues_issued_on", date(2026, 9, 2))
    assert not ok and "Cannot issue" in msg
    assert actions.set_nodues(SOC, tr, "nodues_refused_on", date(2026, 9, 2))[0] is True           # refusing is never blocked
    set_rule(cur, "owner_loan_blocks_nodues", 0)                                                   # master switches the policy off
    assert actions.set_nodues(SOC, tr, "nodues_issued_on", date(2026, 9, 3))[0] is True


# ── bye-law 7 ────────────────────────────────────────────────────────────────
def test_bye_law7_counts_only_overdue_outstanding_loans(cur):
    set_rule(cur, "owner_loan_counts_bye_law7", 1)      # opt-in: off by default (bye-law 7 covers common-expense arrears only)
    apt = apartment(cur)
    base = b7(cur, apt)
    loan = make_loan(cur, apt, 50000, due=OLD_DUE)
    row = b7(cur, apt)
    assert row["overdue_amount"] - base["overdue_amount"] == 50000 and row["eligible"] is False
    assert row["oldest_due_date"] <= OLD_DUE and row["days_overdue"] >= (date(2026, 3, 31) - OLD_DUE).days

    cur.execute("UPDATE owner_loans SET due_date=NULL WHERE id=%s", (loan,))                       # no repayment date -> never overdue
    assert b7(cur, apt)["overdue_amount"] == base["overdue_amount"]
    cur.execute("UPDATE owner_loans SET due_date=%s WHERE id=%s", (date(2026, 3, 1), loan))        # past due, but < 60 days before cut-off
    assert b7(cur, apt)["overdue_amount"] == base["overdue_amount"]
    cur.execute("UPDATE owner_loans SET due_date=%s WHERE id=%s", (OLD_DUE, loan))
    repay_all(cur, loan)                                                                           # repaid -> drops out
    assert b7(cur, apt)["overdue_amount"] == base["overdue_amount"]


def test_bye_law7_loan_term_is_off_by_default_and_switchable(cur):
    apt = apartment(cur)
    base = b7(cur, apt)
    make_loan(cur, apt, 50000, due=OLD_DUE)
    assert b7(cur, apt)["overdue_amount"] == base["overdue_amount"]          # default: a loan is not a common-expense arrear
    set_rule(cur, "owner_loan_counts_bye_law7", 1)
    assert b7(cur, apt)["overdue_amount"] - base["overdue_amount"] == 50000   # society opted in


def test_bye_law7_partial_repayment_counts_remaining_balance(cur):
    set_rule(cur, "owner_loan_counts_bye_law7", 1)
    apt = apartment(cur)
    base = b7(cur, apt)
    loan = make_loan(cur, apt, 50000, due=OLD_DUE)
    assert q1(cur, "SELECT msg FROM fn_repay_owner_loan(%s,%s,20000,0,'bank',%s)", (loan, date(2026, 9, 1), admin(cur)))["msg"] == "OK"
    assert b7(cur, apt)["overdue_amount"] - base["overdue_amount"] == 30000


# ── section 22 ───────────────────────────────────────────────────────────────
def _proceeding(cur, apt):
    return q1(cur, """INSERT INTO service_cutoff_proceedings (society_id, apartment_id, service_type, default_since)
                      VALUES (%s,%s,'water',%s) RETURNING id""", (SOC, apt, date(2025, 1, 1)))["id"]


def _s22_dues_blocker(cur, pid, asof=date(2026, 9, 1)):
    """True when service cut-off is blocked because nothing is owed.

    fn_service_cutoff_check() reports this as "no common-expense dues are
    unpaid for more than N months ... so s.22 is not triggered". s.22 lets a
    society cut a service only when charges have been unpaid for over the
    statutory period, so a flat with nothing outstanding — or with an overdue
    loan the society has chosen not to count — is *blocked*, not cleared. The rule under test (owner_loan_counts_s22) decides which of those
    two the loan produces.
    """
    blockers = q1(cur, "SELECT blockers FROM fn_service_cutoff_check(%s,%s)", (pid, asof))["blockers"]
    return any("s.22 is not triggered" in b for b in blockers)


def test_s22_ignores_loans_by_default_and_counts_them_when_switched_on(cur):
    apt = apartment(cur, clean=True)
    pid = _proceeding(cur, apt)
    make_loan(cur, apt, 50000, due=OLD_DUE)
    assert _s22_dues_blocker(cur, pid) is True         # default OFF: a loan alone is not a ground for cutting a service
    set_rule(cur, "owner_loan_counts_s22", 1)
    assert _s22_dues_blocker(cur, pid) is False        # ON: the overdue loan counts as dues remaining
    cur.execute("UPDATE owner_loans SET due_date=NULL WHERE apartment_id=%s", (apt,))
    assert _s22_dues_blocker(cur, pid) is True         # no repayment date -> not overdue, even when ON


# ── actions layer ────────────────────────────────────────────────────────────
def test_disburse_loan_with_due_date_and_set_due_date_action(cur, actions):
    apt = apartment(cur)
    res = approved_loan_resolution(cur_runner(cur))
    ok, msg = actions.disburse_loan(SOC, admin(cur), apt, LOAN_DATE, 40000, 0, "bank", "t", "BM-9", due_date=OLD_DUE, resolution_id=res)
    assert ok, msg
    loan = q1(cur, "SELECT id, due_date FROM owner_loans WHERE resolution_ref='BM-9' ORDER BY id DESC LIMIT 1")
    assert loan["due_date"] == OLD_DUE
    assert not actions.disburse_loan(SOC, admin(cur), apt, LOAN_DATE, 40000, 0, "bank", "t", "BM-10",
                                     due_date=LOAN_DATE - timedelta(days=1), resolution_id=res)[0]
    assert actions.set_loan_due_date(SOC, loan["id"], None)[0] is True
    assert q1(cur, "SELECT due_date FROM owner_loans WHERE id=%s", (loan["id"],))["due_date"] is None
    assert not actions.set_loan_due_date(SOC, 999999, OLD_DUE)[0]
    assert not actions.set_loan_due_date(SOC, loan["id"], "not-a-date")[0]


def test_card_data_exposes_loan_columns(cur, actions):
    apt = apartment(cur)
    tr = transfer(cur, apt)
    make_loan(cur, apt, 50000, due=OLD_DUE)
    data = actions.load_card_data(SOC)
    assert any(r["id"] == tr and r["loan_outstanding"] >= 50000 for r in data["transfers"])
    assert any(r["overdue"] and r["due_date"] == OLD_DUE for r in data["loans"])
