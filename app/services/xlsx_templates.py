# app/services/xlsx_templates.py
"""
Shared Excel template builder / upload parser (onboarding review items 6, 9, 10).

Template download pattern: dcc.send_bytes, as in
bulk_enroll_callbacks.download_bulk_enroll_template.
Upload: .xlsx ONLY (.xls/.csv rejected); header match case-insensitive, extra
columns ignored; numbers parsed via Decimal(str(v)); errors collected, never
partial-applied (preview table + error list, then "Apply to form").

Pandas is allowed for reading (pd.read_excel(..., engine="openpyxl")).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

MAX_BYTES = 1_048_576          # 1 MB
MAX_ROWS = 500
TDS_MAX_ROWS = 200

_HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
_HEADER_FONT = Font(bold=True, color="1F1F1F")
_LOCKED_FILL = PatternFill("solid", fgColor="EDEDED")
_BODY_ALIGN = Alignment(wrap_text=True, vertical="top")
_THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)


@dataclass
class SheetSpec:
    name: str
    columns: list[str]            # in order
    locked: set[str] = field(default_factory=set)   # grey, not user-editable
    numeric: set[str] = field(default_factory=set)  # data-validation decimal >= 0
    rows: list[dict] = field(default_factory=list)  # one dict per data row


@dataclass
class ParseResult:
    sheet: str
    matched: int                 # rows matched by key
    blank: int                   # rows with no editable value
    errors: list[str] = field(default_factory=list)   # per-row, 1-based Excel row numbers
    rows: list[dict] = field(default_factory=list)    # parsed rows (key -> value)


def _style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN
    ws.freeze_panes = "A2"


def build_template(sheets: list[SheetSpec]) -> bytes:
    """Build an .xlsx workbook: Instructions sheet first, then one sheet per spec."""
    wb = Workbook()
    first = True
    for spec in sheets:
        ws = wb.active if first else wb.create_sheet(spec.name)
        first = False
        ws.title = spec.name
        # header row
        for ci, col in enumerate(spec.columns, start=1):
            ws.cell(row=1, column=ci, value=col)
        _style_header(ws, len(spec.columns))
        # data rows
        for ri, row in enumerate(spec.rows, start=2):
            for ci, col in enumerate(spec.columns, start=1):
                cell = ws.cell(row=ri, column=ci, value=row.get(col, ""))
                if col in spec.locked:
                    cell.fill = _LOCKED_FILL
                    cell.font = Font(color="595959")
                cell.border = _THIN
                if col in spec.numeric:
                    cell.data_validation = None  # placeholder; validation added below
        # data validation on numeric columns
        if spec.numeric:
            from openpyxl.worksheet.datavalidation import DataValidation
            dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle="Invalid amount", error="Enter a number >= 0.")
            ws.add_data_validation(dv)
            for col in spec.numeric:
                ci = spec.columns.index(col) + 1
                dv.add(f"{ws.cell(row=1, column=ci).coordinate}2:{ws.cell(row=ri, column=ci).coordinate}")
        widths = [max(len(str(c)), 12) for c in spec.columns]
        for ci, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=ci).column_letter].width = min(w, 46)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _instructions_sheet(lines: list[str]) -> SheetSpec:
    rows = [{"A": ln} for ln in lines]
    return SheetSpec(name="Instructions", columns=["A"], rows=rows)


def build_tds_template(tan: str, effective_date: str, tds_rows: list[dict]) -> bytes:
    """Sheet 'TDS Rates' (locked reference columns, editable rate columns) + Header + Instructions."""
    sheets = [
        SheetSpec(
            name="TDS Rates",
            columns=["section", "section_2025", "discriminator", "reference_rate",
                     "nature_of_income", "rate", "rate_no_pan",
                     "single_bill_threshold", "annual_aggregate_threshold"],
            locked={"section", "section_2025", "discriminator", "reference_rate"},
            numeric={"rate", "rate_no_pan", "single_bill_threshold", "annual_aggregate_threshold"},
            rows=tds_rows,
        ),
        SheetSpec(name="Header", columns=["tan", "effective_date"],
                  rows=[{"tan": tan or "", "effective_date": effective_date or ""}]),
        _instructions_sheet([
            "TDS Rates template (Income-tax Act, 2025 from 1 Apr 2026).",
            "Grey columns are locked: section, section_2025, discriminator, reference_rate.",
            "reference_rate is a hint only - never copied into rate.",
            "Fill rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold as your CA advises.",
            "Leave a rate blank when TDS does not apply to that row.",
            "Max 200 data rows. Amounts are percentages >= 0.",
        ]),
    ]
    return build_template(sheets)


def build_bf_template(fy: int, bf_rows: list[dict]) -> bytes:
    """Sheet 'Brought Forward' + Header + Instructions."""
    sheets = [
        SheetSpec(
            name="Brought Forward",
            columns=["account_id", "tab", "account_name", "side", "bf_amount", "remarks"],
            locked={"account_id", "tab", "account_name", "side"},
            numeric={"bf_amount"},
            rows=bf_rows,
        ),
        SheetSpec(name="Header", columns=["financial_year"],
                  rows=[{"financial_year": fy}]),
        _instructions_sheet([
            "Brought Forward template.",
            "Grey columns are locked: account_id, tab, account_name, side.",
            "Enter bf_amount (>= 0, 2 dp) and optional remarks. Blank amount = 0.",
            "Rows equal the on-screen account list; unknown account ids are rejected.",
            "Apply may be unbalanced - the Review/validator blocks a non-zero difference."]),
    ]
    return build_template(sheets)


def build_receivables_template(rows: list[dict]) -> bytes:
    """Sheet 'Receivables' + Instructions."""
    sheets = [
        SheetSpec(
            name="Receivables",
            columns=["flat_number", "amount", "overdue_days", "remarks"],
            numeric={"amount", "overdue_days"},
            rows=rows,
        ),
        _instructions_sheet([
            "Pending receivables by apartment.",
            "flat_number is required and unique; amount > 0; days overdue >= 0 (blank = unknown).",
            "The sum must tie to the Sundry Debtors accounts entered on the Brought Forward step."]),
    ]
    return build_template(sheets)


def _read_bytes(contents: str) -> bytes:
    if not contents or "," not in contents:
        raise ValueError("No file contents.")
    import base64
    return base64.b64decode(contents.split(",", 1)[1])


def parse_upload(contents: str, filename: str, sheet: str, required: list[str],
                 max_rows: int = MAX_ROWS, max_bytes: int = MAX_BYTES) -> ParseResult:
    """Parse an uploaded .xlsx file. Never partial-applies: errors collected, preview returned."""
    name = (filename or "").lower()
    if not name.endswith(".xlsx"):
        return ParseResult(sheet=sheet, matched=0, blank=0,
                           errors=["Only .xlsx files are accepted (.xls and .csv are not)."])
    try:
        raw = _read_bytes(contents)
    except Exception:
        return ParseResult(sheet=sheet, matched=0, blank=0, errors=["Could not read the uploaded file."])
    if len(raw) > max_bytes:
        return ParseResult(sheet=sheet, matched=0, blank=0,
                           errors=[f"File is {len(raw)//1024} KB; limit is {max_bytes//1024} KB."])
    try:
        xl = pd.ExcelFile(BytesIO(raw), engine="openpyxl")
    except Exception as exc:
        return ParseResult(sheet=sheet, matched=0, blank=0, errors=[f"Could not open the workbook: {exc}"])
    if sheet not in xl.sheet_names:
        return ParseResult(sheet=sheet, matched=0, blank=0,
                           errors=[f"Sheet '{sheet}' not found. Sheets present: {', '.join(xl.sheet_names)}."])
    try:
        df = pd.read_excel(BytesIO(raw), sheet_name=sheet, engine="openpyxl", dtype=str)
    except Exception as exc:
        return ParseResult(sheet=sheet, matched=0, blank=0, errors=[f"Could not read sheet '{sheet}': {exc}"])
    if df.empty:
        return ParseResult(sheet=sheet, matched=0, blank=0, errors=[f"Sheet '{sheet}' has no data rows."])
    if len(df) > max_rows:
        return ParseResult(sheet=sheet, matched=0, blank=0,
                           errors=[f"{len(df)} data rows exceed the {max_rows} row limit."])
    # header match, case-insensitive, extra columns ignored
    lower = {str(c).strip().lower(): c for c in df.columns}
    missing = [r for r in required if r.lower() not in lower]
    if missing:
        return ParseResult(sheet=sheet, matched=0, blank=0,
                           errors=[f"Missing required column(s): {', '.join(missing)}."])
    col = {r: lower[r.lower()] for r in required}

    result = ParseResult(sheet=sheet, matched=0, blank=0)
    for excel_row in range(2, len(df) + 2):   # 1-based Excel row numbers
        vals = {r: df.iloc[excel_row - 2][col[r]] for r in required}
        key = tuple(str(v).strip() for v in vals.values())
        parsed = {r: (str(v).strip() if pd.notna(v) else "") for r, v in vals.items()}
        if not any(parsed.values()):
            continue
        # numeric validation
        for r in ("rate", "rate_no_pan", "single_bill_threshold", "annual_aggregate_threshold", "bf_amount", "amount"):
            if r in parsed and parsed[r]:
                try:
                    d = Decimal(str(parsed[r]))
                    if d < 0:
                        raise InvalidOperation
                    parsed[r] = str(d.quantize(Decimal("0.01")))
                except (InvalidOperation, ValueError):
                    result.errors.append(f"Row {excel_row}: '{r}' must be a number >= 0.")
                    parsed[r] = ""
        if "overdue_days" in parsed and parsed["overdue_days"]:
            try:
                v = int(parsed["overdue_days"])
                if v < 0:
                    raise ValueError
                parsed["overdue_days"] = v
            except ValueError:
                result.errors.append(f"Row {excel_row}: 'overdue_days' must be an integer >= 0.")
                parsed["overdue_days"] = None
        if "tan" in parsed and parsed["tan"]:
            import re
            if not re.fullmatch(r"[A-Z]{4}[0-9]{5}[A-Z]", parsed["tan"]):
                result.errors.append(f"Row {excel_row}: TAN must match ABCD12345E.")
        result.rows.append(parsed)
        result.matched += 1
        if not any(v for k, v in parsed.items() if k not in required or k in ("nature_of_income", "remarks")):
            result.blank += 1
    return result
