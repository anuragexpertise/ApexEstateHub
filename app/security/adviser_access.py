# app/security/adviser_access.py
"""
What an adviser (Auditor, CA, Advocate) may see, and for how long (Plan v5, V5.9).

A login with role 'adviser' works only while its appointment is IN FORCE: not revoked, between term_start and term_end, and
sealed by the office-bearers' signatures (fn_adviser_in_force). That is checked at sign-in and again on every callback, so a
login stops on the term's last day without anyone doing anything. The reach of each kind is fixed here, in one table:

    auditor, ca   the books (ledger, statements, receipts, expenses), resolutions and agreements, read only, owner names masked
    advocate      resolutions, agreements and legal records only. EVERY ledger read is refused.
"""
from __future__ import annotations

import logging

from database.db_manager import db

log = logging.getLogger(__name__)

CAPABILITIES = {
    "auditor":  frozenset({"ledger", "statements", "resolutions", "agreements", "appointments", "export"}),
    "ca":       frozenset({"ledger", "statements", "resolutions", "agreements", "appointments", "export"}),
    "advocate": frozenset({"resolutions", "agreements", "appointments"}),
}
LEDGER_CAPS = frozenset({"ledger", "statements", "export"})


class AdviserRefused(PermissionError):
    """The adviser may not do this (or has no appointment in force); the message is safe to show."""


def in_force(user_id: int) -> dict | None:
    try:
        row = db._execute("SELECT * FROM fn_adviser_in_force(%s)", (user_id,), fetch_one=True)
    except Exception:                                                       # noqa: BLE001 - fail closed
        log.exception("adviser appointment lookup failed for user %s", user_id)
        return None
    return dict(row) if row and row.get("appointment_id") else None


def appointment(user_id: int) -> dict | None:
    """The appointment row (any state) for this login, newest first, for the adviser's own screen."""
    return db._execute("SELECT * FROM adviser_appointments WHERE login_user_id=%s ORDER BY term_end DESC LIMIT 1", (user_id,), fetch_one=True)


def may(user_id: int, capability: str) -> bool:
    cur = in_force(user_id)
    return bool(cur and capability in CAPABILITIES.get(cur["kind"], frozenset()))


def require(user_id: int, capability: str) -> dict:
    cur = in_force(user_id)
    if not cur:
        raise AdviserRefused("Your appointment is not in force (ended, revoked or not yet signed). Ask the society.")
    if capability not in CAPABILITIES.get(cur["kind"], frozenset()):
        what = "the ledger" if capability in LEDGER_CAPS else capability
        raise AdviserRefused(f"An {cur['kind'].title()} cannot read {what} for this society.")
    return cur


def expire_due(today=None) -> dict:
    """Daily job: end every appointment whose term is over and switch its login off. Returns what it did."""
    rows = db._execute(
        """UPDATE adviser_appointments SET active=FALSE, revoked_at=NOW(), revoked_reason='Term ended'
            WHERE active AND term_end < COALESCE(%s::date, CURRENT_DATE) RETURNING id, society_id, login_user_id""",
        (today,), fetch_all=True) or []
    for r in rows:
        if r["login_user_id"]:
            db._execute("UPDATE users SET active=FALSE WHERE id=%s", (r["login_user_id"],))
        db._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
                    "VALUES (%s,NULL,'ADVISER_TERM_ENDED','adviser_appointment',%s,'{}'::jsonb,'system')", (r["society_id"], str(r["id"])))
    return {"ended": len(rows)}
