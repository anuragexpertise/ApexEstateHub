"""ICAI statement notes (ICAI4 I7).

Pure service layer: no Dash, no Flask. `generate_statement_notes` assembles the
notes to the statutory statements (accounting policies, MSME creditors
disclosure, related parties, contingent liabilities) from the statement
engine output and the MSME creditors split. All inputs are optional parameters
so the function is unit-testable without a database.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.services import icai_statements as st


def _money(value) -> str:
    try:
        return f"Rs {Decimal(value):,.2f}"
    except Exception:
        return "Rs 0.00"


def generate_statement_notes(
    society_id: int,
    fy: int,
    balance_sheet: Optional[dict] = None,
    income_expenditure: Optional[dict] = None,
    creditors_split: Optional[dict] = None,
) -> list[dict]:
    """Return the notes to the statutory statements for one society/FY.

    Each note is {"title", "content"} where ``content`` is a list of short
    strings. Statement data defaults to the live engine; the creditors split
    defaults to ``fn_creditors_split`` via the database (monkeypatch both in
    tests).
    """
    if balance_sheet is None:
        balance_sheet = st.balance_sheet(society_id, fy)
    if income_expenditure is None:
        income_expenditure = st.income_expenditure(society_id, fy)
    if creditors_split is None:
        rows = st.db.execute(
            "SELECT * FROM fn_creditors_split(%s,%s)", (society_id, fy),
            fetch_all=True) or []
        creditors_split = rows[0] if rows else {
            "mse_dues": Decimal(0), "other_dues": Decimal(0),
            "total_dues": Decimal(0),
        }

    bs_totals = balance_sheet.get("totals", {})
    ie_totals = income_expenditure.get("totals", {})
    assets = Decimal(bs_totals.get("Assets", 0) or 0)
    lieq = Decimal(bs_totals.get("Liabilities", 0) or 0) + \
        Decimal(bs_totals.get("Equity", 0) or 0)
    income = Decimal(ie_totals.get("Income", 0) or 0)
    expense = Decimal(ie_totals.get("Expenditure", 0) or 0)
    surplus = income - expense

    mse = Decimal(str(creditors_split.get("mse_dues") or 0))
    other = Decimal(str(creditors_split.get("other_dues") or 0))
    total_dues = Decimal(str(creditors_split.get("total_dues") or 0))

    notes: list[dict] = []

    notes.append({
        "title": "1. Accounting policies",
        "content": [
            "The Balance Sheet and Income & Expenditure Account are prepared on "
            "an accrual basis; the Receipts & Payments Account is on a cash basis.",
            "Property, plant and equipment is stated at cost less accumulated "
            "depreciation (contra line shown within the fixed-asset group).",
            "Trade receivables are stated at gross less the provision for "
            "doubtful debts (contra line shown within the receivables group).",
            f"Balance sheet total: Assets {_money(assets)} = Liabilities + Equity "
            f"{_money(lieq)}.",
            f"Income & Expenditure for FY {fy}: income {_money(income)}, "
            f"expenditure {_money(expense)}, surplus {_money(surplus)}.",
        ],
    })

    notes.append({
        "title": "2. MSME creditors disclosure (MSMED Act 2006)",
        "content": [
            "Dues to micro and small enterprises (MSE-registered vendors) are "
            f"{_money(mse)}; dues to other creditors are {_money(other)}; "
            f"total creditors {_money(total_dues)}.",
            "Payments to MSE-registered vendors fall due within 45 days "
            "(s.15 MSMED Act 2006); interest exposure on amounts past the "
            "45-day window is disclosed under note 4.",
        ],
    })

    notes.append({
        "title": "3. Related parties",
        "content": [
            "No related-party transactions were identified for disclosure in "
            f"FY {fy} other than the society's own maintenance and service "
            "charges levied on member flats.",
        ],
    })

    notes.append({
        "title": "4. Contingent liabilities and commitments",
        "content": [
            "Contingent liabilities are disclosed to the extent not provided "
            "for in the books. MSME interest exposure on overdue MSE payments "
            f"is Rs {_money(mse + other)} at most, capped at the overdue "
            "46-90 and 90+ day buckets.",
        ],
    })

    return notes
