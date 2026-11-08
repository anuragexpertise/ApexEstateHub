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
        "section","section_2025","discriminator","reference_rate","nature_of_income","effective_start_date","rate","rate_no_pan","single_bill_threshold","annual_aggregate_threshold"
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
        ws.cell(row=r, column=6, value=item.get("effective_start_date") or "")
        ws.cell(row=r, column=7, value=""); ws.cell(row=r, column=8, value=""); ws.cell(row=r, column=9, value=""); ws.cell(row=r, column=10, value="")
        for c in (1, 2, 3, 4):
            ws.cell(row=r, column=c).fill = locked_fill
    dv = DataValidation(type="decimal", operator="between", formula1="0", formula2="100", allow_blank=True)
    dv.add("G2:J500"); ws.add_data_validation(dv)
    ws.freeze_panes = "A2"

    # Header sheet
    wh = wb.create_sheet("Header")
    wh.append(["tan", "effective_date"])
    wh.append(["", "YYYY-MM-DD"])

    # Instructions
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Rates are as signed by the CA and are not marked provisional. Leave a rate blank if TDS does not apply to that row. Upload the CA-signed scan in EstateHub (server SHA-256). effective_start_date (YYYY-MM-DD) gives one row its own effective date; leave it blank to use the Header effective_date."])
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
    wh.append(["financial_year","as_on_date"])
    wh.append([fy or "", "YYYY-MM-DD"])

    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Match on account_id; do not change locked columns. As-on date may be mid-year (not necessarily financial-year start). Attach bank/deposit/cash account statements for the same As-on date."])
    wi.append(["Blank = 0. Amounts must be >= 0."])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ELECTION_COLUMNS = ["office", "flat_number", "name", "email", "mobile", "flat_area_sqft", "resolution_ref"]


def build_election_template(rows: list[dict] | None = None) -> bytes:
    """Election Results.xlsx: one row each for President, Secretary, Treasurer and the Grievance officer."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Election Results"
    ws.append(ELECTION_COLUMNS)
    for c in range(1, len(ELECTION_COLUMNS) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    by_office = {str(r.get("office")): r for r in (rows or [])}
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for i, office in enumerate(("president", "secretary", "treasurer", "grievance_officer"), start=2):
        item = by_office.get(office) or {}
        ws.cell(row=i, column=1, value=office).fill = locked_fill
        for c, h in enumerate(ELECTION_COLUMNS[1:], start=2):
            ws.cell(row=i, column=c, value=item.get(h) or "")
    ws.freeze_panes = "A2"
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Keep the office column as is. President, Secretary and Treasurer need three different flats and three different emails; each needs a mobile and the resolution reference under which they were elected."])
    wi.append(["The grievance_officer row needs only name, email and (optionally) mobile."])
    wi.append(["Passwords, signature images and the signed minutes are not taken from this file: add them on each office card, then print, sign, scan and upload the signed Election Results."])
    wi.append(["Only .xlsx is accepted."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


STATEMENT_COLUMNS = ["account_id", "account_name", "tab", "as_on_date", "closing_balance"]


def build_statement_template(acc: dict, as_on: str | None) -> bytes:
    """Account Statement.xlsx for ONE bank / deposit / cash account. The as_on_date must equal the Brought Forward As-on date."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Header"
    ws.append(STATEMENT_COLUMNS)
    for c in range(1, len(STATEMENT_COLUMNS) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    ws.append([acc.get("id"), acc.get("name") or "", acc.get("tab_name") or "", as_on or "YYYY-MM-DD", ""])
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for c in (1, 2, 3):
        ws.cell(row=2, column=c).fill = locked_fill
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    dv.add("E2:E2")
    ws.add_data_validation(dv)
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Fill closing_balance with the balance per the bank / deposit statement or the cash count as on as_on_date."])
    wi.append(["as_on_date must be the same As-on date as Brought Forward; a statement as on any other date is rejected."])
    wi.append(["Do not change account_id: the file is only accepted for the account it was downloaded for. Only .xlsx is accepted."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BYE_LAW_COLUMNS = ["clause_id", "clause_title", "choice", "variation_text", "note"]
BYE_LAW_CHOICES = ("adopted_as_is", "adopted_with_variation", "not_adopted")


def build_bye_laws_template(clauses, current: dict | None = None, locked=()) -> bytes:
    """Society_bye_laws.xlsx: one row per Model Bye-Law clause (1-58). `clauses` is [(clause_id, title)], `current` maps
    clause_id -> {"choice", "variation_text"} (what is already recorded), `locked` are clauses that cannot be 'not_adopted'."""
    current = current or {}
    locked = set(locked or ())
    wb = Workbook()
    ws = wb.active
    ws.title = "Bye-laws"
    ws.append(BYE_LAW_COLUMNS)
    for c in range(1, len(BYE_LAW_COLUMNS) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    grey = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for r, (cid, title) in enumerate(clauses, start=2):
        cur = current.get(cid) or {}
        ws.cell(row=r, column=1, value=cid).fill = grey
        ws.cell(row=r, column=2, value=title).fill = grey
        ws.cell(row=r, column=3, value=cur.get("choice") or "")
        ws.cell(row=r, column=4, value=cur.get("variation_text") or "")
        ws.cell(row=r, column=5, value="Enforced by the engine: cannot be 'not_adopted'" if cid in locked else "")
    dv = DataValidation(type="list", formula1='"%s"' % ",".join(BYE_LAW_CHOICES), allow_blank=True)
    dv.add("C2:C%d" % (len(clauses) + 1))
    ws.add_data_validation(dv)
    ws.freeze_panes = "A2"
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["choice: adopted_as_is, adopted_with_variation or not_adopted. Leave choice blank to leave that clause as it is."])
    wi.append(["adopted_with_variation needs variation_text. Clauses marked in the note column cannot be not_adopted."])
    wi.append(["The choices stay provisional until the General Body resolution is recorded. Print, sign, scan and upload the signed list in EstateHub."])
    wi.append(["Do not change clause_id. Only .xlsx is accepted."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def validate_bye_law_rows(rows: list[dict], valid_ids, locked=()) -> ParseResult:
    """Validate parsed Society_bye_laws.xlsx rows. Returns the rows to apply ({clause_id, choice, variation_text}) and ALL
    the errors (one list), so the user fixes the file once. Blank choices are skipped (clause left unchanged)."""
    valid = {str(v).upper(): str(v) for v in valid_ids}
    locked = {str(v).upper() for v in (locked or ())}
    out, errors, seen = [], [], set()
    for i, rec in enumerate(rows or [], start=2):
        raw_id = str(rec.get("clause_id") or "").strip().upper()
        choice = str(rec.get("choice") or "").strip().lower().replace(" ", "_").replace("-", "_")
        var = str(rec.get("variation_text") or "").strip()
        if not raw_id and not choice:
            continue
        if raw_id not in valid:
            errors.append(f"Row {i}: unknown clause '{rec.get('clause_id')}'.")
            continue
        if raw_id in seen:
            errors.append(f"Row {i}: clause {raw_id} appears more than once.")
            continue
        seen.add(raw_id)
        if not choice:
            continue
        if choice not in BYE_LAW_CHOICES:
            errors.append(f"Row {i}: {raw_id} choice must be one of {', '.join(BYE_LAW_CHOICES)}.")
            continue
        if choice == "adopted_with_variation" and not var:
            errors.append(f"Row {i}: {raw_id} is adopted_with_variation but variation_text is empty.")
            continue
        if choice == "not_adopted" and raw_id in locked:
            errors.append(f"Row {i}: {raw_id} is enforced by the engine and cannot be not_adopted.")
            continue
        out.append({"clause_id": valid[raw_id], "choice": choice,
                    "variation_text": var if choice == "adopted_with_variation" else ""})
    return ParseResult(rows=out, errors=errors)


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
