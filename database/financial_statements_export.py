# database/financial_statements_export.py
"""
Three-Statement Financial Report Export — EstateHub
====================================================
Generates the three statutory financial statements required for
registered society annual filing:

1. Receipts & Payments Account (Cash basis)
2. Income & Expenditure Account (Accrual basis)
3. Balance Sheet (Position statement)

Data sources:
- fn_receipts_payments_fy(p_society_id, p_fy)
- fn_income_expenditure_fy(p_society_id, p_fy)
- fn_balance_sheet_fy(p_society_id, p_fy)

Following the pattern of income_tax_export.py and asset_export.py.
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
_FONT_SUBTOTAL = Font(name="Arial", size=9, bold=True, italic=True)

_FILL_HEADER = PatternFill("solid", fgColor="D9E1F2")
_FILL_TOTAL = PatternFill("solid", fgColor="E2EFDA")
_FILL_SECTION = PatternFill("solid", fgColor="F2F2F2")

_ALIGN_C = Alignment(horizontal="center", vertical="center")
_ALIGN_L = Alignment(horizontal="left", vertical="center")
_ALIGN_R = Alignment(horizontal="right", vertical="center")

_THIN = Side(style="thin")
_BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FMT_AMT = '#,##0.00;[Red](#,##0.00);"-"'

_COL_WIDTHS_RP = {"A": 40, "B": 18, "C": 18}
_COL_WIDTHS_IE = {"A": 40, "B": 18}
_COL_WIDTHS_BS = {"A": 40, "B": 18}


def _apply_header(ws, row: int, widths: dict) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    ws.row_dimensions[row].height = 22


def _write_row(ws, row: int, values: list, font=_FONT_BODY, fill=None, align=None, border=_BORDER_ALL, fmt=None) -> None:
    for col, val in enumerate(values, start=1):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = font
        if fill:
            cell.fill = fill
        if align:
            cell.alignment = align
        else:
            cell.alignment = _ALIGN_L if col == 1 else _ALIGN_R
        if border:
            cell.border = border
        if fmt and col > 1 and isinstance(val, (int, float)):
            cell.number_format = fmt


def _write_receipts_payments_sheet(ws, rows: list[dict], society_name: str, fy: int) -> None:
    """Write Receipts & Payments Account sheet."""
    ws.cell(row=1, column=1, value=f"{society_name}")
    ws.cell(row=1, column=1).font = Font(name="Arial", size=12, bold=True)

    ws.cell(row=2, column=1, value=f"Receipts & Payments Account for FY {fy}-{fy+1}")
    ws.cell(row=2, column=1).font = _FONT_TITLE

    ws.cell(row=3, column=1, value=f"Period: 1 April {fy} – 31 March {fy+1}")
    ws.cell(row=3, column=1).font = Font(name="Arial", size=9, italic=True)

    headers = ["Particulars", "Dr (Receipts)", "Cr (Payments)"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 5
    current_section = None
    section_totals = {"Receipt": 0.0, "Payment": 0.0}

    for row in rows:
        line_type = row.get("line_type", "")
        account_name = row.get("account_name", "")
        dr_amount = float(row.get("dr_amount", 0) or 0)
        cr_amount = float(row.get("cr_amount", 0) or 0)

        if line_type != current_section:
            if current_section in ("Receipt", "Payment") and section_totals[current_section] > 0:
                total_label = f"Total {current_section}s"
                if current_section == "Receipt":
                    _write_row(ws, r, [total_label, section_totals["Receipt"], 0], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
                else:
                    _write_row(ws, r, [total_label, 0, section_totals["Payment"]], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
                r += 1
            current_section = line_type
            section_totals = {"Receipt": 0.0, "Payment": 0.0}

        if line_type == "Opening":
            _write_row(ws, r, [account_name, dr_amount, cr_amount], _FONT_BODY, fmt=_FMT_AMT)
        elif line_type == "Receipt":
            _write_row(ws, r, [account_name, dr_amount, 0], _FONT_BODY, fmt=_FMT_AMT)
            section_totals["Receipt"] += dr_amount
        elif line_type == "Payment":
            _write_row(ws, r, [account_name, 0, cr_amount], _FONT_BODY, fmt=_FMT_AMT)
            section_totals["Payment"] += cr_amount
        elif line_type == "Closing":
            _write_row(ws, r, [account_name, dr_amount, cr_amount], _FONT_BODY, fmt=_FMT_AMT)
        r += 1

    if current_section in ("Receipt", "Payment") and section_totals[current_section] > 0:
        total_label = f"Total {current_section}s"
        if current_section == "Receipt":
            _write_row(ws, r, [total_label, section_totals["Receipt"], 0], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
        else:
            _write_row(ws, r, [total_label, 0, section_totals["Payment"]], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
        r += 1

    total_receipts = sum(float(row.get("dr_amount", 0) or 0) for row in rows if row.get("line_type") == "Receipt")
    total_payments = sum(float(row.get("cr_amount", 0) or 0) for row in rows if row.get("line_type") == "Payment")

    _write_row(ws, r, ["Grand Total", total_receipts, total_payments], _FONT_TOTAL, _FILL_TOTAL, fmt=_FMT_AMT)

    r += 2
    note = ws.cell(
        row=r, column=1,
        value=(
            "Note: Receipts & Payments Account is prepared on cash basis. "
            "Only actual cash/bank transactions (modes: cash, cheque, UPI, card, bank, crypto) are included. "
            "Journal entries (mode='journal') are excluded as they are non-cash book entries. "
            "Opening and Closing balances represent aggregate Cash-in-hand and Bank account balances."
        ),
    )
    note.font = Font(name="Arial", size=8, italic=True)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    ws.row_dimensions[r].height = 45


def _write_income_expenditure_sheet(ws, rows: list[dict], society_name: str, fy: int) -> None:
    """Write Income & Expenditure Account sheet."""
    ws.cell(row=1, column=1, value=f"{society_name}")
    ws.cell(row=1, column=1).font = Font(name="Arial", size=12, bold=True)

    ws.cell(row=2, column=1, value=f"Income & Expenditure Account for FY {fy}-{fy+1}")
    ws.cell(row=2, column=1).font = _FONT_TITLE

    ws.cell(row=3, column=1, value=f"Period: 1 April {fy} – 31 March {fy+1}")
    ws.cell(row=3, column=1).font = Font(name="Arial", size=9, italic=True)

    headers = ["Particulars", "Amount"]
    for col, hdr in enumerate(headers, start=1):
        cell = ws.cell(row=4, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    r = 5
    current_section = None
    section_total = 0.0
    income_total = 0.0
    expense_total = 0.0

    for row in rows:
        section = row.get("statement_section", "")
        account_name = row.get("account_name", "")
        amount = float(row.get("amount", 0) or 0)

        if section != current_section:
            if current_section == "Income" and section_total > 0:
                _write_row(ws, r, ["Total Income", section_total], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
                income_total = section_total
                r += 1
            elif current_section == "Expenditure" and section_total > 0:
                _write_row(ws, r, ["Total Expenditure", section_total], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
                expense_total = section_total
                r += 1
            current_section = section
            section_total = 0.0

        if section == "Income":
            _write_row(ws, r, [account_name, amount], _FONT_BODY, fmt=_FMT_AMT)
            section_total += amount
        elif section == "Expenditure":
            _write_row(ws, r, [account_name, amount], _FONT_BODY, fmt=_FMT_AMT)
            section_total += amount
        elif section == "Surplus/Deficit":
            _write_row(ws, r, [account_name, amount], _FONT_TOTAL, _FILL_TOTAL, fmt=_FMT_AMT)
        r += 1

    if current_section == "Income" and section_total > 0:
        _write_row(ws, r, ["Total Income", section_total], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
        income_total = section_total
        r += 1
    elif current_section == "Expenditure" and section_total > 0:
        _write_row(ws, r, ["Total Expenditure", section_total], _FONT_SUBTOTAL, _FILL_SECTION, fmt=_FMT_AMT)
        expense_total = section_total
        r += 1

    surplus_deficit = income_total - expense_total
    label = "Surplus" if surplus_deficit >= 0 else "Deficit"
    _write_row(ws, r, [f"Excess of Income over Expenditure ({label})", abs(surplus_deficit)], _FONT_TOTAL, _FILL_TOTAL, fmt=_FMT_AMT)

    r += 2
    note = ws.cell(
        row=r, column=1,
        value=(
            "Note: Income & Expenditure Account is prepared on accrual basis. "
            "Income includes receivables accruals and confirmed receipts credited to income accounts. "
            "Expenditure includes confirmed expenses, verified payables, and depreciation. "
            "Surplus/Deficit = Total Income - Total Expenditure."
        ),
    )
    note.font = Font(name="Arial", size=8, italic=True)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    ws.row_dimensions[r].height = 45


def _fetch_society_metadata(db, society_id: int, fy: int) -> dict:
    row = db._execute(
        """
        SELECT
            s.name,
            s.address,
            s.PAN_number AS pan_number,
            s.TAN_number AS tan_number,
            s.gstin,
            s.registration_number,
            lrp.name AS legal_regime_name,
            lrp.code AS legal_regime_code
        FROM societies AS s
        LEFT JOIN society_legal_regime AS slr
            ON slr.society_id = s.id
           AND slr.effective_from <= MAKE_DATE(%s + 1, 3, 31)
           AND (slr.effective_to IS NULL OR slr.effective_to >= MAKE_DATE(%s, 4, 1))
        LEFT JOIN legal_regime_profiles AS lrp
            ON lrp.code = slr.regime_code
        WHERE s.id = %s
        """,
        (fy, fy, society_id),
        fetch_one=True,
    )
    return row or {}


def _fetch_balance_sheet_rows(db, society_id: int, fy: int) -> list[dict]:
    return db._execute(
        """
        SELECT
            bs.*,
            COALESCE(NULLIF(a.tab_name, ''), bs.account_name, '') AS account_tab_name
        FROM fn_balance_sheet_fy(%s, %s) AS bs
        LEFT JOIN accounts AS a
            ON a.society_id = %s
           AND a.id = bs.account_code
        """,
        (society_id, fy, society_id),
        fetch_all=True,
    ) or []


def _fetch_balance_sheet_hierarchy(db, society_id: int, fy: int) -> tuple[list[dict], dict[int, list[dict]], dict]:
    """Fetch Balance Sheet data from fn_fy_closing_report with parent_account_id hierarchy.
    
    Returns:
        - root_children: Direct children of the root account (tab_name='Bal')
        - children_by_parent: Dict mapping parent_account_id to list of child accounts
        - closing_by_id: Dict mapping account_id to its closing row data
    """
    closing_rows = db._execute(
        "SELECT * FROM fn_fy_closing_report(%s,%s) ORDER BY sort_path",
        (society_id, fy), fetch_all=True,
    ) or []
    
    closing_by_id = {r["account_id"]: r for r in closing_rows}
    children_by_parent: dict[int, list[dict]] = {}
    for r in closing_rows:
        pid = r.get("parent_account_id")
        if pid is not None:
            children_by_parent.setdefault(pid, []).append(r)
    
    root = next((r for r in closing_rows if r.get("parent_account_id") is None), None)
    root_children = children_by_parent.get((root or {}).get("id"), []) if root else []
    
    return root_children, children_by_parent, closing_by_id


def _write_balance_sheet_metadata(ws, society_name: str, metadata: dict, fy: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=3)
    society_cell = ws.cell(row=1, column=1, value=society_name.upper())
    society_cell.font = Font(name="Arial", size=12, bold=True)

    ws.cell(row=1, column=8, value="Financial Year").font = _FONT_HEADER
    ws.cell(row=1, column=9, value=f"{fy}-{fy + 1}").font = _FONT_BODY

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=3)
    address_cell = ws.cell(
        row=2,
        column=1,
        value=metadata.get("address") or "",
    )
    address_cell.font = _FONT_BODY
    address_cell.alignment = Alignment(horizontal="left", wrap_text=True, vertical="center")

    ws.cell(row=2, column=6, value="PAN").font = _FONT_HEADER
    ws.cell(row=2, column=7, value=metadata.get("pan_number") or "").font = _FONT_BODY
    ws.cell(row=2, column=8, value="TAN").font = _FONT_HEADER
    ws.cell(row=2, column=9, value=metadata.get("tan_number") or "").font = _FONT_BODY

    ws.cell(row=3, column=1, value="Legal Regime").font = _FONT_HEADER
    ws.cell(
        row=3,
        column=2,
        value=metadata.get("legal_regime_name") or metadata.get("legal_regime_code") or "",
    ).font = _FONT_BODY

    ws.cell(row=3, column=6, value="GSTIN").font = _FONT_HEADER
    ws.cell(row=3, column=7, value=metadata.get("gstin") or "").font = _FONT_BODY
    ws.cell(row=3, column=8, value="Registration No.").font = _FONT_HEADER
    ws.cell(row=3, column=9, value=metadata.get("registration_number") or "").font = _FONT_BODY

    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 30
    ws.row_dimensions[3].height = 22
    ws.row_dimensions[4].height = 22
    ws.row_dimensions[5].height = 22


def _write_balance_sheet_sheet(
    ws,
    rows: list[dict],
    society_name: str,
    fy: int,
    society_metadata: dict = None,
) -> None:
    """Write Balance Sheet sheet in 2-column Liabilities|Assets format
    matching ld.xlsx 'Bal' sheet layout (A=Date, B-D=Liabilities, F-I=Assets).
    
    If statutory metadata is present (statutory_head_code), groups accounts
    by statutory head for jurisdiction-aware presentation (UP AOA, etc.)."""
    from collections import defaultdict

    fy_end = date(fy + 1, 3, 31)

    _apply_header(ws, 3, {"A": 14, "B": 20, "C": 28, "D": 18,
                           "F": 20, "G": 24, "H": 20, "I": 18})
    ws.column_dimensions["E"].width = 3

    metadata = society_metadata or {}
    _write_balance_sheet_metadata(ws, society_name, metadata, fy)

    ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=9)
    title_cell = ws.cell(
        row=5,
        column=1,
        value=f"Balance Sheet as at 31 March {fy + 1}",
    )
    title_cell.font = Font(name="Arial", size=16, bold=True)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.cell(row=8, column=2, value="Liabilities").font = _FONT_HEADER
    ws.cell(row=8, column=6, value="Assets").font = _FONT_HEADER

    headers = {
        1: "Date", 2: "A/c", 3: "Account Name", 4: "Amount",
        6: "A/c", 7: "Account Name", 8: "", 9: "Amount",
    }
    for col, hdr in headers.items():
        cell = ws.cell(row=7, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    # Check for statutory metadata
    has_statutory = any(r.get("statutory_head_code") for r in rows)

    liabilities = [r for r in rows if r.get("statement_section") == "Liabilities"]
    assets = [r for r in rows if r.get("statement_section") == "Assets"]
    equity = [r for r in rows if r.get("statement_section") == "Equity"]

    def _account_tab_name(row: dict) -> str:
        if "account_tab_name" in row:
            return row.get("account_tab_name") or ""
        return row.get("tab_name") or row.get("account_code") or ""

    def _equity_tab_name(row: dict) -> str:
        account_name = row.get("account_name", "")
        if account_name == "Capital Account":
            return row.get("account_tab_name") or row.get("tab_name") or "CapAc"
        if account_name in {"Reserves & Surplus", "Reserve & Surplus", "Reserve &Surplus"}:
            return row.get("account_tab_name") or row.get("tab_name") or "ResSur"
        return ""

    def _write_grouped_section(ws, section_rows, start_row, col_date, col_code, col_name, col_amt, 
                               is_liability=True, section_title=None):
        """Write a section (Liabilities or Assets) with optional statutory grouping."""
        if not section_rows:
            return start_row, start_row - 1
        
        r = start_row
        if section_title:
            ws.cell(row=r, column=col_name if is_liability else col_code, value=section_title).font = _FONT_HEADER
            r += 1
        
        if has_statutory:
            # Group by statutory head
            head_groups = defaultdict(list)
            for row in section_rows:
                head_code = row.get("statutory_head_code") or "UNMAPPED"
                head_groups[head_code].append(row)
            
            # Sort groups by display_order, then by head_code
            sorted_groups = sorted(
                head_groups.items(),
                key=lambda x: (x[1][0].get("statutory_display_order") or 999, x[0])
            )
            
            for head_code, group_rows in sorted_groups:
                if len(group_rows) > 1:
                    # Multiple accounts under this head - show as group header + items
                    head_label = group_rows[0].get("statutory_head_label") or head_code
                    ws.cell(row=r, column=col_name if is_liability else col_code, value=head_label).font = _FONT_HEADER
                    r += 1
                    for row in sorted(group_rows, key=lambda x: x.get("statutory_display_order") or 0):
                        ws.cell(row=r, column=col_date, value=fy_end).number_format = "DD-MMM-YYYY"
                        ws.cell(row=r, column=col_code, value=_account_tab_name(row))
                        ws.cell(row=r, column=col_name, value=row.get("account_name", ""))
                        ws.cell(row=r, column=col_amt, value=float(row.get("amount", 0) or 0)).number_format = _FMT_AMT
                        for col in (col_date, col_code, col_name, col_amt):
                            cell = ws.cell(row=r, column=col)
                            cell.font = _FONT_BODY
                            cell.border = _BORDER_ALL
                            cell.alignment = _ALIGN_R if col in (col_date, col_amt) else _ALIGN_L
                        r += 1
                else:
                    # Single account
                    row = group_rows[0]
                    ws.cell(row=r, column=col_date, value=fy_end).number_format = "DD-MMM-YYYY"
                    ws.cell(row=r, column=col_code, value=_account_tab_name(row))
                    ws.cell(row=r, column=col_name, value=row.get("account_name", ""))
                    ws.cell(row=r, column=col_amt, value=float(row.get("amount", 0) or 0)).number_format = _FMT_AMT
                    for col in (col_date, col_code, col_name, col_amt):
                        cell = ws.cell(row=r, column=col)
                        cell.font = _FONT_BODY
                        cell.border = _BORDER_ALL
                        cell.alignment = _ALIGN_R if col in (col_date, col_amt) else _ALIGN_L
                    r += 1
        else:
            # Flat list (legacy)
            for row in section_rows:
                ws.cell(row=r, column=col_date, value=fy_end).number_format = "DD-MMM-YYYY"
                ws.cell(row=r, column=col_code, value=_account_tab_name(row))
                ws.cell(row=r, column=col_name, value=row.get("account_name", ""))
                ws.cell(row=r, column=col_amt, value=float(row.get("amount", 0) or 0)).number_format = _FMT_AMT
                for col in (col_date, col_code, col_name, col_amt):
                    cell = ws.cell(row=r, column=col)
                    cell.font = _FONT_BODY
                    cell.border = _BORDER_ALL
                    cell.alignment = _ALIGN_R if col in (col_date, col_amt) else _ALIGN_L
                r += 1
        return r, r - 1

    liab_start = 9
    _, liab_end = _write_grouped_section(ws, liabilities, liab_start, 1, 2, 3, 4, True)

    asset_start = 9
    _, asset_end = _write_grouped_section(ws, assets, asset_start, 1, 6, 7, 9, False)

    equity_start = liab_end + 1
    ws.cell(row=equity_start, column=2, value="Equity & Surplus").font = _FONT_HEADER
    r = equity_start + 1
    for row in equity:
        ws.cell(row=r, column=1, value=fy_end).number_format = "DD-MMM-YYYY"
        ws.cell(row=r, column=2, value=_equity_tab_name(row)).font = _FONT_BODY
        ws.cell(row=r, column=3, value=row.get("account_name", "")).font = _FONT_BODY
        ws.cell(row=r, column=4, value=float(row.get("amount", 0) or 0)).font = _FONT_BODY
        ws.cell(row=r, column=4).number_format = _FMT_AMT
        for col in (1, 2, 3, 4):
            cell = ws.cell(row=r, column=col)
            cell.font = _FONT_BODY
            cell.border = _BORDER_ALL
            cell.alignment = _ALIGN_R if col in (1, 4) else _ALIGN_L
        r += 1

    equity_end = r - 1 if equity else liab_end
    total_row = max(asset_end, equity_end) + 2
    combined_end = max(liab_end, equity_end)
    combined_formula = (
        f"=SUM(D{liab_start}:D{combined_end})"
        if combined_end >= liab_start
        else "=0"
    )
    asset_formula = (
        f"=SUM(I{asset_start}:I{asset_end})"
        if asset_end >= asset_start
        else "=0"
    )

    combined_label = ws.cell(
        row=total_row,
        column=2,
        value="Total Liabilities + Equity & Surplus",
    )
    combined_label.font = _FONT_TOTAL
    combined_label.border = _BORDER_ALL
    combined_label.alignment = _ALIGN_L

    combined_amount = ws.cell(row=total_row, column=4, value=combined_formula)
    combined_amount.font = _FONT_TOTAL
    combined_amount.border = _BORDER_ALL
    combined_amount.alignment = _ALIGN_R
    combined_amount.number_format = _FMT_AMT

    asset_total_label = ws.cell(row=total_row, column=7, value="Total")
    asset_total_label.font = _FONT_TOTAL
    asset_total_label.fill = _FILL_SECTION
    asset_total_label.border = _BORDER_ALL
    asset_total_label.alignment = _ALIGN_L

    asset_total_amount = ws.cell(row=total_row, column=9, value=asset_formula)
    asset_total_amount.font = _FONT_TOTAL
    asset_total_amount.fill = _FILL_SECTION
    asset_total_amount.border = _BORDER_ALL
    asset_total_amount.alignment = _ALIGN_R
    asset_total_amount.number_format = _FMT_AMT

    note = ws.cell(
        row=total_row + 2, column=1,
        value=(
            "Note: Balance Sheet is prepared from closing balances of the financial year. "
            "Assets = Dr-natured accounts (Cash, Bank, Debtors, Fixed Assets, Investments, Loans Given). "
            "Liabilities = Cr-natured accounts (Creditors, Funds, Loans Taken, Provisions). "
            "Equity = Capital Account + Current Year Surplus/Deficit (from Income & Expenditure). "
            "Mutual income (exempt) and Non-mutual income (taxable) shown in Income Tax — Mutuality Summary. "
            "Statutory head grouping per UP Apartment Act 2010 / Model Bye-Laws where applicable."
        ),
    )
    note.font = Font(name="Arial", size=8, italic=True)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=total_row + 2, start_column=1, end_row=total_row + 2, end_column=9)
    ws.row_dimensions[total_row + 2].height = 45


def _write_balance_sheet_hierarchical(
    ws,
    root_children: list[dict],
    children_by_parent: dict[int, list[dict]],
    closing_by_id: dict,
    society_name: str,
    fy: int,
    society_metadata: dict = None,
) -> None:
    """Write Balance Sheet using parent_account_id hierarchy from fn_fy_closing_report.
    
    2-column Liabilities|Assets format matching ld.xlsx 'Bal' sheet layout.
    """
    from collections import defaultdict

    fy_end = date(fy + 1, 3, 31)

    _apply_header(ws, 3, {"A": 14, "B": 20, "C": 28, "D": 18,
                           "F": 20, "G": 24, "H": 20, "I": 18})
    ws.column_dimensions["E"].width = 3

    metadata = society_metadata or {}
    _write_balance_sheet_metadata(ws, society_name, metadata, fy)

    ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=9)
    title_cell = ws.cell(
        row=5,
        column=1,
        value=f"Balance Sheet as at 31 March {fy + 1}",
    )
    title_cell.font = Font(name="Arial", size=16, bold=True)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.cell(row=8, column=2, value="Liabilities").font = _FONT_HEADER
    ws.cell(row=8, column=6, value="Assets").font = _FONT_HEADER

    headers = {
        1: "Date", 2: "A/c", 3: "Account Name", 4: "Amount",
        6: "A/c", 7: "Account Name", 8: "", 9: "Amount",
    }
    for col, hdr in headers.items():
        cell = ws.cell(row=7, column=col, value=hdr)
        cell.font = _FONT_HEADER
        cell.fill = _FILL_HEADER
        cell.alignment = _ALIGN_C
        cell.border = _BORDER_ALL

    def _account_tab_name(row: dict) -> str:
        return row.get("tab_name") or row.get("account_name") or ""

    def _indent(cell):
        cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # Split root children into Liabilities (Cr) and Assets (Dr)
    liabilities = sorted(
        (c for c in root_children if c.get("drcr_account") == "Cr"),
        key=lambda x: x.get("sort_path") or "",
    )
    assets = sorted(
        (c for c in root_children if c.get("drcr_account") == "Dr"),
        key=lambda x: x.get("sort_path") or "",
    )

    # Find Capital Account (Equity) - it's a root child but handled separately
    cap_ac = next((c for c in root_children if c.get("tab_name") == "CapAc"), None)

    # Write Liabilities section
    r = 9
    liab_start = r
    for item in liabilities:
        kids = sorted(children_by_parent.get(item["account_id"], []),
                       key=lambda x: x.get("sort_path") or "")
        amount = float(item.get("display_amount") or 0)

        c1 = ws.cell(row=r, column=1, value=fy_end)
        c1.font, c1.number_format = _FONT_BODY, "DD-MMM-YYYY"
        ws.cell(row=r, column=2, value=_account_tab_name(item)).font = _FONT_BODY
        ws.cell(row=r, column=3, value=item.get("account_name", "")).font = _FONT_BODY
        if not kids and amount:
            c4 = ws.cell(row=r, column=4, value=amount)
            c4.font, c4.alignment, c4.number_format = _FONT_BODY, _ALIGN_R, _FMT_AMT
        r += 1

        for kid in kids:
            kamt = float(kid.get("display_amount") or 0)
            if kamt == 0:
                continue
            c3 = ws.cell(row=r, column=3, value=kid.get("account_name", ""))
            c3.font = _FONT_BODY
            _indent(c3)
            c4 = ws.cell(row=r, column=4, value=kamt)
            c4.font, c4.number_format = _FONT_BODY, _FMT_AMT
            _indent(c4)
            c4.alignment = _ALIGN_R
            r += 1
    liab_last_row = r - 1

    # Write Assets section
    r = 9
    asset_start = r
    for item in assets:
        kids = sorted(children_by_parent.get(item["account_id"], []),
                       key=lambda x: x.get("sort_path") or "")
        amount = float(item.get("display_amount") or 0)

        c1 = ws.cell(row=r, column=1, value=fy_end)
        c1.font, c1.number_format = _FONT_BODY, "DD-MMM-YYYY"
        ws.cell(row=r, column=6, value=_account_tab_name(item)).font = _FONT_BODY
        ws.cell(row=r, column=7, value=item.get("account_name", "")).font = _FONT_BODY
        if not kids and amount:
            c9 = ws.cell(row=r, column=9, value=amount)
            c9.font, c9.alignment, c9.number_format = _FONT_BODY, _ALIGN_R, _FMT_AMT
        r += 1

        for kid in kids:
            kamt = float(kid.get("display_amount") or 0)
            if kamt == 0:
                continue
            ws.cell(row=r, column=8, value=kid.get("account_name", "")).font = _FONT_BODY
            c9 = ws.cell(row=r, column=9, value=kamt)
            c9.font, c9.alignment, c9.number_format = _FONT_BODY, _ALIGN_R, _FMT_AMT
            r += 1
    asset_last_row = r - 1

    # Write Equity section (Capital Account + Reserves & Surplus)
    equity_start = liab_last_row + 1
    ws.cell(row=equity_start, column=2, value="Equity & Surplus").font = _FONT_HEADER
    r = equity_start + 1
    
    # Capital Account
    if cap_ac:
        cap_amount = float(cap_ac.get("own_closing") or 0)
        ws.cell(row=r, column=1, value=fy_end).number_format = "DD-MMM-YYYY"
        ws.cell(row=r, column=2, value=_account_tab_name(cap_ac)).font = _FONT_BODY
        ws.cell(row=r, column=3, value=cap_ac.get("account_name", "")).font = _FONT_BODY
        c4 = ws.cell(row=r, column=4, value=cap_amount)
        c4.font, c4.alignment, c4.number_format = _FONT_BODY, _ALIGN_R, _FMT_AMT
        r += 1
        
        # Capital Account children (Reserves, etc.)
        cap_kids = sorted(children_by_parent.get(cap_ac["account_id"], []),
                          key=lambda x: x.get("sort_path") or "")
        for kid in cap_kids:
            kamt = float(kid.get("display_amount") or 0)
            if kamt == 0:
                continue
            c3 = ws.cell(row=r, column=3, value=kid.get("account_name", ""))
            c3.font = _FONT_BODY
            _indent(c3)
            c4 = ws.cell(row=r, column=4, value=kamt)
            c4.font, c4.number_format = _FONT_BODY, _FMT_AMT
            _indent(c4)
            c4.alignment = _ALIGN_R
            r += 1

    equity_end = r - 1 if r > equity_start + 1 else liab_last_row

    # Totals
    total_row = max(asset_last_row, equity_end) + 2
    combined_end = max(liab_last_row, equity_end)
    combined_formula = (
        f"=SUM(D{liab_start}:D{combined_end})"
        if combined_end >= liab_start
        else "=0"
    )
    asset_formula = (
        f"=SUM(I{asset_start}:I{asset_last_row})"
        if asset_last_row >= asset_start
        else "=0"
    )

    combined_label = ws.cell(
        row=total_row,
        column=2,
        value="Total Liabilities + Equity & Surplus",
    )
    combined_label.font = _FONT_TOTAL
    combined_label.border = _BORDER_ALL
    combined_label.alignment = _ALIGN_L

    combined_amount = ws.cell(row=total_row, column=4, value=combined_formula)
    combined_amount.font = _FONT_TOTAL
    combined_amount.border = _BORDER_ALL
    combined_amount.alignment = _ALIGN_R
    combined_amount.number_format = _FMT_AMT

    asset_total_label = ws.cell(row=total_row, column=7, value="Total")
    asset_total_label.font = _FONT_TOTAL
    asset_total_label.fill = _FILL_SECTION
    asset_total_label.border = _BORDER_ALL
    asset_total_label.alignment = _ALIGN_L

    asset_total_amount = ws.cell(row=total_row, column=9, value=asset_formula)
    asset_total_amount.font = _FONT_TOTAL
    asset_total_amount.fill = _FILL_SECTION
    asset_total_amount.border = _BORDER_ALL
    asset_total_amount.alignment = _ALIGN_R
    asset_total_amount.number_format = _FMT_AMT

    note = ws.cell(
        row=total_row + 2, column=1,
        value=(
            "Note: Balance Sheet is prepared from closing balances of the financial year. "
            "Assets = Dr-natured accounts (Cash, Bank, Debtors, Fixed Assets, Investments, Loans Given). "
            "Liabilities = Cr-natured accounts (Creditors, Funds, Loans Taken, Provisions). "
            "Equity = Capital Account + Current Year Surplus/Deficit (from Income & Expenditure). "
            "Hierarchical presentation per parent_account_id from fn_fy_closing_report. "
            "Statutory head grouping per UP Apartment Act 2010 / Model Bye-Laws where applicable."
        ),
    )
    note.font = Font(name="Arial", size=8, italic=True)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=total_row + 2, start_column=1, end_row=total_row + 2, end_column=9)
    ws.row_dimensions[total_row + 2].height = 45


def _build_workbook(society_id: int, fy: int, db, society_name: str = None) -> Workbook:
    """Build the three-sheet workbook."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    society_metadata = _fetch_society_metadata(db, society_id, fy)

    if society_name is None:
        society_name = society_metadata.get("name") or "Society"

    # Fetch data from SQL functions
    rp_rows = db._execute(
        "SELECT * FROM fn_receipts_payments_fy(%s,%s)", (society_id, fy), fetch_all=True
    ) or []

    ie_rows = db._execute(
        "SELECT * FROM fn_income_expenditure_fy(%s,%s)", (society_id, fy), fetch_all=True
    ) or []

    # Fetch hierarchical Balance Sheet data from fn_fy_closing_report
    root_children, children_by_parent, closing_by_id = _fetch_balance_sheet_hierarchy(db, society_id, fy)

    wb = Workbook()
    wb.remove(wb.active)

    # Sheet 1: Receipts & Payments
    ws1 = wb.create_sheet(title="Receipts & Payments")
    _apply_header(ws1, 4, _COL_WIDTHS_RP)
    _write_receipts_payments_sheet(ws1, rp_rows, society_name, fy)

    # Sheet 2: Income & Expenditure
    ws2 = wb.create_sheet(title="Income & Expenditure")
    _apply_header(ws2, 4, _COL_WIDTHS_IE)
    _write_income_expenditure_sheet(ws2, ie_rows, society_name, fy)

    # Sheet 3: Balance Sheet (hierarchical)
    ws3 = wb.create_sheet(title="Balance Sheet")
    _write_balance_sheet_hierarchical(ws3, root_children, children_by_parent, closing_by_id, society_name, fy, society_metadata)

    return wb


def export_receipts_payments(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Receipts & Payments Account export (standalone)."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    row = db._execute("SELECT name FROM societies WHERE id=%s", (society_id,), fetch_one=True)
    society_name = row.get("name", "Society") if row else "Society"

    rp_rows = db._execute(
        "SELECT * FROM fn_receipts_payments_fy(%s,%s)", (society_id, fy), fetch_all=True
    ) or []

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title="Receipts & Payments")
    _apply_header(ws, 4, _COL_WIDTHS_RP)
    _write_receipts_payments_sheet(ws, rp_rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_income_expenditure(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Income & Expenditure Account export (standalone)."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    row = db._execute("SELECT name FROM societies WHERE id=%s", (society_id,), fetch_one=True)
    society_name = row.get("name", "Society") if row else "Society"

    ie_rows = db._execute(
        "SELECT * FROM fn_income_expenditure_fy(%s,%s)", (society_id, fy), fetch_all=True
    ) or []

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title="Income & Expenditure")
    _apply_header(ws, 4, _COL_WIDTHS_IE)
    _write_income_expenditure_sheet(ws, ie_rows, society_name, fy)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_balance_sheet(db, society_id: int, fy: int, format: str = "xlsx") -> bytes:
    """Generate Balance Sheet export (standalone)."""
    from database.db_manager import db as _db
    if db is None:
        db = _db

    society_metadata = _fetch_society_metadata(db, society_id, fy)
    society_name = society_metadata.get("name") or "Society"

    root_children, children_by_parent, closing_by_id = _fetch_balance_sheet_hierarchy(db, society_id, fy)

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title="Balance Sheet")
    _write_balance_sheet_hierarchical(ws, root_children, children_by_parent, closing_by_id, society_name, fy, society_metadata)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_all_three_statements(db, society_id: int, fy: int) -> bytes:
    """Generate combined workbook with three sheets."""
    wb = _build_workbook(society_id, fy, db)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
