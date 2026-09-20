# database/financial_statements_export.py
"""
Three-Statement Financial Report Excel Generator — EstateHub
=============================================================
Generates the three statutory financial statements required for
registered society annual filing:
1. Receipts & Payments Account (Cash basis)
2. Income & Expenditure Account (Accrual basis)
3. Balance Sheet (Position statement)

Each export calls the corresponding SQL function and formats as
structured Excel with proper headers. The combined export creates
a workbook with three sheets.

Data source:
- fn_receipts_payments_fy(p_society_id, p_fy)
- fn_income_expenditure_fy(p_society_id, p_fy)
- fn_balance_sheet_fy(p_society_id, p_fy)
"""

from __future__ import annotations
import io
from datetime import date

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

_COL_WIDTHS_RP = {"A": 35, "B": 18, "C": 18}
_COL_WIDTHS_IE = {"A": 35, "B": 18, "C": 20}
_COL_WIDTHS_BS = {"A": 35, "B": 18, "C": 20}


def _apply_header(ws, row: int, widths: dict) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.row_dimensions[row].height = 22


def _get_society_name(db, society_id: int) -> str:
    row = db._execute("SELECT name FROM societies WHERE id = %s", (society_id,), fetch_one=True)
    return row.get("name", f"Society {society_id}") if row else f"Society {society_id}"


def _fy_label(fy: int) -> str:
    return f"1 April {fy} – 31 March {fy + 1}"


def _write_receipts_payments_sheet(ws, rows: list[dict], society_name: str, fy: int) -> None:
    ws.cell(row=1, column=1, value=f"{society_name}")
    ws.cell(row=1, column=1).font = _FONT_TITLE
    ws.cell(row=2, column=1, value=f"Receipts & Payments Account")
    ws.cell(row=2, column=1).font = _FONT_TITLE
    ws.cell(row=3, column=1, value=f"For the period {_fy_label(fy)}")
    ws.cell(row=3, column=1).font = Font(name="Arial", size=9, italic=True)

    headers = ["Particulars", "Dr Amount (₹)", "Cr Amount (₹)"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 6
    total_dr = 0.0
    total_cr = 0.0
    for row in rows:
        dr = float(row.get("dr_amount") or 0)
        cr = float(row.get("cr_amount") or 0)
        total_dr += dr
        total_cr += cr

        values = [row.get("account_name", ""), dr if dr else None, cr if cr else None]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col == 1:
                cell.alignment = _ALIGN_L
            else:
                cell.alignment = _ALIGN_R
                if val is not None:
                    cell.number_format = _FMT_AMT
        r += 1

    # Totals row
    cell_a = ws.cell(row=r, column=1, value="TOTAL")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=total_dr)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL
    ws.cell(row=r, column=3).fill = _FILL_TOTAL
    ws.cell(row=r, column=3).border = _BORDER_ALL
    cell_c = ws.cell(row=r, column=3, value=total_cr)
    cell_c.font = _FONT_TOTAL
    cell_c.fill = _FILL_TOTAL
    cell_c.alignment = _ALIGN_R
    cell_c.number_format = _FMT_AMT
    cell_c.border = _BORDER_ALL


def _write_income_expenditure_sheet(ws, rows: list[dict], society_name: str, fy: int) -> None:
    ws.cell(row=1, column=1, value=f"{society_name}")
    ws.cell(row=1, column=1).font = _FONT_TITLE
    ws.cell(row=2, column=1, value=f"Income & Expenditure Account")
    ws.cell(row=2, column=1).font = _FONT_TITLE
    ws.cell(row=3, column=1, value=f"For the period {_fy_label(fy)}")
    ws.cell(row=3, column=1).font = Font(name="Arial", size=9, italic=True)

    headers = ["Particulars", "Amount (₹)"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 6
    income_total = 0.0
    expense_total = 0.0

    # Income section
    for row in rows:
        if row.get("statement_section") == "Income":
            amt = float(row.get("amount") or 0)
            income_total += amt
            values = [row.get("account_name", ""), amt]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.font = _FONT_BODY
                cell.border = _BORDER_ALL
                if col == 1:
                    cell.alignment = _ALIGN_L
                else:
                    cell.alignment = _ALIGN_R
                    cell.number_format = _FMT_AMT
            r += 1

    # Income total
    cell_a = ws.cell(row=r, column=1, value="Total Income")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=income_total)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL
    r += 1

    # Expenditure section
    for row in rows:
        if row.get("statement_section") == "Expenditure":
            amt = float(row.get("amount") or 0)
            expense_total += amt
            values = [row.get("account_name", ""), amt]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.font = _FONT_BODY
                cell.border = _BORDER_ALL
                if col == 1:
                    cell.alignment = _ALIGN_L
                else:
                    cell.alignment = _ALIGN_R
                    cell.number_format = _FMT_AMT
            r += 1

    # Expenditure total
    cell_a = ws.cell(row=r, column=1, value="Total Expenditure")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=expense_total)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL
    r += 2

    # Surplus/Deficit
    surplus_deficit = income_total - expense_total
    label = "Surplus" if surplus_deficit >= 0 else "Deficit"
    cell_a = ws.cell(row=r, column=1, value=f"{label} (Income - Expenditure)")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=surplus_deficit)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL


def _write_balance_sheet_sheet(ws, rows: list[dict], society_name: str, fy: int) -> None:
    ws.cell(row=1, column=1, value=f"{society_name}")
    ws.cell(row=1, column=1).font = _FONT_TITLE
    ws.cell(row=2, column=1, value=f"Balance Sheet")
    ws.cell(row=2, column=1).font = _FONT_TITLE
    ws.cell(row=3, column=1, value=f"As at {_fy_label(fy).replace('–', '31 March')}")
    ws.cell(row=3, column=1).font = Font(name="Arial", size=9, italic=True)

    headers = ["Particulars", "Amount (₹)"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 6
    assets_total = 0.0
    liabilities_total = 0.0
    equity_total = 0.0

    # Assets
    for row in rows:
        if row.get("statement_section") == "Assets":
            amt = float(row.get("amount") or 0)
            assets_total += amt
            values = [row.get("account_name", ""), amt]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.font = _FONT_BODY
                cell.border = _BORDER_ALL
                if col == 1:
                    cell.alignment = _ALIGN_L
                else:
                    cell.alignment = _ALIGN_R
                    cell.number_format = _FMT_AMT
            r += 1

    cell_a = ws.cell(row=r, column=1, value="Total Assets")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=assets_total)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL
    r += 1

    # Liabilities
    for row in rows:
        if row.get("statement_section") == "Liabilities":
            amt = float(row.get("amount") or 0)
            liabilities_total += amt
            values = [row.get("account_name", ""), amt]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.font = _FONT_BODY
                cell.border = _BORDER_ALL
                if col == 1:
                    cell.alignment = _ALIGN_L
                else:
                    cell.alignment = _ALIGN_R
                    cell.number_format = _FMT_AMT
            r += 1

    # Equity (Capital Account + Surplus/Deficit)
    for row in rows:
        if row.get("statement_section") == "Equity":
            amt = float(row.get("amount") or 0)
            equity_total += amt
            values = [row.get("account_name", ""), amt]
            for col, val in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=val)
                cell.font = _FONT_BODY
                cell.border = _BORDER_ALL
                if col == 1:
                    cell.alignment = _ALIGN_L
                else:
                    cell.alignment = _ALIGN_R
                    cell.number_format = _FMT_AMT
            r += 1

    cell_a = ws.cell(row=r, column=1, value="Total Liabilities & Equity")
    cell_a.font = _FONT_TOTAL
    cell_a.fill = _FILL_TOTAL
    cell_a.alignment = _ALIGN_L
    cell_a.border = _BORDER_ALL
    ws.cell(row=r, column=2).fill = _FILL_TOTAL
    ws.cell(row=r, column=2).border = _BORDER_ALL
    cell_b = ws.cell(row=r, column=2, value=liabilities_total + equity_total)
    cell_b.font = _FONT_TOTAL
    cell_b.fill = _FILL_TOTAL
    cell_b.alignment = _ALIGN_R
    cell_b.number_format = _FMT_AMT
    cell_b.border = _BORDER_ALL


def export_receipts_payments(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Receipts & Payments Account export."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    rows = db._execute(
        "SELECT * FROM fn_receipts_payments_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    society_name = _get_society_name(db, society_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Receipts & Payments"
    _apply_header(ws, 5, _COL_WIDTHS_RP)
    _write_receipts_payments_sheet(ws, rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_income_expenditure(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Income & Expenditure Account export."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    rows = db._execute(
        "SELECT * FROM fn_income_expenditure_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    society_name = _get_society_name(db, society_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Income & Expenditure"
    _apply_header(ws, 5, _COL_WIDTHS_IE)
    _write_income_expenditure_sheet(ws, rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_balance_sheet(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Balance Sheet export."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    rows = db._execute(
        "SELECT * FROM fn_balance_sheet_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    society_name = _get_society_name(db, society_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Balance Sheet"
    _apply_header(ws, 5, _COL_WIDTHS_BS)
    _write_balance_sheet_sheet(ws, rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_all_three_statements(db, society_id: int, fy: int) -> bytes:
    """Generate combined workbook with three sheets."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    society_name = _get_society_name(db, society_id)

    rp_rows = db._execute(
        "SELECT * FROM fn_receipts_payments_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    ie_rows = db._execute(
        "SELECT * FROM fn_income_expenditure_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    bs_rows = db._execute(
        "SELECT * FROM fn_balance_sheet_fy(%s,%s)",
        (society_id, fy), fetch_all=True,
    ) or []

    wb = Workbook()

    # Sheet 1: Receipts & Payments
    ws_rp = wb.active
    ws_rp.title = "Receipts & Payments"
    _apply_header(ws_rp, 5, _COL_WIDTHS_RP)
    _write_receipts_payments_sheet(ws_rp, rp_rows, society_name, fy)

    # Sheet 2: Income & Expenditure
    ws_ie = wb.create_sheet(title="Income & Expenditure")
    _apply_header(ws_ie, 5, _COL_WIDTHS_IE)
    _write_income_expenditure_sheet(ws_ie, ie_rows, society_name, fy)

    # Sheet 3: Balance Sheet
    ws_bs = wb.create_sheet(title="Balance Sheet")
    _apply_header(ws_bs, 5, _COL_WIDTHS_BS)
    _write_balance_sheet_sheet(ws_bs, bs_rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()