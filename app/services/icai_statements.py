"""ICAI statutory statements engine (ICAI3 H8 / G11).

Computes the society's statutory statements from the SQL functions already
defined in database/estatehub.sql:

* fn_trial_balance_fy(p_society_id, p_fy)
* fn_balance_sheet_fy(p_society_id, p_fy)
* fn_income_expenditure_fy(p_society_id, p_fy)
* fn_receipts_payments_fy(p_society_id, p_fy)

Pure service layer: no Dash, no Flask. Returns plain dicts/lists so a route,
a card, or an export can consume them without knowing SQL. Balances are
Cr-positive per fn_fy_closing_report's own_closing convention (a positive
closing balance → closing_cr; a negative one → closing_dr).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from database.chart_mapping import is_contra, section_for_account
from database.db_manager import db
from database.money import D

ZERO = D(0)


def _rows(sql: str, params: tuple) -> list:
    try:
        return db.execute(sql, params, fetch_all=True) or []
    except Exception:
        return []


def trial_balance(society_id: int, fy: int) -> list:
    """Trial Balance: account_id, account_name, closing_dr, closing_cr."""
    return _rows("SELECT * FROM fn_trial_balance_fy(%s,%s) ORDER BY account_id",
                 (society_id, fy))


def balance_sheet(society_id: int, fy: int) -> dict:
    """Balance Sheet: Assets / Liabilities / Equity, each with rows and a
    section total, plus the Assets = Liabilities + Equity check."""
    sections = {"Assets": [], "Liabilities": [], "Equity": []}
    totals = {"Assets": ZERO, "Liabilities": ZERO, "Equity": ZERO}
    for row in _rows("SELECT * FROM fn_balance_sheet_fy(%s,%s) ORDER BY account_code",
                     (society_id, fy)):
        section = row.get("statement_section") or section_for_account(row.get("account_id") or 0)
        amount = D(row.get("amount") or 0)
        entry = {
            "account_id": row.get("account_id") or row.get("account_code"),
            "account_name": row.get("account_name"),
            "account_code": row.get("account_code"),
            "amount": amount,
            "is_contra": is_contra(row.get("account_id") or row.get("account_code") or 0),
        }
        if section in sections:
            sections[section].append(entry)
            totals[section] += amount
    assets = totals["Assets"]
    lieq = totals["Liabilities"] + totals["Equity"]
    return {
        "sections": sections,
        "totals": {k: str(v) for k, v in totals.items()},
        "assets": str(assets),
        "liabilities_plus_equity": str(lieq),
        "balanced": abs(assets - lieq) <= Decimal("0.01"),
        "fy": fy,
        "society_id": society_id,
    }


def income_expenditure(society_id: int, fy: int) -> dict:
    """Income & Expenditure Account: Income / Expenditure rows plus surplus."""
    sections = {"Income": [], "Expenditure": []}
    totals = {"Income": ZERO, "Expenditure": ZERO}
    for row in _rows("SELECT * FROM fn_income_expenditure_fy(%s,%s) ORDER BY account_code",
                     (society_id, fy)):
        section = row.get("statement_section") or section_for_account(row.get("account_id") or 0)
        amount = D(row.get("amount") or 0)
        entry = {
            "account_id": row.get("account_id") or row.get("account_code"),
            "account_name": row.get("account_name"),
            "account_code": row.get("account_code"),
            "amount": amount,
        }
        if section in sections:
            sections[section].append(entry)
            totals[section] += amount
    surplus = totals["Income"] - totals["Expenditure"]
    return {
        "sections": sections,
        "totals": {k: str(v) for k, v in totals.items()},
        "income": str(totals["Income"]),
        "expenditure": str(totals["Expenditure"]),
        "surplus": str(surplus),
        "fy": fy,
        "society_id": society_id,
    }


def receipts_payments(society_id: int, fy: int) -> list:
    """Receipts & Payments Account (cash basis)."""
    return _rows("SELECT * FROM fn_receipts_payments_fy(%s,%s) ORDER BY trx_date",
                 (society_id, fy))


def statements(society_id: int, fy: Optional[int] = None) -> dict:
    """All three statements plus the trial balance for one society/FY."""
    if fy is None:
        fy = date.today().year
        # FY runs 1 April - 31 March; before 1 April the current FY is the
        # previous calendar year.
        if date.today().month < 4:
            fy -= 1
    return {
        "society_id": society_id,
        "fy": fy,
        "trial_balance": trial_balance(society_id, fy),
        "balance_sheet": balance_sheet(society_id, fy),
        "income_expenditure": income_expenditure(society_id, fy),
        "receipts_payments": receipts_payments(society_id, fy),
        "generated_at": date.today().isoformat(),
    }
