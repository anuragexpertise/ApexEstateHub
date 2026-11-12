# app/services/undivided_declaration.py
"""
Builder's Declaration of undivided interest (Stage 5, Enrollment).

Votes at a General Body meeting are weighted by each flat's undivided interest (Act s.12(1)(f), bye-laws 2(e) and 8),
and the Declaration the builder filed is the authority for those shares. This module takes the Declaration in three
parts, all in one step:

  1. a template the admin downloads ("Declaration - Undivided-Interest.xlsx": Flat No, Area, Undivided-Interest),
     pre-filled with any flats already enrolled;
  2. the filled workbook, which is validated (every flat once, every share > 0, shares total 100%, area whole sq ft)
     and then written to the flats: existing flats are updated, flats not yet enrolled are created as bare flats
     (no login yet) so that the Apartments bulk upload can fill in the owners' details afterwards;
  3. the builder's signed Declaration as a PDF, stored as onboarding evidence with its SHA-256 (the server computes it;
     nobody types a hash).

Nothing is written unless the whole file is valid. The apartments trigger trg_apartment_uip_basis marks the society's
basis as 'declaration', after which fn_fill_undivided_interest_after_enrolment never overwrites the figures.

Enrollment cannot be marked complete until the shares are complete and total 100% and the Declaration is on file
(blockers()). A society with no builder's Declaration can proceed only with a stated, audited reason.
"""
from __future__ import annotations

import io
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from app.services import onboarding_service as ob
from database.db_manager import db

log = logging.getLogger(__name__)

PURPOSE = "declaration_undivided_interest"   # shared with the Part A print; the builder's Declaration rows carry meta.xlsx_sha256
TEMPLATE_FILENAME = "Declaration - Undivided-Interest.xlsx"
HEADERS = ("Flat No", "Area", "Undivided-Interest")
MAX_ROWS = 500
MAX_XLSX_BYTES = 5 * 1024 * 1024
TOLERANCE = Decimal("0.001")          # the same tolerance as fn_undivided_interest_summary
SIX_DP = Decimal("0.000001")          # apartments.undivided_interest_pct is NUMERIC(9,6)
WAIVER_MIN_CHARS = 10

_ALIASES = {
    "flat": {"flatno", "flatnumber", "flat", "flatno.", "apartment", "apartmentno", "unit", "unitno"},
    "area": {"area", "areasqft", "areainsqft", "areasqfeet", "apartmentsize", "size", "carpetarea", "superarea"},
    "pct": {"undividedinterest", "undividedinterestpct", "undividedinterest%", "undividedshare", "share", "pct",
            "undivideinterest", "undividedinterestpercentage"},
}


def _rows(sql, params=None):
    return db._execute(sql, params, fetch_all=True) or []


def _row(sql, params=None):
    return db._execute(sql, params, fetch_one=True)


def flat_key(v) -> str:
    """Flat numbers compared ignoring case, spaces and hyphens (the same rule the receivable linker uses)."""
    return re.sub(r"[\s\-]", "", str(v or "").strip().lower())


def _clean_flat(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _header_map(cells) -> dict:
    found = {}
    for idx, c in enumerate(cells):
        key = re.sub(r"[^a-z0-9%.]", "", str(c or "").strip().lower())
        for field, names in _ALIASES.items():
            if key in names and field not in found:
                found[field] = idx
    return found


# ── template ─────────────────────────────────────────────────────────────────────────────────────────────────────
def template_bytes(society_id: int) -> bytes:
    """The Declaration workbook. Flats already enrolled are listed with their area (and their share only when it came
    from the Declaration itself, never when it was derived from area)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    soc = _row("SELECT name, undivided_interest_basis AS basis FROM societies WHERE id=%s", (society_id,)) or {}
    flats = _rows("SELECT flat_number, apartment_size, undivided_interest_pct FROM apartments "
                  "WHERE society_id=%s AND active ORDER BY flat_number", (society_id,))
    wb = Workbook()
    ws = wb.active
    ws.title = "Declaration"
    ws.append(list(HEADERS))
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E79")
        c.alignment = Alignment(horizontal="center")
    from_decl = soc.get("basis") == "declaration"
    for f in flats:
        ws.append([f["flat_number"], f["apartment_size"] or None,
                   float(f["undivided_interest_pct"]) if from_decl and f["undivided_interest_pct"] is not None else None])
    last = MAX_ROWS + 1
    for col, fmt in (("A", "@"), ("B", "0"), ("C", "0.000000")):
        for r in range(2, last + 1):
            ws[f"{col}{r}"].number_format = fmt
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 22
    dv_area = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                             errorTitle="Area", error="Enter the area in square feet as a number.")
    dv_pct = DataValidation(type="decimal", operator="between", formula1="0", formula2="100", allow_blank=True,
                            errorTitle="Undivided-Interest", error="Enter the share as a percentage between 0 and 100 (for example 1.25).")
    ws.add_data_validation(dv_area)
    ws.add_data_validation(dv_pct)
    dv_area.add(f"B2:B{last}")
    dv_pct.add(f"C2:C{last}")
    ws.freeze_panes = "A2"

    wi = wb.create_sheet("Instructions")
    lines = [
        (f"Declaration of undivided interest: {soc.get('name') or 'society'}", True),
        ("Copy the figures from the Declaration the builder filed under the Apartment Act. Do not estimate them.", False),
        ("", False),
        ("Flat No: the flat's number exactly as the society will use it (one row per flat, no repeats).", False),
        ("Area: the flat's area in square feet, a whole number (a fraction is rounded to the nearest foot).", False),
        ("Undivided-Interest: the flat's share as a percentage, for example 1.25 for 1.25%. Up to 6 decimal places.", False),
        ("The shares must total 100%. Every flat in the building must be listed, including flats not yet enrolled.", False),
        ("", False),
        ("Upload this workbook (.xlsx) together with the builder's signed Declaration as a PDF.", False),
        ("The PDF is kept as evidence with its SHA-256. Nothing is saved unless every row is valid.", False),
        ("", False),
        ("Running total of the Undivided-Interest column (must read 100):", True),
    ]
    for text, bold in lines:
        wi.append([text])
        if bold:
            wi.cell(row=wi.max_row, column=1).font = Font(bold=True)
    wi.append([f"=SUM(Declaration!C2:C{last})"])
    wi.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── parse ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _to_decimal(v, percent_formatted: bool = False):
    """A cell as a Decimal percentage/area, or None when blank; raises ValueError when it is not a number."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        raise ValueError("not a number")  # noqa: TRY004
    if isinstance(v, (int, float, Decimal)):
        d = Decimal(str(v))
        return d * 100 if percent_formatted else d
    s = str(v).strip().replace(",", "")
    pct_sign = s.endswith("%")
    if pct_sign:
        s = s[:-1].strip()
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ValueError("not a number") from None


def parse_workbook(data: bytes) -> tuple[list[dict], list[str]]:
    """Read the Declaration workbook. Returns (rows, errors); rows are only trustworthy when errors is empty."""
    from openpyxl import load_workbook

    errors: list[str] = []
    if not data or len(data) > MAX_XLSX_BYTES:
        return [], ["The Excel file must be between 1 byte and 5 MB."]
    if not data.startswith(b"PK"):
        return [], ["That is not an .xlsx workbook. If you have an older .xls file, open it in Excel and Save As .xlsx."]
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    except Exception:                                                  # noqa: BLE001
        return [], ["The Excel file could not be read. Re-save it as .xlsx and try again."]
    ws = wb["Declaration"] if "Declaration" in wb.sheetnames else wb.worksheets[0]
    allrows = list(ws.iter_rows(min_row=1))
    if not allrows:
        return [], ["The workbook is empty."]
    hdr = _header_map([c.value for c in allrows[0]])
    missing = [name for key, name in (("flat", HEADERS[0]), ("area", HEADERS[1]), ("pct", HEADERS[2])) if key not in hdr]
    if missing:
        return [], ["Row 1 must hold the column headings: " + ", ".join(HEADERS) + ". Missing: " + ", ".join(missing) + "."]

    parsed: list[dict] = []
    seen: dict[str, int] = {}
    for r_idx, cells in enumerate(allrows[1:], start=2):
        flat_c, area_c, pct_c = (cells[hdr[k]] if hdr[k] < len(cells) else None for k in ("flat", "area", "pct"))
        flat_v, area_v, pct_v = (c.value if c is not None else None for c in (flat_c, area_c, pct_c))
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in (flat_v, area_v, pct_v)):
            continue
        if len(parsed) >= MAX_ROWS:
            errors.append(f"More than {MAX_ROWS} flats. Split the building or contact support.")
            break
        flat = _clean_flat(flat_v)
        if not flat:
            errors.append(f"Row {r_idx}: Flat No is blank.")
            continue
        if len(flat) > 20:
            errors.append(f"Row {r_idx}: Flat No «{flat[:25]}…» is longer than 20 characters.")
            continue
        k = flat_key(flat)
        if k in seen:
            errors.append(f"Row {r_idx}: flat {flat} repeats row {seen[k]}.")
            continue
        seen[k] = r_idx
        try:
            area = _to_decimal(area_v)
        except ValueError:
            errors.append(f"Row {r_idx} (flat {flat}): Area is not a number.")
            continue
        if area is None or area <= 0:
            errors.append(f"Row {r_idx} (flat {flat}): Area must be greater than zero.")
            continue
        pct_fmt = bool(pct_c is not None and "%" in str(getattr(pct_c, "number_format", "") or ""))
        try:
            pct = _to_decimal(pct_v, percent_formatted=pct_fmt)
        except ValueError:
            errors.append(f"Row {r_idx} (flat {flat}): Undivided-Interest is not a number.")
            continue
        if pct is None:
            errors.append(f"Row {r_idx} (flat {flat}): Undivided-Interest is blank.")
            continue
        if pct <= 0 or pct > 100:
            errors.append(f"Row {r_idx} (flat {flat}): Undivided-Interest must be above 0 and at most 100 (got {pct.normalize():f}).")
            continue
        if pct.quantize(SIX_DP) != pct:
            errors.append(f"Row {r_idx} (flat {flat}): Undivided-Interest has more than 6 decimal places.")
            continue
        area_i = int(area.to_integral_value(rounding="ROUND_HALF_UP"))
        parsed.append({"row": r_idx, "flat": flat, "area": area_i, "area_rounded": area != area_i,
                       "pct": pct.quantize(SIX_DP)})
    if not parsed and not errors:
        errors.append("The workbook has no flats. Fill one row per flat under the headings.")
    return parsed, errors


# ── validate against the society ─────────────────────────────────────────────────────────────────────────────────
def plan(society_id: int, rows: list[dict]) -> tuple[dict, list[str]]:
    """Compare the parsed rows with the society's flats. Returns (plan, errors); nothing is written."""
    errors: list[str] = []
    total = sum((r["pct"] for r in rows), Decimal(0))
    if abs(total - 100) > TOLERANCE:
        diff = total - 100
        hint = ""
        if rows and all(r["pct"] <= 1 for r in rows) and abs(total - 1) <= Decimal("0.01"):
            hint = " The figures look like fractions of 1; enter percentages (1.25, not 0.0125)."
        errors.append(f"The shares total {total.normalize():f}%, which is {abs(diff).normalize():f} "
                      f"{'over' if diff > 0 else 'short of'} 100%.{hint}")
    existing = {flat_key(a["flat_number"]): a for a in _rows(
        "SELECT id, flat_number, active FROM apartments WHERE society_id=%s", (society_id,))}
    in_file = {flat_key(r["flat"]) for r in rows}
    update, create = [], []
    for r in rows:
        a = existing.get(flat_key(r["flat"]))
        if a is None:
            create.append(r)
        elif not a["active"]:
            errors.append(f"Row {r['row']}: flat {r['flat']} exists in the society but is inactive. Reactivate it first.")
        else:
            update.append({**r, "id": a["id"], "flat": a["flat_number"]})
    not_listed = sorted(a["flat_number"] for k, a in existing.items() if a["active"] and k not in in_file)
    if not_listed:
        shown = ", ".join(not_listed[:15]) + (" …" if len(not_listed) > 15 else "")
        errors.append(f"{len(not_listed)} enrolled flat(s) are missing from the file: {shown}. Every flat needs a share.")
    if create:
        from app.services.plan_limits import remaining_apartment_slots
        left, plan_name, limit = remaining_apartment_slots(society_id)
        if len(create) > left:
            errors.append(f"The «{plan_name}» plan allows {limit} apartments; this file adds {len(create)} but only {left} slot(s) are left.")
    passed = _row("""SELECT COUNT(*) AS n FROM resolutions r JOIN meetings m ON m.id = r.meeting_id
                      WHERE m.society_id=%s AND r.status='passed'""", (society_id,)) or {}
    if int(passed.get("n") or 0):
        errors.append("A resolution has already been passed using the current shares, so they cannot be replaced here. "
                      "Record a corrective decision with the society's advocate instead.")
    return {"total": total, "update": update, "create": create,
            "area_total": sum(r["area"] for r in rows),
            "rounded": sum(1 for r in rows if r["area_rounded"])}, errors


def _validate_pdf(pdf_name: str, pdf: bytes) -> bytes:
    if not (pdf_name or "").lower().endswith(".pdf"):
        raise ob.OnboardingError("Attach the builder's Declaration as a PDF file.")
    if not pdf or len(pdf) > ob.EVIDENCE_MAX_BYTES:
        raise ob.OnboardingError("The PDF must be between 1 byte and 5 MB.")
    if not pdf.startswith(b"%PDF-"):
        raise ob.OnboardingError("The file does not look like a real PDF.")
    return pdf


# ── apply ────────────────────────────────────────────────────────────────────────────────────────────────────────
def apply(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes, pdf_name: str, pdf: bytes) -> str:
    """Validate everything, then write flats and evidence in ONE transaction. Raises OnboardingError on any problem,
    leaving the society untouched."""
    if ob.state_of(society_id) != "active":
        raise ob.OnboardingError("The Declaration is entered after the Agreement is sealed, in Enrollment.")
    pdf = _validate_pdf(pdf_name, pdf)
    rows, errs = parse_workbook(xlsx)
    if errs:
        raise ob.OnboardingError(_join(errs))
    pl, errs = plan(society_id, rows)
    if errs:
        raise ob.OnboardingError(_join(errs))

    digest = ob._sha(pdf)
    xlsx_digest = ob._sha(xlsx)
    stored = f"{digest}.pdf"
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import ASSETS_ROOT
        folder = ASSETS_ROOT / str(society_id) / "evidence"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / stored).write_bytes(pdf)
    except Exception:
        log.exception("could not keep the Declaration PDF for society %s", society_id)
    meta = {"xlsx_name": (xlsx_name or "")[:200], "xlsx_sha256": xlsx_digest, "flats": len(rows),
            "created": len(pl["create"]), "updated": len(pl["update"]), "total_pct": f"{pl['total']:f}",
            "area_total": pl["area_total"], "areas_rounded": pl["rounded"]}
    with db._conn() as conn:                    # one transaction: commits on exit, rolls back on any error
        cur = conn.cursor()
        for r in pl["update"]:
            cur.execute("UPDATE apartments SET apartment_size=%s, undivided_interest_pct=%s, updated_at=NOW() "
                        "WHERE id=%s AND society_id=%s", (r["area"], r["pct"], r["id"], society_id))
        for r in pl["create"]:
            cur.execute("INSERT INTO apartments (society_id, flat_number, apartment_size, undivided_interest_pct, active) "
                        "VALUES (%s,%s,%s,%s,TRUE)", (society_id, r["flat"], r["area"], r["pct"]))
        # The trigger only fires on a changed value; say so explicitly so identical figures still lock the basis.
        cur.execute("UPDATE societies SET undivided_interest_basis='declaration' WHERE id=%s", (society_id,))
        cur.execute("""INSERT INTO onboarding_evidence (society_id, purpose, acc_id, filename, stored_name, sha256,
                                                        size_bytes, meta, uploaded_by)
                       VALUES (%s,%s,NULL,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (society_id, PURPOSE, pdf_name[:200], stored, digest, len(pdf), json.dumps(meta), actor_id))
    ob._audit(society_id, actor_id, "UNDIVIDED_DECLARATION_APPLIED", "society", society_id,
              {"pdf_sha256": digest, **meta})
    try:
        ob.relink_pending_for_existing_flats(society_id)   # newly declared flats may already carry opening receivables
    except Exception:
        log.exception("could not link opening receivables after the Declaration for society %s", society_id)
    note = f" {pl['rounded']} area(s) were rounded to whole sq ft." if pl["rounded"] else ""
    return (f"Declaration applied: {len(rows)} flats ({len(pl['create'])} new, {len(pl['update'])} updated), "
            f"total {pl['total']:f}%. PDF SHA-256 {digest[:16]}….{note} "
            + (f"Next: fill the owners' details with the Apartments bulk upload for {len(pl['create'])} new flat(s)."
               if pl["create"] else ""))


def _join(errs: list[str], limit: int = 12) -> str:
    shown = errs[:limit]
    more = f" (+{len(errs) - limit} more)" if len(errs) > limit else ""
    return "Nothing was saved. " + " ".join(shown) + more


# ── status and the completion check ──────────────────────────────────────────────────────────────────────────────
def latest_evidence(society_id: int) -> dict | None:
    r = _row("""SELECT id, filename, stored_name, sha256, size_bytes, meta, uploaded_at FROM onboarding_evidence
                 WHERE society_id=%s AND purpose=%s AND meta ->> 'xlsx_sha256' IS NOT NULL
                 ORDER BY uploaded_at DESC, id DESC LIMIT 1""", (society_id, PURPOSE))
    return dict(r) if r else None


def billing_waits(society_id: int) -> bool:
    """True while bills by undivided interest are on hold for want of the builder's Declaration (see
    fn_billing_waits_for_declaration). False once the Declaration is on file or Enrollment is complete."""
    try:
        r = _row("SELECT fn_billing_waits_for_declaration(%s) AS w", (society_id,))
    except Exception:
        log.exception("could not read the billing hold for society %s", society_id)
        return False
    return bool((r or {}).get("w"))


def declared_unenrolled(society_id: int) -> list[dict]:
    """Flats that exist (from the Declaration) but have no owner login yet."""
    return _rows("""SELECT a.id, a.flat_number, a.apartment_size, a.undivided_interest_pct
                      FROM apartments a
                     WHERE a.society_id=%s AND a.active
                       AND NOT EXISTS (SELECT 1 FROM users u WHERE u.society_id=a.society_id AND u.role='apartment'
                                        AND u.linked_id=a.id)
                     ORDER BY a.flat_number""", (society_id,))


def status(society_id: int) -> dict:
    s = _row("SELECT * FROM fn_undivided_interest_summary(%s)", (society_id,)) or {}
    b = _row("SELECT undivided_interest_basis AS basis FROM societies WHERE id=%s", (society_id,)) or {}
    return {"basis": b.get("basis"), "flats": int(s.get("apartments_total") or 0),
            "missing": int(s.get("apartments_missing") or 0),
            "total_pct": Decimal(str(s.get("total_declared_pct") or 0)),
            "balanced": bool(s.get("balanced")), "evidence": latest_evidence(society_id),
            "unenrolled": len(declared_unenrolled(society_id))}


def blockers(society_id: int, waiver_reason: str | None = None) -> list[str]:
    """Why Enrollment cannot be marked complete as far as the shares go. Empty when it can."""
    s = _row("SELECT * FROM fn_undivided_interest_summary(%s)", (society_id,))
    if not s:
        return []
    out = []
    waiver = (waiver_reason or "").strip()
    if not latest_evidence(society_id) and len(waiver) < WAIVER_MIN_CHARS:
        out.append("The builder's Declaration of undivided interest is not on file. Upload it (workbook and signed PDF), "
                   f"or, if the building has none, tick that box and give a reason of {WAIVER_MIN_CHARS} characters or more.")
    if int(s.get("apartments_missing") or 0) or not s.get("balanced"):
        out.append(f"The flats' undivided-interest shares total {Decimal(str(s.get('total_declared_pct') or 0)).normalize():f}% "
                   f"with {int(s.get('apartments_missing') or 0)} flat(s) missing a share. Every flat needs a share and they must total 100%.")
    return out
