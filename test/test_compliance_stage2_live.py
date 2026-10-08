"""Tests for the 'compliance stage2' commit: weighted polls, owner-loan consent, the s.20(2) recovery list, the
s.23(2) purchaser statement and the audit gate on published statements. Real Postgres only; every test rolls back."""
import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled
from test.loan_fixtures import approved_loan_resolution, cur_runner

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
LOAN_DATE = date(2026, 9, 1)


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


def refused(cur, sql, args=None):
    """Run a statement that must be rejected by the database; the transaction survives (savepoint)."""
    cur.execute("SAVEPOINT refusal")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute(sql, args)
    cur.execute("ROLLBACK TO SAVEPOINT refusal")
    return str(e.value)


def admin(cur):
    return q1(cur, "SELECT id FROM users WHERE role='admin' AND society_id=%s LIMIT 1", (SOC,))["id"]


def flats(cur):
    cur.execute("SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id", (SOC,))
    return [r["id"] for r in cur.fetchall()]


def clean_flat(cur):
    apt = flats(cur)[0]
    cur.execute("DELETE FROM receivables WHERE entity_id=%s AND role='apartment'", (apt,))
    return apt


def bill(cur, apt, amount=1000, due=date(2025, 1, 15), kind="common_expense"):
    acc = q1(cur, "SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,))["id"]
    return q1(cur, """INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount, interest_amount,
                                               amount, due_date, status, charge_kind)
                      VALUES (%s,%s,'apartment',%s,'test bill',%s,0,%s,%s,'pending',%s) RETURNING id""",
              (SOC, apt, acc, amount, amount, due, kind))["id"]


def pay(cur, rec, on):
    cur.execute("SELECT set_config('app.payment_date', %s, true)", (on.isoformat(),))
    cur.execute("UPDATE receivables SET paid_amount=amount, paid_principal=amount-interest_amount, status='paid' WHERE id=%s", (rec,))
    cur.execute("SELECT set_config('app.payment_date', '', true)")


# ═════════════════════════ weighted polls (bye-laws 8, 9, 2(e); Act s.12(1)(f)) ══════════════════════════════
def _weights(cur, first_pct=60, other_pct=5):
    """First flat carries first_pct %, every other flat other_pct %; returns the percentages' sum."""
    ids = flats(cur)
    cur.execute("UPDATE apartments SET undivided_interest_pct=%s WHERE society_id=%s AND active", (other_pct, SOC))
    cur.execute("UPDATE apartments SET undivided_interest_pct=%s WHERE id=%s", (100 - other_pct * (len(ids) - 1), ids[0]))


def _poll(cur, basis="undivided_interest", open_to="all_members"):
    return q1(cur, """SELECT fn_create_poll(%s,'Test poll'::varchar,'d'::text,2::smallint,'yes'::varchar,'no'::varchar,NULL::varchar,
                          NULL::varchar,NULL::varchar,(NOW()+interval '1 day')::timestamp,%s::varchar,%s::varchar) AS id""",
              (SOC, open_to, basis))["id"]


def _owner_users(cur, n):
    cur.execute("SELECT id FROM users WHERE society_id=%s AND role='apartment' AND user_type='owner' ORDER BY id LIMIT %s", (SOC, n))
    rows = [r["id"] for r in cur.fetchall()]
    if len(rows) < n:
        pytest.skip("seed has too few owner users")
    return rows


def test_weighted_poll_refused_unless_every_flat_has_a_percentage_that_sums_to_100(cur):
    cur.execute("UPDATE apartments SET undivided_interest_pct=NULL WHERE id=%s", (flats(cur)[0],))
    assert "no undivided-interest percentage" in refused(cur, "SELECT fn_create_poll(%s,'t'::varchar,'d'::text,2::smallint,'a'::varchar,'b'::varchar,NULL::varchar,NULL::varchar,NULL::varchar,NULL::timestamp,'all_members'::varchar,'undivided_interest'::varchar)", (SOC,))
    cur.execute("UPDATE apartments SET undivided_interest_pct=1 WHERE society_id=%s", (SOC,))
    assert "not 100" in refused(cur, "SELECT fn_create_poll(%s,'t'::varchar,'d'::text,2::smallint,'a'::varchar,'b'::varchar,NULL::varchar,NULL::varchar,NULL::varchar,NULL::timestamp,'all_members'::varchar,'undivided_interest'::varchar)", (SOC,))


def test_unweighted_poll_needs_no_percentages_and_unknown_basis_is_refused(cur):
    cur.execute("UPDATE apartments SET undivided_interest_pct=NULL WHERE society_id=%s", (SOC,))
    assert _poll(cur, basis="apartment")
    assert "vote_basis" in refused(cur, "SELECT fn_create_poll(%s,'t'::varchar,'d'::text,2::smallint,'a'::varchar,'b'::varchar,NULL::varchar,NULL::varchar,NULL::varchar,NULL::timestamp,'all_members'::varchar,'by_head'::varchar)", (SOC,))


def test_weight_not_headcount_decides_and_the_result_is_not_a_resolution(cur):
    _weights(cur, 60, 5)
    pid = _poll(cur)
    voters = _owner_users(cur, 3)            # voter 1 owns flat 1 (60%); voters 2 and 3 own 5% flats
    for uid, choice in zip(voters, (1, 2, 2)):
        ok = q1(cur, "SELECT * FROM fn_cast_vote(%s,%s,%s,%s::smallint)", (pid, uid, SOC, choice))
        assert ok["success"], ok
    res = q1(cur, "SELECT * FROM fn_declare_results(%s,%s,%s)", (pid, admin(cur), SOC))["results"]
    assert res["choice_breakdown"] == {"choice_1": 1, "choice_2": 2}              # by head, choice 2 would win
    assert float(res["weight_breakdown"]["choice_1"]) == 60.0 and float(res["weight_breakdown"]["choice_2"]) == 10.0
    assert res["winning_choice"] == 1                                              # by weight, choice 1 wins
    assert res["quorum_met"] is True and res["statutory_resolution"] is False
    assert "not a General Body resolution" in res["note"]


def test_quorum_is_a_share_of_owners_and_comes_from_the_rule(cur):
    _weights(cur)
    pid = _poll(cur)
    assert float(q1(cur, "SELECT quorum_pct, majority_pct FROM polls WHERE id=%s", (pid,))["quorum_pct"]) == 30.0
    assert float(q1(cur, "SELECT majority_pct FROM polls WHERE id=%s", (pid,))["majority_pct"]) == 51.0
    uid = _owner_users(cur, 2)
    for u in uid:
        assert q1(cur, "SELECT * FROM fn_cast_vote(%s,%s,%s,1::smallint)", (pid, u, SOC))["success"]
    r = q1(cur, "SELECT * FROM fn_declare_results(%s,%s,%s)", (pid, admin(cur), SOC))
    assert r["success"] is False and "Quorum not met" in r["message"]             # 2 of 9 owners = 22.2% < 30%


def test_society_can_raise_the_poll_quorum_and_new_polls_follow(cur):
    mid = q1(cur, "INSERT INTO meetings (society_id,type,held_on,quorum_met,minutes_pdf) VALUES (%s,'GBM',%s,TRUE,'m.pdf') RETURNING id",
             (SOC, date.today()))["id"]
    dt = q1(cur, "SELECT id, majority_pct FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    res = q1(cur, """INSERT INTO resolutions (meeting_id,clause_id,decision_type_id,body,majority_required,passed,passed_on)
                     VALUES (%s,'poll_quorum_pct',%s,'raise quorum',%s,TRUE,%s) RETURNING id""", (mid, dt["id"], dt["majority_pct"], date.today()))["id"]
    cur.execute("""INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,value,resolution_id,effective_from)
                   VALUES (%s,'poll_quorum_pct',2,'adopted_with_variation',50,%s,%s)""", (SOC, res, date.today()))
    _weights(cur)
    assert float(q1(cur, "SELECT quorum_pct FROM polls WHERE id=%s", (_poll(cur),))["quorum_pct"]) == 50.0
    cur.execute("""INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,value,resolution_id,effective_from)
                   VALUES (%s,'poll_quorum_pct',3,'adopted_with_variation',20,%s,%s)""", (SOC, res, date.today()))
    assert float(q1(cur, "SELECT value FROM fn_rule(%s,'poll_quorum_pct')", (SOC,))["value"]) == 50.0   # below the Layer-1 floor: ignored


# ═════════════════════════ owner loans: consent of the owners (bye-law 3(1)(f)) ═════════════════════════════════
def _loan(cur, res=None, purpose="roof repair", due=LOAN_DATE + timedelta(days=90), principal=10000, mode="bank", ref=""):
    apt = flats(cur)[0]
    return q1(cur, "SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s)",
              (SOC, apt, LOAN_DATE, principal, mode, purpose, ref, admin(cur), res, due))


def test_loan_needs_a_resolution_in_the_up_scheme(cur):
    r = _loan(cur)
    assert r["loan_id"] is None and "General Body resolution" in r["msg"]


@pytest.mark.parametrize("kw,needle", [
    (dict(dcode="SET_SOCIETY_POLICY"), "not an Approve Owner Loan"),
    (dict(passed=False), "did not pass"),
    (dict(mtype="MC", dcode="APPROVE_LOAN"), "General Body meeting"),
    (dict(quorum=False), "quorum"),
    (dict(on=LOAN_DATE + timedelta(days=1)), "after the loan date"),
])
def test_loan_resolution_must_be_a_passed_quorate_general_body_approval_before_the_loan(cur, kw, needle):
    kw = dict(kw)
    on = kw.pop("on", date(2026, 8, 1))
    res = approved_loan_resolution(cur_runner(cur), SOC, on, **kw)
    r = _loan(cur, res)
    assert r["loan_id"] is None and needle in r["msg"], r["msg"]


def test_loan_needs_purpose_and_a_short_repayment_date(cur):
    res = approved_loan_resolution(cur_runner(cur), SOC, date(2026, 8, 1))
    assert "emergent necessity" in _loan(cur, res, purpose="")["msg"]
    assert "repayment date" in _loan(cur, res, due=None)["msg"]
    assert "repayment date" in _loan(cur, res, due=LOAN_DATE)["msg"]                       # not after the loan date
    r = _loan(cur, res, due=LOAN_DATE + timedelta(days=366))                                # one day past 365
    assert "short-term limit is 365 days" in r["msg"]


def test_lawful_loan_is_posted_with_a_generated_reference(cur):
    res = approved_loan_resolution(cur_runner(cur), SOC, date(2026, 8, 1))
    r = _loan(cur, res, due=LOAN_DATE + timedelta(days=365))
    assert r["msg"] == "OK"
    row = q1(cur, "SELECT resolution_id, resolution_ref, due_date FROM owner_loans WHERE id=%s", (r["loan_id"],))
    assert row["resolution_id"] == res and "resolution #%d" % res in row["resolution_ref"] and row["due_date"] == LOAN_DATE + timedelta(days=365)


def test_text_mode_restores_the_free_text_reference(cur):
    cur.execute("UPDATE regime_rule_parameters SET value_text='text' WHERE regime_code='UP_AOA_2010' AND rule_key='owner_loan_resolution_mode'")
    assert _loan(cur, None, due=None, ref="")["msg"].startswith("Error") and "reference" in _loan(cur, None, due=None, ref="")["msg"]
    assert _loan(cur, None, due=None, ref="BM-1")["msg"] == "OK"


# ═════════════════════════ audit gate on published statements (bye-law 49(3)) ═══════════════════════════════════
_FILING = "INSERT INTO aoa_statutory_filings (society_id, fy_start_year, statements_published_on, auditor_name, audit_signed_off_on) VALUES (%s,2025,%s,%s,%s)"


def test_a_statement_cannot_be_recorded_as_published_without_an_auditor_and_sign_off(cur):
    pub = date(2026, 7, 20)
    assert "chk_aoa_published_is_audited" in refused(cur, _FILING, (SOC, pub, None, date(2026, 7, 10)))      # no auditor
    assert "chk_aoa_published_is_audited" in refused(cur, _FILING, (SOC, pub, "  ", date(2026, 7, 10)))      # blank auditor
    assert "chk_aoa_published_is_audited" in refused(cur, _FILING, (SOC, pub, "ABC & Co", None))             # no sign-off
    assert "chk_aoa_published_is_audited" in refused(cur, _FILING, (SOC, pub, "ABC & Co", date(2026, 7, 21)))  # signed after publication
    cur.execute(_FILING, (SOC, pub, "ABC & Co", pub))                                                         # same day is fine
    assert q1(cur, "SELECT count(*) AS n FROM aoa_statutory_filings WHERE society_id=%s AND fy_start_year=2025", (SOC,))["n"] == 1


def test_an_unpublished_filing_needs_no_auditor_yet(cur):
    cur.execute("INSERT INTO aoa_statutory_filings (society_id, fy_start_year) VALUES (%s,2024)", (SOC,))


# ═════════════════════════ s.20(2): recovery candidates ═══════════════════════════════════════════════════════════
ASOF = date(2026, 10, 1)


def _s20(cur, apt):
    cur.execute("SELECT * FROM fn_s20_recovery_candidates(%s,%s) WHERE apartment_id=%s", (SOC, ASOF, apt))
    return cur.fetchone()


def test_flat_unpaid_for_more_than_12_months_is_a_candidate(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 1000, due=date(2025, 6, 1))
    bill(cur, apt, 500, due=date(2026, 3, 1))                  # newer bill: counts toward the amount only if itself old enough
    row = _s20(cur, apt)
    assert row and float(row["amount_due"]) == 1000.0 and row["bills"] == 1 and row["months_threshold"] == 12
    assert row["oldest_due_date"] == date(2025, 6, 1)


def test_exactly_12_months_is_not_yet_a_candidate_and_one_day_more_is(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 1000, due=date(2025, 10, 1))                # due exactly 12 months before ASOF
    assert _s20(cur, apt) is None
    cur.execute("UPDATE receivables SET due_date=%s WHERE entity_id=%s AND role='apartment'", (date(2025, 9, 30), apt))
    assert _s20(cur, apt) is not None


def test_paid_bills_and_the_transfer_fee_are_not_candidates(cur):
    apt = clean_flat(cur)
    paid = bill(cur, apt, 1000, due=date(2025, 3, 1))
    pay(cur, paid, date(2025, 4, 1))
    bill(cur, apt, 5000, due=date(2025, 3, 1), kind="transfer_fee")      # payable by the transferor, not a common expense
    assert _s20(cur, apt) is None


def test_s20_is_tested_as_at_the_date_given(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt, 1000, due=date(2025, 3, 1))
    pay(cur, rec, date(2026, 11, 1))                                      # settled AFTER the as-at date
    assert _s20(cur, apt) is not None


def test_the_twelve_months_follow_the_rule_value(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 1000, due=date(2026, 3, 1))                            # ~7 months old
    assert _s20(cur, apt) is None
    cur.execute("UPDATE regime_rule_parameters SET value=6 WHERE regime_code='UP_AOA_2010' AND rule_key='s20_recovery_months'")
    assert _s20(cur, apt) is not None


# ═════════════════════════ s.23(2): purchaser's statement of unpaid assessments ══════════════════════════════════
def _sale(cur, apt, ttype="sale", on=date(2026, 9, 1)):
    return q1(cur, "SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,1000000,'Seller','Buyer',%s,%s)",
              (SOC, apt, on, admin(cur), ttype))["transfer_id"]


def test_statement_shows_common_expenses_unpaid_at_the_transfer_date_and_keeps_the_fee_apart(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 1000, due=date(2026, 6, 1))
    bill(cur, apt, 700, due=date(2026, 8, 1))
    bill(cur, apt, 900, due=date(2026, 10, 1))                             # falls due after the transfer: not the transferor's
    tr = _sale(cur, apt)
    s = q1(cur, "SELECT * FROM fn_purchaser_dues_statement(%s)", (tr,))
    assert float(s["common_expense_unpaid"]) == 1700.0 and s["bills"] == 2 and s["as_at"] == date(2026, 9, 1)
    assert float(s["transfer_fee_unpaid"]) == 5000.0                       # the 1/2% fee is reported, not folded in


def test_issuing_freezes_the_figure_and_cannot_be_repeated(cur):
    apt = clean_flat(cur)
    rec = bill(cur, apt, 1000, due=date(2026, 6, 1))
    tr = _sale(cur, apt)
    r = q1(cur, "SELECT * FROM fn_issue_purchaser_statement(%s,%s)", (tr, admin(cur)))
    assert r["ok"] and float(r["statement_amount"]) == 1000.0
    pay(cur, rec, date(2026, 9, 5))                                        # paid after the statement was issued
    t = q1(cur, "SELECT statement_amount, statement_issued_on, statement_issued_by FROM apartment_transfers WHERE id=%s", (tr,))
    assert float(t["statement_amount"]) == 1000.0 and t["statement_issued_on"] == date.today() and t["statement_issued_by"] == admin(cur)
    again = q1(cur, "SELECT * FROM fn_issue_purchaser_statement(%s,%s)", (tr, admin(cur)))
    assert again["ok"] is False and "already issued" in again["msg"]
    # The figure is "as at the transfer date" by default, so the later payment does not change it ...
    assert float(q1(cur, "SELECT common_expense_unpaid FROM fn_purchaser_dues_statement(%s)", (tr,))["common_expense_unpaid"]) == 1000.0
    # ... but asking as at a date after the payment shows what is owed now.
    assert float(q1(cur, "SELECT common_expense_unpaid FROM fn_purchaser_dues_statement(%s,%s)", (tr, date(2026, 9, 10)))["common_expense_unpaid"]) == 0.0


def test_statement_for_a_gift_or_succession_and_for_an_unknown_transfer(cur):
    apt = clean_flat(cur)
    bill(cur, apt, 400, due=date(2026, 6, 1))
    tr = _sale(cur, apt, "succession")
    assert float(q1(cur, "SELECT statement_amount FROM fn_issue_purchaser_statement(%s,%s)", (tr, admin(cur)))["statement_amount"]) == 400.0
    nf = q1(cur, "SELECT * FROM fn_issue_purchaser_statement(%s,%s)", (999999, admin(cur)))
    assert nf["ok"] is False and "not found" in nf["msg"]
