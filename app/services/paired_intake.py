# app/services/paired_intake.py
"""
Shared logic for the five paired intakes (NEMOTRON_PLAN_five_intakes.md, section 5).

Each intake pairs a fillable xlsx with the signed PDF it was typed from. The PDF is a
normal onboarding_evidence row; the xlsx is kept next to it as <xlsx_sha256>.xlsx in the
same evidence folder (xlsx is not an allowed evidence type). The PDF row's meta records
the pairing and a default pending-verification note.

undivided_declaration imports this module lazily (inside functions) to avoid a circular
import; this module imports onboarding_service at module top only.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from decimal import Decimal

from openpyxl import load_workbook

from app.services import onboarding_service as ob
from app.services import pending_receivables as pr
from app.services import xlsx_templates as xt
from app.utils.fiscal import fy_start_year

log = logging.getLogger(__name__)

XLSX_MAGIC = b"PK\x03\x04"
XLSX_MAX_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Intake:
    key: str            # "declaration" | "election" | "ca_review" | "balances"
    label: str          # shown to the admin
    purpose: str        # onboarding_evidence.purpose
    pdf_label: str      # "Builder's Declaration (as submitted to the Registrar)" etc.
    xlsx_filename: str  # download name
    stage: str          # "apartment_charges" | "committee" | "brought_forward"


INTAKES = {
    "declaration": Intake(key="declaration", label="Builder's Declaration",
                          purpose="declaration_undivided_interest",
                          pdf_label="Builder's Declaration (as submitted to the Registrar)",
                          xlsx_filename="Declaration - Undivided-Interest.xlsx",
                          stage="apartment_charges"),
    "election": Intake(key="election", label="Election Results",
                       purpose="election_results", pdf_label="Signed election minutes",
                       xlsx_filename="Election Results.xlsx", stage="committee"),
    "ca_review": Intake(key="ca_review", label="CA / advocate questionnaire",
                        purpose="review_letter", pdf_label="CA review letter",
                        xlsx_filename="CA Questionnaire.xlsx", stage="committee"),
    "balances": Intake(key="balances", label="Account / label balances",
                       purpose="account_statement", pdf_label="Account statement",
                       xlsx_filename="Statement.xlsx", stage="brought_forward"),
    "pending_receivables": Intake(key="pending_receivables", label="Pending Receivables",
                                  purpose="pending_receivables", pdf_label="Arrears statement",
                                  xlsx_filename="Pending Receivables.xlsx", stage="brought_forward"),
}


def check_xlsx(name: str, data: bytes) -> None:
    """Validate an uploaded workbook (type, size, magic bytes). Writes nothing."""
    if not (name or "").lower().endswith(".xlsx"):
        raise ob.OnboardingError("Attach the workbook as an .xlsx file.")
    if not data or len(data) > XLSX_MAX_BYTES:
        raise ob.OnboardingError("The workbook must be between 1 byte and 5 MB.")
    if not data.startswith(XLSX_MAGIC):
        raise ob.OnboardingError("That is not a real .xlsx workbook. Re-save it as .xlsx and try again.")


def keep_xlsx(society_id: int, data: bytes) -> str:
    """Write <sha>.xlsx into the society's evidence folder, read back and compare the hash."""
    xsha = ob._sha(data)
    stored = f"{xsha}.xlsx"
    folder = ob.evidence_folder(society_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / stored
    try:
        if not path.is_file() or ob._sha(path.read_bytes()) != xsha:
            path.write_bytes(data)
        if ob._sha(path.read_bytes()) != xsha:
            raise OSError("read-back hash mismatch")
    except Exception:
        log.exception("could not keep the workbook for society %s", society_id)
        raise ob.OnboardingError("The workbook could not be stored safely. Please upload it again; if it keeps failing, "
                                 "contact the platform operator.")
    return stored


def verification_note(xlsx_name: str, xlsx_sha: str, pdf_label: str) -> str:
    """Default pending-verification note written on every pair row."""
    return (f"Manual verification pending: compare the figures in workbook '{xlsx_name}' "
            f"(SHA-256 {xlsx_sha}) with this {pdf_label} before marking it verified.")


def file_pair(society_id: int, actor_id: int, key: str, xlsx_name: str, xlsx: bytes,
              pdf_name: str, pdf: bytes, summary: dict) -> dict:
    """File an xlsx + PDF pair as one evidence row; dedupe on purpose + PDF SHA + xlsx SHA."""
    spec = INTAKES[key]
    check_xlsx(xlsx_name, xlsx)
    xsha = ob._sha(xlsx)
    psha = ob._sha(pdf)
    row = ob._row("""SELECT id, sha256 FROM onboarding_evidence
                      WHERE society_id=%s AND purpose=%s AND sha256=%s AND meta ->> 'xlsx_sha256' = %s""",
                  (society_id, spec.purpose, psha, xsha))
    if row:
        return {"id": row["id"], "sha256": row["sha256"], "duplicate": True}
    stored_x = keep_xlsx(society_id, xlsx)
    meta = {"pair_key": key, "xlsx_name": (xlsx_name or "")[:200], "xlsx_sha256": xsha,
            "xlsx_stored": stored_x, "kind": spec.purpose, **summary}
    ev = ob.store_evidence_file(society_id, spec.purpose, None, pdf_name, pdf, actor_id, meta)
    ob.db._execute("UPDATE onboarding_evidence SET verification_note=%s WHERE id=%s AND society_id=%s",
                   (verification_note(xlsx_name, xsha, spec.pdf_label), ev["id"], society_id))
    ob._audit(society_id, actor_id, "INTAKE_FILED", "onboarding_evidence", ev["id"],
              {"key": key, "pdf_sha256": psha, "xlsx_sha256": xsha, **summary})
    return {**ev, "xlsx_sha256": xsha, "duplicate": False}


def file_document(society_id: int, actor_id: int, doc_name: str, pdf_name: str, pdf: bytes) -> dict:
    """Intake 5: file any named PDF as other_paper_evidence (no xlsx, no verification note)."""
    doc_name = (doc_name or "").strip()
    if not (3 <= len(doc_name) <= 120):
        raise ob.OnboardingError("Give the document a name (3 to 120 characters).")
    if any(ord(ch) < 32 for ch in doc_name):
        raise ob.OnboardingError("The document name must not contain control characters.")
    if not (pdf_name or "").lower().endswith(".pdf"):
        raise ob.OnboardingError("Attach the document as a PDF file.")
    psha = ob._sha(pdf)
    row = ob._row("""SELECT id, sha256 FROM onboarding_evidence
                      WHERE society_id=%s AND purpose=%s AND sha256=%s AND meta ->> 'doc_name' = %s""",
                  (society_id, "other_paper_evidence", psha, doc_name))
    if row:
        return {"id": row["id"], "sha256": row["sha256"], "duplicate": True}
    meta = {"kind": "other_document", "doc_name": doc_name}
    ev = ob.store_evidence_file(society_id, "other_paper_evidence", None, pdf_name, pdf, actor_id, meta)
    ob._audit(society_id, actor_id, "DOCUMENT_FILED", "onboarding_evidence", ev["id"],
              {"doc_name": doc_name, "pdf_sha256": psha})
    return {**ev, "duplicate": False}


def latest_pair(society_id: int, key: str) -> dict | None:
    """Newest evidence row for a purpose whose meta.pair_key = key."""
    spec = INTAKES[key]
    rows = ob.get_evidence(society_id, spec.purpose) or []
    for r in rows:
        if (r.get("meta") or {}).get("pair_key") == key:
            return r
    return None


def registration_certificate(society_id: int) -> dict | None:
    """Newest registration_certificate evidence row (the master's upload at registration)."""
    rows = ob.get_evidence(society_id, "registration_certificate") or []
    return rows[0] if rows else None


# ── Intake 2: election ─────────────────────────────────────────────────────────

def file_election_pair(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                       minutes_name: str, minutes: bytes) -> dict:
    """File the Election Results workbook + signed minutes as an election pair."""
    res = xt.parse_bytes(xlsx, xlsx_name or "", "Election Results", ["office"])
    if res.errors:
        raise ob.OnboardingError(" ".join(res.errors))
    return file_pair(society_id, actor_id, "election", xlsx_name or "", xlsx,
                     minutes_name or "", minutes, {"offices": len(res.rows)})


# ── Intake 3: CA / advocate questionnaire ──────────────────────────────────────

def check_ca_rows(rows: list[dict]) -> tuple[dict, list[str]]:
    """Pure validation of parsed CA questionnaire rows. Returns (answers, all errors)."""
    answers: dict = {}
    errors: list[str] = []
    seen: set = set()
    by_query = {q.strip(): (key, kind, required) for key, q, kind, required in xt.CA_QUESTIONS}
    for i, r in enumerate(rows or [], start=2):
        query = str(r.get("query") or "").strip()
        value = r.get("value")
        if query not in by_query:
            errors.append(f"Row {i}: unknown question '{query}'.")
            continue
        key, kind, required = by_query[query]
        if key in seen:
            errors.append(f"Row {i}: '{query}' is already answered.")
            continue
        seen.add(key)
        blank = value is None or str(value).strip() == ""
        if required and blank:
            errors.append(f"Row {i}: '{query}' is required.")
            continue
        if blank:
            continue
        v = str(value).strip()
        if kind == "yesno":
            if v.lower() not in ("yes", "no"):
                errors.append(f"Row {i}: '{query}' must be yes or no.")
            else:
                answers[key] = v.lower()
        elif kind == "choice":
            if v not in ("registered", "not_required", "below_threshold"):
                errors.append(f"Row {i}: '{query}' must be one of registered, not_required, below_threshold.")
            else:
                answers[key] = v
        elif kind == "date":
            try:
                ob._iso_day(v)
            except ValueError:
                errors.append(f"Row {i}: '{query}' must be a date (YYYY-MM-DD).")
            else:
                answers[key] = v
        else:
            answers[key] = v
    if answers.get("gst_status") == "registered" and not answers.get("gstin"):
        errors.append("GSTIN is required when GST status is registered.")
    if answers.get("audit_qualified") == "yes" and not answers.get("audit_qualification"):
        errors.append("Audit qualification is required when the last audit was qualified.")
    if answers.get("litigation_pending") == "yes" and not answers.get("litigation_summary"):
        errors.append("Litigation summary is required when litigation is pending.")
    return answers, errors


def apply_ca_review(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                    pdf_name: str, pdf: bytes) -> str:
    """File the CA questionnaire workbook with the CA review letter."""
    res = xt.parse_bytes(xlsx, xlsx_name or "", xt.CA_SHEET, ["query", "value"])
    if res.errors:
        raise ob.OnboardingError(" ".join(res.errors))
    answers, errors = check_ca_rows(res.rows)
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    filed = file_pair(society_id, actor_id, "ca_review", xlsx_name or "", xlsx,
                      pdf_name or "", pdf, {"answers": answers})
    psha = ob._sha(pdf)
    msg = f"CA review filed: {len(answers)} answer(s), PDF SHA-256 {psha[:16]}…."
    if filed.get("duplicate"):
        msg = "Duplicate (already on file): " + msg
    return msg


def latest_ca_answers(society_id: int) -> dict:
    """Answers from the newest filed CA review pair, or {}."""
    row = latest_pair(society_id, "ca_review")
    return (row.get("meta") or {}).get("answers", {}) if row else {}


# ── Intake 4: account / label balances ─────────────────────────────────────────

def eligible_accounts() -> list[dict]:
    """Every account that carries a brought-forward flag (has_bf = True), in bf_layout order (Cr then Dr).

    The name is the display name (ACC[3]) used in the grid and the statement template.
    """
    from app.services import bf_layout as bl
    from database.seed import ACCOUNTS

    ids = bl.ordered_account_ids(lambda acc_id: False)
    by_id = {a[0]: a for a in ACCOUNTS}
    out = []
    for aid in ids:
        a = by_id[aid]
        out.append({"id": a[0], "name": a[3] or f"Account {a[0]}", "tab": a[2], "side": a[5]})
    return out


def read_statement_rows(xlsx_bytes: bytes, fy: int, as_on: str | None = None) -> tuple[list[dict], list[str]]:
    """Parse the single Statement sheet named ``str(fy)`` (or the only sheet).

    Returns (rows, all errors). Nothing is applied on error. Validation:
    account_id must be a visible has_bf account; side and account_tab must match the master;
    amount >= 0; label required for deposits (tab Dp), blank for Sundry Debtors tabs;
    as_on_date valid YYYY-MM-DD and equal to the wizard As-on date; no duplicate (account_id, label).
    """
    errors: list[str] = []
    if as_on is None:
        errors.append("Set the As-on date for Brought Forward first.")
    if len(xlsx_bytes) > XLSX_MAX_BYTES:
        errors.append("File exceeds 5 MB.")
    if not xlsx_bytes.startswith(XLSX_MAGIC):
        errors.append("That is not a real .xlsx workbook.")
    if errors:
        return [], errors
    try:
        wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    except Exception as exc:  # noqa: BLE001
        return [], [f"Could not open xlsx: {exc}"]
    sheet = str(fy)
    if sheet not in wb.sheetnames:
        if len(wb.sheetnames) == 1:
            sheet = wb.sheetnames[0]
        else:
            return [], [f"Expected a sheet named {fy}"]
    ws = wb[sheet]
    headers = [str(cell.value).strip().lower() if cell.value is not None else "" for cell in ws[1]]
    norm = [h.replace("-", "_").replace(" ", "_") for h in headers]
    lower = {h: i for i, h in enumerate(norm) if h}
    required = ["account_id", "account_tab", "account_name", "label", "side", "amount", "as_on_date"]
    missing = [r for r in required if r not in lower]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}"]
    accs = {a["id"]: a for a in eligible_accounts()}
    rows = []
    seen = set()
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        rec = {h: row[cidx] if cidx < len(row) else None for h, cidx in lower.items()}
        if all((v is None or str(v).strip() == "") for v in rec.values()):
            continue
        account_id_raw = rec.get("account_id")
        label = str(rec.get("label") or "").strip()
        amount_raw = rec.get("amount")
        side_raw = str(rec.get("side") or "").strip()
        tab_raw = str(rec.get("account_tab") or "").strip()
        as_on_raw = str(rec.get("as_on_date") or "").strip()
        if account_id_raw in (None, "") and not label and amount_raw in (None, ""):
            continue
        acc_id = str(account_id_raw).strip() if account_id_raw is not None else ""
        if acc_id not in {str(a) for a in accs}:
            errors.append(f"Row {i}: unknown account {account_id_raw}.")
            continue
        acc = accs[int(acc_id)]
        if side_raw != acc["side"] or tab_raw != acc["tab"]:
            errors.append(f"Row {i}: side/tab do not match account {acc_id} ({acc['name']}).")
            continue
        try:
            amount = ob.money(amount_raw)
        except (ValueError, ArithmeticError):
            errors.append(f"Row {i}: amount must be a number.")
            continue
        if amount < 0:
            errors.append(f"Row {i}: amount must be 0 or more.")
            continue
        if acc["tab"] == "Dp" and not label:
            errors.append(f"Row {i}: label (FD number) is required for deposit account {acc_id}.")
            continue
        if acc["tab"] in ("SDr", "SDrDig", "SDrCash") and label:
            errors.append(f"Row {i}: receivables account {acc_id} must have a blank label — list flats in the Apt-Arrears sheet.")
            continue
        key = (acc_id, label)
        if key in seen:
            errors.append(f"Row {i}: duplicate account {acc_id} with label '{label}'.")
            continue
        seen.add(key)
        if not as_on_raw:
            errors.append(f"Row {i}: as_on_date is missing.")
            continue
        try:
            row_as_on = ob._iso_day(as_on_raw)
        except ValueError:
            errors.append(f"Row {i}: as_on_date must be YYYY-MM-DD.")
            continue
        if as_on is not None and row_as_on != as_on:
            errors.append(f"Row {i}: as_on_date {row_as_on} does not match the Brought Forward As-on date {as_on}.")
            continue
        rows.append({"account_id": int(acc_id), "label": label, "amount": str(amount),
                     "tab": acc["tab"], "side": acc["side"], "name": acc["name"],
                     "as_on_date": row_as_on})
    return rows, errors


def apply_balances(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                   pdf_name: str, pdf: bytes) -> str:
    """File the balances statement workbook with the statements PDF and replace the draft rows.

    Fill = replace: the sheet becomes exactly draft.brought_forward.rows. Per account:
    bf_amount = sum of its rows; ledger_rows = its labelled rows. Each stored row carries
    the filed evidence id / sha256 / filename.
    """
    if ob.annexes_sealed(society_id):
        raise ob.OnboardingError("The annexes are sealed, so brought-forward balances can no longer change here.")
    check_xlsx(xlsx_name or "", xlsx)
    draft = ob.declaration(society_id) or {}
    bf = draft.get("draft", {}).get("brought_forward", {})
    fy = int(bf.get("fy") or fy_start_year())
    as_on = bf.get("as_on_date") or ""
    if not as_on:
        raise ob.OnboardingError("Set the As-on date for Brought Forward first.")
    rows, errors = read_statement_rows(xlsx, fy, as_on=as_on)
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    if not rows:
        raise ob.OnboardingError("No data found in the workbook.")
    accounts_map = {a["id"]: a for a in eligible_accounts()}
    per_acc: dict[int, list[dict]] = {}
    for r in rows:
        per_acc.setdefault(r["account_id"], []).append(r)
    new_rows = []
    total_all = Decimal(0)
    for acc_id, acc_rows in per_acc.items():
        acc = accounts_map[acc_id]
        bf_amount = str(sum((Decimal(r["amount"]) for r in acc_rows), Decimal(0)).quantize(Decimal("0.01")))
        total_all += Decimal(bf_amount)
        labelled = [{"flat_number": r["label"], "amount": r["amount"], "overdue_days": None, "remarks": ""}
                    for r in acc_rows if r["label"]]
        new_rows.append({
            "acc_id": acc_id, "tab": acc["tab"], "side": acc["side"],
            "bf_amount": bf_amount,
            "remarks": f"Per statement {as_on}",
            "evidence_id": None, "sha256": None, "filename": "",
            "ledger_rows": labelled,
        })
    filed = file_pair(society_id, actor_id, "balances", xlsx_name or "", xlsx,
                      pdf_name or "", pdf,
                      {"rows": len(rows), "accounts": len(per_acc),
                       "total": str(total_all.quantize(Decimal("0.01"))), "as_on": as_on})
    psha = ob._sha(pdf)
    for row in new_rows:
        row["evidence_id"] = filed["id"]
        row["sha256"] = psha
        row["filename"] = pdf_name or ""
    d = ob.declaration(society_id) or {}
    bf = d.setdefault("draft", {}).setdefault("brought_forward", {})
    bf["rows"] = new_rows
    ob._save_declaration(society_id, d, actor_id)
    dup = " (duplicate; re-applied)" if filed.get("duplicate") else ""
    return (f"Balances filed: {len(rows)} row(s), {len(per_acc)} account(s), total ₹{total_all:,.2f}. "
            f"PDF SHA-256 {psha[:16]}….{dup}")


def apply_pending_receivables(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                              pdf_name: str, pdf: bytes) -> str:
    """File Pending Receivables.xlsx + arrears PDF as a pending_receivables pair, tie out to SDR, and
    merge receivables into the brought-forward draft."""
    if ob.annexes_sealed(society_id):
        raise ob.OnboardingError("The annexes are sealed, so pending receivables can no longer change here.")
    # Known flats for canonical flat-name resolution.
    known_flats = ob.known_flat_numbers(society_id)
    draft = ob.declaration(society_id) or {}
    bf = ((draft.get("draft") or {}).get("brought_forward")) or {}
    clean, errors, info = pr.parse_upload(xlsx, xlsx_name or "", known_flats=known_flats,
                                          fy=bf.get("fy"), as_on=bf.get("as_on_date"))
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    if not clean:
        raise ob.OnboardingError("The workbook has no receivables rows.")
    # File the pair.
    filed = file_pair(society_id, actor_id, "pending_receivables", xlsx_name or "", xlsx,
                      pdf_name or "", pdf,
                         {"rows": len(clean), "total": str(pr.total(clean).quantize(Decimal("0.01")))})
    psha = ob._sha(pdf)
    d = ob.declaration(society_id) or {}
    rt = pr.total(clean)
    # Merge into draft brought_forward.receivables.
    bf = d.setdefault("draft", {}).setdefault("brought_forward", {})
    bf["receivables"] = clean
    ob._save_declaration(society_id, d, actor_id)
    dup = " (duplicate; re-applied)" if filed.get("duplicate") else ""
    return (f"Pending receivables filed: {len(clean)} flat(s), total ₹{rt:,.2f}. "
            f"PDF SHA-256 {psha[:16]}….{dup}")
