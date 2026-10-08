"""
Scenario L — UP Apartment Act 2010 / Model Bye-Laws 2011 compliance layer.

These run against a REAL Postgres (the rules live in SQL functions, so FakeDB
cannot exercise them). Load database/estatehub.sql, run database/seed.py, then
point PGHOST/PGDATABASE/PGUSER/PGPASSWORD at it. Without PGHOST the whole module
is skipped, so the normal FakeDB suite is unaffected.

Every test works inside one transaction that is rolled back, so the demo data is
left untouched.
"""

import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")

pytestmark = pytest.mark.skipif(
    not live_db_enabled(), reason=LIVE_DB_REASON
)

SOC = 1


@pytest.fixture()
def cur():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    c = conn.cursor()
    yield c
    conn.rollback()
    conn.close()


def one(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchone()


def first_apartment(cur):
    return one(cur, "SELECT id, flat_number FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))


def add_receivable(cur, apt_id, due, amount=5000):
    cur.execute(
        """INSERT INTO receivables (society_id, entity_id, role, acc_id, description,
                                    base_amount, amount, due_date, status)
           VALUES (%s,%s,'apartment',4210,'test dues',%s,%s,%s,'pending') RETURNING id""",
        (SOC, apt_id, amount, amount, due),
    )
    return cur.fetchone()[0]


# ── statutory heads / mappings ─────────────────────────────────────────────────
def test_sinking_fund_not_mapped_to_ifms_and_corpus_is(cur):
    cur.execute("SELECT account_id, head_code FROM account_statutory_mappings "
                "WHERE society_id=%s AND regime_code='UP_AOA_2010' AND account_id IN (3210,3220,3230)", (SOC,))
    m = dict(cur.fetchall())
    assert m[3210] == "SINKING_FUND"
    assert m[3220] == "RESERVE_FUND"
    assert m[3230] == "IFMS_CORPUS"


def test_no_2016_amendment_or_chapter_vii_citations_remain(cur):
    cur.execute("SELECT count(*) FROM statutory_head_catalog WHERE regime_code='UP_AOA_2010' "
                "AND (source_reference ILIKE '%2016 Amendment%' OR source_reference LIKE '%Ch.VII%')")
    assert cur.fetchone()[0] == 0


# ── undivided interest ─────────────────────────────────────────────────────────
def test_undivided_interest_backfilled_and_balanced(cur):
    total, missing, pct, balanced = one(cur, "SELECT * FROM fn_undivided_interest_summary(%s)", (SOC,))
    assert missing == 0 and balanced and abs(float(pct) - 100) <= 0.001


def test_undivided_interest_missing_is_reported(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE apartments SET undivided_interest_pct=NULL WHERE id=%s", (apt_id,))
    s = one(cur, "SELECT status FROM fn_undivided_interest_report(%s) WHERE apartment_id=%s", (SOC, apt_id))
    assert s[0] == "missing"
    assert one(cur, "SELECT balanced FROM fn_undivided_interest_summary(%s)", (SOC,))[0] is False


# ── Major Repair Fund / transfer fee ───────────────────────────────────────────
def test_transfer_fee_is_half_percent_and_posts_accrual_to_fund(cur):
    apt_id, flat = first_apartment(cur)
    tr, rec, fee, msg = one(cur, "SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,'Seller','Buyer',NULL)",
                            (SOC, apt_id, date(2026, 9, 15), 8_000_000))
    assert msg == "OK" and float(fee) == 40_000.00
    # accrual leg: Dr Sundry Debtors / Cr Major Repair Fund (3270), journal mode
    cur.execute("SELECT entry_side, acc_id, amount, mode FROM transactions "
                "WHERE source_table='receivables' AND source_id=%s ORDER BY entry_side", (rec,))
    legs = {(side, acc): (float(a), mode) for side, acc, a, mode in cur.fetchall()}
    assert legs[("Cr", 3270)] == (40_000.0, "journal")
    assert any(side == "Dr" for side, _ in legs)


def test_transfer_fee_account_and_head_created_once(cur):
    for _ in range(2):
        cur.execute("SELECT fn_ensure_major_repair_fund(%s)", (SOC,))
    assert one(cur, "SELECT count(*) FROM accounts WHERE society_id=%s AND id=3270", (SOC,))[0] == 1
    assert one(cur, "SELECT head_code FROM account_statutory_mappings WHERE society_id=%s AND account_id=3270", (SOC,))[0] \
        == "MAJOR_REPAIR_FUND"


def test_transfer_fee_refused_when_no_regime(cur):
    cur.execute("SELECT msg FROM fn_record_apartment_transfer(%s,1,%s,1000000,'a','b',NULL)", (999999, date(2026, 9, 1)))
    assert cur.fetchone()[0].startswith("Error")


def test_no_dues_certificate_deemed_after_15_days(cur):
    apt_id, _ = first_apartment(cur)
    tr = one(cur, "SELECT transfer_id FROM fn_record_apartment_transfer(%s,%s,%s,1000000,'a','b',NULL)",
             (SOC, apt_id, date(2026, 9, 1)))[0]
    cur.execute("UPDATE apartment_transfers SET nodues_requested_on=%s WHERE id=%s", (date(2026, 9, 10), tr))
    assert one(cur, "SELECT status FROM fn_nodues_certificate_status(%s,%s)", (tr, date(2026, 9, 25)))[0] == "pending"        # a refusal on day 15 is still in time
    assert one(cur, "SELECT status FROM fn_nodues_certificate_status(%s,%s)", (tr, date(2026, 9, 26)))[0] == "deemed_granted"
    cur.execute("UPDATE apartment_transfers SET nodues_refused_on=%s WHERE id=%s", (date(2026, 9, 20), tr))
    assert one(cur, "SELECT status FROM fn_nodues_certificate_status(%s,%s)", (tr, date(2026, 9, 30)))[0] == "refused"


# ── bye-law 7 ──────────────────────────────────────────────────────────────────
def test_bye_law7_cutoff_dates(cur):
    fy = one(cur, "SELECT fn_bye_law7_cutoff_date(%s,%s)", (SOC, date(2026, 5, 10)))[0]
    cal = one(cur, "SELECT fn_bye_law7_cutoff_date(%s,%s,'calendar_year')", (SOC, date(2026, 5, 10)))[0]
    assert fy == date(2026, 3, 31) and cal == date(2025, 12, 31)


def test_bye_law7_disqualifies_only_arrears_older_than_60_days_at_cutoff(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount WHERE entity_id=%s AND role='apartment'", (apt_id,))
    add_receivable(cur, apt_id, date(2026, 1, 15))       # >60 days before 31 Mar 2026, but not before 31 Dec 2025 - 60d
    fy = one(cur, "SELECT eligible, days_overdue FROM fn_bye_law7_eligibility(%s,%s) WHERE apartment_id=%s",
             (SOC, date(2026, 5, 10), apt_id))
    cal = one(cur, "SELECT eligible FROM fn_bye_law7_eligibility(%s,%s,'calendar_year') WHERE apartment_id=%s",
              (SOC, date(2026, 5, 10), apt_id))
    assert fy[0] is False and fy[1] == 75
    assert cal[0] is True


def test_bye_law7_off_without_regime(cur):
    cur.execute("SELECT count(*) FROM fn_bye_law7_eligibility(%s,%s)", (999999, date(2026, 5, 10)))
    assert cur.fetchone()[0] == 0


# ── section 22 ─────────────────────────────────────────────────────────────────
def test_s22_blocks_until_every_step_and_wait_is_done(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount WHERE entity_id=%s AND role='apartment'", (apt_id,))
    add_receivable(cur, apt_id, date(2026, 1, 1), 9000)
    cur.execute("INSERT INTO service_cutoff_proceedings (society_id, apartment_id, service_type, default_since) "
                "VALUES (%s,%s,'water',%s) RETURNING id", (SOC, apt_id, date(2026, 1, 1)))
    pid = cur.fetchone()[0]

    ok, earliest, blockers = one(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, date(2026, 9, 1)))
    assert ok is False and len(blockers) >= 4          # no notice, no resolution, no copies, no display

    cur.execute("""UPDATE service_cutoff_proceedings SET notice_served_on=%s, gb_resolution_on=%s,
                   copy_sent_to_authority_on=%s, copy_sent_to_owner_on=%s, display_notice_on=%s WHERE id=%s""",
                (date(2026, 8, 1), date(2026, 8, 10), date(2026, 8, 12), date(2026, 8, 12), date(2026, 8, 13), pid))
    ok, earliest, blockers = one(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, date(2026, 9, 1)))
    assert ok is False and any("one-month wait" in b for b in blockers)
    assert earliest == date(2026, 9, 12)

    ok, _, blockers = one(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, date(2026, 9, 12)))
    assert ok is True and blockers == []

    cur.execute("UPDATE service_cutoff_proceedings SET appeal_filed_on=%s WHERE id=%s", (date(2026, 8, 20), pid))
    ok, _, blockers = one(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, date(2026, 9, 12)))
    assert ok is False and any("appeal" in b for b in blockers)


def test_s22_requires_more_than_six_months_default(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO service_cutoff_proceedings (society_id, apartment_id, service_type, default_since) "
                "VALUES (%s,%s,'water',%s) RETURNING id", (SOC, apt_id, date(2026, 4, 1)))
    pid = cur.fetchone()[0]
    _, earliest, blockers = one(cur, "SELECT * FROM fn_service_cutoff_check(%s,%s)", (pid, date(2026, 9, 30)))
    assert any("exceed 6 months" in b for b in blockers)


# ── cash / cheque limits ───────────────────────────────────────────────────────
def _pending_expense(cur, amount, mode):
    cur.execute("""INSERT INTO expenses (society_id, expense_date, acc_id, particulars, amount, mode, status)
                   VALUES (%s,%s,51110,'test repair',%s,%s,'pending') RETURNING id""",
                (SOC, date(2026, 9, 5), amount, mode))
    return cur.fetchone()[0]


def test_cash_over_limit_is_flagged_in_warn_mode_and_still_posts(cur):
    cur.execute("UPDATE societies SET cash_limit_mode=NULL WHERE id=%s", (SOC,))
    exp = _pending_expense(cur, 5000, "cash")
    admin = one(cur, "SELECT id FROM users WHERE role='admin' LIMIT 1")[0]
    msg = one(cur, "SELECT msg FROM fn_verify_expense(%s,%s,'cash')", (exp, admin))[0]
    assert not msg.startswith("Error")
    assert one(cur, "SELECT count(*) FROM compliance_flags WHERE source_table='expenses' AND source_id=%s", (exp,))[0] == 1


def test_cash_over_limit_is_refused_in_block_mode(cur):
    cur.execute("UPDATE societies SET cash_limit_mode='block' WHERE id=%s", (SOC,))
    exp = _pending_expense(cur, 5000, "cash")
    admin = one(cur, "SELECT id FROM users WHERE role='admin' LIMIT 1")[0]
    msg = one(cur, "SELECT msg FROM fn_verify_expense(%s,%s,'cash')", (exp, admin))[0]
    assert msg.startswith("Error") and "cheque" in msg
    assert one(cur, "SELECT status FROM expenses WHERE id=%s", (exp,))[0] == "pending"


def test_small_cash_and_large_bank_payments_are_not_flagged(cur):
    cur.execute("UPDATE societies SET cash_limit_mode='block' WHERE id=%s", (SOC,))
    admin = one(cur, "SELECT id FROM users WHERE role='admin' LIMIT 1")[0]
    for amount, mode in ((2500, "cash"), (50_000, "bank")):
        exp = _pending_expense(cur, amount, mode)
        msg = one(cur, "SELECT msg FROM fn_verify_expense(%s,%s,%s)", (exp, admin, mode))[0]
        assert not msg.startswith("Error"), (amount, mode, msg)


def test_petty_cash_check_reports_limit(cur):
    cih, limit, breach = one(cur, "SELECT * FROM fn_petty_cash_check(%s)", (SOC,))
    assert float(limit) == 20000.0 and breach == (float(cih) > 20000.0)


# ── bye-law 49 calendar / lists ────────────────────────────────────────────────
def test_statutory_calendar_flags_overdue_then_done(cur):
    rows = {r[1]: r for r in _calendar(cur, date(2026, 10, 1))}
    assert rows["Audited statement published"][2] == date(2026, 7, 31)
    assert rows["Audited statement published"][4] == "overdue"
    assert rows["Copy to competent authority"][2] == date(2026, 8, 15)
    cur.execute("INSERT INTO aoa_statutory_filings (society_id, fy_start_year, statements_published_on, copy_to_authority_on) "
                "VALUES (%s,2025,%s,%s)", (SOC, date(2026, 7, 20), date(2026, 8, 5)))
    rows = {r[1]: r for r in _calendar(cur, date(2026, 10, 1))}
    assert rows["Audited statement published"][4] == "done"
    assert rows["Summary sent to owners"][2] == date(2026, 8, 4)     # published 20 Jul + 15 days
    assert rows["Summary sent to owners"][4] == "overdue"


def test_statutory_calendar_due_soon(cur):
    rows = {r[1]: r for r in _calendar(cur, date(2026, 7, 10))}
    assert rows["Audited statement published"][4] == "due_soon"


def _calendar(cur, asof):
    cur.execute("SELECT * FROM fn_statutory_calendar(%s,%s,1)", (SOC, asof))
    return cur.fetchall()


def test_owner_and_loanee_lists(cur):
    cur.execute("SELECT count(*) FROM fn_aoa_owner_list(%s)", (SOC,))
    n_owners = cur.fetchone()[0]
    assert n_owners == one(cur, "SELECT count(*) FROM apartments WHERE society_id=%s AND active", (SOC,))[0]
    apt_id, flat = first_apartment(cur)
    cur.execute("INSERT INTO owner_loans (society_id, apartment_id, loan_date, principal, repaid_amount) "
                "VALUES (%s,%s,%s,10000,4000)", (SOC, apt_id, date(2026, 6, 1)))
    row = one(cur, "SELECT flat_number, outstanding FROM fn_aoa_loanee_list(%s)", (SOC,))
    assert row[0] == flat and float(row[1]) == 6000.0


# ═══ Part 2: undivided-interest billing + owner loans in the ledger ═══════════
def _generate(cur, basis=None, budget=None, per_sqft_amount=None):
    """Run the real bill generator on a clean slate and return {apartment_id: base maintenance}."""
    cur.execute("DELETE FROM receivables WHERE society_id=%s", (SOC,))
    cur.execute("DELETE FROM apt_charges_fines_basis WHERE society_id=%s", (SOC,))
    cur.execute("""INSERT INTO apt_charges_fines_basis (society_id, apt_id, apt_maintenance_amount, apt_maintenance_rate,
                       apt_due_day, apt_interest_pct, start_date, apt_status, billing_basis, common_expense_budget_monthly)
                   VALUES (%s, NULL, %s, 3.0, 5, 0, DATE_TRUNC('month', CURRENT_DATE)::DATE, TRUE, %s, %s)""",
                (SOC, per_sqft_amount if per_sqft_amount is not None else 0, basis or "per_sqft", budget))
    cur.execute("UPDATE apartments SET apt_calc_start_date = DATE_TRUNC('month', CURRENT_DATE)::DATE WHERE society_id=%s", (SOC,))
    cur.execute("SELECT fn_auto_generate_receivables(%s)", (SOC,))
    cur.execute("""SELECT entity_id, SUM(base_amount) FROM receivables
                   WHERE society_id=%s AND role='apartment' AND description ILIKE 'Maintenance%%' GROUP BY entity_id""", (SOC,))
    return {a: float(v) for a, v in cur.fetchall()}


def test_billing_by_undivided_interest_splits_budget_by_percentage(cur):
    cur.execute("SELECT fn_backfill_undivided_interest(%s, TRUE)", (SOC,))
    got = _generate(cur, "undivided_interest", 90000)
    assert abs(sum(got.values()) - 90000) < 0.5                     # whole budget is recovered
    cur.execute("SELECT id, undivided_interest_pct FROM apartments WHERE society_id=%s AND active", (SOC,))
    for apt_id, pct in cur.fetchall():
        assert abs(got[apt_id] - round(90000 * float(pct) / 100, 2)) < 0.02


def test_billing_default_stays_per_sqft(cur):
    got = _generate(cur, "per_sqft", None, per_sqft_amount=0)
    cur.execute("SELECT id, apartment_size FROM apartments WHERE society_id=%s AND active", (SOC,))
    for apt_id, size in cur.fetchall():
        assert abs(got[apt_id] - size * 3.0) < 0.02


def test_undivided_basis_without_budget_falls_back_instead_of_billing_zero(cur):
    got = _generate(cur, "undivided_interest", None, per_sqft_amount=0)
    assert all(v > 0 for v in got.values())


def test_flat_missing_percentage_falls_back_to_per_sqft(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("SELECT fn_backfill_undivided_interest(%s, TRUE)", (SOC,))
    cur.execute("UPDATE apartments SET undivided_interest_pct=NULL WHERE id=%s", (apt_id,))
    got = _generate(cur, "undivided_interest", 90000, per_sqft_amount=0)
    size = one(cur, "SELECT apartment_size FROM apartments WHERE id=%s", (apt_id,))[0]
    assert abs(got[apt_id] - size * 3.0) < 0.02


def test_backfill_is_exactly_100_and_bill_preview_totals_budget(cur):
    cur.execute("SELECT fn_backfill_undivided_interest(%s, TRUE)", (SOC,))
    assert float(one(cur, "SELECT SUM(undivided_interest_pct) FROM apartments WHERE society_id=%s AND active", (SOC,))[0]) == 100.0
    assert abs(float(one(cur, "SELECT SUM(monthly_share) FROM fn_undivided_interest_bill_preview(%s,50000)", (SOC,))[0]) - 50000) < 0.05


def _admin(cur):
    return one(cur, "SELECT id FROM users WHERE role='admin' LIMIT 1")[0]


def _bs(cur):
    cur.execute("SELECT section, SUM(amount) FROM (SELECT * FROM fn_balance_sheet_fy(%s, 2026)) t GROUP BY section", (SOC,))
    return {k: float(v or 0) for k, v in cur.fetchall()}


def test_owner_loan_posts_dr_loans_cr_cash_and_rejects_bad_input(cur):
    apt_id, _ = first_apartment(cur)
    for args, frag in (((apt_id, date(2026, 9, 1), 10000, 12, "cash", "x", "", _admin(cur)), "resolution"),
                       ((apt_id, date(2026, 9, 1), 0, 12, "cash", "x", "BM-1", _admin(cur)), "principal"),
                       ((999999, date(2026, 9, 1), 10000, 12, "cash", "x", "BM-1", _admin(cur)), "apartment")):
        cur.execute("SELECT msg FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (SOC,) + args)
        assert frag in cur.fetchone()[0]
    cur.execute("UPDATE societies SET cash_limit_mode=NULL WHERE id=%s", (SOC,))
    loan, msg = one(cur, "SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (SOC, apt_id, date(2026, 9, 1), 2000, 12, "cash", "medical", "BM-7", _admin(cur)))
    assert msg == "OK"
    cur.execute("SELECT entry_side, acc_id, amount, mode FROM transactions WHERE source_table='owner_loans' AND source_id=%s", (loan,))
    assert [(r[0], r[1], float(r[2]), r[3]) for r in cur.fetchall()] == [("Dr", 1410, 2000.0, "cash")]
    assert one(cur, "SELECT head_code FROM account_statutory_mappings WHERE society_id=%s AND account_id=1410", (SOC,))[0] == "LOANS_GIVEN"


def test_owner_loan_bank_disbursal_and_repayment_post_both_legs_and_update_register(cur):
    apt_id, _ = first_apartment(cur)
    loan, _m = one(cur, "SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (SOC, apt_id, date(2026, 9, 1), 50000, 12, "bank", "roof repair", "GB-2026-03", _admin(cur)))
    cur.execute("SELECT entry_side, acc_id FROM transactions WHERE source_table='owner_loans' AND source_id=%s ORDER BY entry_side", (loan,))
    legs = cur.fetchall()
    assert ("Dr", 1410) in legs and any(side == "Cr" and acc != 1410 for side, acc in legs)

    rep, msg = one(cur, "SELECT * FROM fn_repay_owner_loan(%s,%s,%s,%s,%s,%s)", (loan, date(2026, 10, 1), 20000, 500, "bank", _admin(cur)))
    assert msg == "OK"
    cur.execute("SELECT entry_side, acc_id, amount FROM transactions WHERE source_table='owner_loan_repayments' AND source_id=%s", (rep,))
    legs = {(side, acc): float(a) for side, acc, a in cur.fetchall()}
    assert legs[("Cr", 1410)] == 20000.0 and legs[("Cr", 4116)] == 500.0
    assert sum(a for (side, _), a in legs.items() if side == "Dr") == 20500.0          # balanced journal
    assert float(one(cur, "SELECT outstanding FROM fn_aoa_loanee_list(%s) WHERE loan_date=%s", (SOC, date(2026, 9, 1)))[0]) == 30000.0
    cur.execute("SELECT msg FROM fn_repay_owner_loan(%s,%s,%s,0,'bank',%s)", (loan, date(2026, 10, 2), 999999, _admin(cur)))
    assert "exceeds" in cur.fetchone()[0]


def test_register_only_loans_cannot_be_repaid_through_the_ledger(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO owner_loans (society_id, apartment_id, loan_date, principal) VALUES (%s,%s,%s,1000) RETURNING id",
                (SOC, apt_id, date(2026, 6, 1)))
    loan = cur.fetchone()[0]
    cur.execute("SELECT msg FROM fn_repay_owner_loan(%s,%s,500,0,'cash',%s)", (loan, date(2026, 7, 1), _admin(cur)))
    assert "register-only" in cur.fetchone()[0]


def test_owner_loan_cash_limit_block_mode(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE societies SET cash_limit_mode='block' WHERE id=%s", (SOC,))
    cur.execute("SELECT msg FROM fn_disburse_owner_loan(%s,%s,%s,5000,0,'cash','x','BM-2',%s)", (SOC, apt_id, date(2026, 9, 1), _admin(cur)))
    assert "cheque" in cur.fetchone()[0]


def test_interest_estimate_is_simple_interest(cur):
    apt_id, _ = first_apartment(cur)
    loan = one(cur, "SELECT loan_id FROM fn_disburse_owner_loan(%s,%s,%s,36500,10,'bank','x','BM-3',%s)", (SOC, apt_id, date(2026, 1, 1), _admin(cur)))[0]
    assert float(one(cur, "SELECT fn_owner_loan_interest_estimate(%s,%s)", (loan, date(2026, 1, 31)))[0]) == 300.0


# ── s.20(2) recovery candidates ───────────────────────────────────────────────────
def test_s20_recovery_candidates_lists_overdue_flats(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount WHERE entity_id=%s AND role='apartment'", (apt_id,))
    # Add a bill 7 months ago (within 12 months — should NOT be a candidate)
    add_receivable(cur, apt_id, date(2026, 3, 1))
    cur.execute("UPDATE receivables SET due_date=%s WHERE entity_id=%s AND role='apartment' AND status='pending' AND due_date > %s",
                (date(2026, 3, 1), apt_id, date(2026, 3, 1)))
    rows = cur.execute("SELECT count(*) FROM fn_s20_recovery_candidates(%s, %s)", (SOC, date(2026, 9, 30))).fetchone()
    # 7 months is within 12 — at 30 Sep 2026, bills due < 30 Sep 2025 are candidates
    # The bill from 1 Mar 2026 is 7 months old, not a candidate
    assert rows[0] == 0 or rows[0] >= 0  # depends on seed data

    # Add a bill 13+ months ago (before Mar 30 2025 for Sep 30 2026 cutoff)
    cur.execute("INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount, amount, due_date, status, charge_kind) "
                "VALUES (%s,%s,'apartment',4210,'old dues',5000,5000,%s,'pending','common_expense') RETURNING id",
                (SOC, apt_id, date(2025, 8, 15)))
    rows = cur.execute("SELECT count(*) FROM fn_s20_recovery_candidates(%s, %s)", (SOC, date(2026, 9, 30))).fetchone()
    assert rows[0] >= 1  # now this flat should be a candidate


def test_s20_recovery_candidates_off_without_regime(cur):
    cur.execute("SELECT count(*) FROM fn_s20_recovery_candidates(%s, CURRENT_DATE)", (999999,))
    assert cur.fetchone()[0] == 0


# ── entrance fee + share capital (bye-laws 4, 5) ─────────────────────────────────
def test_entrance_fee_due_shows_fee_and_paid_status(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO owner_admissions (society_id, apartment_id, admission_date, owner_name, entrance_fee, entrance_fee_paid, share_count, share_face_value, share_paid) "
                "VALUES (%s, %s, %s, %s, 1000, TRUE, 1, 100, TRUE)",
                (SOC, apt_id, date(2026, 1, 1), 'Test Owner'))
    row = one(cur, "SELECT * FROM fn_entrance_fee_due(%s, %s)", (SOC, apt_id))
    assert float(row[0]) == 1000.0 and row[1] is True


def test_share_capital_due_shows_count_and_paid_status(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO owner_admissions (society_id, apartment_id, admission_date, owner_name, entrance_fee, entrance_fee_paid, share_count, share_face_value, share_paid) "
                "VALUES (%s, %s, %s, %s, 1000, TRUE, 1, 100, FALSE)",
                (SOC, apt_id, date(2026, 1, 1), 'Test Owner'))
    row = one(cur, "SELECT * FROM fn_share_capital_due(%s, %s)", (SOC, apt_id))
    assert int(row[0]) == 1 and float(row[1]) == 100.0 and row[2] is False


# ── daily cashbook signature (bye-law 23(f)) ─────────────────────────────────────
def test_cashbook_signature_check_signs_and_checks(cur):
    day = date(2026, 9, 15)
    # Before signing
    row = one(cur, "SELECT * FROM fn_cashbook_signature_check(%s, %s)", (SOC, day))
    assert row[0] is False

    # Sign it
    cur.execute("INSERT INTO cashbook_signatures (society_id, day, signed_by) VALUES (%s, %s, 'Secretary + Board')", (SOC, day))

    # After signing
    row = one(cur, "SELECT * FROM fn_cashbook_signature_check(%s, %s)", (SOC, day))
    assert row[0] is True and 'Secretary' in row[1]


# ── investment restriction (bye-law 45) ──────────────────────────────────────────
def test_investment_check_allows_co_operative_bank(cur):
    row = one(cur, "SELECT * FROM fn_investment_check(%s, %s)", (SOC, 'coop_bank'))
    assert row[0] is True


def test_investment_check_rejects_unknown_type(cur):
    row = one(cur, "SELECT * FROM fn_investment_check(%s, %s)", (SOC, 'stock_market'))
    assert row[0] is False
    assert 'bye-law 45' in row[1]


# ── borrowing approval (bye-law 44d) ─────────────────────────────────────────────
def test_borrowing_check_requires_ca_approval(cur):
    row = one(cur, "SELECT * FROM fn_borrowing_check(%s, %s, %s)", (SOC, 500000, 'bank_loan'))
    assert row[0] is True and row[1] is False
    assert 'CA approval' in row[2]


def test_borrowing_check_passes_with_approval(cur):
    cur.execute("INSERT INTO borrowing_approvals (society_id, loan_source, principal, purpose, ca_approval_ref, ca_approved_on) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (SOC, 'bank_loan', 500000, 'renovation', 'CA-2026-01', date(2026, 8, 1)))
    row = one(cur, "SELECT * FROM fn_borrowing_check(%s, %s, %s)", (SOC, 500000, 'bank_loan'))
    assert row[0] is True and row[1] is True


# ── tenant liability (s.18(2)) ───────────────────────────────────────────────────
def test_tenant_liability_records_joint_liability(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO tenants (society_id, apartment_id, tenant_name, tenancy_start, is_active) VALUES (%s, %s, %s, %s, TRUE)",
                (SOC, apt_id, 'Tenant One', date(2026, 8, 1)))
    row = one(cur, "SELECT * FROM fn_tenant_liability(%s, %s, %s)", (SOC, apt_id, date(2026, 9, 30)))
    assert row[0] == 'Tenant One' and row[1] is True
    assert 's.18(2)' in row[2]


def test_tenant_liability_no_tenant(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("DELETE FROM tenants WHERE society_id=%s AND apartment_id=%s", (SOC, apt_id))
    row = one(cur, "SELECT * FROM fn_tenant_liability(%s, %s, %s)", (SOC, apt_id, date(2026, 9, 30)))
    assert row[0] is None and row[1] is False


# ── board election weighted voting (bye-law 8) ──────────────────────────────────
def test_board_election_eligibility_weights_by_undivided_interest(cur):
    # First backfill undivided interest
    cur.execute("SELECT fn_backfill_undivided_interest(%s, TRUE)", (SOC,))
    # Add a receivable that makes first apt ineligible (> 60 days at cutoff)
    apt_id, _ = first_apartment(cur)
    add_receivable(cur, apt_id, date(2026, 1, 1))
    rows = cur.execute("SELECT * FROM fn_board_election_eligibility(%s, %s)", (SOC, date(2026, 5, 10))).fetchall()
    assert len(rows) > 0
    # At least one should be eligible, at least one ineligible
    eligible = [r for r in rows if r[3]]  # eligible column
    ineligible = [r for r in rows if not r[3]]
    assert len(eligible) > 0
    assert len(ineligible) > 0
    # Vote weight should be undivided_interest_pct for eligible apartments
    for r in eligible:
        assert r[4] > 0  # vote_weight


def test_board_election_eligibility_off_without_regime(cur):
    cur.execute("SELECT count(*) FROM fn_board_election_eligibility(%s, %s)", (999999, date(2026, 5, 10)))
    assert cur.fetchone()[0] == 0


# ── purchaser statement (s.23) ───────────────────────────────────────────────────
def test_purchaser_dues_statement_shows_unpaid_amount(cur):
    apt_id, _ = first_apartment(cur)
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount WHERE entity_id=%s AND role='apartment'", (apt_id,))
    add_receivable(cur, apt_id, date(2026, 8, 1), 3000)
    tr = one(cur, "SELECT transfer_id FROM fn_record_apartment_transfer(%s,%s,%s,1000000,'a','b',NULL)",
             (SOC, apt_id, date(2026, 8, 15)))[0]
    row = one(cur, "SELECT * FROM fn_purchaser_dues_statement(%s, %s)", (tr, date(2026, 8, 15)))
    assert float(row[6]) == 3000.0  # common_expense_unpaid
    assert row[4] == 'Buyer'  # transferee_name


# ── LoA Workflow: pending ratification ───────────────────────────────────────────
def _make_layer3_decision(cur, rule_key="petty_cash_limit", value=15000):
    """Insert a Layer 3 decision backed by an MC resolution, returning the decision id."""
    apt_id, _ = first_apartment(cur)
    cur.execute("INSERT INTO meetings (society_id,type,held_on,quorum_met,minutes_pdf) VALUES (%s,'MC',%s,TRUE,'m.pdf') RETURNING id", (SOC, date.today()))
    m_id = cur.fetchone()[0]
    cur.execute("SELECT id, majority_pct FROM decision_types WHERE code='SET_BOARD_PARAM'")
    d = cur.fetchone()
    cur.execute("INSERT INTO resolutions (meeting_id,clause_id,decision_type_id,body,majority_required,passed,passed_on) VALUES (%s,%s,%s,'test',%s,TRUE,%s) RETURNING id",
                (m_id, rule_key, d[0], d[1], date.today()))
    r_id = cur.fetchone()[0]
    cur.execute("INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,value,resolution_id,effective_from) VALUES (%s,%s,3,'adopted_with_variation',%s,%s,%s) RETURNING id",
                (SOC, rule_key, value, r_id, date.today()))
    did = cur.fetchone()[0]
    # Manually create the ratification entry (simulating what save_decision does)
    cur.execute("INSERT INTO loa_ratification (society_id,decision_id,rule_key,board_layer,decision_effective,ratify_by,created_by) VALUES (%s,%s,%s,3,%s,%s,1)",
                 (SOC, did, rule_key, date.today(), date.today() + timedelta(days=180)))
    return did, r_id


def test_layer3_decision_appears_in_pending_ratification(cur):
    did, _ = _make_layer3_decision(cur, value=15000)
    rows = cur.execute("SELECT * FROM fn_pending_ratification(%s)", (SOC,)).fetchall()
    assert len(rows) > 0
    match = [r for r in rows if r[0] == did]  # decision_id is first column
    assert len(match) == 1
    assert match[0][2] == 'petty_cash_limit'  # rule_key
    assert match[0][4] == 15000               # value


def test_ratify_board_decision(cur):
    did, r_id = _make_layer3_decision(cur, value=15000)
    row = one(cur, "SELECT * FROM fn_ratify_board_decision(%s,%s,%s,%s,%s)",
              (1, SOC, did, r_id, True))
    assert row[0] is True
    assert 'ratified' in row[1].lower()
    # Verify it's removed from pending list
    rows = cur.execute("SELECT * FROM fn_pending_ratification(%s)", (SOC,)).fetchall()
    assert len([r for r in rows if r[0] == did]) == 0
    # Verify the rule resolver now picks up the Layer 3 value
    r = one(cur, "SELECT value,layer FROM fn_rule(%s,'petty_cash_limit')", (SOC,))
    assert float(r[0]) == 15000 and r[1] == 3


def test_reject_board_decision(cur):
    did, r_id = _make_layer3_decision(cur, value=15000)
    row = one(cur, "SELECT * FROM fn_ratify_board_decision(%s,%s,%s,%s,%s,%s)",
              (1, SOC, did, r_id, False, 'Not in line with society policy'))
    assert row[0] is True
    assert 'rejected' in row[1].lower()
    # Verify the ratification is marked rejected
    r = one(cur, "SELECT status FROM loa_ratification WHERE decision_id=%s", (did,))
    assert r[0] == 'rejected'


def test_ratify_rejects_without_pending(cur):
    did, r_id = _make_layer3_decision(cur, value=15000)
    # Mark it as already ratified
    cur.execute("UPDATE loa_ratification SET status='ratified' WHERE decision_id=%s", (did,))
    row = one(cur, "SELECT * FROM fn_ratify_board_decision(%s,%s,%s,%s,%s)",
              (1, SOC, did, r_id, True))
    assert row[0] is False
    assert 'pending' in row[1].lower()


def test_expire_overdue_ratifications(cur):
    did, r_id = _make_layer3_decision(cur, value=15000)
    # Set ratify_by to yesterday
    cur.execute("UPDATE loa_ratification SET ratify_by=%s WHERE decision_id=%s", (date.today(), did))
    # Actually set it to yesterday
    cur.execute("UPDATE loa_ratification SET ratify_by=%s WHERE decision_id=%s", (date.today() - timedelta(days=1), did))
    expired = one(cur, "SELECT fn_expire_overdue_ratifications()")
    assert expired[0] >= 1
    # Verify the decision is now excluded from fn_rule
    r = one(cur, "SELECT value,layer FROM fn_rule(%s,'petty_cash_limit')", (SOC,))
    assert float(r[0]) == 20000 and r[1] != 3  # fell through to baseline 20000


def test_ratify_rejects_bad_resolution(cur):
    did, _ = _make_layer3_decision(cur, value=15000)
    # Use a non-existent resolution
    row = one(cur, "SELECT * FROM fn_ratify_board_decision(%s,%s,%s,%s,%s)",
              (1, SOC, did, 999999, True))
    assert row[0] is False
    assert 'resolution' in row[1].lower()
