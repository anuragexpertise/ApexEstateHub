"""
Signatures on records (Gold-Standard Plan v3, tasks 2.1, 2.2, 2.11, 2.12).

Every person who signs, approves or declines confirms with THEIR OWN login password (the shared login lockout
applies) and must hold a serving office that is eligible for that kind of record. Each confirmation stores the user,
office, time and the SHA-256 of the exact item text. When the required signatures for the same item version are in,
the record is sealed: signed with the society's key (NOC -> SIGNING_NOC; everything else -> SIGNING_AGREEMENT) and
recorded in signed_records. Editing the sealed text is then blocked by database triggers, and verification recomputes
the hash of what is stored now.

A password confirmation records who confirmed. It is NOT a legal e-signature; keep signed paper minutes. No voter
identity appears in any signed poll record (tally only).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from app.services import signing_service

KINDS = ("noc", "agreement", "resolution", "minutes", "poll", "expense", "fund_withdrawal")
PURPOSE = {"noc": "SIGNING_NOC"}          # every other kind is sealed with SIGNING_AGREEMENT
OFFICES = ("president", "vice_president", "secretary", "joint_secretary", "treasurer", "working_committee_member")
ALL_BEARERS = list(OFFICES)

# Defaults (the plan's "planned signers"); a society overrides them in signer_policy.
DEFAULT_POLICY = {
    "noc":             dict(eligible=["secretary"], required=["secretary"], min=1),
    "agreement":       dict(eligible=["president", "secretary", "platform"], required=["president", "secretary", "platform"], min=3),
    "resolution":      dict(eligible=["president", "vice_president", "secretary", "joint_secretary", "chair"], required=["secretary", "chair"], min=2),
    "minutes":         dict(eligible=["president", "vice_president", "secretary", "joint_secretary", "chair"], required=["secretary", "chair"], min=2),
    "poll":            dict(eligible=["secretary", "president"], required=[], min=1),
    "expense":         dict(eligible=["secretary", "treasurer", "president"], required=[], min=1),
    "fund_withdrawal": dict(eligible=["secretary", "treasurer", "president"], required=[], min=2),
}


class SigningRefused(RuntimeError):
    """A confirmation or seal was refused; the message is safe to show the user."""


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── the exact text of each record ───────────────────────────────────────────────────────────────────────────────
def item_text(kind: str, subject_id: int, db=None) -> tuple[int, str]:
    """(society_id, canonical text) of the record AS STORED NOW."""
    d = _db(db)
    if kind == "noc":
        r = d._execute("SELECT society_id, apartment_id, certificate_no, issued_date, valid_until, body_text FROM nocs WHERE id=%s", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("NOC not found.")
        return r["society_id"], f"noc|{subject_id}|{r['apartment_id']}|{r['certificate_no']}|{r['issued_date']}|{r['valid_until']}|{r['body_text']}"
    if kind == "agreement":
        r = d._execute("SELECT society_id, agreement_no, society_name, registration_number, body_text FROM society_agreements WHERE id=%s", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("Agreement not found.")
        return r["society_id"], f"agreement|{subject_id}|{r['agreement_no']}|{r['society_name']}|{r['registration_number']}|{r['body_text']}"
    if kind == "resolution":
        r = d._execute("""SELECT m.society_id, x.id, x.body, x.clause_id, x.majority_required, x.votes_for_pct, x.owners_present_pct, x.passed_on, x.status
                            FROM resolutions x JOIN meetings m ON m.id = x.meeting_id WHERE x.id=%s""", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("Resolution not found.")
        if r["status"] != "passed":
            raise SigningRefused("Only a passed resolution can be signed.")
        reg = d._execute("SELECT COALESCE(md5(string_agg(apartment_id::text||vote||weight::text, ',' ORDER BY apartment_id)),'') AS h FROM resolution_votes WHERE resolution_id=%s", (subject_id,), fetch_one=True)
        creg = d._execute("SELECT COALESCE(md5(string_agg(person_key||vote, ',' ORDER BY person_key)),'') AS h FROM committee_votes WHERE resolution_id=%s", (subject_id,), fetch_one=True)
        return r["society_id"], (f"resolution|{subject_id}|{r['clause_id']}|{r['body']}|{r['majority_required']}|{r['votes_for_pct']}|"
                                 f"{r['owners_present_pct']}|{r['passed_on']}|reg:{reg['h']}|creg:{creg['h']}")
    if kind == "minutes":
        r = d._execute("SELECT society_id, type, held_on, agenda, venue, minutes_pdf FROM meetings WHERE id=%s", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("Meeting not found.")
        res = d._execute("SELECT COALESCE(string_agg(id::text||':'||COALESCE(status,'')||':'||COALESCE(votes_for_pct::text,''), ',' ORDER BY id),'') AS s FROM resolutions WHERE meeting_id=%s", (subject_id,), fetch_one=True)
        return r["society_id"], f"minutes|{subject_id}|{r['type']}|{r['held_on']}|{r['venue']}|{r['agenda']}|{r['minutes_pdf']}|{res['s']}"
    if kind == "poll":
        r = d._execute("SELECT society_id, title, choice_1, choice_2, choice_3, choice_4, choice_5, majority_pct, quorum_pct, vote_basis, status FROM polls WHERE id=%s", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("Poll not found.")
        if r["status"] != "results_declared":
            raise SigningRefused("Only a poll whose results are declared can be signed.")
        tally = d._execute("SELECT COALESCE(string_agg(choice::text||'='||n::text, ',' ORDER BY choice), '') AS t FROM "
                           "(SELECT choice, COUNT(*) AS n FROM poll_ballots WHERE poll_id=%s GROUP BY choice) q", (subject_id,), fetch_one=True)
        # Tally only: no ballot row, flat or voter appears in the signed text.
        return r["society_id"], (f"poll|{subject_id}|{r['title']}|{r['choice_1']}|{r['choice_2']}|{r['choice_3']}|{r['choice_4']}|{r['choice_5']}|"
                                 f"{r['majority_pct']}|{r['quorum_pct']}|{r['vote_basis']}|tally:{tally['t']}")
    if kind == "expense":
        r = d._execute("SELECT society_id, entity_id, role, acc_id, amount, mode, particulars, trx_date FROM expenses WHERE id=%s", (subject_id,), fetch_one=True) \
            if _has_col(d, "expenses", "trx_date") else d._execute("SELECT society_id, entity_id, role, acc_id, amount, mode, particulars, expense_date AS trx_date FROM expenses WHERE id=%s", (subject_id,), fetch_one=True)
        if not r:
            raise SigningRefused("Expense not found.")
        return r["society_id"], f"expense|{subject_id}|{r['entity_id']}|{r['role']}|{r['acc_id']}|{r['amount']}|{r['mode']}|{r['particulars']}|{r['trx_date']}"
    raise SigningRefused(f"Unsupported record kind {kind!r}.")


def _has_col(d, table, col) -> bool:
    return bool(d._execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s", (table, col), fetch_one=True))


# ── policy ──────────────────────────────────────────────────────────────────────────────────────────────────────
def policy(society_id: int, kind: str, db=None, subject_id: int | None = None) -> dict:
    d = _db(db)
    row = d._execute("SELECT eligible_offices, required_offices, min_signers FROM signer_policy WHERE society_id=%s AND subject_kind=%s",
                     (society_id, kind), fetch_one=True)
    if row:
        return dict(eligible=list(row["eligible_offices"]), required=list(row["required_offices"]), min=row["min_signers"])
    pol = dict(DEFAULT_POLICY[kind])
    if kind == "expense" and subject_id:                          # the amount-based ladder (expense_approval)
        from app.services import expense_approval as ea
        need, _why = ea.required_signers(subject_id, d)
        pol["min"] = max(need, 1)
    return pol


def set_policy(society_id: int, kind: str, eligible, required, min_signers: int, actor_id: int, db=None) -> None:
    d = _db(db)
    bad = [o for o in list(eligible) + list(required) if o not in ALL_BEARERS + ["chair", "platform"]]
    if bad or not set(required) <= set(eligible) or not (1 <= int(min_signers) <= 5) or int(min_signers) < len(required):
        raise SigningRefused("Invalid signer list: required offices must be eligible and min_signers must cover them (1 to 5).")
    d._execute("""INSERT INTO signer_policy (society_id, subject_kind, eligible_offices, required_offices, min_signers, updated_by)
                  VALUES (%s,%s,%s,%s,%s,%s)
                  ON CONFLICT (society_id, subject_kind) DO UPDATE SET eligible_offices=EXCLUDED.eligible_offices,
                  required_offices=EXCLUDED.required_offices, min_signers=EXCLUDED.min_signers, updated_by=EXCLUDED.updated_by, updated_at=NOW()""",
               (society_id, kind, list(eligible), list(required), int(min_signers), actor_id))


# ── who is this user for this record? ───────────────────────────────────────────────────────────────────────────
def serving_offices(society_id: int, user_id: int, on: date | None = None, db=None) -> list[dict]:
    on = on or date.today()
    return _db(db)._execute(
        """SELECT id, office_code FROM committee_offices WHERE society_id=%s AND user_id=%s AND status='active'
              AND term_start <= %s AND (term_end IS NULL OR term_end >= %s)""",
        (society_id, user_id, on, on), fetch_all=True) or []


def _signer_roles(d, society_id, kind, subject_id, user_id) -> list[tuple[str, int | None]]:
    """The signing capacities this user has for this record: [(office_code, committee_office_id)]."""
    roles = [(o["office_code"], o["id"]) for o in serving_offices(society_id, user_id, db=d)]
    u = d._execute("SELECT role FROM users WHERE id=%s", (user_id,), fetch_one=True) or {}
    if u.get("role") == "master":
        roles.append(("platform", None))
    if kind in ("resolution", "minutes"):
        mid = subject_id if kind == "minutes" else (d._execute("SELECT meeting_id FROM resolutions WHERE id=%s", (subject_id,), fetch_one=True) or {}).get("meeting_id")
        m = d._execute("SELECT chaired_by FROM meetings WHERE id=%s", (mid,), fetch_one=True) or {}
        if m.get("chaired_by") == user_id:
            roles.append(("chair", None))
    return roles


def _confirm_password(user_id: int, password: str) -> None:
    from app.services.auth_service import verify_password_with_lockout
    ok, msg = verify_password_with_lockout(user_id, password or "")
    if not ok:
        raise SigningRefused(msg or "The password did not match.")


def _audit(d, society_id, user_id, action, kind, subject_id, extra):
    d._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
               "VALUES (%s,%s,%s,%s,%s,%s::jsonb,'app')", (society_id, user_id, action, f"signature_{kind}", str(subject_id), json.dumps(extra)))


def status(kind: str, subject_id: int, db=None) -> dict:
    """The Signatures panel: required signers, who has signed the CURRENT text, whether it is sealed."""
    d = _db(db)
    society_id, text = item_text(kind, subject_id, d) if kind not in ("resolution", "poll") else _safe_item(d, kind, subject_id)
    h = sha256(text) if text else None
    pol = policy(society_id, kind, d, subject_id)
    sigs = d._execute("""SELECT s.user_id, s.office_code, s.action, s.signed_at, s.reason, u.name FROM document_signatures s JOIN users u ON u.id = s.user_id
                         WHERE s.subject_kind=%s AND s.subject_id=%s AND s.item_hash=%s ORDER BY s.id""", (kind, subject_id, h), fetch_all=True) if h else []
    signed = [x for x in sigs if x["action"] in ("sign", "approve")]
    declined = [x for x in sigs if x["action"] == "decline"]
    seal = d._execute("SELECT * FROM signed_records WHERE subject_kind=%s AND subject_id=%s AND status='valid'", (kind, subject_id), fetch_one=True)
    have = {x["office_code"] for x in signed}
    return {"policy": pol, "signed": signed, "declined": declined, "missing_required": [o for o in pol["required"] if o not in have],
            "people_signed": len({x["user_id"] for x in signed}), "min_signers": pol["min"], "sealed": bool(seal), "seal": seal, "item_hash": h}


def _safe_item(d, kind, subject_id):
    try:
        return item_text(kind, subject_id, d)
    except SigningRefused:
        row = d._execute({"resolution": "SELECT m.society_id FROM resolutions x JOIN meetings m ON m.id=x.meeting_id WHERE x.id=%s",
                          "poll": "SELECT society_id FROM polls WHERE id=%s"}[kind], (subject_id,), fetch_one=True)
        if not row:
            raise
        return row["society_id"], ""


def _complete(st: dict) -> bool:
    return not st["missing_required"] and st["people_signed"] >= st["min_signers"] and not st["declined"]


def sign(kind: str, subject_id: int, user_id: int, password: str, db=None, action: str = "sign", reason: str | None = None) -> dict:
    """Record this user's confirmation ('sign'/'approve') or refusal ('decline', needs a written reason).
    Returns the new status; the record is sealed when the last required signature arrives."""
    if kind not in KINDS:
        raise SigningRefused("Unknown record kind.")
    if action not in ("sign", "approve", "decline"):
        raise SigningRefused("Unknown action.")
    d = _db(db)
    society_id, text = item_text(kind, subject_id, d)
    if d._execute("SELECT 1 FROM signed_records WHERE subject_kind=%s AND subject_id=%s AND status='valid'", (kind, subject_id), fetch_one=True):
        raise SigningRefused("This record is already sealed.")
    if action == "decline" and len((reason or "").strip()) < 10:
        raise SigningRefused("Say why you decline (at least 10 characters).")
    pol = policy(society_id, kind, d, subject_id)
    roles = [r for r in _signer_roles(d, society_id, kind, subject_id, user_id) if r[0] in pol["eligible"]]
    if not roles:
        raise SigningRefused("You do not hold an office that may sign this record.")
    _confirm_password(user_id, password)                                   # wrong password never signs
    h = sha256(text)
    # Prefer a REQUIRED capacity not yet covered, else the first eligible one.
    have = {x["office_code"] for x in d._execute("SELECT office_code FROM document_signatures WHERE subject_kind=%s AND subject_id=%s AND item_hash=%s AND action IN ('sign','approve')",
                                                  (kind, subject_id, h), fetch_all=True) or []}
    office, coid = next((r for r in roles if r[0] in pol["required"] and r[0] not in have), roles[0])
    if _self_dealing(d, kind, subject_id, user_id, society_id):
        raise SigningRefused("You cannot sign an item concerning your own flat.")
    try:
        d._execute("""INSERT INTO document_signatures (society_id, subject_kind, subject_id, action, user_id, office_code, committee_office_id, item_hash, reason)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (society_id, kind, subject_id, action, user_id, office, coid, h, (reason or None)))
    except Exception as exc:                                               # noqa: BLE001
        if "uq_doc_signature_person" in str(exc):
            raise SigningRefused("You have already signed this item; one person counts once.") from exc
        raise
    _audit(d, society_id, user_id, f"DOCUMENT_{action.upper()}", kind, subject_id, {"office": office, "item_hash": h})
    st = status(kind, subject_id, d)
    if action != "decline" and _complete(st):
        st["seal"] = _seal(d, society_id, kind, subject_id, h, st)
        st["sealed"] = True
    return st


def _self_dealing(d, kind, subject_id, user_id, society_id) -> bool:
    """Nobody signs a payment to their own flat (the payee is an apartment login of the signer's flat)."""
    if kind not in ("expense", "fund_withdrawal"):
        return False
    r = d._execute("""SELECT 1 FROM expenses x JOIN users u ON u.id=%s AND u.society_id=x.society_id
                       WHERE x.id=%s AND x.role='apartment' AND u.role='apartment' AND u.linked_id = x.entity_id""",
                   (user_id, subject_id), fetch_one=True) if kind == "expense" else None
    return r is not None


def _seal(d, society_id, kind, subject_id, item_hash, st) -> dict:
    purpose = PURPOSE.get(kind, "SIGNING_AGREEMENT")
    rec = signing_service.sign(society_id, purpose, f"{kind}|{subject_id}|{item_hash}", db=d)
    signers = [{"user_id": x["user_id"], "office": x["office_code"], "at": str(x["signed_at"])} for x in st["signed"]]
    d._execute("""INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
               (society_id, kind, subject_id, purpose, item_hash, rec["signature"], rec["key_version"], rec["key_id"], rec["algorithm"], json.dumps(signers)))
    _audit(d, society_id, None, "DOCUMENT_SEALED", kind, subject_id, {"purpose": purpose, "key_version": rec["key_version"], "item_hash": item_hash})
    return d._execute("SELECT * FROM signed_records WHERE subject_kind=%s AND subject_id=%s AND status='valid'", (kind, subject_id), fetch_one=True)


# ── verification (also behind the public page) ─────────────────────────────────────────────────────────────────
def verify(kind: str, subject_id: int, db=None) -> dict:
    """'valid' | 'superseded' | 'revoked' | 'tampered' | 'untrusted' | 'unsigned'. Recomputes the hash of the text as stored NOW."""
    d = _db(db)
    row = d._execute("SELECT * FROM signed_records WHERE subject_kind=%s AND subject_id=%s ORDER BY id DESC LIMIT 1", (kind, subject_id), fetch_one=True)
    if not row:
        return {"status": "unsigned"}
    if row["status"] != "valid":
        return {"status": row["status"], "signed_at": row["signed_at"]}
    try:
        society_id, text = item_text(kind, subject_id, d)
    except SigningRefused:
        return {"status": "tampered", "signed_at": row["signed_at"]}
    if sha256(text) != row["item_hash"]:
        return {"status": "tampered", "signed_at": row["signed_at"]}
    res = signing_service.verify(row["society_id"], row["purpose"], f"{kind}|{subject_id}|{row['item_hash']}", row["signature"],
                                 row["key_version"], row["signed_at"], db=d)
    out = {"status": "valid" if res["valid"] else ("untrusted" if res["status"] == "untrusted" else "tampered"),
           "signed_at": row["signed_at"], "signers": [{"office": s["office"], "at": s["at"]} for s in row["signers"]]}
    return out


def revoke(kind: str, subject_id: int, user_id: int, reason: str, db=None) -> None:
    d = _db(db)
    if len((reason or "").strip()) < 10:
        raise SigningRefused("Say why the seal is revoked (at least 10 characters).")
    d._execute("UPDATE signed_records SET status='revoked', revoked_reason=%s WHERE subject_kind=%s AND subject_id=%s AND status='valid'", (reason, kind, subject_id))
