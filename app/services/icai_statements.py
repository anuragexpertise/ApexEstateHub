"""ICAI statutory statements engine (ICAI3 H8 / G11, ICAI4 I5).

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

The Balance Sheet presents Property, plant and equipment and Trade receivables
on a gross / less / net basis: accumulated depreciation (1190) and the
provision for doubtful debts (1530) are "less" lines inside their asset group,
never separate assets (ICAI4 J6/J7).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app.services import bf_controls as bc
from database.chart_mapping import (
    ACCUM_DEPRECIATION,
    PPE_GROSS_ACCOUNTS,
    PROVISION_DOUBTFUL_DEBTS,
    TRADE_RECEIVABLES_GROSS,
    is_contra,
    line_for_account,
    section_for_account,
)
from database.db_manager import db
from database.money import D

ZERO = D(0)


class StatementUnavailable(Exception):
    """Raised when a statement has no data for a society/FY.

    Carries society_id and fy so a route can turn it into an explicit
    404/no-data response instead of an empty "balanced" statement (ICAI4 J1).
    """

    def __init__(self, society_id: int, fy: int,
                 message: str = "no statement data for this society/FY"):
        self.society_id = society_id
        self.fy = fy
        self.message = message
        super().__init__(message)


def _rows(sql: str, params: tuple) -> list:
    # Database errors must propagate: a silent empty result would make an
    # empty statement look balanced (ICAI4 J1).
    return db.execute(sql, params, fetch_all=True) or []


def trial_balance(society_id: int, fy: int) -> list:
    """Trial Balance: account_id, account_name, closing_dr, closing_cr."""
    return _rows("SELECT * FROM fn_trial_balance_fy(%s,%s) ORDER BY account_id",
                 (society_id, fy))


def balance_sheet(society_id: int, fy: int) -> dict:
    """Balance Sheet: Assets / Liabilities / Equity, each with rows and a
    section total, plus the Assets = Liabilities + Equity check.

    Raises StatementUnavailable when the SQL function returns no rows: a
    society with genuinely no data for that year gets an explicit no-data
    response, never an empty "balanced" statement (ICAI4 J1).
    """
    rows = _rows("SELECT * FROM fn_balance_sheet_fy(%s,%s) ORDER BY account_code",
                 (society_id, fy))
    if not rows:
        raise StatementUnavailable(society_id, fy,
                                   "balance sheet has no rows for this society/FY")
    sections = {"Assets": [], "Liabilities": [], "Equity": []}
    totals = {"Assets": ZERO, "Liabilities": ZERO, "Equity": ZERO}
    by_code: dict[int, Decimal] = {}
    for row in rows:
        code = row.get("account_code")
        amount = D(row.get("amount") or 0)
        if code is not None:
            by_code[int(code)] = amount
        section = row.get("statement_section") or section_for_account(
            row.get("account_id") or 0)
        entry = {
            "account_id": row.get("account_id") or code,
            "account_name": row.get("account_name"),
            "account_code": code,
            "line": line_for_account(int(code)) if code is not None else None,
            "amount": amount,
            "is_contra": is_contra(int(code)) if code is not None else False,
        }
        if section in sections:
            sections[section].append(entry)
            totals[section] += amount

    # ── Contra netting groups (gross / less / net) ────────────────────
    ppe_gross = sum((by_code.get(a, ZERO) for a in PPE_GROSS_ACCOUNTS), ZERO)
    accum_dep = -by_code.get(ACCUM_DEPRECIATION, ZERO)
    ppe_net = ppe_gross - accum_dep

    recv_gross = sum((by_code.get(a, ZERO) for a in TRADE_RECEIVABLES_GROSS),
                     ZERO)
    provision = -by_code.get(PROVISION_DOUBTFUL_DEBTS, ZERO)
    recv_net = recv_gross - provision

    assets = totals["Assets"]
    lieq = totals["Liabilities"] + totals["Equity"]
    return {
        "sections": sections,
        "totals": {k: str(v) for k, v in totals.items()},
        "assets": str(assets),
        "liabilities_plus_equity": str(lieq),
        "balanced": abs(assets - lieq) <= Decimal("0.01"),
        "groups": {
            "property_plant_equipment": {
                "gross": str(ppe_gross),
                "less_accumulated_depreciation": str(accum_dep),
                "net": str(ppe_net),
            },
            "trade_receivables": {
                "gross": str(recv_gross),
                "less_provision_for_doubtful_debts": str(provision),
                "net": str(recv_net),
            },
        },
        "fy": fy,
        "society_id": society_id,
    }


def income_expenditure(society_id: int, fy: int) -> dict:
    """Income & Expenditure Account: Income / Expenditure rows plus surplus.

    Raises StatementUnavailable when the SQL function returns no rows (ICAI4 J1).
    """
    rows = _rows("SELECT * FROM fn_income_expenditure_fy(%s,%s) ORDER BY account_code",
                 (society_id, fy))
    if not rows:
        raise StatementUnavailable(society_id, fy,
                                   "income & expenditure has no rows for this society/FY")
    sections = {"Income": [], "Expenditure": []}
    totals = {"Income": ZERO, "Expenditure": ZERO}
    for row in rows:
        code = row.get("account_code")
        amount = D(row.get("amount") or 0)
        section = row.get("statement_section") or section_for_account(
            row.get("account_id") or 0)
        entry = {
            "account_id": row.get("account_id") or code,
            "account_name": row.get("account_name"),
            "account_code": code,
            "line": line_for_account(int(code)) if code is not None else None,
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


def receipts_payments(society_id: int, fy: int) -> dict:
    """Receipts & Payments Account (cash basis) as a structured dict.

    Returns {"opening", "receipts", "payments", "closing"} instead of raw
    rows (ICAI4 J7).
    """
    rows = _rows("SELECT * FROM fn_receipts_payments_fy(%s,%s) ORDER BY trx_date",
                 (society_id, fy))
    opening_dr = ZERO
    opening_cr = ZERO
    closing_dr = ZERO
    closing_cr = ZERO
    receipts = []
    payments = []
    for row in rows:
        line_type = (row.get("line_type") or "").strip()
        name = row.get("account_name") or ""
        dr = D(row.get("dr_amount") or 0)
        cr = D(row.get("cr_amount") or 0)
        if line_type == "Opening":
            opening_dr += dr
            opening_cr += cr
        elif line_type == "Closing":
            closing_dr += dr
            closing_cr += cr
        elif line_type == "Receipt":
            receipts.append({"account": name, "amount": str(dr)})
        elif line_type == "Payment":
            payments.append({"account": name, "amount": str(cr)})
    return {
        "opening": {"cash_and_bank": str(opening_dr - opening_cr)},
        "receipts": receipts,
        "payments": payments,
        "closing": {
            "cash_and_bank_dr": str(closing_dr),
            "cash_and_bank_cr": str(closing_cr),
        },
        "fy": fy,
        "society_id": society_id,
    }


def export_gate(society_id: int, fy: int) -> dict:
    """Gate an export / FY close: refuse when the trial balance is unbalanced,
    the FY is locked (fn_fy_lock_preview can_lock is false), or any
    bf_controls control (balanced / funds_backed / arrears_tie) fails.

    Returns {"allowed": bool, "reason": str, "trial_balance_balanced": bool,
    "fy_locked": bool, "controls": {...}}.
    """
    tb = db.execute("SELECT * FROM fn_trial_balance_check(%s,%s)",
                    (society_id, fy), fetch_one=True)
    tb_balanced = bool(tb.get("balanced")) if tb else False

    lock = db.execute("SELECT * FROM fn_fy_lock_preview(%s,%s)",
                      (society_id, fy), fetch_one=True) or {}
    fy_locked = not bool(lock.get("can_lock"))
    lock_blockers = lock.get("blockers") or ""

    bf_rows = db.execute(
        "SELECT acc_id, drcr_bf AS drcr_account, bf_amount FROM brought_forward "
        "WHERE society_id=%s AND financial_year=%s",
        (society_id, fy), fetch_all=True) or []
    accs = {
        r["id"]: {"tab_name": r["tab_name"], "drcr_account": r["drcr_account"]}
        for r in db.execute(
            "SELECT id, tab_name, drcr_account FROM accounts WHERE society_id=%s",
            (society_id,), fetch_all=True) or []
    }
    totals = bc.totals(
        [{"acc_id": r["acc_id"], "bf_amount": str(r["bf_amount"])} for r in bf_rows],
        accs)
    controls = bc.three_controls(totals, Decimal(0))
    # arrears_tie is now a hard refusal gate (ICAI4 I6), not advisory only.
    controls_pass = (controls["balanced"]["passed"]
                     and controls["funds_backed"]["passed"]
                     and controls["arrears_tie"]["passed"])

    allowed = tb_balanced and not fy_locked and controls_pass
    reasons = []
    if fy_locked:
        reasons.append("FY is locked: " + lock_blockers)
    if not tb_balanced:
        reasons.append("trial balance is unbalanced")
    if not controls["balanced"]["passed"]:
        reasons.append("brought-forward debits do not equal credits")
    if not controls["funds_backed"]["passed"]:
        reasons.append("declared funds exceed bank, cash and deposits")
    if not controls["arrears_tie"]["passed"]:
        reasons.append("receivables control does not tie to declared arrears")
    reason = "; ".join(reasons) if reasons else "ok"

    return {
        "allowed": allowed,
        "reason": reason,
        "trial_balance_balanced": tb_balanced,
        "fy_locked": fy_locked,
        "controls": {k: {"passed": c["passed"], "reason": c["reason"]}
                     for k, c in controls.items()},
    }


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
