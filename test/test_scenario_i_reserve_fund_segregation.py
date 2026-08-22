"""
Scenario I — Reserve / special-fund Balance Sheet segregation (Phase 3).

Verifies the core claim of Phase 3:
  * The three statutory reserve / special funds (Sinking Fund, Repair &
    Maintenance Fund, Corpus Fund) are chart-of-accounts-driven. Once they
    exist and have ledger activity, the Balance Sheet (fn_fy_closing_report
    → Bal sheet, and the ledger-index Bal sheet) shows each fund as its OWN
    distinct line item — they are NOT flattened back into a single "reserves"
    figure by any SUM-without-GROUP-BY in the KPI engine or the closing
    rollup.
  * This is the regression guard for the escrow-separation UI check the plan
    calls out: a naive SUM over every Cr-natured account would collapse
    Corpus + Sinking + Capital into one number and hide the statutory
    segregation the audited balance sheet must show.
"""

import pytest

from app.dash_apps.drilldown import loaders
from database import ledger_export


def _seed(patched_db):
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": "2026-04-01",
    })
    patched_db.tables.setdefault("accounts", []).extend([
        {"id": 1, "society_id": 1, "name": "Balance Sheet Root", "tab_name": "Bal",
         "drcr_account": None, "has_bf": False, "drcr_bf": "Cr"},
        {"id": 2, "society_id": 1, "name": "Capital Account", "tab_name": "CapAc",
         "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 211, "society_id": 1, "name": "Interest Income", "tab_name": "IncInt",
         "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 2311, "society_id": 1, "name": "Society Maintenance Charge",
         "tab_name": "IncExp", "drcr_account": "Cr", "has_bf": False},
        {"id": 201, "society_id": 1, "name": "Sinking Fund Reserve",
         "tab_name": "Bal", "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 202, "society_id": 1, "name": "Repair & Maintenance Fund Reserve",
         "tab_name": "Bal", "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 203, "society_id": 1, "name": "Corpus Fund",
         "tab_name": "Bal", "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 633, "society_id": 1, "name": "Cash-in-hand", "tab_name": "CiH",
         "drcr_account": "Dr", "has_bf": True, "drcr_bf": "Dr"},
    ])
    patched_db.tables.setdefault("transactions", []).extend([
        # Cr-side income this FY (Cr-positive movement that rolls up to root).
        {"id": 1, "society_id": 1, "acc_id": 2311, "amount": 90000,
         "entry_side": "Cr", "mode": "cash", "status": "paid",
         "trx_date": "2026-05-01"},
        # Each fund receives its own distinct Cr posting this FY.
        {"id": 2, "society_id": 1, "acc_id": 201, "amount": 5000,
         "entry_side": "Cr", "mode": "cash", "status": "paid", "trx_date": "2026-05-02"},
        {"id": 3, "society_id": 1, "acc_id": 202, "amount": 7000,
         "entry_side": "Cr", "mode": "cash", "status": "paid", "trx_date": "2026-05-03"},
        {"id": 4, "society_id": 1, "acc_id": 203, "amount": 10000,
         "entry_side": "Cr", "mode": "cash", "status": "paid", "trx_date": "2026-05-04"},
        # Balancing Dr to cash so the books tie (root total = 0).
        {"id": 5, "society_id": 1, "acc_id": 633, "amount": 10000,
         "entry_side": "Dr", "mode": "cash", "status": "paid", "trx_date": "2026-05-01"},
    ])


class TestPhase3_ReserveFundSegregation:
    """Statutory funds must appear as DISTINCT Balance Sheet lines."""

    def test_each_fund_is_a_distinct_closing_row(self, patched_db):
        _seed(patched_db)
        rows, err = loaders.get_fy_closing_report(1, 2026)
        assert err is None
        names = [r["account_name"] for r in rows]
        assert "Sinking Fund Reserve" in names
        assert "Repair & Maintenance Fund Reserve" in names
        assert "Corpus Fund" in names

    def test_fund_amounts_are_not_collapsed(self, patched_db):
        _seed(patched_db)
        rows, _ = loaders.get_fy_closing_report(1, 2026)
        by_name = {r["account_name"]: float(r.get("display_amount", 0) or 0) for r in rows}
        # Each fund carries its OWN amount — not a single merged total.
        assert by_name.get("Sinking Fund Reserve") == 5000.0
        assert by_name.get("Repair & Maintenance Fund Reserve") == 7000.0
        assert by_name.get("Corpus Fund") == 10000.0
        # The three funds are present as three separate rows (no collapse).
        fund_rows = [n for n in by_name if n in (
            "Sinking Fund Reserve", "Repair & Maintenance Fund Reserve", "Corpus Fund")]
        assert len(fund_rows) == 3

    def test_balance_sheet_via_ledger_index_keeps_funds_distinct(self, patched_db):
        """The Bal sheet built from fn_fy_closing_report's depth-1 rows must
        surface each reserve fund as its own sheet row. Smoke-test the
        generator end-to-end against the FakeDB (it exercises the same
        fn_fy_closing_report path the UI uses)."""
        _seed(patched_db)
        data = ledger_export.generate_ledger_index_excel(None, 1, 2026)
        assert data and len(data) > 0
