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


def secretary_fallback_allowed(society_id: int | None) -> bool:
    """The current user is the seated Secretary AND no Treasurer is seated. The capability is NOT consulted here."""
    if not society_id:
        return False
    try:
        principal = current_principal()
    except Exception:       # noqa: BLE001
        return False
    if principal is None or not principal.user_id:
        return False
    return _is_acting_secretary(society_id, principal.user_id) and not treasurer_seated(society_id)


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
        # The first rate (a society whose Admin left GST blank at setup) is in force from the first day of the
        # accounting-start month, like the one the Setup Wizard writes, so that earlier billing months find it.
        db._execute("INSERT INTO gst_rates (society_id, cgst_rate_pct, sgst_rate_pct, effective_from) "
                    "SELECT s.id, %s, %s, date_trunc('month', COALESCE(s.calc_start_date, CURRENT_DATE))::DATE "
                    "FROM societies s WHERE s.id = %s", (cgst, sgst, society_id))
    mark_pending(society_id)
    audit_event("gst_rates.edited", RESOURCE, society_id, before=dict(row) if row else None,
                after={"cgst": cgst, "sgst": sgst}, permission_used=Cap.FINANCE_TAX_RATES_MANAGE, society_id=society_id)


# -- what the "TDS & GST Rates" tab shows and saves -------------------------------------------------------------------
def tds_rows(society_id: int) -> list[dict]:
    rows = db._execute(
        "SELECT id, section, discriminator, nature_of_income, rate, rate_no_pan, single_bill_threshold, "
        "annual_aggregate_threshold, effective_from, effective_to, act_version FROM tds_section_rates "
        "WHERE society_id = %s ORDER BY section, discriminator NULLS FIRST, effective_from, id",
        (society_id,), fetch_all=True) or []
    return [dict(r) for r in rows]


def gst_row(society_id: int) -> dict | None:
    row = db._execute("SELECT cgst_rate_pct, sgst_rate_pct, effective_from FROM gst_rates WHERE society_id = %s "
                      "ORDER BY effective_from DESC, id DESC LIMIT 1", (society_id,), fetch_one=True)
    return dict(row) if row else None


def status(society_id: int) -> dict:
    """{'pending': bool, 'confirmed_at': datetime|None, 'confirmed_by': str|None}"""
    row = db._execute(
        "SELECT s.ca_rates_confirmed_at AS at, u.name AS who FROM societies s "
        "LEFT JOIN users u ON u.id = s.ca_rates_confirmed_by WHERE s.id = %s", (society_id,), fetch_one=True) or {}
    return {"pending": row.get("at") is None, "confirmed_at": row.get("at"), "confirmed_by": row.get("who")}


def _num(v, label: str, lo: float = 0.0, hi: float | None = None):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if f < lo or (hi is not None and f > hi):
        raise ValueError(f"{label} must be between {lo:g} and {hi:g}." if hi is not None else f"{label} cannot be below {lo:g}.")
    return f


def save_tds_rates(society_id: int, changes: list[dict]) -> int:
    """Edit TDS rows in place. `changes` = [{id, rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold}].
    A blank value leaves that column as it is. Only rows of THIS society are touched. -> number of rows changed."""
    _require(society_id)
    n, before_after = 0, []
    for ch in changes:
        try:
            rid = int(ch["id"])
        except (KeyError, TypeError, ValueError):
            continue
        vals = {
            "rate": _num(ch.get("rate"), "TDS rate", 0, 100),
            "rate_no_pan": _num(ch.get("rate_no_pan"), "TDS rate without PAN", 0, 100),
            "single_bill_threshold": _num(ch.get("single_bill_threshold"), "Single-bill threshold"),
            "annual_aggregate_threshold": _num(ch.get("annual_aggregate_threshold"), "Annual threshold"),
        }
        given = {k: v for k, v in vals.items() if v is not None}
        if not given:
            continue
        cur = db._execute("SELECT id, rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold "
                          "FROM tds_section_rates WHERE id = %s AND society_id = %s", (rid, society_id), fetch_one=True)
        if not cur:
            continue                      # not a row of this society: ignore, never touch
        if all(cur.get(k) is not None and float(cur[k]) == v for k, v in given.items()):
            continue                      # nothing actually changed
        sets = ", ".join(f"{k} = %s" for k in given)
        db._execute(f"UPDATE tds_section_rates SET {sets} WHERE id = %s AND society_id = %s",
                    (*given.values(), rid, society_id))
        before_after.append({"id": rid, "before": {k: cur.get(k) for k in given}, "after": given})
        n += 1
    if n:
        mark_pending(society_id)
        audit_event("tds_rates.edited", RESOURCE, society_id, after={"rows": before_after},
                    permission_used=Cap.FINANCE_TAX_RATES_MANAGE, society_id=society_id)
    return n
