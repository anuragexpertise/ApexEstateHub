"""
Shared xlsx template builder / upload parser for onboarding (items 6, 9, 10).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation


@dataclass
class ParseResult:
    rows: list[dict]
    errors: list[str]


def _protect_sheet(ws):
    ws.protection.sheet = True
    ws.protection.enable()


def build_tds_template(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "TDS Rates"
    headers = [
        "section",
        "section_2025",
        "discriminator",
        "reference_rate",
        "nature_of_income",
        "rate",
        "rate_no_pan",
        "single_bill_threshold",
        "annual_aggregate_threshold",
    ]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True)
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for r, item in enumerate(rows or [], start=2):
        ws.cell(row=r, column=1, value=item.get("section") or "").protection = Protection(locked=True)
        ws.cell(row=r, column=2, value=item.get("section_2025") or item.get("it2025_twin") or "").protection = Protection(locked=True)
        ws.cell(row=r, column=3, value=item.get("discriminator") or "").protection = Protection(locked=True)
        ws.cell(row=r, column=4, value=item.get("reference_rate") or "").protection = Protection(locked=True)
        ws.cell(row=r, column=5, value=item.get("nature_of_income") or "")
        ws.cell(row=r, column=6, value="")
        ws.cell(row=r, column=7, value="")
        ws.cell(row=r, column=8, value="")
        ws.cell(row=r, column=9, value="")
        for c in (1, 2, 3, 4):
            ws.cell(row=r, column=c).fill = locked_fill
    dv = DataValidation(type="decimal", operator="between", formula1="0", formula2="100", allow_blank=True)
    dv.add("F2:I500")
    ws.add_data_validation(dv)
    ws.freeze_panes = "A2"

    # Header sheet
    wh = wb.create_sheet("Header")
    wh.append(["tan", "effective_date"])
    wh.append(["", "YYYY-MM-DD"])

    # Instructions
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Rates are pending the CA's confirmation; leave a rate blank if TDS does not apply to that row."])
    wi.append(["Tax Year 2026-27 onward: file under the Income-tax Act, 2025 section numbers where applicable."])
    wi.append(["Only .xlsx is accepted. Numbers must be >= 0."])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_bf_template(rows: list[dict], fy: int | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Brought Forward"
    headers = ["account_id", "tab", "account_name", "side", "bf_amount", "remarks"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for r, item in enumerate(rows or [], start=2):
        for c, h in enumerate(headers, start=1):
            val = item.get(h) if h in item else item.get("bf_amount") if h == "bf_amount" else item.get(h)
            cell = ws.cell(row=r, column=c, value=val)
            if h in ("account_id", "tab", "account_name", "side"):
                cell.protection = Protection(locked=True)
                cell.fill = locked_fill
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    dv.add("E2:E500")
    ws.add_data_validation(dv)
    ws.freeze_panes = "A2"

    wh = wb.create_sheet("Header")
    wh.append(["financial_year"])
    wh.append([fy or ""])

    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Match on account_id; do not change locked columns."])
    wi.append(["Blank = 0. Amounts must be >= 0."])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_upload(contents: str, filename: str, sheet: str, required: list[str], max_rows: int = 500,
                 max_bytes: int = 1_048_576) -> ParseResult:
    # Basic guards
    if filename and filename.lower().endswith(".xls"):
        return ParseResult(rows=[], errors=["Only .xlsx is accepted (not .xls)."])
    if contents and "," in contents:
        import base64
        b = contents.split(",", 1)[1]
        raw = base64.b64decode(b)
    else:
        raw = b""
    if len(raw) > max_bytes:
        return ParseResult(rows=[], errors=["File exceeds 1 MB."])
    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as exc:
        return ParseResult(rows=[], errors=[f"Could not open xlsx: {exc}"])
    if sheet not in wb.sheetnames:
        return ParseResult(rows=[], errors=[f"Sheet '{sheet}' not found."])
    ws = wb[sheet]
    # header
    headers = []
    for cell in ws[1]:
        headers.append(str(cell.value).strip().lower() if cell.value is not None else "")
    lower = {h: i for i, h in enumerate(headers) if h}
    missing = [r for r in required if r.lower() not in lower]
    if missing:
        return ParseResult(rows=[], errors=[f"Missing column(s): {', '.join(missing)}"])
    rows = []
    errors = []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if idx - 1 > max_rows:
            errors.append(f"Too many rows (> {max_rows}).")
            break
        rec = {}
        for h, cidx in lower.items():
            rec[h] = row[cidx] if cidx < len(row) else None
        # skip empty
        if all((v is None or str(v).strip() == "") for v in rec.values()):
            continue
        rows.append(rec)
    return ParseResult(rows=rows, errors=errors)
