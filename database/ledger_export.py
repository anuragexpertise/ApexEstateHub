# database/ledger_export.py
"""
Ledger Excel Generator — EstateHub
====================================
Produces a per-account ledger in the traditional non-paired format,
matching the ld.xlsx reference layout supplied 2026-08:

  Date | A/c | Description | CB F No. | Debit | Credit | Dr or Cr | Balance

DEPENDS ON: fn_account_ledger_fy (estatehub.sql SECTION 5), which already
implements the full year-end cascade — FY-scoped BF resolution, per-
transaction entry_side netting, the depreciation split for depreciable
accounts, and the C/F-to-hierarchy-parent closing row — via row_type
'bf' | 'txn' | 'depreciation' | 'closing'. This module is a thin
Excel-formatting layer over that function's output; it does NOT
reimplement any of the closing arithmetic itself.

Fixed (2026-08): this module previously queried `transactions` directly
and computed its own running balance, then wrote a placeholder C/F row
(`_compute_closing_row`) that zeroed the account against itself and was
explicitly flagged as not implementing the real cascade. That cascade
already exists in fn_account_ledger_fy — the placeholder just wasn't
pointed at it. Rewritten to call fn_account_ledger_fy directly instead of
duplicating (and under-implementing) its logic.

Entity/user scoping: NONE. fn_account_ledger_fy takes no entity_id /
entity_role — it's an account-level ledger (every transaction posted to
this one account, across the whole society), not an entity-scoped one.
This matches the live "Account Ledger" drilldown view (loaders.py's
`entity == "ledger"` branch, reached via profile_account -> show_ledger),
which has never taken entity scoping either. Both are consistent with
`ledger` being an admin-only entity (renderers.py's _PORTAL_PERMS gives
every non-admin role an empty permission set for it) — no other portal
can reach a ledger export, so there is nothing to scope by entity in the
first place.
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

_FILL_HEADER = PatternFill("solid", fgColor="D9E1F2")
_FILL_BF     = PatternFill("solid", fgColor="E2EFDA")
_FILL_CF     = PatternFill("solid", fgColor="FCE4D6")
_FILL_DEP    = PatternFill("solid", fgColor="FFF2CC")

_ALIGN_C = Alignment(horizontal="center", vertical="center")
_ALIGN_L = Alignment(horizontal="left",   vertical="center")
_ALIGN_R = Alignment(horizontal="right",  vertical="center")

_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_DATE = "DD-MMM-YY"
_FMT_AMT  = '#,##0.00;[Red](#,##0.00);"-"'

_COL_WIDTHS = {"A": 11, "B": 12, "C": 32, "D": 8, "E": 11, "F": 11, "G": 8, "H": 12}

_ROW_STYLE = {
    "bf":           (_FONT_BFCF, _FILL_BF),
    "closing":      (_FONT_BFCF, _FILL_CF),
    "depreciation": (_FONT_BODY, _FILL_DEP),
    "txn":          (_FONT_BODY, PatternFill()),
}


def generate_ledger_excel(
    db,
    society_id: int,
    fy: int,
    account_id: int,
) -> bytes:
    """
    Builds a single-account ledger sheet for the given FY, sourced
    entirely from fn_account_ledger_fy(society_id, account_id, fy) — see
    module docstring for why no entity_id/entity_role params are taken.
    """
    from database.db_manager import db as _db
    if db is None:
        db = _db

    acc = db._execute(
        "SELECT id, name FROM accounts WHERE id=%s AND society_id=%s",
        (account_id, society_id), fetch_one=True,
    )
    if not acc:
        raise ValueError(f"Account {account_id} not found for society {society_id}")

    asst_year = f"{fy}-{fy+1}"

    # Insertion order out of fn_account_ledger_fy is already correct
    # (bf -> txns by date -> depreciation -> closing); no ORDER BY here,
    # since sorting by row_date alone would shuffle the depreciation and
    # closing rows, which share the same FY-end date.
    ledger_rows = db._execute(
        "SELECT * FROM fn_account_ledger_fy(%s,%s,%s)",
        (society_id, account_id, fy), fetch_all=True,
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

    current_row = 6
    for r in ledger_rows:
        row_type = r.get("row_type") or "txn"
        font, fill = _ROW_STYLE.get(row_type, (_FONT_BODY, PatternFill()))
        debit  = float(r["debit"])  if r.get("debit")  else None
        credit = float(r["credit"]) if r.get("credit") else None
        balance = float(r.get("balance") or 0)
        drcr = None
        if row_type in ("bf", "txn", "depreciation"):
            drcr = "Dr" if debit and not credit else ("Cr" if credit and not debit else None)

        row = {
            1: r.get("row_date"), 2: r.get("parent_name") if row_type == "closing" else acc["name"],
            3: r.get("particulars") or "",
            5: debit, 6: credit, 7: drcr, 8: abs(balance) if balance is not None else None,
        }
        for col, val in row.items():
            cell = ws.cell(row=current_row, column=col, value=val)
            cell.font, cell.fill = font, fill
            cell.border = _BORDER_ALL
            cell.alignment = _ALIGN_R if col in (5, 6, 8) else _ALIGN_L
            if col == 1 and val:
                cell.number_format = _FMT_DATE
            elif col in (5, 6, 8):
                cell.number_format = _FMT_AMT
        current_row += 1

    ws.freeze_panes = "A6"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
