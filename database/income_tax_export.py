# database/income_tax_export.py
"""
Income Tax (Principle of Mutuality) — WORKING PAPER FOR CA — EstateHub
=======================================================================
This report is a WORKING PAPER for the society's Chartered Accountant.
IT IS NOT a taxable-income computation and MUST NOT be filed as or
mistaken for an income-tax return (ITR-5).

What this report does:
  Produces a mutual-vs-non-mutual income/expenditure breakup for one
  financial year from P&L accounts (statement_section = Income/Expenditure)
  ONLY — balance-sheet items, capital receipts, fund appropriations and
  liability legs are excluded (A-03 fix).

What the CA must do before filing:
  1. Verify apportionment of common expenses between mutual/non-mutual income.
  2. Add depreciation per the CA's schedule (IT Act 2025 s.19 / Sch II).
  3. Check brought-forward losses (if any).
  4. Confirm Sec 269ST cash receipt compliance.
  5. Confirm interest from non-co-operative banks is treated as taxable
     non-mutual income (doctrine of mutuality; Bangalore Club v CIT, SC 2013).
  6. File ITR-5 with the correct tax regime.

Data source: fn_income_tax_summary_fy(p_society_id, p_fy)
See ER.md §2 (A-03) for the statutory background.
"""

from __future__ import annotations
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


_FONT_BODY = Font(name="Arial", size=9)
_FONT_HEADER = Font(name="Arial", size=9, bold=True)
_FONT_TITLE = Font(name="Arial", size=10, bold=True)
_FONT_TOTAL = Font(name="Arial", size=9, bold=True)

_FILL_HEADER = PatternFill("solid", fgColor="D9E1F2")
_FILL_TOTAL = PatternFill("solid", fgColor="E2EFDA")

_ALIGN_C = Alignment(horizontal="center", vertical="center")
_ALIGN_L = Alignment(horizontal="left", vertical="center")
_ALIGN_R = Alignment(horizontal="right", vertical="center")

_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_AMT = '#,##0.00;[Red](#,##0.00);"-"'

_COL_WIDTHS = {"A": 22, "B": 18, "C": 20, "D": 20}


def _apply_header(ws, row: int, widths: dict) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.row_dimensions[row].height = 22


def _write_mutuality_sheet(ws, rows: list[dict], fy: int) -> None:
    ws.cell(
        row=1, column=1,
        value=f"WORKING PAPER FOR CA — NOT A TAX RETURN  |  Mutuality Analysis FY {fy}-{fy + 1}"
    )
    ws.cell(row=1, column=1).font = Font(name="Arial", size=10, bold=True, color="CC0000")

    headers = ["Category", "Nature", "Total Amount (₹)"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    totals = {
        ("Income", "mutual"): 0.0, ("Income", "non_mutual"): 0.0,
        ("Expense", "mutual"): 0.0, ("Expense", "non_mutual"): 0.0,
    }
    r = 3
    for row in rows:
        category = row.get("category") or ""
        nature = row.get("nature") or ""
        # A-03 / Hygiene: use Decimal so statement totals match SQL NUMERIC to the paisa.
        amount = Decimal(str(row.get("total_amount") or "0"))
        totals[(category, nature)] = totals.get((category, nature), 0.0) + amount

        values = [category, nature.replace("_", " ").title(), amount]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col == 3:
                cell.alignment = _ALIGN_R
                cell.number_format = _FMT_AMT
            else:
                cell.alignment = _ALIGN_L
        r += 1

    r += 1
    # A-03: category is now 'Expenditure' (not 'Expense') matching statement_section
    taxable_estimate = (
        totals.get(("Income", "non_mutual"), Decimal(0))
        - totals.get(("Expenditure", "non_mutual"), Decimal(0))
    )
    summary_rows = [
        ("Total Mutual Income (exempt under mutuality)", totals.get(("Income", "mutual"), Decimal(0))),
        ("Total Non-Mutual Income (potentially taxable)", totals.get(("Income", "non_mutual"), Decimal(0))),
        ("Total Non-Mutual Expenditure (P&L accounts)", totals.get(("Expenditure", "non_mutual"), Decimal(0))),
        ("Indicated Surplus for CA Review — NOT taxable income", taxable_estimate),
    ]
    for label, val in summary_rows:
        cell_a = ws.cell(row=r, column=1, value=label)
        cell_a.font = _FONT_TOTAL
        cell_a.fill = _FILL_TOTAL
        cell_a.alignment = _ALIGN_L
        cell_a.border = _BORDER_ALL
        ws.cell(row=r, column=2).fill = _FILL_TOTAL
        ws.cell(row=r, column=2).border = _BORDER_ALL
        cell_c = ws.cell(row=r, column=3, value=val)
        cell_c.font = _FONT_TOTAL
        cell_c.fill = _FILL_TOTAL
        cell_c.alignment = _ALIGN_R
        cell_c.number_format = _FMT_AMT
        cell_c.border = _BORDER_ALL
        r += 1

    note = ws.cell(
        row=r + 1, column=1,
        value=(
            "IMPORTANT — WORKING PAPER ONLY: This report is restricted to P&L accounts "
            "(statement_section = Income/Expenditure) and excludes capital receipts, "
            "fund appropriations and liability legs. It is NOT a taxable-income computation "
            "and MUST NOT be used as a substitute for ITR-5 preparation by a qualified CA. "
            "The CA must additionally consider: (1) apportionment of common expenses between "
            "mutual/non-mutual income; (2) depreciation per IT Act 2025 s.19/Sch II; "
            "(3) brought-forward losses; (4) Sec 269ST cash receipt compliance; "
            "(5) interest income from non-cooperative banks (taxable regardless of mutuality). "
            "Source: fn_income_tax_summary_fy — see ER.md A-03."
        ),
    )
    note.font = Font(name="Arial", size=8, italic=True, color="CC0000")
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=4)
    ws.row_dimensions[r + 1].height = 60


def generate_income_tax_summary_excel(
    db,
    society_id: int,
    fy: int,
    filename_prefix: str = "MutualitySummary",
) -> bytes:
    """Builds the Income Tax mutuality summary workbook for one society FY."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    rows = db._execute(
        "SELECT * FROM fn_income_tax_summary_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet(title="Working Paper (CA)")
    ws.append([
        "WORKING PAPER FOR CA — NOT A TAX RETURN",
        f"FY {fy}-{fy+1}",
        "",
        "",
        "",
        "",
        ""
    ])
    ws.merge_cells('A1:G1')
    _apply_header(ws, 3, _COL_WIDTHS)
    _write_mutuality_sheet(ws, rows, fy)

    filename = f"{filename_prefix}_FY{fy}-{fy+1}.xlsx"
    wb._it_filename = filename  # type: ignore[attr-defined]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
