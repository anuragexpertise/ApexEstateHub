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
from database.money import D, money

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

    # ── Creditors split: MSE vs others (fn_creditors_split) ─────────────
    # Shown as an informational group; the Sundry Creditors (2240) line stays
    # in Liabilities with its full balance, so section totals are unchanged.
    split_row = _first_row(db.execute(
        "SELECT * FROM fn_creditors_split(%s,%s)", (society_id, fy), fetch_one=True))
    mse_dues = D(split_row.get("mse_dues") or 0)
    other_dues = D(split_row.get("other_dues") or 0)
    split_total = mse_dues + other_dues

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
            "creditors": {
                "mse": str(mse_dues),
                "other": str(other_dues),
                "total": str(split_total),
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


def _first_row(result) -> dict:
    """Normalise a db.execute result to a single row dict.

    Some test doubles return a list for every query; a real cursor returns a
    dict (or None) for fetch_one. Treat a non-empty list as its first row.
    """
    if isinstance(result, list):
        return result[0] if result else {}
    if isinstance(result, dict):
        return result
    return {}


def declared_arrears_total(society_id: int, fy: int) -> Decimal | None:
    """Declared Apt-Arrears total for the FY, from the sealed Annex C.

    Annex C (onboarding_annexes, annex_code='C', status='sealed') carries
    ``arrears_by_flat``: [{flat_number, amount, overdue_days, remarks}]. The
    declared total is the sum of those amounts for the annex whose
    financial_year matches `fy`.

    Returns None when no sealed Annex C exists for this society/FY — the
    figure is unreadable and the gate must say cannot_verify, never substitute 0.
    Returns 0 when the annex exists but declares no arrears.
    """
    row = db.execute(
        "SELECT content FROM onboarding_annexes "
        "WHERE society_id=%s AND annex_code='C' AND status='sealed' "
        "AND (content->>'financial_year')::INT=%s",
        (society_id, fy), fetch_one=True)
    if row is None:
        return None
    arrears = (row.get("content") or {}).get("arrears_by_flat") or []
    total = ZERO
    for item in arrears or []:
        try:
            total += money(item.get("amount"))
        except (TypeError, ValueError):
            continue
    return total


def export_gate(society_id: int, fy: int) -> dict:
    """Gate an export / FY close: refuse when the trial balance is unbalanced,
    the FY is locked (fn_fy_lock_preview can_lock is false), or any
    bf_controls control (balanced / funds_backed / arrears_tie) fails.

    Returns {"allowed": bool, "status": "ok"|"refused"|"cannot_verify",
    "reason": str, "trial_balance_balanced": bool,
    "locked": bool, "can_lock": bool, "blockers": [str], "controls": {...}}.

    `locked` is True when a fy_locks row exists for this society/FY.
    `can_lock` is True when the preview has no blockers. `blockers` is the
    list of blocker messages. The two are independent: a year can be locked
    yet still preview-clear, or unlocked yet blocked.

    `arrears_tie` uses the society's declared Apt-Arrears total for the FY
    (from the sealed Annex C). When that figure cannot be read, the gate
    returns cannot_verify: it neither passes nor substitutes 0 (ICAI5 A1).
    """
    tb = db.execute("SELECT * FROM fn_trial_balance_check(%s,%s)",
                    (society_id, fy), fetch_one=True)
    tb_balanced = bool(tb.get("balanced")) if tb else False

    lock = db.execute("SELECT * FROM fn_fy_lock_preview(%s,%s)",
                      (society_id, fy), fetch_one=True) or {}
    already_locked = bool(lock.get("already_locked"))
    can_lock = bool(lock.get("can_lock"))
    lock_blockers_text = lock.get("blockers") or ""
    blockers = [b for b in lock_blockers_text.split("; ") if b]
    fy_locked = not can_lock
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

    declared_arrears = declared_arrears_total(society_id, fy)
    if declared_arrears is None:
        return {
            "allowed": False,
            "status": "cannot_verify",
            "reason": "declared arrears cannot be read: no sealed Annex C for society "
                      + str(society_id) + " FY " + str(fy),
            "trial_balance_balanced": tb_balanced,
            "locked": already_locked,
            "can_lock": can_lock,
            "blockers": blockers,
            "controls": {},
        }

    controls = bc.three_controls(totals, declared_arrears)

    # Creditors tie (ICAI5 A4): creditors split total (MSE + others) must equal
    # the Sundry Creditors (2240) balance on the balance sheet.
    split_row = db.execute(
        "SELECT * FROM fn_creditors_split(%s,%s)", (society_id, fy), fetch_one=True) or {}
    split_total = D(split_row.get("total_dues") or 0)
    sundry_row = _first_row(db.execute(
        "SELECT amount FROM fn_balance_sheet_fy(%s,%s) "
        "WHERE account_code=%s AND statement_section='Liabilities'",
        (society_id, fy, 2240), fetch_one=True))
    sundry_creditors = D(sundry_row.get("amount") or 0)
    controls["creditors_tie"] = bc.creditors_tie(split_total, sundry_creditors)

    # arrears_tie and creditors_tie are hard refusal gates (ICAI4 I6 / ICAI5 A4),
    # not advisory only.
    controls_pass = (controls["balanced"]["passed"]
                     and controls["funds_backed"]["passed"]
                     and controls["arrears_tie"]["passed"]
                     and controls["creditors_tie"]["passed"])

    allowed = tb_balanced and not fy_locked and not already_locked and controls_pass
    status = "ok" if allowed else "refused"
    reasons = []
    if fy_locked:
        reasons.append("FY cannot be locked: " + lock_blockers_text)
    if already_locked:
        reasons.append("FY is already locked")
    if not tb_balanced:
        reasons.append("trial balance is unbalanced")
    if not controls["balanced"]["passed"]:
        reasons.append("brought-forward debits do not equal credits")
    if not controls["funds_backed"]["passed"]:
        reasons.append("declared funds exceed bank, cash and deposits")
    if not controls["arrears_tie"]["passed"]:
        reasons.append("receivables control does not tie to declared arrears")
    if not controls["creditors_tie"]["passed"]:
        reasons.append("creditors split does not tie to Sundry Creditors")
    reason = "; ".join(reasons) if reasons else "ok"

    return {
        "allowed": allowed,
        "status": status,
        "reason": reason,
        "trial_balance_balanced": tb_balanced,
        "locked": already_locked,
        "can_lock": can_lock,
        "blockers": blockers,
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
