# app/services/committee_service.py
"""
The Managing Committee (President, Vice President, Secretary, Joint Secretary, Treasurer, Working Committee).

Two records describe an office-bearer and they must move together:

  * committee_offices        - who holds which seat, for which flat, since when (the legal record; written by the
                               database function fn_appoint_office_bearer, which enforces bye-law 7 and that the
                               holder belongs to the flat they represent, and ended by fn_end_office);
  * user_role_assignments    - what the holder's login may DO (society_president / society_secretary / treasurer /
                               committee_member), which is what authorization.py reads.

appoint() writes both in ONE transaction, so a seat is never recorded without its powers or the reverse. end_office()
closes the seat and revokes the power the seat conferred, unless the person still holds another seat that confers it
or was given it some other way (only assignments this service made - source 'aoa' - are ever revoked).

Admin of the SAME society only (rra._require_writer, master_ok=False): the committee is the society's own governance.
The society always comes from the caller's server-side session, never from a browser value.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from flask import has_request_context

from app.security.authorization import Cap
from app.security.service_guard import audit_event
from app.services.regime_rules_admin import _require_writer
from database.db_manager import db

# (office_code, label, single_seat, role_definitions.code the seat confers)
OFFICES = (
    ("president",                "President",                 True,  "society_president"),
    ("vice_president",           "Vice President",            True,  "committee_member"),
    ("secretary",                "Secretary",                 True,  "society_secretary"),
    ("joint_secretary",          "Joint Secretary",           True,  "committee_member"),
    ("treasurer",                "Treasurer",                 True,  "treasurer"),
    ("working_committee_member", "Working Committee Member",  False, "committee_member"),
)
OFFICE_LABEL = {c: label for c, label, _s, _r in OFFICES}
OFFICE_ROLE = {c: role for c, _l, _s, role in OFFICES}
SINGLE_SEAT = tuple(c for c, _l, single, _r in OFFICES if single)
# The seats a society is expected to have filled; the rest are optional.
CORE_OFFICES = ("president", "secretary", "treasurer")
SOURCE = "aoa"
MIN_REASON = 5

_UNIQUE_MESSAGES = {
    "uq_committee_single_seat": "That seat is already held. End the current holder's office first, then appoint.",
    "uq_committee_flat_office": "This flat already holds that office.",
}


def _rows(sql, params=None) -> list[dict]:
    return db._execute(sql, params, fetch_all=True) or []


def _row(sql, params=None) -> dict | None:
    return db._execute(sql, params, fetch_one=True)


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _invalidate_permission_cache() -> None:
    try:
        from app.security import policy
        policy._invalidate_cache()
    except Exception:       # a cache that is not there cannot be stale
        pass


def _audit(cur, action: str, office_id, after: dict) -> None:
    """Append the audit row INSIDE the caller's transaction, so the change and its record commit or roll back together
    (a failure here rolls the appointment back too: no un-audited change of who holds office). Skipped only when there
    is no web request to take the actor from (scripts, tests); every UI path has one. Contains no contact details."""
    if has_request_context():
        audit_event(action, "committee_office", office_id, after=after, permission_used=Cap.ROLES_MANAGE, cur=cur)


def _db_message(exc: Exception) -> str:
    """The sentence the database raised (our fn_* functions RAISE EXCEPTION in plain English), or a safe fallback."""
    diag = getattr(exc, "diag", None)
    constraint = getattr(diag, "constraint_name", None)
    if constraint in _UNIQUE_MESSAGES:
        return _UNIQUE_MESSAGES[constraint]
    primary = getattr(diag, "message_primary", None)
    if primary:
        return primary
    return "The appointment could not be saved."


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────────────────
def current_committee(society_id: int) -> list[dict]:
    """Serving office-bearers today with their flat's standing (fn_committee_current), president first."""
    rows = _rows("SELECT * FROM fn_committee_current(%(sid)s)", {"sid": int(society_id)})
    for r in rows:
        r["office_label"] = OFFICE_LABEL.get(r["office_code"], r["office_code"])
    return rows


def committee_history(society_id: int, limit: int = 10) -> list[dict]:
    rows = _rows(
        """SELECT o.office_code, o.holder_name, a.flat_number, o.term_start, o.term_end, o.ended_reason
             FROM committee_offices o JOIN apartments a ON a.id = o.apartment_id
            WHERE o.society_id = %(sid)s AND o.status = 'ended'
            ORDER BY o.ended_at DESC NULLS LAST, o.id DESC LIMIT %(n)s""",
        {"sid": int(society_id), "n": int(limit)})
    for r in rows:
        r["office_label"] = OFFICE_LABEL.get(r["office_code"], r["office_code"])
    return rows


def vacant_core_offices(society_id: int) -> list[str]:
    """Labels of the President / Secretary / Treasurer seats nobody holds today."""
    held = {r["office_code"] for r in current_committee(society_id)}
    return [OFFICE_LABEL[c] for c in CORE_OFFICES if c not in held]


def summary(society_id: int) -> dict:
    committee = current_committee(society_id)
    return {"seated": len(committee), "vacant_core": vacant_core_offices(society_id),
            "in_arrears": sum(1 for r in committee if r.get("ineligible_stand"))}


def flat_choices(society_id: int) -> list[dict]:
    """Every active flat with its owner and today's standing, for the appointment form."""
    return _rows(
        """SELECT a.id, a.flat_number, a.owner_name, s.ineligible_stand, s.dues_outstanding
             FROM apartments a
             LEFT JOIN LATERAL fn_get_standing(%(sid)s, a.id, CURRENT_DATE) s ON TRUE
            WHERE a.society_id = %(sid)s AND a.active
            ORDER BY a.flat_number""",
        {"sid": int(society_id)})


def flat_detail(society_id: int, apartment_id: int) -> dict | None:
    """One flat of THIS society: its owner, today's standing and the owner logins that could hold the office."""
    flat = _row(
        """SELECT a.id, a.flat_number, a.owner_name, s.ineligible_stand, s.dues_outstanding, s.loan_outstanding
             FROM apartments a
             LEFT JOIN LATERAL fn_get_standing(%(sid)s, a.id, CURRENT_DATE) s ON TRUE
            WHERE a.id = %(aid)s AND a.society_id = %(sid)s AND a.active""",
        {"sid": int(society_id), "aid": int(apartment_id)})
    if not flat:
        return None
    flat["users"] = _rows(
        """SELECT id, name, email FROM users
            WHERE society_id = %(sid)s AND role = 'apartment' AND user_type = 'owner' AND linked_id = %(aid)s
            ORDER BY id""",
        {"sid": int(society_id), "aid": int(apartment_id)})
    return flat


# ── writing ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _grant(cur, user_id: int, role_code: str, society_id: int, granted_by) -> None:
    cur.execute("SELECT id FROM role_definitions WHERE code = %(c)s AND scope = 'society'", {"c": role_code})
    rd = cur.fetchone()
    if not rd:
        raise RuntimeError(f"role_definitions has no society role '{role_code}'")
    cur.execute(
        """INSERT INTO user_role_assignments (user_id, role_definition_id, society_id, source, status, granted_by)
           SELECT %(u)s, %(r)s, %(s)s, %(src)s, 'active', %(g)s
            WHERE NOT EXISTS (SELECT 1 FROM user_role_assignments x
                               WHERE x.user_id = %(u)s AND x.role_definition_id = %(r)s AND x.society_id = %(s)s
                                 AND x.status = 'active' AND (x.effective_to IS NULL OR x.effective_to > NOW()))
           ON CONFLICT (user_id, role_definition_id, society_id, entity_link, effective_from) DO NOTHING""",
        {"u": user_id, "r": rd["id"], "s": society_id, "src": SOURCE, "g": granted_by})


def clean_email(v):
    """Normalised email, or False when it is not plausible."""
    v = (v or "").strip().lower()
    return v if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", v) and len(v) <= 100 else False


def clean_phone(v):
    """Digits with an optional leading +, or False when it is not plausible."""
    v = re.sub(r"[\s\-()]", "", (v or ""))
    return v if re.fullmatch(r"\+?\d{8,15}", v) else False


def owner_prefill(society_id, apartment_id) -> dict:
    """Name / email / phone of the flat's owner login, to prefill the office-bearer form (the Secretary edits the phone)."""
    r = _row("SELECT u.name, u.email, a.mobile AS phone FROM apartments a LEFT JOIN users u ON u.society_id=a.society_id "
             "AND u.role='apartment' AND u.linked_id=a.id WHERE a.society_id=%s AND a.id=%s ORDER BY u.id LIMIT 1",
             (society_id, apartment_id)) or {}
    ph = clean_phone(r.get("phone"))
    return {"name": r.get("name"), "email": r.get("email"), "phone": ph or None}


def appoint(actor_id, actor_role, society_id, apartment_id, office_code, holder_name, user_id=None,
            term_start=None, term_end=None, resolution_ref=None, actor_society_id=None,
            email=None, phone=None, signature_image=None, evidence_file=None, evidence_hash=None) -> tuple[bool, str]:
    """Seat `holder_name` (the owner of `apartment_id`) in `office_code`. Returns (ok, str)."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    if office_code not in OFFICE_LABEL:
        return False, "Choose an office."
    try:
        sid, aid = int(society_id), int(apartment_id)
    except (TypeError, ValueError):
        return False, "Choose the flat the office-bearer represents."
    name = (holder_name or "").strip()
    if not name:
        return False, "The office-bearer's name is required."
    start = _date(term_start) or date.today()
    end = _date(term_end)
    if term_end and end is None:
        return False, "The term end is not a valid date."
    if end is not None and end <= start:
        return False, "The term must end after it starts."
    uid = int(user_id) if user_id not in (None, "") else None
    ref = (resolution_ref or "").strip()[:255] or None
    role_code = OFFICE_ROLE[office_code]
    pre = owner_prefill(sid, aid)
    email = clean_email(email) if (email or "").strip() else pre.get("email")
    phone = clean_phone(phone) if (phone or "").strip() else pre.get("phone")
    if email is False or phone is False:
        return False, "The email or phone number is not valid."
    sig = (signature_image or "").strip()[:255] or None
    ev_file = (evidence_file or "").strip()[:255] or None
    ev_hash = (evidence_hash or "").strip() or None
    if ev_hash and len(ev_hash) != 64:
        return False, "Evidence hash must be a 64-character SHA-256."
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT fn_appoint_office_bearer(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS id",
                        (sid, aid, office_code, name, uid, start, end, ref, None, actor_id))
            office_id = (cur.fetchone() or {}).get("id")
            cur.execute("UPDATE committee_offices SET email=%s, phone=%s, signature_image=%s, "
                        "evidence_file=%s, evidence_hash=%s WHERE id=%s AND society_id=%s",
                        (email, phone, sig, ev_file, ev_hash, office_id, sid))
            if uid is not None:
                _grant(cur, uid, role_code, sid, actor_id)
            _audit(cur, "committee.appoint", office_id,
                   {"office": office_code, "apartment_id": aid, "user_id": uid, "term_start": str(start),
                    "term_end": str(end) if end else None, "resolution_ref": ref,
                    "evidence_file": ev_file, "evidence_hash": ev_hash, "role_conferred": role_code})
    except Exception as exc:
        return False, _db_message(exc)
    _invalidate_permission_cache()
    powers = "" if uid is not None else (" No login is linked, so this office-bearer cannot sign or approve "
                                         "anything until a flat owner login is chosen.")
    return True, f"{name} is now {OFFICE_LABEL[office_code]}.{powers}"


def end_office(actor_id, actor_role, society_id, office_id, reason, actor_society_id=None) -> tuple[bool, str]:
    """Close a seat. The holder keeps their flat and login; the powers the seat conferred are revoked."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    why = (reason or "").strip()
    if len(why) < MIN_REASON:
        return False, f"Say why the office is ending (at least {MIN_REASON} characters)."
    try:
        sid, oid = int(society_id), int(office_id)
    except (TypeError, ValueError):
        return False, "Choose the office to end."
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT office_code, holder_name, user_id FROM committee_offices "
                        "WHERE id = %s AND society_id = %s AND status = 'active'", (oid, sid))
            office = cur.fetchone()
            if not office:
                return False, "That office is not active in your society."
            cur.execute("SELECT fn_end_office(%s,%s,%s) AS ended", (oid, sid, why))
            cur.fetchone()
            uid, role_code = office["user_id"], OFFICE_ROLE[office["office_code"]]
            if uid is not None:
                # Keep the power if the person still holds another seat that confers it.
                cur.execute("SELECT office_code FROM committee_offices WHERE society_id = %s AND user_id = %s "
                            "AND status = 'active'", (sid, uid))
                still = {OFFICE_ROLE[r["office_code"]] for r in cur.fetchall()}
                if role_code not in still:
                    cur.execute(
                        """UPDATE user_role_assignments ura SET status = 'revoked', effective_to = NOW()
                             FROM role_definitions rd
                            WHERE rd.id = ura.role_definition_id AND rd.code = %s AND rd.scope = 'society'
                              AND ura.user_id = %s AND ura.society_id = %s AND ura.source = %s
                              AND ura.status = 'active'""",
                        (role_code, uid, sid, SOURCE))
            _audit(cur, "committee.end", oid, {"office": office["office_code"], "user_id": uid, "reason": why})
    except Exception as exc:
        return False, _db_message(exc)
    _invalidate_permission_cache()
    return True, f"{office['holder_name']} is no longer {OFFICE_LABEL[office['office_code']]}."


def update_office(actor_id, actor_role, society_id, office_id, holder_name=None, term_end=None,
                  resolution_ref=None, actor_society_id=None, email=None, phone=None, signature_image=None) -> tuple[bool, str]:
    """Correct the details of an ACTIVE seat (name, planned term end, resolution reference).

    The office, the flat and the login are not editable: they decide who holds power, so changing them means ending
    the seat and appointing again (end_office / appoint), which is audited and re-grants the role."""
    _require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    try:
        sid, oid = int(society_id), int(office_id)
    except (TypeError, ValueError):
        return False, "Choose the office to edit."
    row = _row("SELECT holder_name, term_start, term_end, resolution_ref, email, phone, signature_image FROM committee_offices "
               "WHERE id = %s AND society_id = %s AND status = 'active'", (oid, sid))
    if not row:
        return False, "That office is not active in your society."
    name = (holder_name if holder_name is not None else row["holder_name"] or "").strip()
    if not name:
        return False, "The office-bearer's name is required."
    end = row["term_end"]
    if term_end is not None:
        end = _date(term_end)
        if str(term_end).strip() and end is None:
            return False, "The term end is not a valid date."
    if end is not None and end < row["term_start"]:
        return False, "The term must not end before it starts."
    ref = row["resolution_ref"] if resolution_ref is None else ((resolution_ref or "").strip()[:255] or None)
    em = row["email"] if email is None else (clean_email(email) if (email or "").strip() else None)
    ph = row["phone"] if phone is None else (clean_phone(phone) if (phone or "").strip() else None)
    if em is False or ph is False:
        return False, "The email or phone number is not valid."
    sg = row["signature_image"] if signature_image is None else ((signature_image or "").strip()[:255] or None)
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE committee_offices SET holder_name = %s, term_end = %s, resolution_ref = %s, "
                        "email = %s, phone = %s, signature_image = %s "
                        "WHERE id = %s AND society_id = %s AND status = 'active'", (name, end, ref, em, ph, sg, oid, sid))
            _audit(cur, "committee.update", oid, {"holder_name": name, "term_end": str(end) if end else None,
                                                  "resolution_ref": ref})
    except Exception as exc:
        return False, _db_message(exc)
    return True, "Office details updated."
