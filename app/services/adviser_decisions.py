"""
Society-scoped adviser decisions (Gold-Standard Plan v3, Phase 0).

Which majority a society needs for a kind of decision, and how a contested rule is to be read, are questions for THAT
society's Advocate, CA or Auditor. They are filled per society, from a start date, and stay PROVISIONAL until BOTH the
Secretary and the Treasurer (two different people) have approved them on the adviser's behalf, with the adviser's
reference number and PDF attached.

The database enforces the rules (society_decision_types, rule_parameter_defs rows with a society_id,
society_decision_approvals, fn_sign_society_decision, fn_require_confirmed). This module is the thin layer the screens
call. It:

  * validates and stores the adviser's PDF (type, size, SHA-256);
  * re-checks the signer's own password with the login lockout before an approval;
  * never trusts a subject id from the browser: every row is looked up WITH the caller's society_id;
  * turns the database's "DECISION REQUIRED" refusal into one loud message the screens can show as a banner.

Who may prepare or approve is decided at the callback (a capability), not here, except that only the serving
Secretary and Treasurer can sign: the database refuses anyone else.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime

log = logging.getLogger(__name__)

LOUD_PREFIX = "DECISION REQUIRED"
MAX_PDF_BYTES = 5 * 1024 * 1024
ADVISERS = ("Advocate", "CA", "Auditor")
KINDS = ("decision", "rule")
ROLES = ("secretary", "treasurer")
REFERENCE_MAX = 50


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


# ── the loud message ─────────────────────────────────────────────────────────────────────────────────────────────
def loud_message(exc_or_text) -> str | None:
    """The refusal text if `exc_or_text` is the database's DECISION REQUIRED error, else None.

    psycopg2 appends CONTEXT lines naming the SQL functions; those are for developers, so only the first line is kept.
    """
    text = str(exc_or_text or "")
    i = text.find(LOUD_PREFIX)
    if i < 0:
        return None
    first = text[i:].strip().splitlines()[0]
    return first[:600]


def gate(society_id: int, kind: str, key: str, on: date | None = None, db=None) -> str:
    """'not_required' | 'ok' | 'awaiting_approval' | 'missing'."""
    if kind not in KINDS:
        raise ValueError("kind must be 'decision' or 'rule'")
    row = _db(db)._execute("SELECT fn_decision_gate(%s,%s,%s,%s) AS g", (society_id, kind, key, on or date.today()), fetch_one=True)
    return row["g"] if row else "missing"


def block_message(society_id: int, kind: str, key: str, on: date | None = None, db=None) -> str | None:
    """None if the engine may proceed; otherwise the loud DECISION REQUIRED text (what the database would raise)."""
    d = _db(db)
    on = on or date.today()
    try:
        d._execute("SELECT fn_require_confirmed(%s,%s,%s,%s)", (society_id, kind, key, on), fetch_one=True)
        return None
    except Exception as exc:                                    # noqa: BLE001
        msg = loud_message(exc)
        if msg is None:
            raise
        return msg


# ── reading ──────────────────────────────────────────────────────────────────────────────────────────────────────
def get_state(society_id: int, on: date | None = None, db=None) -> dict:
    """Everything the Adviser Decisions screen and the banner need."""
    d = _db(db)
    on = on or date.today()
    items = d._execute("SELECT * FROM fn_society_decision_status(%s,%s)", (society_id, on), fetch_all=True) or []
    detail = {}
    for r in d._execute(
            """SELECT 'decision' AS kind, x.id, x.decision_code AS key, x.choice_options, x.default_choice, x.majority_pct,
                      x.majority_basis, x.start_date, x.end_date, x.on_behalf_of, x.reference_text, x.reference_doc_id,
                      x.confirmed_at, dt.verification AS catalogue_verification, dt.source_provision
                 FROM society_decision_types x JOIN decision_types dt ON dt.code = x.decision_code
                WHERE x.society_id = %s
               UNION ALL
               SELECT 'rule', r.id, r.rule_key, NULL, NULL, NULL, NULL, r.start_date, NULL, r.on_behalf_of, r.reference_text,
                      r.reference_doc_id, r.confirmed_at, r.verification, r.provision
                 FROM rule_parameter_defs r WHERE r.society_id = %s""", (society_id, society_id), fetch_all=True) or []:
        detail[(r["kind"], r["id"])] = dict(r)
    out = []
    for it in items:
        row = dict(it)
        row.update({k: v for k, v in detail.get((it["kind"], it["subject_id"]), {}).items() if k not in row})
        out.append(row)
    blocked = [r for r in out if r["gate"] in ("missing", "awaiting_approval")]
    return {"items": out, "blocked": blocked, "all_confirmed": bool(out) and not blocked}


def banner(society_id: int, db=None) -> str | None:
    """One line for a top-of-screen alert while anything is unconfirmed, or None."""
    st = get_state(society_id, db=db)
    if not st["items"]:
        return (f"{LOUD_PREFIX}: this society has not recorded its adviser decisions yet. Open Governance > Adviser "
                "Decisions and fill them in before recording resolutions, cash receipts, poll results or election lists.")
    n = len(st["blocked"])
    if not n:
        return None
    return (f"{LOUD_PREFIX}: {n} adviser decision(s) are still provisional. Actions that depend on them are blocked until "
            "the Secretary and the Treasurer have both approved each one.")


# ── writing ──────────────────────────────────────────────────────────────────────────────────────────────────────
def ensure_rows(society_id: int, user_id: int | None, start: date | None = None, db=None) -> int:
    """Create the society's provisional rows (idempotent). -> number of rows created."""
    row = _db(db)._execute("SELECT fn_init_society_decisions(%s,%s,%s) AS n", (society_id, user_id, start), fetch_one=True)
    return int(row["n"]) if row else 0


def attach_pdf(society_id: int, user_id: int | None, file_name: str, content: bytes, db=None) -> tuple[bool, str, int | None]:
    """Store the adviser's PDF. -> (ok, message, document_id). Evidence is immutable: a new file is a new row."""
    if not content or len(content) < 5:
        return False, "The file is empty.", None
    if len(content) > MAX_PDF_BYTES:
        return False, f"The PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.", None
    if content[:5] != b"%PDF-":
        return False, "That file is not a PDF.", None
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", (file_name or "adviser-reference.pdf").strip())[-120:] or "adviser-reference.pdf"
    import psycopg2
    row = _db(db)._execute(
        """INSERT INTO adviser_reference_documents (society_id, file_name, size_bytes, sha256, content, uploaded_by)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (society_id, name, len(content), hashlib.sha256(content).hexdigest(), psycopg2.Binary(content), user_id), fetch_one=True)
    return True, "PDF stored.", int(row["id"])


def _owns(society_id: int, kind: str, subject_id: int, d) -> dict | None:
    if kind == "decision":
        return d._execute("SELECT id, approved_status FROM society_decision_types WHERE id=%s AND society_id=%s",
                          (subject_id, society_id), fetch_one=True)
    return d._execute("SELECT id, approved_status FROM rule_parameter_defs WHERE id=%s AND society_id=%s",
                      (subject_id, society_id), fetch_one=True)


def save(society_id: int, kind: str, subject_id: int, *, on_behalf_of: str | None = None, reference_text: str | None = None,
         reference_doc_id: int | None = None, majority_pct: float | None = None, start_date: date | str | None = None,
         db=None) -> tuple[bool, str]:
    """Fill in a provisional row. Changing anything on a confirmed row voids its approvals (the database does that)."""
    d = _db(db)
    if kind not in KINDS:
        return False, "Unknown kind of decision."
    if not _owns(society_id, kind, subject_id, d):
        return False, "That decision does not belong to this society."
    if on_behalf_of is not None and on_behalf_of not in ADVISERS:
        return False, "Choose whose advice this is: Advocate, CA or Auditor."
    ref = (reference_text or "").strip() if reference_text is not None else None
    if ref is not None and len(ref) > REFERENCE_MAX:
        return False, f"The reference number can be at most {REFERENCE_MAX} characters."
    if reference_doc_id is not None:
        ok = d._execute("SELECT 1 AS x FROM adviser_reference_documents WHERE id=%s AND society_id=%s",
                        (reference_doc_id, society_id), fetch_one=True)
        if not ok:
            return False, "That document belongs to another society."
    sets, params = [], []
    for col, val in (("on_behalf_of", on_behalf_of), ("reference_text", ref), ("reference_doc_id", reference_doc_id)):
        if val is not None:
            sets.append(f"{col} = %s"); params.append(val)
    if start_date is not None:
        try:
            sd = start_date if isinstance(start_date, date) else datetime.strptime(str(start_date)[:10], "%Y-%m-%d").date()
        except ValueError:
            return False, "Give the start date as YYYY-MM-DD."
        sets.append("start_date = %s"); params.append(sd)
    if majority_pct is not None:
        if kind != "decision":
            return False, "Only a decision has a majority."
        sets.append("majority_pct = %s"); params.append(majority_pct)
    if not sets:
        return False, "Nothing to save."
    table = "society_decision_types" if kind == "decision" else "rule_parameter_defs"
    try:
        d._execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = %s AND society_id = %s", tuple(params) + (subject_id, society_id))
    except Exception as exc:                                    # noqa: BLE001
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else "could not save"
        if "ck_sdt_choice" in first:
            return False, "Choose one of the offered majorities."
        log.info("adviser decision save refused: %s", first)
        return False, first
    return True, "Saved. It stays provisional until the Secretary and the Treasurer both approve it."


def sign(society_id: int, kind: str, subject_id: int, user_id: int, role: str, password: str, db=None) -> tuple[bool, str]:
    """Approve as Secretary or Treasurer, re-checking the signer's own login password (same lockout as login)."""
    d = _db(db)
    if kind not in KINDS or role not in ROLES:
        return False, "Only the Secretary or the Treasurer can approve."
    if not _owns(society_id, kind, subject_id, d):
        return False, "That decision does not belong to this society."
    from app.services.auth_service import verify_password_with_lockout
    ok, why = verify_password_with_lockout(user_id, password)
    if not ok:
        return False, why or "The password is not correct."
    try:
        row = d._execute("SELECT fn_sign_society_decision(%s,%s,%s,%s) AS m", (kind, subject_id, role, user_id), fetch_one=True)
    except Exception as exc:                                    # noqa: BLE001
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else "could not approve"
        return False, first
    return True, row["m"]
