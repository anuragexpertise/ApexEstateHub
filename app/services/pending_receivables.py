"""Opening ("pending") receivables by apartment: parsing, validation, merging and tie-out.

Pure functions only (no Dash, no database) so the manual grid, the bulk upload, the wizard validator and
Annex C all apply the same rules.

A row is ``{"flat_number": str, "amount": str(Decimal), "overdue_days": int | None, "remarks": str}``.
"""
from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

FIELDS = ("flat_number", "amount", "overdue_days", "remarks")
SDR_TABS = ("SDr", "SDrCash", "SDrDig")           # Sundry Debtors account tabs the receivables must tie to

MAX_ROWS = 2000
MAX_BYTES = 2 * 1024 * 1024
MAX_AMOUNT = Decimal("9999999999.99")             # NUMERIC(12,2)
MAX_DAYS = 36500
MAX_REMARKS = 200
MAX_FLAT_LEN = 20

# Header spellings accepted in an uploaded file -> canonical column
_ALIASES = {
    "flat_number": {"flat_number", "flat", "flat no", "flat no.", "flat number", "flatno", "apartment",
                    "apartment no", "apartment number", "unit", "unit no"},
    "amount": {"amount", "value receivable", "value receivable (₹)", "value receivable (rs)", "outstanding",
               "due", "dues", "arrears", "balance"},
    "overdue_days": {"overdue_days", "days overdue", "overdue days", "days", "age", "age (days)"},
    "remarks": {"remarks", "remark", "note", "notes", "comment", "comments", "narration"},
}


# ── scalar cleaning ─────────────────────────────────────────────────────────────────────────────────────────
def _blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:           # NaN (what pandas yields for an empty cell)
        return True
    return str(v).strip().lower() in ("", "nan", "none", "null")


def normalise_flat(v) -> str:
    """Trim and collapse internal whitespace; Excel numbers (101 / 101.0) become '101'."""
    if _blank(v):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def flat_key(v) -> str:
    """Identity of a flat for duplicate detection: case-insensitive, ignoring spaces around separators."""
    return re.sub(r"\s*([-/])\s*", r"\1", normalise_flat(v)).upper()


def canonical_flat(v, known=()) -> str:
    """Use the spelling of an already-registered flat when it matches case-insensitively (so 'a-101' links
    to 'A-101'); otherwise just the normalised text."""
    flat = normalise_flat(v)
    k = flat_key(flat)
    for kf in known or ():
        if flat_key(kf) == k:
            return normalise_flat(kf)
    return flat


def parse_amount(v) -> Decimal:
    """'30,000.50', '₹ 30000', 30000, 3e4 -> Decimal. Raises ValueError when not a finite number."""
    if isinstance(v, bool):
        raise ValueError("not a number")
    if isinstance(v, (int, Decimal)):
        d = Decimal(v)
    elif isinstance(v, float):
        d = Decimal(repr(v))
    else:
        s = re.sub(r"[₹\s]|^rs\.?|^inr", "", str(v).strip(), flags=re.I)
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        if "," in s:
            # A comma is only accepted as thousands grouping (1,234,567 or Indian 12,34,567). Anything else,
            # e.g. a decimal comma like "7,5", is rejected rather than silently read as 75.
            whole = s.split(".", 1)[0].lstrip("+-")
            if not (re.fullmatch(r"\d{1,3}(,\d{3})+", whole) or re.fullmatch(r"\d{1,2}(,\d{2})*,\d{3}", whole)):
                raise ValueError("ambiguous comma")
            s = s.replace(",", "")
        try:
            d = Decimal(s)
        except InvalidOperation as exc:
            raise ValueError("not a number") from exc
    if not d.is_finite():
        raise ValueError("not a number")
    return d


def _parse_days(v):
    if _blank(v):
        return None
    try:
        d = parse_amount(v)
    except ValueError as exc:
        raise ValueError("not a whole number") from exc
    if d != d.to_integral_value():
        raise ValueError("not a whole number")
    return int(d)


# ── validation ──────────────────────────────────────────────────────────────────────────────────────────────
def clean_rows(raw_rows, known_flats=(), first_row_number=1):
    """Validate and normalise rows.

    Returns ``(clean, errors)``. Completely blank rows are skipped silently. Every problem names its row
    number (as the user sees it: grid row, or the spreadsheet row when `first_row_number` is 2). Rows with a
    problem are left out of `clean`; a duplicate flat keeps its first occurrence and reports the later ones.
    """
    clean, errors, seen = [], [], {}
    for i, r in enumerate(raw_rows or []):
        n = first_row_number + i
        r = r or {}
        flat_raw, amt_raw, days_raw, rem_raw = (r.get(f) for f in FIELDS)
        if all(_blank(x) for x in (flat_raw, amt_raw, days_raw, rem_raw)):
            continue
        flat = canonical_flat(flat_raw, known_flats)
        row_errors = []
        if not flat:
            row_errors.append("flat number is required")
        elif len(flat) > MAX_FLAT_LEN:
            row_errors.append(f"flat number is longer than {MAX_FLAT_LEN} characters")
        amount = None
        if _blank(amt_raw):
            row_errors.append("amount is required")
        else:
            try:
                amount = parse_amount(amt_raw)
                if amount <= 0:
                    row_errors.append("amount must be greater than 0")
                    amount = None
                elif amount > MAX_AMOUNT:
                    row_errors.append("amount is too large")
                    amount = None
                elif amount != amount.quantize(Decimal("0.01")):
                    row_errors.append("amount can have at most 2 decimal places")
                    amount = None
            except ValueError:
                row_errors.append("amount must be a number")
        days = None
        try:
            days = _parse_days(days_raw)
            if days is not None and not 0 <= days <= MAX_DAYS:
                row_errors.append("days overdue must be between 0 and %d" % MAX_DAYS)
        except ValueError:
            row_errors.append("days overdue must be a whole number")
        if flat and flat_key(flat) in seen:
            row_errors.append(f"flat {flat} is already on row {seen[flat_key(flat)]}")
        if row_errors:
            errors.append(f"Row {n}: " + "; ".join(row_errors) + ".")
            continue
        seen[flat_key(flat)] = n
        remarks = "" if _blank(rem_raw) else re.sub(r"\s+", " ", str(rem_raw)).strip()[:MAX_REMARKS]
        clean.append({"flat_number": flat, "amount": str(amount.quantize(Decimal("0.01"))),
                      "overdue_days": days, "remarks": remarks})
    return clean, errors


def total(rows) -> Decimal:
    t = Decimal(0)
    for r in rows or []:
        try:
            t += parse_amount(r.get("amount")).quantize(Decimal("0.01"))
        except (ValueError, AttributeError):
            continue
    return t


def sdr_total(bf_rows) -> Decimal:
    """Sum of the Dr Sundry-Debtors lines of a Brought Forward row list ({side, tab, bf_amount})."""
    t = Decimal(0)
    for r in bf_rows or []:
        if r.get("side") == "Dr" and r.get("tab") in SDR_TABS:
            try:
                t += parse_amount(r.get("bf_amount"))
            except ValueError:
                continue
    return t


def tie_out(rows, sdr: Decimal):
    """(receivables_total, sundry_debtors_total, difference)."""
    rt = total(rows)
    return rt, sdr, rt - sdr


def validation_errors(rows, sdr: Decimal | None = None, known_flats=()):
    """Everything wrong with a saved receivables list: row problems plus (when `sdr` is given and there are
    receivables) the tie-out. Used by the wizard step validator so Next/Finalize enforce the same rules as
    the grid shows."""
    clean, errors = clean_rows(rows, known_flats)
    if sdr is not None and (clean or errors):
        rt = total(clean)
        if not errors and rt != sdr:
            errors.append(f"Pending receivables (₹{rt:,.2f}) do not tie to Sundry Debtors accounts (₹{sdr:,.2f}).")
    return errors


# ── merging ─────────────────────────────────────────────────────────────────────────────────────────────────
def merge(existing, incoming, mode="add"):
    """Combine rows. mode 'replace' drops what was there; 'add' upserts by flat (an uploaded flat that is
    already in the grid updates that row instead of creating a duplicate).
    Returns ``(rows, added, updated)``."""
    if mode == "replace":
        return list(incoming), len(incoming), 0
    rows = [dict(r) for r in (existing or []) if not all(_blank(r.get(f)) for f in FIELDS)]
    index = {flat_key(r.get("flat_number")): i for i, r in enumerate(rows) if not _blank(r.get("flat_number"))}
    added = updated = 0
    for r in incoming:
        k = flat_key(r["flat_number"])
        if k in index:
            rows[index[k]] = dict(r)
            updated += 1
        else:
            index[k] = len(rows)
            rows.append(dict(r))
            added += 1
    return rows, added, updated


# ── file reading ────────────────────────────────────────────────────────────────────────────────────────────
class UploadError(ValueError):
    """The file cannot be used at all (as opposed to individual bad rows)."""


def _canonical_header(h):
    key = re.sub(r"\s+", " ", str(h or "")).strip().lower()
    for canon, names in _ALIASES.items():
        if key in names:
            return canon
    return None


def _grid_from_xlsx(data: bytes):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:                                    # noqa: BLE001 - any parser failure
        raise UploadError("This is not a valid .xlsx file.") from exc
    names = wb.sheetnames
    ws = wb["Receivables"] if "Receivables" in names else wb[names[0]]
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append(list(row))
        if len(rows) > MAX_ROWS + 50:
            raise UploadError(f"More than {MAX_ROWS} rows; split the file.")
    return rows


def _grid_from_csv(data: bytes):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def parse_upload(data: bytes, filename: str = "", known_flats=()):
    """Read an .xlsx or .csv of receivables.

    Returns ``(clean_rows, errors, info)``; raises UploadError when the file is unusable. `info` carries
    ``rows_read`` and the spreadsheet ``header_row``. Row numbers in errors are spreadsheet rows.
    """
    if not data:
        raise UploadError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadError("The file is larger than 2 MB.")
    name = (filename or "").lower()
    grid = _grid_from_csv(data) if name.endswith(".csv") else _grid_from_xlsx(data)

    header_idx, colmap = None, {}
    for i, row in enumerate(grid[:10]):                         # tolerate a title line above the headers
        m = {}
        for j, cell in enumerate(row):
            canon = _canonical_header(cell)
            if canon and canon not in m:
                m[canon] = j
        if "flat_number" in m and "amount" in m:
            header_idx, colmap = i, m
            break
    if header_idx is None:
        raise UploadError("Could not find the header row. The first row must contain 'flat_number' and 'amount' "
                          "(optionally 'overdue_days' and 'remarks'). Download the template to start from.")

    raw = []
    for row in grid[header_idx + 1:]:
        raw.append({f: (row[colmap[f]] if f in colmap and colmap[f] < len(row) else None) for f in FIELDS})
    if len(raw) > MAX_ROWS:
        raise UploadError(f"More than {MAX_ROWS} rows; split the file.")
    clean, errors = clean_rows(raw, known_flats, first_row_number=header_idx + 2)
    return clean, errors, {"rows_read": sum(1 for r in raw if not all(_blank(v) for v in r.values())),
                           "header_row": header_idx + 1}


def build_template(rows=(), known_flats=()):
    """Template workbook: a 'Receivables' sheet (text-formatted flat column so Excel keeps '101' and '07'),
    plus Instructions and, when flats are already registered, a reference list."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.worksheet.datavalidation import DataValidation
    wb = Workbook()
    ws = wb.active
    ws.title = "Receivables"
    ws.append(list(FIELDS))
    for c in range(1, 5):
        ws.cell(row=1, column=c).font = Font(bold=True)
    for item in rows or []:
        ws.append([normalise_flat(item.get("flat_number")), _num(item.get("amount")),
                   _num(item.get("overdue_days")), "" if _blank(item.get("remarks")) else str(item["remarks"])])
    for r in range(2, MAX_ROWS + 2):
        ws.cell(row=r, column=1).number_format = "@"
        ws.cell(row=r, column=2).number_format = "#,##0.00"
    dv_amt = DataValidation(type="decimal", operator="greaterThan", formula1="0", allow_blank=True)
    dv_amt.add(f"B2:B{MAX_ROWS + 1}")
    ws.add_data_validation(dv_amt)
    dv_days = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
    dv_days.add(f"C2:C{MAX_ROWS + 1}")
    ws.add_data_validation(dv_days)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 40
    ws.freeze_panes = "A2"
    wi = wb.create_sheet("Instructions")
    for line in ("Opening receivables by apartment",
                 "One row per flat. flat_number and amount are required.",
                 "amount: arrears carried forward, greater than 0, at most 2 decimals.",
                 "overdue_days: whole number of days, blank allowed.",
                 "Each flat may appear only once.",
                 "The total must equal the Sundry Debtors balance entered in Brought Forward."):
        wi.append([line])
    wi["A1"].font = Font(bold=True)
    wi.column_dimensions["A"].width = 80
    if known_flats:
        wk = wb.create_sheet("Registered flats")
        wk.append(["flat_number"])
        for f in sorted({normalise_flat(x) for x in known_flats if not _blank(x)}):
            wk.append([f])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _num(v):
    if _blank(v):
        return None
    try:
        d = parse_amount(v)
        return int(d) if d == d.to_integral_value() else float(d)
    except ValueError:
        return str(v)
