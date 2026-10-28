"""Statute catalogue verification (Plan v3, task 2.7).

Only the Treasurer (a serving office-bearer) or an Auditor can mark an instrument verified, and only with the source link,
notification number, date and an opinion reference. The database refuses a 'verified' row that lacks any of these, and
returns a row to 'unverified' when its substance is edited. Unverified rows are labelled in the wizard and carry no link."""
from __future__ import annotations

from datetime import date

from app.services import document_signing as ds


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def verifier_role(society_id: int, user_id: int, db=None) -> str | None:
    d = _db(db)
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") == "auditor":
        return "auditor"
    if any(o["office_code"] == "treasurer" for o in ds.serving_offices(society_id, user_id, db=d)):
        return "treasurer"
    return None


def verify(society_id, user_id, instrument_id, notification_no, source_url, opinion_ref, verified_on=None, db=None) -> str:
    d = _db(db)
    role = verifier_role(society_id, user_id, d)
    if not role:
        raise ds.SigningRefused("Only the Treasurer or an Auditor can verify an instrument.")
    try:
        r = d._execute("SELECT fn_verify_instrument(%s,%s,%s,%s,%s,%s,%s) AS r",
                       (int(instrument_id), user_id, role, (notification_no or "").strip(), (source_url or "").strip(),
                        (opinion_ref or "").strip(), verified_on or date.today()), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise ds.SigningRefused(str(exc).split("\n")[0].replace("ERROR:", "").strip()) from exc
    d._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
               "VALUES (%s,%s,'INSTRUMENT_VERIFIED','legal_instrument_catalog',%s,%s::jsonb,'app')",
               (society_id, user_id, str(instrument_id), '{"role": "%s", "notification_no": "%s"}' % (role, (notification_no or "").replace('"', ""))))
    return r["r"]
