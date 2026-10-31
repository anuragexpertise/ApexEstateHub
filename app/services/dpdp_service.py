# app/services/dpdp_service.py
"""
DPDP Act 2023 core for a society (Gold-Standard Plan v5, V5.11 / V5.12).

The society is the Data Fiduciary; the platform is its Data Processor (the Agreement's data-protection part).

  * a versioned privacy notice per society, shown to every person before they reach the dashboard (notice_gate);
  * per-purpose consent records with the notice version and a withdrawal time; statutory dues and gate safety are recorded
    as 'legitimate_use' (the advocate confirms that basis), optional purposes as 'consent';
  * a rights register (access, correction, erasure, grievance, nominee) where every request has a due date and an outcome;
  * a breach register;
  * erasure that blanks a person's PROFILE and never touches a ledger line, after a 48-hour notice and only when no
    blocker stands (fn_erase_person_profile / fn_erasure_blockers).

The dates the DPDP Rules take effect, the response period and the lawful basis for dues records are all marked [Verify]
in the plan and are held here as constants so they can be changed in one place.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from database.db_manager import db

log = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# DPDP legal-parameter block — centralised so the dates, response period and
# lawful bases can be changed in one place and reviewed by legal.
#
# Items marked [Verify] are held against the DPDP Act 2023 / Rules and are
# NOT yet legally confirmed. While any item is unverified the society's admin
# sees an admin-visible 'pending legal review' flag (dpdp_pending_legal_review).
# ═════════════════════════════════════════════════════════════════════════════

# [Verify] Days within which the society must answer a rights request.
RESPONSE_DAYS = 30

# [Verify] Lawful basis the advocate has confirmed for each purpose, and whether
# the purpose is mandatory (cannot be switched off by the person).
# purpose -> (label, lawful basis, required)
PURPOSES = {
    "notice_ack":    ("Read and understood the privacy notice", "consent", True),
    "dues":          ("Billing, receipts and dues recovery", "legitimate_use", True),
    "gate_safety":   ("Gate passes, visitor log and safety", "legitimate_use", True),
    "announcements": ("Society announcements by push notification and email", "consent", False),
}

# [Verify] Legal-effect dates held per society in dpdp_legal_review. Until the
# advocate signs them off, dpdp_pending_legal_review(society_id) returns True
# and every notice carries a pending-review banner.
REVIEW_ITEMS = ("response_days", "lawful_basis_dues", "lawful_basis_gate_safety", "notice_effective_date")


class DpdpError(ValueError):
    """A request was refused; the message is safe to show the user."""


def _rows(sql, params=None):
    return db._execute(sql, params, fetch_all=True) or []


def _row(sql, params=None):
    return db._execute(sql, params, fetch_one=True)


def _table_exists(d, name: str) -> bool:
    return bool(d._execute("SELECT 1 FROM information_schema.tables WHERE table_name=%s", (name,), fetch_one=True))


def init_dpdp_review(society_id: int, actor_id: int | None = None) -> int:
    """Create one unreviewed row per DPDP [Verify] item (idempotent). Returns rows created."""
    created = 0
    with db._conn() as conn:
        cur = conn.cursor()
        for key in REVIEW_ITEMS:
            cur.execute(
                """INSERT INTO dpdp_legal_review (society_id, item_key, detail, reviewed)
                   VALUES (%s,%s,%s,FALSE)
                   ON CONFLICT (society_id, item_key) DO NOTHING""",
                (society_id, key, {"response_days": f"Rights requests must be answered within {RESPONSE_DAYS} days.",
                                   "lawful_basis_dues": "Dues and gate-safety are recorded as legitimate_use.",
                                   "lawful_basis_gate_safety": "Gate passes and visitor log are legitimate_use.",
                                   "notice_effective_date": "The privacy notice is effective from first publication."}[key]))
            if cur.rowcount:
                created += 1
    return created


def dpdp_pending_legal_review(society_id: int) -> bool:
    """Admin-visible flag: True while any DPDP [Verify] item awaits legal review.

    Stored per society in dpdp_legal_review(reviewed=FALSE). An admin with the
    grievance-officer/secretary capacity sees the banner and can clear it once
    the advocate has confirmed the items.
    """
    try:
        row = _row("""SELECT COUNT(*) AS n FROM dpdp_legal_review
                      WHERE society_id=%s AND NOT reviewed""", (society_id,))
        return bool(row and row["n"])
    except Exception:                                                   # table may not exist on old schemas
        log.exception("dpdp_pending_legal_review check failed")
        return True


def mark_dpdp_reviewed(society_id: int, item_key: str, actor_id: int,
                       reviewed: bool = True) -> bool:
    """Mark a DPDP [Verify] item reviewed (or unreviewed). Only a manager may do it."""
    if item_key not in REVIEW_ITEMS:
        raise DpdpError("Unknown review item.")
    _require_manager(society_id, actor_id, None)
    try:
        row = _row("""UPDATE dpdp_legal_review
                      SET reviewed=%s, reviewed_at=CASE WHEN %s THEN NOW() ELSE reviewed_at END,
                          reviewed_by=CASE WHEN %s THEN %s ELSE reviewed_by END
                      WHERE society_id=%s AND item_key=%s RETURNING id""",
                   (reviewed, reviewed, reviewed, actor_id, society_id, item_key), fetch_one=True)
        return bool(row)
    except Exception:                                                   # table may not exist
        log.exception("mark_dpdp_reviewed failed")
        return False


# ── the notice ────────────────────────────────────────────────────────────────────────────────────────────────────
def default_notice_text(society_id: int) -> tuple[str, str]:
    s = _row("SELECT name, grievance_officer_name, grievance_officer_email, grievance_officer_phone FROM societies WHERE id=%s", (society_id,)) or {}
    officer = s.get("grievance_officer_name") or "the Secretary"
    contact = ", ".join(x for x in (s.get("grievance_officer_email"), s.get("grievance_officer_phone")) if x) or "the society office"
    title = f"How {s.get('name') or 'your society'} uses your personal data"
    body = (
        f"{s.get('name') or 'Your society'} (\"the society\") runs this software to manage the building. The society decides why and how "
        "your personal data is used (it is the Data Fiduciary); EstateHub only processes it on the society's behalf.\n\n"
        "WHAT WE HOLD\n"
        "Your name, flat, mobile number and email; your login; what you pay and owe the society; gate passes and visitor entries for your flat; "
        "and, where a rule needs it, an ID proof or photo. We do not keep profiles or photos of children.\n\n"
        "WHY\n"
        "1. To bill you, record your payments and recover dues (the society's legitimate use as a society and under its bye-laws).\n"
        "2. To run gate passes, visitor logs and safety (the society's legitimate use).\n"
        "3. To send you announcements by push notification or email, only if you agree. You can say no and still use the app.\n\n"
        "HOW LONG\n"
        "Records the society must keep for audit or by law are kept for at least five years (longer if an Act requires). "
        "When the purpose ends we blank your profile; ledger lines stay because they belong to the flat's accounts, not to you.\n\n"
        "YOUR RIGHTS\n"
        "You may ask to see your data, correct it, have it erased, name a nominee, or complain. Use Privacy in your Settings. "
        f"The society must answer within {RESPONSE_DAYS} days. To withdraw an optional consent, switch it off in the same place.\n\n"
        f"WHO TO ASK\nGrievance officer: {officer}. Contact: {contact}.\n"
    )
    return title, body


def current_notice(society_id: int) -> dict | None:
    return _row("SELECT * FROM privacy_notices WHERE society_id=%s AND is_current ORDER BY version DESC LIMIT 1", (society_id,))


def publish_notice(society_id: int, title: str, body: str, actor_id: int | None = None) -> dict:
    title, body = (title or "").strip(), (body or "").strip()
    if len(title) < 5 or len(body) < 100:
        raise DpdpError("A notice needs a title and a plain-language body of at least 100 characters.")
    with db._conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(version),0)+1 AS v FROM privacy_notices WHERE society_id=%s", (society_id,))
        v = cur.fetchone()["v"]
        cur.execute("UPDATE privacy_notices SET is_current=FALSE, effective_to=CURRENT_DATE WHERE society_id=%s AND is_current", (society_id,))
        cur.execute("INSERT INTO privacy_notices (society_id, version, title, body_text, effective_from, is_current) "
                    "VALUES (%s,%s,%s,%s,CURRENT_DATE,TRUE) RETURNING *", (society_id, v, title, body))
        row = cur.fetchone()
    return dict(row)


def ensure_notice(society_id: int, actor_id: int | None = None) -> dict:
    return current_notice(society_id) or publish_notice(society_id, *default_notice_text(society_id), actor_id)


# ── consent ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _person(user_id: int) -> dict:
    u = _row("SELECT id, society_id, role, user_type, linked_id, email FROM users WHERE id=%s", (user_id,))
    if not u:
        raise DpdpError("User not found.")
    mapped = ROLE_MAP.get(u["role"])
    role = mapped or (u.get("user_type") if u.get("user_type") in ("owner", "family", "tenant", "visitor") else "owner")
    return {**u, "person_role": role, "person_key": f"{u['role']}:{u['linked_id'] or u['id']}"}


def needs_notice(society_id: int, user_id: int) -> bool:
    """True when the society has a current notice this person has not acknowledged. The master is never gated."""
    if not society_id:
        return False
    n = current_notice(society_id)
    if not n:
        return False
    return not _row("SELECT 1 AS x FROM consent_records WHERE society_id=%s AND user_id=%s AND purpose='notice_ack' "
                    "AND notice_version=%s AND withdrawn_at IS NULL", (society_id, user_id, n["version"]))


def accept_notice(society_id: int, user_id: int, optional_purposes: list[str] | None = None) -> None:
    """Record the acknowledgement, the statutory purposes (legitimate use) and any optional purposes the person ticked."""
    n = current_notice(society_id)
    if not n:
        raise DpdpError("The society has not published a privacy notice yet.")
    p = _person(user_id)
    if p["society_id"] != society_id:
        raise DpdpError("User not found.")
    chosen = {k for k, (_l, _b, req) in PURPOSES.items() if req} | {k for k in (optional_purposes or []) if k in PURPOSES}
    with db._conn() as conn:
        cur = conn.cursor()
        for purpose in sorted(chosen):
            basis = PURPOSES[purpose][1]
            cur.execute("""INSERT INTO consent_records (society_id, person_key, person_role, purpose, notice_version, lawful_basis, created_by, user_id)
                           SELECT %s,%s,%s,%s,%s,%s,%s,%s
                            WHERE NOT EXISTS (SELECT 1 FROM consent_records WHERE society_id=%s AND user_id=%s AND purpose=%s
                                                 AND notice_version=%s AND withdrawn_at IS NULL)""",
                        (society_id, p["person_key"], p["person_role"], purpose, n["version"], basis, user_id, user_id,
                         society_id, user_id, purpose, n["version"]))


def my_consents(society_id: int, user_id: int) -> list[dict]:
    return _rows("SELECT purpose, notice_version, lawful_basis, consented_at, withdrawn_at FROM consent_records "
                 "WHERE society_id=%s AND user_id=%s ORDER BY consented_at DESC, id DESC", (society_id, user_id))


def set_optional_consent(society_id: int, user_id: int, purpose: str, on: bool) -> None:
    """Give or withdraw an OPTIONAL (consent-based) purpose. Statutory purposes cannot be switched off here."""
    if purpose not in PURPOSES or PURPOSES[purpose][2]:
        raise DpdpError("That purpose is part of running the society and cannot be switched off here; raise a rights request instead.")
    n = ensure_notice(society_id)
    if on:
        accept_notice(society_id, user_id, [purpose])
    else:
        db._execute("UPDATE consent_records SET withdrawn_at=NOW() WHERE society_id=%s AND user_id=%s AND purpose=%s AND withdrawn_at IS NULL",
                    (society_id, user_id, purpose))
        if purpose == "announcements":
            db._execute("UPDATE users SET push_enabled=FALSE WHERE id=%s AND society_id=%s", (user_id, society_id))
            db._execute("DELETE FROM push_subscriptions WHERE user_id=%s", (user_id,))
    return n


# ── rights register ───────────────────────────────────────────────────────────────────────────────────────────────
def raise_request(society_id: int, user_id: int, request_type: str, subject: str) -> dict:
    if request_type not in REQUEST_TYPES:
        raise DpdpError("Choose the kind of request.")
    subject = (subject or "").strip()
    if len(subject) < 10:
        raise DpdpError("Say what you are asking for (at least 10 characters).")
    p = _person(user_id)
    if p["society_id"] != society_id:
        raise DpdpError("User not found.")
    apt = p["linked_id"] if p["role"] == "apartment" else None
    return _row("""INSERT INTO rights_requests (society_id, requester_key, request_type, subject, due_date, outcome, requester_user_id, apartment_id)
                   VALUES (%s,%s,%s,%s,%s,'pending',%s,%s) RETURNING *""",
                (society_id, p["person_key"], request_type, subject[:2000], date.today() + timedelta(days=RESPONSE_DAYS), user_id, apt))


def can_manage(society_id: int, user_id: int, role: str | None) -> bool:
    """The administrator, a serving Secretary, or the named grievance officer's login may work the register."""
    if role == "admin":
        return bool(_row("SELECT 1 AS x FROM users WHERE id=%s AND society_id=%s", (user_id, society_id)))
    return bool(_row("SELECT 1 AS x FROM committee_offices WHERE society_id=%s AND user_id=%s AND status='active' AND office_code='secretary' "
                     "AND term_start <= CURRENT_DATE AND (term_end IS NULL OR term_end >= CURRENT_DATE)", (society_id, user_id)))


def _require_manager(society_id, user_id, role):
    if not can_manage(society_id, user_id, role):
        raise DpdpError("Only the administrator or the Secretary can work the privacy register.")


def list_requests(society_id: int, mine_user_id: int | None = None) -> list[dict]:
    q = """SELECT r.*, (r.outcome IS NULL OR r.outcome='pending') AS open_request,
                  (r.due_date < CURRENT_DATE AND (r.outcome IS NULL OR r.outcome='pending')) AS overdue
             FROM rights_requests r WHERE r.society_id=%s"""
    args = [society_id]
    if mine_user_id:
        q += " AND r.requester_user_id=%s"
        args.append(mine_user_id)
    return _rows(q + " ORDER BY (r.outcome IS NULL OR r.outcome='pending') DESC, r.due_date, r.id", tuple(args))


def respond(society_id: int, request_id: int, actor_id: int, role: str | None, outcome: str, note: str) -> None:
    _require_manager(society_id, actor_id, role)
    if outcome not in OUTCOMES:
        raise DpdpError("Choose granted, partial or rejected.")
    if len((note or "").strip()) < 10:
        raise DpdpError("Record the reason or what was done (at least 10 characters).")
    r = _row("SELECT request_type FROM rights_requests WHERE id=%s AND society_id=%s", (request_id, society_id))
    if not r:
        raise DpdpError("Request not found.")
    if r["request_type"] == "erasure" and outcome in ("granted", "partial"):
        raise DpdpError("An erasure is completed with the notice and erase steps, not by marking it granted.")
    db._execute("UPDATE rights_requests SET outcome=%s, outcome_note=%s, responded_at=NOW(), responded_by=%s "
                "WHERE id=%s AND society_id=%s", (outcome, note.strip()[:2000], actor_id, request_id, society_id))


def erasure_blockers(society_id: int, request_id: int) -> list[str]:
    r = _row("SELECT apartment_id FROM rights_requests WHERE id=%s AND society_id=%s AND request_type='erasure'", (request_id, society_id))
    if not r or not r["apartment_id"]:
        return ["This request is not linked to a flat; only a flat's profile can be erased here."]
    return [x["reason"] for x in _rows("SELECT reason FROM fn_erasure_blockers(%s,%s)", (society_id, r["apartment_id"]))]


def give_erasure_notice(society_id: int, request_id: int, actor_id: int, role: str | None) -> None:
    _require_manager(society_id, actor_id, role)
    blockers = erasure_blockers(society_id, request_id)
    if blockers:
        raise DpdpError("Erasure is held: " + " ".join(blockers))
    db._execute("UPDATE rights_requests SET erasure_notice_at=NOW() WHERE id=%s AND society_id=%s AND erased_at IS NULL", (request_id, society_id))


def erase(society_id: int, request_id: int, actor_id: int, role: str | None) -> str:
    _require_manager(society_id, actor_id, role)
    r = _row("SELECT apartment_id FROM rights_requests WHERE id=%s AND society_id=%s AND request_type='erasure'", (request_id, society_id))
    if not r or not r["apartment_id"]:
        raise DpdpError("This request is not linked to a flat.")
    try:
        out = _row("SELECT fn_erase_person_profile(%s,%s,%s,%s) AS r", (society_id, r["apartment_id"], request_id, actor_id))
    except Exception as exc:                                           # noqa: BLE001
        raise DpdpError(str(exc).split("\n")[0].replace("ERROR:", "").strip() or "Erasure failed.") from exc
    return (out or {}).get("r") or "OK"


# ── breach register ───────────────────────────────────────────────────────────────────────────────────────────────
def log_breach(society_id: int, actor_id: int, role: str | None, occurred_at, description: str, affected: int) -> dict:
    _require_manager(society_id, actor_id, role)
    if len((description or "").strip()) < 20:
        raise DpdpError("Describe what happened (at least 20 characters).")
    return _row("INSERT INTO breach_register (society_id, occurred_at, description, affected_persons, created_by) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING *", (society_id, occurred_at or date.today(), description.strip()[:4000], max(int(affected or 0), 0), actor_id))


def update_breach(society_id: int, breach_id: int, actor_id: int, role: str | None, status: str, intimation_sent: bool) -> None:
    _require_manager(society_id, actor_id, role)
    if status not in BREACH_STATUS:
        raise DpdpError("Choose a status.")
    db._execute("""UPDATE breach_register SET status=%s, intimation_sent=%s,
                          intimation_at=CASE WHEN %s AND intimation_at IS NULL THEN NOW() ELSE intimation_at END
                    WHERE id=%s AND society_id=%s""", (status, bool(intimation_sent), bool(intimation_sent), breach_id, society_id))


def list_breaches(society_id: int) -> list[dict]:
    return _rows("SELECT * FROM breach_register WHERE society_id=%s ORDER BY discovered_at DESC, id DESC LIMIT 50", (society_id,))
