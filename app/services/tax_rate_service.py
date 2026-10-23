# app/services/tax_rate_service.py
"""
Who may edit the society's TDS / GST rates, and the CA confirmation of them.

The figures are first typed by the Admin in the Setup Wizard and are PROVISIONAL until the CA confirms them
(societies.ca_rates_confirmed_at IS NULL means "pending CA confirmation"). After setup:

  * the CA (an accountant login) and the Treasurer may edit and confirm: capability finance.taxrates.manage;
  * the Secretary may do the same ONLY while no Treasurer is seated (committee_offices has no active 'treasurer');
  * nobody else: not the Admin (the Admin's route is the Setup Wizard, which resets the figures to pending), not the
    Auditor (read-only), not the other office-bearers.

The society always comes from the caller's server-side session. Nothing here trusts a browser value.
Any edit puts the figures back to "pending" until someone entitled confirms them again.
"""
from __future__ import annotations

from app.security.authorization import Cap
from app.security.service_guard import audit_event, check, current_principal
from database.db_manager import db

RESOURCE = "tax_rate_config"


def treasurer_seated(society_id: int) -> bool:
    row = db._execute(
        "SELECT 1 AS x FROM committee_offices WHERE society_id = %s AND office_code = 'treasurer' "
        "AND status = 'active' AND (term_end IS NULL OR term_end >= CURRENT_DATE) LIMIT 1",
        (society_id,), fetch_one=True)
    return bool(row)


def _is_acting_secretary(society_id: int, user_id: int) -> bool:
    row = db._execute(
        "SELECT 1 AS x FROM committee_offices WHERE society_id = %s AND office_code = 'secretary' "
        "AND status = 'active' AND (term_end IS NULL OR term_end >= CURRENT_DATE) AND user_id = %s LIMIT 1",
        (society_id, user_id), fetch_one=True)
    return bool(row)


def may_edit_tax_rates(society_id: int | None) -> tuple[bool, str]:
    """-> (allowed, reason) for the CURRENT session user in THIS society."""
    if not society_id:
        return False, "No society."
    try:
        principal = current_principal()
    except Exception:       # noqa: BLE001 - a policy outage is a denial
        return False, "Authorization is unavailable."
    if principal is None or not principal.user_id:
        return False, "Not signed in."
    if check(Cap.FINANCE_TAX_RATES_MANAGE, RESOURCE, target_society_id=society_id, audit_denials=False).allowed:
        return True, "CA / Treasurer"
    if _is_acting_secretary(society_id, principal.user_id):
        if treasurer_seated(society_id):
            return False, "A Treasurer is seated: the Treasurer or the CA edits the rates."
        return True, "Secretary (no Treasurer seated)"
    return False, "Only the CA, the Treasurer (or the Secretary when there is no Treasurer) can edit TDS / GST rates."


def _require(society_id: int | None) -> None:
    ok, why = may_edit_tax_rates(society_id)
    if not ok:
        audit_event("authz.denied", RESOURCE, society_id, reason=why, permission_used=Cap.FINANCE_TAX_RATES_MANAGE)
        raise PermissionError(why)


def ca_rates_pending(society_id: int) -> bool:
    """True while the TDS / GST figures have not been confirmed by the CA (or the Treasurer / Secretary)."""
    row = db._execute("SELECT ca_rates_confirmed_at FROM societies WHERE id = %s", (society_id,), fetch_one=True)
    return bool(row) and row.get("ca_rates_confirmed_at") is None


def mark_pending(society_id: int) -> None:
    """Called after any edit: the figures are provisional again until confirmed."""
    db._execute("UPDATE societies SET ca_rates_confirmed_at = NULL, ca_rates_confirmed_by = NULL WHERE id = %s",
                (society_id,))


def confirm_ca_rates(society_id: int) -> None:
    """Stamp the figures as confirmed. Same people as editing; the user is the server session's, never a parameter."""
    _require(society_id)
    principal = current_principal()
    db._execute("SELECT fn_confirm_ca_rates(%s, %s)", (society_id, principal.user_id), fetch_one=True)
    audit_event("tax_rates.confirmed", RESOURCE, society_id, permission_used=Cap.FINANCE_TAX_RATES_MANAGE,
                society_id=society_id)


def save_gst_rates(society_id: int, cgst, sgst) -> None:
    """Edit CGST / SGST. TDS rows are edited through the TDS rate card (see _save_tds_rate), under the same rule."""
    _require(society_id)
    try:
        cgst, sgst = float(cgst), float(sgst)
    except (TypeError, ValueError):
        raise ValueError("CGST and SGST must be numbers.")
    if cgst < 0 or sgst < 0:
        raise ValueError("CGST and SGST cannot be negative.")
    row = db._execute("SELECT id, cgst_rate_pct, sgst_rate_pct FROM gst_rates WHERE society_id = %s "
                      "ORDER BY effective_from DESC, id DESC LIMIT 1", (society_id,), fetch_one=True)
    if row:
        db._execute("UPDATE gst_rates SET cgst_rate_pct = %s, sgst_rate_pct = %s WHERE id = %s", (cgst, sgst, row["id"]))
    else:
        db._execute("INSERT INTO gst_rates (society_id, cgst_rate_pct, sgst_rate_pct, effective_from) "
                    "VALUES (%s, %s, %s, CURRENT_DATE)", (society_id, cgst, sgst))
    mark_pending(society_id)
    audit_event("gst_rates.edited", RESOURCE, society_id, before=dict(row) if row else None,
                after={"cgst": cgst, "sgst": sgst}, permission_used=Cap.FINANCE_TAX_RATES_MANAGE, society_id=society_id)
