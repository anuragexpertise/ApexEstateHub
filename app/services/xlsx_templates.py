"""
Shared xlsx template builder / upload parser for onboarding (items 6, 9, 10).
"""
from __future__ import annotations

import io
from dataclasses import dataclass

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


def build_statement_templates(accounts: list[dict], as_on: str | None) -> bytes:
    """One XLSX with one sheet per bank/deposit/cash account — a single 'Account Statements' file for upload."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Accounts"
    ws.append(["account_id", "account_name", "tab", "as_on_date", "closing_balance"])
    for c in range(1, 6):
        ws.cell(row=1, column=c).font = Font(bold=True)
    for acc in accounts:
        ws.append([acc.get("id"), acc.get("name") or "", acc.get("tab_name") or "", as_on or "YYYY-MM-DD", ""])
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    for r in range(2, len(accounts) + 2):
        for c in (1, 2, 3):
            ws.cell(row=r, column=c).fill = locked_fill
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    dv.add(f"E2:E{len(accounts) + 1}")
    ws.add_data_validation(dv)
    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Fill closing_balance with the balance per the bank / deposit statement or the cash count as on as_on_date, one row per account."])
    wi.append(["as_on_date must be the same As-on date as Brought Forward; a statement as on any other date is rejected."])
    wi.append(["Do not change account_id. Each row maps to its account; upload this single file for all accounts."])
    wi.append(["Each account still needs its own 'Attach scan' evidence in the reconciliation cards."])
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
    dv = DataValidation(type="list", formula1='"{}"'.format(",".join(BYE_LAW_CHOICES)), allow_blank=True)
    dv.add("C2:C%d" % (len(clauses) + 1))  # noqa: UP031
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


def parse_bytes(raw: bytes, filename: str, sheet: str, required: list[str], max_rows: int = 500,
                max_bytes: int = 1_048_576) -> ParseResult:
    """Parse an xlsx from raw bytes. Same contract as parse_upload but takes bytes instead of a data URL."""
    # Basic guards
    if filename and filename.lower().endswith(".xls"):
        return ParseResult(rows=[], errors=["Only .xlsx is accepted (not .xls)."])
    if len(raw) > max_bytes:
        return ParseResult(rows=[], errors=["File exceeds 1 MB."])
    try:
        wb = load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as exc:  # noqa: BLE001
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


def parse_upload(contents: str, filename: str, sheet: str, required: list[str], max_rows: int = 500,
                 max_bytes: int = 1_048_576) -> ParseResult:
    if contents and "," in contents:
        import base64
        b = contents.split(",", 1)[1]
        raw = base64.b64decode(b)
    else:
        raw = b""
    return parse_bytes(raw, filename, sheet, required, max_rows=max_rows, max_bytes=max_bytes)


# ── CA / advocate questionnaire (intake 3) ───────────────────────────────────────
CA_QUESTIONS = [
    ("registration_no", "Society registration number (as on the certificate)", "text", True),
    ("registration_date", "Date of registration (YYYY-MM-DD)", "date", True),
    ("society_pan", "PAN of the society", "text", True),
    ("society_tan", "TAN of the society (leave blank if none)", "text", False),
    ("gst_status", "GST status (registered / not_required / below_threshold)", "choice", True),
    ("gstin", "GSTIN (required only if registered)", "text", False),
    ("tds_applicable", "Is TDS deduction applicable to the society's payments? (yes/no)", "yesno", True),
    ("last_audit_fy", "Financial year of the last audited statements", "text", True),
    ("audit_qualified", "Was the last audit report qualified? (yes/no)", "yesno", True),
    ("audit_qualification", "If qualified, summarise the qualification", "text", False),
    ("litigation_pending", "Any pending litigation or notice against the society? (yes/no)", "yesno", True),
    ("litigation_summary", "If yes, give details", "text", False),
    ("statutory_dues_pending", "Any statutory dues (GST / TDS / income tax) unpaid? (yes/no)", "yesno", True),
    ("reviewer_name", "Name of the CA / advocate giving this review", "text", True),
    ("reviewer_membership", "Membership / enrolment number", "text", True),
    ("review_date", "Date of the review letter (YYYY-MM-DD)", "date", True),
]

CA_SHEET = "CA Questionnaire"


def build_ca_questionnaire_template(prefill: dict | None = None) -> bytes:
    """CA questionnaire xlsx: query column locked/grey, value column fillable. yes/no and GST-status picklists."""
    prefill = prefill or {}
    wb = Workbook()
    ws = wb.active
    ws.title = CA_SHEET
    ws.append(["query", "value"])
    for c in range(1, 3):
        ws.cell(row=1, column=c).font = Font(bold=True)
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    yesno_rows, gst_row = [], None
    for r, (key, query, kind, required) in enumerate(CA_QUESTIONS, start=2):
        ws.cell(row=r, column=1, value=query).protection = Protection(locked=True)
        ws.cell(row=r, column=1).fill = locked_fill
        ws.cell(row=r, column=2, value=str(prefill.get(key) or ""))
        if kind == "yesno":
            yesno_rows.append(r)
        if key == "gst_status":
            gst_row = r
    dv_yesno = DataValidation(type="list", formula1='"yes,no"', allow_blank=True)
    dv_yesno.add(f"B2:B{len(CA_QUESTIONS) + 1}")
    ws.add_data_validation(dv_yesno)
    if gst_row:
        dv_gst = DataValidation(type="list", formula1='"registered,not_required,below_threshold"', allow_blank=True)
        dv_gst.add(f"B{gst_row}")
        ws.add_data_validation(dv_gst)
    ws.freeze_panes = "A2"
    _protect_sheet(ws)

    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Answer every question marked required. Leave conditional questions (GSTIN, audit qualification, litigation summary) blank unless the trigger answer makes them required."])
    wi.append(["yes/no answers must be exactly 'yes' or 'no'. GST status must be one of: registered, not_required, below_threshold."])
    wi.append(["Dates use YYYY-MM-DD. Do not change the query column: it is locked."])
    wi.append(["Upload this workbook together with the CA review letter (PDF). Only .xlsx is accepted."])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Account / label balances (intake 4) ──────────────────────────────────────────
BALANCES_SHEET = "Account Balances"


def build_balances_template(accounts: list[dict], as_on: str | None) -> bytes:
    """Account/label balances xlsx: two sheets (Assets Dr / Liabilities & Equity Cr) plus a Tally sheet.
    Every account with has_bf=True is listed; amounts are filled by the admin or read from the Tally sheet."""
    wb = Workbook()

    dr = [a for a in accounts if a["side"] == "Dr"]
    cr = [a for a in accounts if a["side"] == "Cr"]

    _bf_accounts_sheet(wb, "Assets (Dr)", dr, as_on)
    _bf_accounts_sheet(wb, "Liabilities & Equity (Cr)", cr, as_on)
    _bf_tally_sheet(wb, accounts, as_on)

    wh = wb.create_sheet("Header")
    wh.append(["financial_year", "as_on_date"])
    wh.append(["", as_on or "YYYY-MM-DD"])

    wi = wb.create_sheet("Instructions")
    wi.append(["Notes"])
    wi.append(["Two sections: Assets (Dr) and Liabilities & Equity (Cr). Every account with has_bf = True is listed."])
    wi.append(["The Tally sheet is pre-filled from your Tally/ERP export: read it to fill the grid without typing each account by hand."])
    wi.append(["label = ledger row: an FD number, a bank sub-account, or a flat number for receivables. Several rows per account are allowed; blank rows are ignored."])
    wi.append(["as_on_date must equal the Brought Forward As-on date on every row. Amounts must be 0 or more."])
    wi.append(["Do not change account_id, account_name, tab or side: they are locked. Only .xlsx is accepted."])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _bf_accounts_sheet(wb, title: str, accounts: list[dict], as_on: str | None) -> None:
    """One accounts sheet: locked id/name/tab/side, editable label/as_on_date/amount."""
    ws = wb.active if wb.sheetnames == [] else wb.create_sheet(title)
    if wb.sheetnames == []:
        ws.title = title
    headers = ["account_id", "account_name", "tab", "side", "label", "as_on_date", "amount"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    r = 2
    for acc in accounts:
        ws.cell(row=r, column=1, value=acc["id"]).protection = Protection(locked=True)
        ws.cell(row=r, column=2, value=acc["name"]).protection = Protection(locked=True)
        ws.cell(row=r, column=3, value=acc["tab"]).protection = Protection(locked=True)
        ws.cell(row=r, column=4, value=acc["side"]).protection = Protection(locked=True)
        ws.cell(row=r, column=5, value="")
        ws.cell(row=r, column=6, value=as_on or "YYYY-MM-DD")
        ws.cell(row=r, column=7, value="")
        for c in (1, 2, 3, 4):
            ws.cell(row=r, column=c).fill = locked_fill
        r += 1
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    if r > 2:
        dv.add(f"G2:G{r - 1}")
        ws.add_data_validation(dv)
    ws.freeze_panes = "A2"
    _protect_sheet(ws)


def _bf_tally_sheet(wb, accounts: list[dict], as_on: str | None) -> None:
    """Tally sheet: pre-fillable from the society's Tally/ERP export to fill the grid without typing."""
    ws = wb.create_sheet("Tally")
    headers = ["account_id", "account_name", "tab", "side", "amount"]
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    locked_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
    r = 2
    for acc in accounts:
        ws.cell(row=r, column=1, value=acc["id"]).protection = Protection(locked=True)
        ws.cell(row=r, column=2, value=acc["name"]).protection = Protection(locked=True)
        ws.cell(row=r, column=3, value=acc["tab"]).protection = Protection(locked=True)
        ws.cell(row=r, column=4, value=acc["side"]).protection = Protection(locked=True)
        ws.cell(row=r, column=5, value="")
        for c in (1, 2, 3, 4):
            ws.cell(row=r, column=c).fill = locked_fill
        r += 1
    dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    if r > 2:
        dv.add(f"E2:E{r - 1}")
        ws.add_data_validation(dv)
    ws.freeze_panes = "A2"
    _protect_sheet(ws)
