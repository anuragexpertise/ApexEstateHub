# database/rcm_export.py
"""
RCM Liability Excel Generator — EstateHub
==========================================
Produces RCM (Reverse Charge Mechanism) compliance reports.

Three sheets:
  * "RCM Register"    — monthly RCM liability register (all entries)
  * "Vendor Summary"  — vendor-wise RCM aggregation
  * "ITC Reconciliation" — ITC claimed vs GST paid reconciliation

Data source: rcm_liability table + expenses + vendors.
"""

from __future__ import annotations
import io

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
_FMT_DATE = "MMM-YYYY"


def _apply_header(ws, row: int, widths: dict) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.row_dimensions[row].height = 22


def _write_register_sheet(ws, rows: list[dict]) -> int:
    ws.cell(row=1, column=1, value="RCM Liability Register")
    ws.cell(row=1, column=1).font = _FONT_TITLE

    headers = [
        "Date", "Expense ID", "Vendor", "RCM Category",
        "Taxable Value", "CGST", "SGST", "GSTR Filed",
    ]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 3
    t_taxable = 0.0
    t_cgst = 0.0
    t_sgst = 0.0
    for row in rows:
        date_val = row.get("liability_date")
        expense_id = row.get("expense_id", "")
        vendor_name = row.get("vendor_name", "")
        rcm_cat = row.get("rcm_category", "")
        taxable = float(row.get("taxable_value", 0) or 0)
        cgst = float(row.get("cgst_amount", 0) or 0)
        sgst = float(row.get("sgst_amount", 0) or 0)
        gstr_filed = row.get("gstr_filed", False)

        values = [
            date_val, expense_id, vendor_name, rcm_cat,
            taxable, cgst, sgst, "Yes" if gstr_filed else "No",
        ]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col in (1, 2, 4, 8):
                cell.alignment = _ALIGN_C
            elif col in (3,):
                cell.alignment = _ALIGN_L
            else:
                cell.alignment = _ALIGN_R
                cell.number_format = _FMT_AMT
        r += 1
        t_taxable += taxable
        t_cgst += cgst
        t_sgst += sgst

    if r > 3:
        totals = [
            "TOTAL", "", "", "",
            t_taxable, t_cgst, t_sgst, "",
        ]
        for col, val in enumerate(totals, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_TOTAL
            cell.fill = _FILL_TOTAL
            cell.border = _BORDER_ALL
            if col == 1:
                cell.alignment = _ALIGN_L
            elif col in (5, 6, 7):
                cell.alignment = _ALIGN_R
                cell.number_format = _FMT_AMT
            else:
                cell.alignment = _ALIGN_C
    return r


def _write_vendor_summary_sheet(ws, rows: list[dict]) -> None:
    ws.cell(row=1, column=1, value="Vendor-wise RCM Summary")
    ws.cell(row=1, column=1).font = _FONT_TITLE

    headers = [
        "Vendor", "RCM Category", "Expenses", "Taxable Value",
        "CGST", "SGST", "Total RCM GST",
    ]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 3
    t_expenses = 0
    t_taxable = 0.0
    t_cgst = 0.0
    t_sgst = 0.0
    for row in rows:
        vendor = row.get("vendor_name", "")
        rcm_cat = row.get("rcm_category", "")
        n_expenses = int(row.get("n_expenses", 0) or 0)
        taxable = float(row.get("taxable_value", 0) or 0)
        cgst = float(row.get("cgst_amount", 0) or 0)
        sgst = float(row.get("sgst_amount", 0) or 0)

        values = [vendor, rcm_cat, n_expenses, taxable, cgst, sgst, cgst + sgst]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col in (1, 2, 3):
                cell.alignment = _ALIGN_L if col == 1 else _ALIGN_C
            elif col in (4, 5, 6, 7):
                cell.alignment = _ALIGN_R
                cell.number_format = _FMT_AMT
        r += 1
        t_expenses += n_expenses
        t_taxable += taxable
        t_cgst += cgst
        t_sgst += sgst

    totals = [
        "TOTAL", "", t_expenses, t_taxable, t_cgst, t_sgst, t_cgst + t_sgst,
    ]
    for col, val in enumerate(totals, start=1):
        cell = ws.cell(row=r, column=col, value=val)
        cell.font = _FONT_TOTAL
        cell.fill = _FILL_TOTAL
        cell.border = _BORDER_ALL
        if col == 1:
            cell.alignment = _ALIGN_L
        elif col == 3:
            cell.alignment = _ALIGN_C
        elif col in (4, 5, 6, 7):
            cell.alignment = _ALIGN_R
            cell.number_format = _FMT_AMT
        else:
            cell.alignment = _ALIGN_C


def _write_reconciliation_sheet(ws, rows: list[dict]) -> None:
    ws.cell(row=1, column=1, value="ITC Claimed vs GST Paid Reconciliation")
    ws.cell(row=1, column=1).font = _FONT_TITLE

    headers = [
        "Month", "RCM CGST Payable", "RCM SGST Payable",
        "ITC Claimed (Dr Expense)", "Net Payable",
    ]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=2, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 3
    t_cgst = 0.0
    t_sgst = 0.0
    t_itc = 0.0
    for row in rows:
        period = row.get("period_month")
        cgst = float(row.get("cgst_amount", 0) or 0)
        sgst = float(row.get("sgst_amount", 0) or 0)
        itc = float(row.get("itc_claimed", 0) or 0)
        net = cgst + sgst - itc

        values = [period, cgst, sgst, itc, net]
        for col, val in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=val)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            if col == 1:
                cell.alignment = _ALIGN_C
                cell.number_format = _FMT_DATE
            else:
                cell.alignment = _ALIGN_R
                cell.number_format = _FMT_AMT
        r += 1
        t_cgst += cgst
        t_sgst += sgst
        t_itc += itc

    totals = [
        "TOTAL", t_cgst, t_sgst, t_itc, t_cgst + t_sgst - t_itc,
    ]
    for col, val in enumerate(totals, start=1):
        cell = ws.cell(row=r, column=col, value=val)
        cell.font = _FONT_TOTAL
        cell.fill = _FILL_TOTAL
        cell.border = _BORDER_ALL
        if col == 1:
            cell.alignment = _ALIGN_L
        else:
            cell.alignment = _ALIGN_R
            cell.number_format = _FMT_AMT


def generate_rcm_excel(
    db,
    society_id: int,
    fy: int,
    filename_prefix: str = "RCMLiability",
) -> bytes:
    """Builds the RCM compliance workbook for one society FY."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    fy_start = MAKE_DATE(fy, 4, 1)
    fy_end = MAKE_DATE(fy + 1, 3, 31)

    # Sheet 1: RCM Register — all entries for the FY
    register_rows = db._execute(
        "SELECT rl.id, rl.liability_date, rl.rcm_category, rl.taxable_value, "
        "rl.cgst_amount, rl.sgst_amount, rl.gstr_filed, rl.expense_id, "
        "COALESCE(v.business_name, v.name, 'Unknown') AS vendor_name "
        "FROM rcm_liability rl "
        "LEFT JOIN vendors v ON v.id = rl.vendor_id AND v.society_id = rl.society_id "
        "WHERE rl.society_id = %s AND rl.liability_date >= %s AND rl.liability_date <= %s "
        "ORDER BY rl.liability_date, rl.id",
        (society_id, fy_start, fy_end), fetch_all=True,
    ) or []

    # Sheet 2: Vendor Summary
    vendor_rows = db._execute(
        "SELECT COALESCE(v.business_name, v.name, 'Unknown') AS vendor_name, "
        "rl.rcm_category, COUNT(*) AS n_expenses, "
        "SUM(rl.taxable_value) AS taxable_value, "
        "SUM(rl.cgst_amount) AS cgst_amount, "
        "SUM(rl.sgst_amount) AS sgst_amount "
        "FROM rcm_liability rl "
        "LEFT JOIN vendors v ON v.id = rl.vendor_id AND v.society_id = rl.society_id "
        "WHERE rl.society_id = %s AND rl.liability_date >= %s AND rl.liability_date <= %s "
        "GROUP BY COALESCE(v.business_name, v.name, 'Unknown'), rl.rcm_category "
        "ORDER BY rl.rcm_category, vendor_name",
        (society_id, fy_start, fy_end), fetch_all=True,
    ) or []

    # Sheet 3: ITC Reconciliation (RCM amounts are self-invoiced ITC,
    # so ITC claimed = cgst + sgst amounts; net payable = 0 by design)
    recon_rows = db._execute(
        "SELECT DATE_TRUNC('month', liability_date)::DATE AS period_month, "
        "SUM(cgst_amount) AS cgst_amount, SUM(sgst_amount) AS sgst_amount, "
        "SUM(cgst_amount + sgst_amount) AS itc_claimed "
        "FROM rcm_liability "
        "WHERE society_id = %s AND liability_date >= %s AND liability_date <= %s "
        "GROUP BY DATE_TRUNC('month', liability_date)::DATE "
        "ORDER BY period_month",
        (society_id, fy_start, fy_end), fetch_all=True,
    ) or []

    wb = Workbook()
    wb.remove(wb.active)

    ws_reg = wb.create_sheet(title="RCM Register")
    _apply_header(ws_reg, 2, {"A": 14, "B": 12, "C": 20, "D": 16, "E": 16, "F": 14, "G": 14, "H": 12})
    _write_register_sheet(ws_reg, register_rows)

    ws_vend = wb.create_sheet(title="Vendor Summary")
    _apply_header(ws_vend, 2, {"A": 24, "B": 16, "C": 12, "D": 16, "E": 14, "F": 14, "G": 16})
    _write_vendor_summary_sheet(ws_vend, vendor_rows)

    ws_rec = wb.create_sheet(title="ITC Reconciliation")
    _apply_header(ws_rec, 2, {"A": 16, "B": 18, "C": 18, "D": 22, "E": 18})
    _write_reconciliation_sheet(ws_rec, recon_rows)

    filename = f"{filename_prefix}_FY{fy}-{fy+1}.xlsx"
    wb._gst_filename = filename  # type: ignore[attr-defined]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
