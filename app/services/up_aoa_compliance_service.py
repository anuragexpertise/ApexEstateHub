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
