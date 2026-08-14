"""
Scenario G — Financial Year close.

Tests:
  1. FY closing report returns rows for a given FY.
  2. Trial balance sums Dr and Cr sides.
  3. Balance sheet balances (total Dr == total Cr).
  4. Ledger entries for an account are FY-scoped.
  5. Account list returns society-scoped accounts.
"""

import pytest
from datetime import date

from app.services import auth_service, society_service
from app.dash_apps.drilldown import loaders


def _seed_financial_world(patched_db):
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": date(2026, 4, 1),
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
        "linked_id": None, "failed_login_attempts": 0, "locked_until": None,
    })
    patched_db.tables.setdefault("accounts", []).extend([
        {"id": 633, "society_id": 1, "name": "Cash-in-hand", "tab_name": "CurAs",
         "drcr_account": "Dr", "has_bf": True, "drcr_bf": "Dr"},
        {"id": 6311, "society_id": 1, "name": "SBI A/c", "tab_name": "BkAc",
         "drcr_account": "Dr", "has_bf": True, "drcr_bf": "Dr"},
        {"id": 2, "society_id": 1, "name": "Capital Account", "tab_name": "CapAc",
         "drcr_account": "Cr", "has_bf": True, "drcr_bf": "Cr"},
        {"id": 2311, "society_id": 1, "name": "Society Maintenance Charge",
         "tab_name": "IncExp", "drcr_account": "Cr", "has_bf": False},
    ])
    # Seed transactions for FY 2025-26 — balanced books
    patched_db.tables.setdefault("transactions", []).extend([
        {"id": 1, "society_id": 1, "acc_id": 2311, "amount": 12000, "entry_side": "Cr",
         "mode": "cash", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Maint Apr", "updated_by": 1},
        {"id": 2, "society_id": 1, "acc_id": 2311, "amount": 12000, "entry_side": "Cr",
         "mode": "cash", "status": "paid", "trx_date": "2025-05-05",
         "particulars": "Maint May", "updated_by": 1},
        {"id": 3, "society_id": 1, "acc_id": 633, "amount": 12000, "entry_side": "Dr",
         "mode": "cash", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Cash received", "updated_by": 1},
        {"id": 4, "society_id": 1, "acc_id": 6311, "amount": 12000, "entry_side": "Dr",
         "mode": "bank", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Bank receipt", "updated_by": 1},
    ])


class TestScenarioG_FinancialYearClose:
    """FY closing report, trial balance, balance sheet, and ledger."""

    def test_fy_closing_report_returns_rows(self, patched_db):
        _seed_financial_world(patched_db)
        rows, err = loaders.get_fy_closing_report(1, 2025)
        assert err is None
        assert len(rows) > 0

    def test_fy_closing_report_contains_known_accounts(self, patched_db):
        _seed_financial_world(patched_db)
        rows, _ = loaders.get_fy_closing_report(1, 2025)
        names = [r["account_name"] for r in rows]
        assert any("Cash" in n or "Capital" in n for n in names)

    def test_trial_balance_sums_dr_and_cr(self, patched_db):
        _seed_financial_world(patched_db)
        rows = patched_db._fn_trial_balance(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=True
        )
        assert rows is not None
        for r in rows:
            assert "dr_total" in r
            assert "cr_total" in r

    def test_balance_sheet_totals_match(self, patched_db):
        _seed_financial_world(patched_db)
        bs = patched_db._fn_balance_sheet(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=False
        )
        assert bs is not None
        assert "total_dr" in bs
        assert "total_cr" in bs
        # In our fake, both sides should equal the seeded transaction totals
        assert bs["total_dr"] == bs["total_cr"]

    def test_ledger_fy_scoped_returns_entries(self, patched_db):
        _seed_financial_world(patched_db)
        ledger = patched_db._fn_account_ledger_fy(
            {"p0": 1, "p1": 2311, "p2": 2025}, fetch_one=False, fetch_all=True
        ) or []
        assert len(ledger) == 2
        amounts = [float(t["amount"]) for t in ledger]
        assert sum(amounts) == 24000.0

    def test_ledger_different_fy_returns_empty(self, patched_db):
        _seed_financial_world(patched_db)
        ledger = patched_db._fn_account_ledger_fy(
            {"p0": 1, "p1": 2311, "p2": 2026}, fetch_one=False, fetch_all=True
        ) or []
        assert len(ledger) == 0

    def test_account_list_returns_society_accounts(self, patched_db):
        _seed_financial_world(patched_db)
        accounts = patched_db._fn_accounts_list(
            {"p0": 1, "p1": None}, fetch_one=False, fetch_all=True
        )
        assert accounts is not None
        assert len(accounts) == 4
        names = [a["name"] for a in accounts]
        assert "Cash-in-hand" in names
        assert "Capital Account" in names

    def test_get_available_financial_years(self, patched_db):
        _seed_financial_world(patched_db)
        years = loaders.get_available_financial_years(1)
        assert isinstance(years, list)
        assert len(years) > 0
        assert all(isinstance(y, int) for y in years)

    def test_fy_label_format(self, patched_db):
        label = loaders.fy_label(2025)
        assert label == "2025-26"

    def test_receipt_affects_balance_sheet(self, patched_db):
        _seed_financial_world(patched_db)
        # Add a receipt (Cr to Capital or Income)
        patched_db.tables["transactions"].append({
            "id": 10, "society_id": 1, "acc_id": 2, "amount": 5000,
            "entry_side": "Cr", "mode": "cash", "status": "paid",
            "trx_date": "2025-06-01", "particulars": "Extra income", "updated_by": 1,
        })
        bs = patched_db._fn_balance_sheet(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=False
        )
        # Capital Cr should now include the extra 5000
        capital = next((r for r in bs.get("cr_side", []) if "Capital" in r.get("account_name", "")), None)
        assert capital is not None
        assert capital["amount"] >= 5000
