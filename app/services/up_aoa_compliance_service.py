# app/services/up_aoa_compliance_service.py
"""
Thin wrappers over the UP Apartment Act 2010 / Model Bye-Laws 2011 compliance
functions in database/estatehub.sql (section "UP AOA COMPLIANCE LAYER").

The rules themselves live in SQL, next to the ledger they police, and are driven by
society_legal_regime -> regime_rule_parameters. A society whose regime does not
define a rule gets an empty list / None back, never a wrong answer. Callers should
treat that as "rule not applicable", not as "compliant".

These functions REPORT. They never cut a service, never disqualify a member and
never file anything: the Board and the competent authority do that.
"""
from __future__ import annotations

from datetime import date

from database.db_manager import db


def _rows(sql: str, params: tuple) -> list[dict]:
    return db._execute(sql, params, fetch_all=True) or []


def statutory_calendar(society_id: int, as_of: date | None = None, years: int = 3) -> list[dict]:
    """Bye-law 49 deadlines (31 Jul statement, 15 Aug authority copy, 15-day owner summary)."""
    return _rows("SELECT * FROM fn_statutory_calendar(%s, COALESCE(%s, CURRENT_DATE), %s)",
                 (society_id, as_of, years))


def bye_law7_eligibility(society_id: int, election_date: date, basis: str | None = None) -> list[dict]:
    """Per-apartment eligibility to vote / stand. basis: 'financial_year' | 'calendar_year' | None (regime default)."""
    return _rows("SELECT * FROM fn_bye_law7_eligibility(%s, %s, %s)", (society_id, election_date, basis))


def service_cutoff_check(proceeding_id: int, as_of: date | None = None) -> dict | None:
    """Section 22 preconditions: {'can_cut_off', 'earliest_cutoff_date', 'blockers'}."""
    rows = _rows("SELECT * FROM fn_service_cutoff_check(%s, COALESCE(%s, CURRENT_DATE))", (proceeding_id, as_of))
    return rows[0] if rows else None


def record_apartment_transfer(society_id: int, apartment_id: int, transfer_date: date, transfer_value: float,
                              transferor: str | None, transferee: str | None, created_by: int | None) -> dict:
    """Levy the 1/2% transfer fee into the Major Repair Fund. Returns {'transfer_id','receivable_id','fee_amount','msg'}."""
    rows = _rows("SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,%s,%s,%s)",
                 (society_id, apartment_id, transfer_date, transfer_value, transferor, transferee, created_by))
    return rows[0] if rows else {"msg": "Error: no response from fn_record_apartment_transfer"}


def nodues_certificate_status(transfer_id: int, as_of: date | None = None) -> dict | None:
    rows = _rows("SELECT * FROM fn_nodues_certificate_status(%s, COALESCE(%s, CURRENT_DATE))", (transfer_id, as_of))
    return rows[0] if rows else None


def undivided_interest_summary(society_id: int) -> dict | None:
    rows = _rows("SELECT * FROM fn_undivided_interest_summary(%s)", (society_id,))
    return rows[0] if rows else None


def undivided_interest_report(society_id: int) -> list[dict]:
    return _rows("SELECT * FROM fn_undivided_interest_report(%s)", (society_id,))


def owner_list(society_id: int) -> list[dict]:
    """Annexure to the bye-law 49 statement."""
    return _rows("SELECT * FROM fn_aoa_owner_list(%s)", (society_id,))


def loanee_list(society_id: int) -> list[dict]:
    """Annexure to the bye-law 49 statement (outstanding owner loans only)."""
    return _rows("SELECT * FROM fn_aoa_loanee_list(%s)", (society_id,))


def petty_cash_check(society_id: int, as_of: date | None = None) -> dict | None:
    rows = _rows("SELECT * FROM fn_petty_cash_check(%s, COALESCE(%s, CURRENT_DATE))", (society_id, as_of))
    return rows[0] if rows else None


def s20_recovery_candidates(society_id: int, as_of: date | None = None) -> list[dict]:
    """Section 20(2): flats with common-expense dues unpaid for more than 12 months — candidates for recovery as land revenue."""
    return _rows("SELECT * FROM fn_s20_recovery_candidates(%s, COALESCE(%s, CURRENT_DATE))", (society_id, as_of))


def entrance_fee_due(society_id: int, apartment_id: int) -> dict | None:
    """Bye-law 4: ₹1,000 entrance fee on owner admission."""
    rows = _rows("SELECT * FROM fn_entrance_fee_due(%s, %s)", (society_id, apartment_id))
    return rows[0] if rows else None


def share_capital_due(society_id: int, apartment_id: int) -> dict | None:
    """Bye-law 5: one share per owner at admission."""
    rows = _rows("SELECT * FROM fn_share_capital_due(%s, %s)", (society_id, apartment_id))
    return rows[0] if rows else None


def cashbook_signature_check(society_id: int, day: date) -> dict | None:
    """Bye-law 23(f): daily cashbook signature check."""
    rows = _rows("SELECT * FROM fn_cashbook_signature_check(%s, %s)", (society_id, day))
    return rows[0] if rows else None


def investment_check(society_id: int, institution_type: str) -> dict | None:
    """Bye-law 45: investment restriction check."""
    rows = _rows("SELECT * FROM fn_investment_check(%s, %s)", (society_id, institution_type))
    return rows[0] if rows else None


def borrowing_check(society_id: int, principal: float, loan_source: str) -> dict | None:
    """Bye-law 44(d): borrowing approval check."""
    rows = _rows("SELECT * FROM fn_borrowing_check(%s, %s, %s)", (society_id, principal, loan_source))
    return rows[0] if rows else None


def tenant_liability(society_id: int, apartment_id: int, as_of: date | None = None) -> dict | None:
    """Act s.18(2): tenant jointly liable with owner for common expenses."""
    rows = _rows("SELECT * FROM fn_tenant_liability(%s, %s, COALESCE(%s, CURRENT_DATE))", (society_id, apartment_id, as_of))
    return rows[0] if rows else None


def board_election_eligibility(society_id: int, election_date: date, basis: str | None = None) -> list[dict]:
    """Bye-law 8: Board election voting eligibility, weighted by undivided interest."""
    return _rows("SELECT * FROM fn_board_election_eligibility(%s, %s, %s)", (society_id, election_date, basis))


def board_election_results(society_id: int, position: str) -> list[dict]:
    """Declare Board election results with weighted vote percentages."""
    return _rows("SELECT * FROM fn_declare_board_election_results(%s, %s)", (society_id, position))


def purchaser_dues_statement(transfer_id: int, as_of: date | None = None) -> dict | None:
    """Act s.23: statement of unpaid common-expense assessment for the purchaser."""
    rows = _rows("SELECT * FROM fn_purchaser_dues_statement(%s, %s)", (transfer_id, as_of))
    return rows[0] if rows else None


# ── Registers, audits and tracked checks (bye-laws 47–58) ────────────────────
# These were written into the SQL layer with "gated"/"tracked" feeds and never
# reached from the app. Each wrapper is one read; the UP compliance card renders
# them all so a "tracked" rule is actually tracked, and a "gated" one shows what
# its gate produces.

def auditor_appointment_check(society_id: int, fy: int) -> dict | None:
    """Bye-law 51: auditor appointment recorded at the AGM for this financial year."""
    rows = _rows("SELECT * FROM fn_auditor_appointment_check(%s, %s)", (society_id, fy))
    return rows[0] if rows else None


def auditor_remuneration_check(society_id: int, fy: int) -> dict | None:
    """Bye-law 52: auditor remuneration fixed by the General Body for this financial year."""
    rows = _rows("SELECT * FROM fn_auditor_remuneration_check(%s, %s)", (society_id, fy))
    return rows[0] if rows else None


def investment_register_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 47: investment register totals and compliance with allowed types."""
    rows = _rows("SELECT * FROM fn_investment_register_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def affiliation_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 48: affiliation register."""
    rows = _rows("SELECT * FROM fn_affiliation_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def accounts_inspection_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 48: accounts available for member inspection."""
    rows = _rows("SELECT * FROM fn_accounts_inspection_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def accounts_publication_check(society_id: int, fy: int) -> dict | None:
    """Bye-law 50: publication of accounts."""
    rows = _rows("SELECT * FROM fn_accounts_publication_check(%s, %s)", (society_id, fy))
    return rows[0] if rows else None


def mortgage_notice_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 53: mortgage notices received and pending Board acknowledgement."""
    rows = _rows("SELECT * FROM fn_mortgage_notice_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def unpaid_assessments_notice(society_id: int, apartment_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 54: statement of unpaid assessments for a flat (transfer context)."""
    rows = _rows("SELECT * FROM fn_unpaid_assessments_notice(%s, %s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, apartment_id, as_of))
    return rows[0] if rows else None


def seal_register_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 56: common-seal register."""
    rows = _rows("SELECT * FROM fn_seal_register_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def ca_inspection_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 57: Competent Authority inspections and pending actions."""
    rows = _rows("SELECT * FROM fn_ca_inspection_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def bye_law_amendment_log(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 58: amendments recorded and still awaiting CA approval."""
    rows = _rows("SELECT * FROM fn_bye_law_amendment_log(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def act_prevails_check(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 55: the Act prevails over inconsistent bye-laws."""
    rows = _rows("SELECT * FROM fn_act_prevails_check(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None


def appropriate_depreciation_fund(society_id: int, as_of: date | None = None) -> dict | None:
    """Bye-law 46(d): create the FY depreciation-fund appropriation receivable.

    This is the posting wrapper for fn_appropriate_depreciation_fund; the rates
    behind it are regime parameters (depreciation_fund_pct / basis / rate) that the
    Board or master records through the AOA Rule Editor with a resolution trail.
    """
    rows = _rows("SELECT * FROM fn_appropriate_depreciation_fund(%s, COALESCE(%s, CURRENT_DATE))",
                 (society_id, as_of))
    return rows[0] if rows else None
