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

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.services import onboarding_service as ob
from app.services import xlsx_templates as xt
from app.services import pending_receivables as pr

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
                       xlsx_filename="Account Balances.xlsx", stage="brought_forward"),
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
    """Every account that carries a brought-forward flag (has_bf = True), Dr side first then Cr."""
    from database.seed import ACCOUNTS
    out = []
    for acc in ACCOUNTS:
        if acc[6]:
            out.append({"id": acc[0], "name": acc[1], "tab": acc[2], "side": acc[5]})
    out.sort(key=lambda a: (a["side"] != "Dr", a["id"]))
    return out


def check_balance_rows(society_id: int, rows: list[dict], default_as_on: str | None = None) -> tuple[list[dict], dict, list[str]]:
    """Validate parsed balances rows. Returns (clean rows, per-account totals, all errors).

    Rows from the Tally sheet (no label/as_on_date columns) are accepted with defaults:
    label = "" and as_on_date = default_as_on. Deposit/receivables label requirement is
    waived for Tally rows (ledger rows are added separately per B3).
    """
    clean: list[dict] = []
    errors: list[str] = []
    accounts = {str(a["id"]): a for a in eligible_accounts()}
    labels_seen: set = set()
    d = ob.declaration(society_id) or {}
    bf = (d.get("draft") or {}).get("brought_forward") or {}
    as_on = bf.get("as_on_date") or default_as_on
    have_as_on = bool(as_on)
    if not have_as_on:
        errors.append("Set the As-on date for Brought Forward first.")
    for i, r in enumerate(rows or [], start=2):
        label = str(r.get("label") or "").strip()
        amount_raw = r.get("amount")
        account_id_raw = r.get("account_id")
        if label == "" and amount_raw in (None, ""):
            continue
        acc_id = str(account_id_raw).strip() if account_id_raw is not None else ""
        if acc_id not in accounts:
            errors.append(f"Row {i}: unknown account {account_id_raw}.")
            continue
        if amount_raw in (None, "") and label:
            errors.append(f"Row {i}: amount is required when a label is given.")
            continue
        try:
            amount = ob.money(amount_raw)
        except (ValueError, ArithmeticError):
            errors.append(f"Row {i}: amount must be a number.")
            continue
        if amount < 0:
            errors.append(f"Row {i}: amount must be 0 or more.")
            continue
        acc = accounts[acc_id]
        is_tally = r.get("_sheet") == "Tally"
        if not is_tally and acc["tab"] in ("Dp", "SDrDig", "SDrCash") and not label:
            errors.append(f"Row {i}: label is required for {acc['tab']} account {acc['name']}.")
            continue
        key = (acc_id, label)
        if key in labels_seen:
            errors.append(f"Row {i}: duplicate account {acc_id} with label '{label}'.")
            continue
        labels_seen.add(key)
        row_as_on = str(r.get("as_on_date") or "").strip() or default_as_on or ""
        try:
            row_as_on = ob._iso_day(row_as_on)
        except ValueError:
            errors.append(f"Row {i}: as_on_date must be YYYY-MM-DD.")
            continue
        if have_as_on and row_as_on != as_on:
            errors.append(f"Row {i}: as_on_date {row_as_on} does not match the Brought Forward As-on date {as_on}.")
            continue
        clean.append({"account_id": int(acc_id), "label": label, "amount": str(amount),
                      "tab": acc["tab"], "side": acc["side"], "name": acc["name"],
                      "as_on_date": row_as_on, "sheet": r.get("_sheet") or ""})
    totals: dict = {}
    for c in clean:
        totals[str(c["account_id"])] = str((Decimal(totals.get(str(c["account_id"]), "0")) + Decimal(c["amount"])).quantize(Decimal("0.01")))
    return clean, totals, errors


def apply_balances(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                   pdf_name: str, pdf: bytes) -> str:
    """File the balances workbook with the statements PDF and merge totals into the draft.

    Reads the Assets (Dr), Liabilities & Equity (Cr) and Tally sheets. Tally-sheet rows
    fill the grid directly (B5) without requiring label or as_on_date.
    """
    if ob.annexes_sealed(society_id):
        raise ob.OnboardingError("The annexes are sealed, so brought-forward balances can no longer change here.")
    draft_as_on = (ob.declaration(society_id) or {}).get("draft", {}).get("brought_forward", {}).get("as_on_date", "")
    all_rows: list[dict] = []
    for sheet, required in (("Assets (Dr)", ["account_id", "account_name", "tab", "side", "label", "as_on_date", "amount"]),
                            ("Liabilities & Equity (Cr)", ["account_id", "account_name", "tab", "side", "label", "as_on_date", "amount"]),
                            ("Tally", ["account_id", "account_name", "tab", "side", "amount"])):
        res = xt.parse_bytes(xlsx, xlsx_name or "", sheet, required)
        if res.errors:
            continue  # sheet may not exist in older uploads
        for r in res.rows:
            r["_sheet"] = sheet
            all_rows.append(r)
    if not all_rows:
        raise ob.OnboardingError("No data found in the workbook.")
    clean, totals, errors = check_balance_rows(society_id, all_rows, default_as_on=draft_as_on)
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    clean, _totals, errors = check_balance_rows(society_id, all_rows, default_as_on=draft_as_on)
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    accounts_map = {a["id"]: a for a in eligible_accounts()}
    # B7: Tally-sheet totals replace manual per-account amounts for the same account.
    tally_by_acc: dict[int, dict] = {}
    manual_by_acc: dict[int, list[dict]] = {}
    for c in clean:
        if c.get("sheet") == "Tally":
            tally_by_acc[c["account_id"]] = c
        else:
            manual_by_acc.setdefault(c["account_id"], []).append(c)
    chosen: dict[int, dict | list[dict]] = {}
    for acc_id, c in tally_by_acc.items():
        chosen[acc_id] = c
    for acc_id, rows_ in manual_by_acc.items():
        if acc_id not in chosen:
            chosen[acc_id] = rows_
    if not chosen:
        raise ob.OnboardingError("No data found in the workbook.")
    total_all = str(sum(
        Decimal(c["amount"]) if not isinstance(c, list) else
        sum((Decimal(r["amount"]) for r in c), Decimal(0))
        for c in chosen.values()
    ).quantize(Decimal("0.01")))
    first = next(iter(chosen.values()))
    as_on = first["as_on_date"] if not isinstance(first, list) else first[0]["as_on_date"]
    as_on = as_on or draft_as_on
    filed = file_pair(society_id, actor_id, "balances", xlsx_name or "", xlsx,
                      pdf_name or "", pdf,
                      {"rows": len(chosen), "accounts": len(chosen), "total": total_all, "as_on": as_on})
    psha = ob._sha(pdf)
    d = ob.declaration(society_id) or {}
    bf = d.setdefault("draft", {}).setdefault("brought_forward", {})
    rows_bf = bf.setdefault("rows", [])
    existing = {int(r["acc_id"]): r for r in rows_bf if r.get("acc_id") is not None}
    for acc_id, c in chosen.items():
        acc = accounts_map[acc_id]
        if isinstance(c, list):
            total = str(sum((Decimal(r["amount"]) for r in c), Decimal(0)).quantize(Decimal("0.01")))
            labelled = [r for r in c if r["label"]]
            remarks_src = c[0]
        else:
            total = c["amount"]
            labelled = [c] if c["label"] else []
            remarks_src = c
        row = {
            "acc_id": acc_id, "tab": acc["tab"], "side": acc["side"],
            "bf_amount": total,
            "remarks": "Per account statement " + remarks_src["as_on_date"],
            "evidence_id": filed["id"], "sha256": psha, "filename": pdf_name or "",
        }
        if labelled:
            row["ledger_rows"] = [{"flat_number": r["label"], "amount": r["amount"],
                                   "overdue_days": None, "remarks": ""} for r in labelled]
        existing[acc_id] = row
    bf["rows"] = list(existing.values())
    ob._save_declaration(society_id, d, actor_id)
    dup = " (duplicate; re-applied)" if filed.get("duplicate") else ""
    return (f"Balances filed: {len(clean)} row(s), {len(totals)} account(s), total {total_all}. "
            f"PDF SHA-256 {psha[:16]}….{dup}")


def apply_pending_receivables(society_id: int, actor_id: int, xlsx_name: str, xlsx: bytes,
                              pdf_name: str, pdf: bytes) -> str:
    """File Pending Receivables.xlsx + arrears PDF as a pending_receivables pair, tie out to SDR, and
    merge receivables into the brought-forward draft."""
    if ob.annexes_sealed(society_id):
        raise ob.OnboardingError("The annexes are sealed, so pending receivables can no longer change here.")
    # Known flats for canonical flat-name resolution.
    known_flats = ob.known_flat_numbers(society_id)
    clean, errors, info = pr.parse_upload(xlsx, xlsx_name or "", known_flats=known_flats)
    if errors:
        raise ob.OnboardingError(" ".join(errors))
    if not clean:
        raise ob.OnboardingError("The workbook has no receivables rows.")
    # Tie out against Sundry Debtors total from Brought Forward.
    d = ob.declaration(society_id) or {}
    bf = d.get("draft", {}).get("brought_forward", {})
    sdr = pr.sdr_total(bf.get("rows") or [])
    rt = pr.total(clean)
    if rt != sdr:
        raise ob.OnboardingError(
            f"Pending receivables total (₹{rt:,.2f}) does not tie to Sundry Debtors balance "
            f"(₹{sdr:,.2f}). Fix the workbook or the Brought Forward amounts first.")
    # File the pair.
    filed = file_pair(society_id, actor_id, "pending_receivables", xlsx_name or "", xlsx,
                      pdf_name or "", pdf,
                      {"rows": len(clean), "total": str(rt.quantize(Decimal("0.01")))})
    psha = ob._sha(pdf)
    # Merge into draft brought_forward.receivables.
    bf = d.setdefault("draft", {}).setdefault("brought_forward", {})
    bf["receivables"] = clean
    ob._save_declaration(society_id, d, actor_id)
    dup = " (duplicate; re-applied)" if filed.get("duplicate") else ""
    return (f"Pending receivables filed: {len(clean)} flat(s), total ₹{rt:,.2f}. "
            f"PDF SHA-256 {psha[:16]}….{dup}")
