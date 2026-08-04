# database/ledger_export.py
"""
Ledger Excel Generator — EstateHub
====================================
Produces a per-account ledger in the traditional non-paired format,
matching the ld.xlsx reference layout supplied 2026-08:

  Date | A/c | Description | CB F No. | Debit | Credit | Dr or Cr | Balance

DEPENDS ON: transactions.entry_side (Phase 1 migration) for correct
Debit/Credit column placement and Dr-or-Cr labeling — see the same caveat
as cashbook_export.py. This module does not fall back to inferring
direction from accounts.drcr_account.

STATUS OF THE YEAR-END CLOSE (depreciation split, C/F to hierarchy parent,
Dep -> Income & Expenditure, profit -> Capital Account -> Balance Sheet):
NOT implemented in this pass. That cascade touches every account in the
hierarchy simultaneously (a leaf account's C/F becomes a line in its
parent's ledger, which itself closes to its parent, and so on up to the
Balance Sheet, with a side-branch through the Depreciation and
Income & Expenditure accounts) and needs its own design + testing before
it's trusted to produce correct closing figures. `_compute_closing_row`
below is the seam where that logic plugs in once it exists — right now it
returns a placeholder C/F that just zeroes the account against itself,
which is NOT correct and is flagged loudly in the generated sheet so it
can't be mistaken for a real closing figure.

Entity/user scoping mirrors cashbook_export.py: entity_id / entity_role
scope the underlying transactions to a specific owner/vendor/security user
when the caller isn't on the admin "ALL" view.
"""

from __future__ import annotations
import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

_FONT_BODY   = Font(name="Arial", size=9)
_FONT_HEADER = Font(name="Arial", size=9, bold=True)
_FONT_TITLE  = Font(name="Arial", size=10, bold=True)
_FONT_BFCF   = Font(name="Arial", size=9, bold=True, italic=True)
_FONT_WARN   = Font(name="Arial", size=9, bold=True, italic=True, color="9C0006")

_FILL_HEADER = PatternFill("solid", fgColor="D9E1F2")
_FILL_BF     = PatternFill("solid", fgColor="E2EFDA")
_FILL_CF     = PatternFill("solid", fgColor="FCE4D6")
_FILL_WARN   = PatternFill("solid", fgColor="FFC7CE")

_ALIGN_C = Alignment(horizontal="center", vertical="center")
_ALIGN_L = Alignment(horizontal="left",   vertical="center")
_ALIGN_R = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_DATE = "DD-MMM-YY"
_FMT_AMT  = '#,##0.00;[Red](#,##0.00);"-"'

_COL_WIDTHS = {"A": 11, "B": 12, "C": 32, "D": 8, "E": 11, "F": 11, "G": 8, "H": 12}


def _compute_closing_row(account: dict, fy_running_balance: float) -> dict:
    """
    PLACEHOLDER — see module docstring. Returns a C/F row that balances
    the account against itself, which does NOT implement depreciation,
    hierarchy transfer, or the Dep/Income&Expenditure/Capital Account
    cascade. Replace this once that engine is designed.
    """
    return {
        "to_account": "(unresolved — see closing engine TODO)",
        "amount": abs(fy_running_balance),
        "side": "Cr" if fy_running_balance > 0 else "Dr",
        "is_placeholder": True,
    }


def generate_ledger_excel(
    db,
    society_id: int,
    fy: int,
    account_id: int,
    entity_id: int | None = None,
    entity_role: str | None = None,
) -> bytes:
    """
    Builds a single-account ledger sheet for the given FY. Requires
    transactions.entry_side to exist.
    """
    from database.db_manager import db as _db
    if db is None:
        db = _db

    acc = db._execute(
        "SELECT id, name, drcr_account, has_bf, drcr_bf, depreciation_percent, "
        "hierarchy_parent_id, is_cash_or_bank "
        "FROM accounts WHERE id=%s AND society_id=%s",
        (account_id, society_id), fetch_one=True,
    )
    if not acc:
        raise ValueError(f"Account {account_id} not found for society {society_id}")

    soc = db._execute(
        "SELECT name FROM societies WHERE id=%s", (society_id,), fetch_one=True
    ) or {}
    society_name = soc.get("name", "Society")
    asst_year = f"{fy}-{fy+1}"

    bf_amount = 0.0
    bf_side = None
    if acc.get("has_bf"):
        bf_row = db._execute(
            "SELECT bf_amount, drcr_bf FROM brought_forward "
            "WHERE acc_id=%s AND society_id=%s AND financial_year=%s",
            (account_id, society_id, fy), fetch_one=True,
        )
        if bf_row:
            bf_amount = float(bf_row["bf_amount"] or 0)
            bf_side = bf_row["drcr_bf"]

    fy_start = date(fy, 4, 1)
    fy_end = date(fy + 1, 3, 31)
    txn_rows = db._execute(
        "SELECT t.trx_date, t.acc_particulars, t.journal_id, t.amount, t.entry_side, "
        "       (SELECT r.receipt_number FROM receipts r WHERE r.transaction_id=t.id) AS cb_f_no "
        "FROM transactions t "
        "WHERE t.acc_id=%s AND t.society_id=%s AND t.status='paid' "
        "  AND t.trx_date BETWEEN %s AND %s "
        "  AND (%s IS NULL OR t.entity_id=%s) "
        "ORDER BY t.trx_date, t.id",
        (account_id, society_id, fy_start, fy_end, entity_id, entity_id),
        fetch_all=True,
    ) or []

    wb = Workbook()
    ws = wb.active
    ws.title = (acc.get("name") or "Ledger")[:31]

    for col_letter, width in _COL_WIDTHS.items():
        ws.column_dimensions[col_letter].width = width

    ws.row_dimensions[1].height = 6
    title = {
        1: f"{acc['name']}.xlsx", 3: acc["name"], 5: "LEDGER",
        7: "Asst. Yr.", 8: asst_year,
    }
    for col, val in title.items():
        cell = ws.cell(row=2, column=col, value=val)
        cell.font, cell.alignment = _FONT_TITLE, _ALIGN_C
    ws.row_dimensions[3].height = 6

    headers = {1: "Date", 2: "A/c", 3: "Description", 4: "CB F No.",
               5: "Debit", 6: "Credit", 7: "Dr or Cr", 8: "Balance"}
    for col, hdr in headers.items():
        cell = ws.cell(row=4, column=col, value=hdr)
        cell.font, cell.fill = _FONT_HEADER, _FILL_HEADER
        cell.alignment, cell.border = _ALIGN_C, _BORDER_ALL
    ws.row_dimensions[5].height = 6

    running_balance = 0.0
    current_row = 6

    if acc.get("has_bf") and bf_side:
        bf_debit  = bf_amount if bf_side == "Dr" else None
        bf_credit = bf_amount if bf_side == "Cr" else None
        running_balance = bf_amount if bf_side == "Dr" else -bf_amount
        row = {1: fy_start, 2: "Balance", 3: "B/F", 5: bf_debit, 6: bf_credit,
               7: bf_side, 8: abs(running_balance)}
        for col, val in row.items():
            cell = ws.cell(row=current_row, column=col, value=val)
            cell.font, cell.fill = _FONT_BFCF, _FILL_BF
            cell.border = _BORDER_ALL
            cell.alignment = _ALIGN_R if col in (5, 6, 8) else _ALIGN_L
            if col == 1:
                cell.number_format = _FMT_DATE
            elif col in (5, 6, 8):
                cell.number_format = _FMT_AMT
        current_row += 1

    for r in txn_rows:
        entry_side = r["entry_side"]
        amt = float(r["amount"] or 0)
        debit  = amt if entry_side == "Dr" else None
        credit = amt if entry_side == "Cr" else None
        running_balance += amt if entry_side == "Dr" else -amt
        row_side = "Dr" if running_balance >= 0 else "Cr"

        row = {
            1: r["trx_date"], 2: acc["name"], 3: r.get("acc_particulars") or "",
            4: r.get("cb_f_no") or r.get("journal_id"),
            5: debit, 6: credit, 7: row_side, 8: abs(running_balance),
        }
        for col, val in row.items():
            cell = ws.cell(row=current_row, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            cell.alignment = _ALIGN_R if col in (5, 6, 8) else _ALIGN_L
            if col == 1:
                cell.number_format = _FMT_DATE
            elif col in (5, 6, 8):
                cell.number_format = _FMT_AMT
        current_row += 1

    # ── C/F row ──────────────────────────────────────────────────────────
    closing = _compute_closing_row(acc, running_balance)
    cf_debit  = closing["amount"] if closing["side"] == "Cr" else None   # opposite side zeroes it out
    cf_credit = closing["amount"] if closing["side"] == "Dr" else None
    row = {1: fy_end, 2: closing["to_account"], 3: "C/F",
           5: cf_debit, 6: cf_credit, 7: None, 8: 0}
    font = _FONT_WARN if closing.get("is_placeholder") else _FONT_BFCF
    fill = _FILL_WARN if closing.get("is_placeholder") else _FILL_CF
    for col, val in row.items():
        cell = ws.cell(row=current_row, column=col, value=val)
        cell.font, cell.fill = font, fill
        cell.border = _BORDER_ALL
        cell.alignment = _ALIGN_R if col in (5, 6, 8) else _ALIGN_L
        if col == 1:
            cell.number_format = _FMT_DATE
        elif col in (5, 6, 8):
            cell.number_format = _FMT_AMT
    if closing.get("is_placeholder"):
        warn_row = current_row + 1
        ws.cell(row=warn_row, column=2,
                value="⚠ Closing engine not yet implemented — this C/F is a placeholder, not a real figure.")
        ws.cell(row=warn_row, column=2).font = _FONT_WARN

    ws.freeze_panes = "A6"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
