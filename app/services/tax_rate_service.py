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
from database.money import D

from datetime import date, datetime, timedelta

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
    if principal.base_role == "master":      # platform operator: the drilldown has always let Master edit TDS rates
        return True, "Master"
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


IT2025_START = date(2026, 4, 1)      # the TDS engine reads only 'IT2025' rows from this date (fn_compute_tds_pct)


def _date(v, label: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a date (YYYY-MM-DD).")


def add_tds_rate(society_id: int, d: dict) -> int:
    """Add a TDS rate that takes effect on a given date. A section can carry several rates, each with its own
    effective date; the engine picks the one in force on the bill's date (and the Act that date falls under).

    `d` = {section, discriminator, nature_of_income, rate, rate_no_pan, single_bill_threshold,
           annual_aggregate_threshold, effective_from, act_version}.
    Required: section, rate, rate_no_pan, effective_from. act_version blank = the Act the date falls under
    (IT2025 from 1-Apr-2026, else IT1961). Blank nature / thresholds are taken from the nearest existing rate of the
    same section, discriminator and Act; with no such rate the single-bill threshold is required.
    The neighbouring rates' end dates are kept consistent: the rate before it ends the day before this one starts, and
    this one ends the day before the next one starts. Returns the new row id."""
    _require(society_id)
    section = (d.get("section") or "").strip()
    if not section or len(section) > 10:
        raise ValueError("Enter the section (up to 10 characters), e.g. 194C.")
    disc = (d.get("discriminator") or "").strip() or None
    if disc and len(disc) > 50:
        raise ValueError("Discriminator is too long.")
    if d.get("effective_from") in (None, ""):
        raise ValueError("Enter the date this rate takes effect.")
    eff = _date(d.get("effective_from"), "Effective from")
    act = (d.get("act_version") or "").strip() or ("IT2025" if eff >= IT2025_START else "IT1961")
    if act not in ("IT1961", "IT2025"):
        raise ValueError("Act must be IT1961 or IT2025.")
    rate = _num(d.get("rate"), "TDS rate", 0, 100)
    nopan = _num(d.get("rate_no_pan"), "TDS rate without PAN", 0, 100)
    if rate is None or nopan is None:
        raise ValueError("Enter both the TDS rate and the rate without PAN. No rate is assumed.")
    single = _num(d.get("single_bill_threshold"), "Single-bill threshold")
    annual = _num(d.get("annual_aggregate_threshold"), "Annual threshold")

    key = (society_id, section, disc, disc, act)
    same = ("society_id = %s AND section = %s AND (discriminator = %s OR (discriminator IS NULL AND %s IS NULL)) "
            "AND act_version = %s")
    if db._execute(f"SELECT 1 AS x FROM tds_section_rates WHERE {same} AND effective_from = %s LIMIT 1",
                   (*key, eff), fetch_one=True):
        raise ValueError(f"A {act} rate for {section} effective {eff:%d %b %Y} already exists. Edit that row instead.")

    # nearest existing rate of the same kind: the previous one if any, else the next one
    prev = db._execute(f"SELECT id, nature_of_income, single_bill_threshold, annual_aggregate_threshold, "
                       f"threshold_inclusive, threshold_basis, section_2025, effective_to FROM tds_section_rates "
                       f"WHERE {same} AND effective_from < %s ORDER BY effective_from DESC LIMIT 1",
                       (*key, eff), fetch_one=True)
    nxt = db._execute(f"SELECT id, nature_of_income, single_bill_threshold, annual_aggregate_threshold, "
                      f"threshold_inclusive, threshold_basis, section_2025, effective_from FROM tds_section_rates "
                      f"WHERE {same} AND effective_from > %s ORDER BY effective_from ASC LIMIT 1",
                      (*key, eff), fetch_one=True)
    base = prev or nxt
    if single is None:
        if not base:
            raise ValueError(f"Enter the single-bill threshold: there is no {act} rate for this section to take it from "
                             "(the limits differ between the 1961 and 2025 Acts, so they are not copied across).")
        single = D(base["single_bill_threshold"])
    if annual is None:
        annual = D(base["annual_aggregate_threshold"]) if base else D(0)
    nature = (d.get("nature_of_income") or "").strip() or (base or {}).get("nature_of_income")
    inclusive = bool(base["threshold_inclusive"]) if base else False
    basis = (base or {}).get("threshold_basis") or "bill"
    section_2025 = (base or {}).get("section_2025")

    to_date = (nxt["effective_from"] - timedelta(days=1)) if nxt else None
    row = db._execute(
        "INSERT INTO tds_section_rates (society_id, section, discriminator, nature_of_income, rate, rate_no_pan, "
        "single_bill_threshold, annual_aggregate_threshold, effective_from, effective_to, act_version, section_2025, "
        "threshold_inclusive, threshold_basis) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (society_id, section, disc, nature, rate, nopan, single, annual, eff, to_date, act, section_2025,
         inclusive, basis), fetch_one=True)
    new_id = int(row["id"])
    if prev and (prev.get("effective_to") is None or prev["effective_to"] >= eff):
        db._execute("UPDATE tds_section_rates SET effective_to = %s WHERE id = %s AND society_id = %s",
                    (eff - timedelta(days=1), prev["id"], society_id))
    mark_pending(society_id)
    audit_event("tds_rate.added", RESOURCE, society_id,
                after={"id": new_id, "section": section, "discriminator": disc, "act_version": act,
                       "effective_from": str(eff), "rate": rate, "rate_no_pan": nopan},
                permission_used=Cap.FINANCE_TAX_RATES_MANAGE, society_id=society_id)
    return new_id


def update_tds_rate(society_id: int, rate_id: int, d: dict) -> None:
    """Edit the VALUES of one existing TDS rate: rate, rate without PAN, limits, nature of payment.

    The section, discriminator and effective date identify the rate and keep the dated chain consistent (each rate
    ends the day before the next one starts), so they cannot be changed here: add a new dated rate instead
    (add_tds_rate). Sending them unchanged is fine."""
    _require(society_id)
    cur = db._execute("SELECT id, section, discriminator, effective_from FROM tds_section_rates "
                      "WHERE id = %s AND society_id = %s", (rate_id, society_id), fetch_one=True)
    if not cur:
        raise ValueError("That TDS rate does not belong to this society.")
    if (d.get("section") or "").strip() not in ("", cur["section"]) or \
       ((d.get("discriminator") or "").strip() or None) != (cur["discriminator"] or None) or \
       (d.get("effective_from") not in (None, "") and _date(d["effective_from"], "Effective from") != cur["effective_from"]):
        raise ValueError("The section, discriminator and effective date of a rate cannot be changed. "
                         "To start a new rate from another date, add a new rate.")
    rate = _num(d.get("rate"), "TDS rate", 0, 100)
    if rate is None:
        raise ValueError("Enter the TDS rate.")
    vals = {"rate": rate,
            "rate_no_pan": _num(d.get("rate_no_pan"), "TDS rate without PAN", 0, 100),
            "single_bill_threshold": _num(d.get("single_bill_threshold"), "Single-bill threshold"),
            "annual_aggregate_threshold": _num(d.get("annual_aggregate_threshold"), "Annual threshold")}
    given = {k: v for k, v in vals.items() if v is not None}
    nature = d.get("nature_of_income")
    sets = [f"{k} = %s" for k in given]
    params = list(given.values())
    if nature is not None:
        sets.append("nature_of_income = %s")
        params.append(nature.strip() or None)
    db._execute(f"UPDATE tds_section_rates SET {', '.join(sets)} WHERE id = %s AND society_id = %s",
                (*params, rate_id, society_id))
    mark_pending(society_id)
    audit_event("tds_rate.edited", RESOURCE, society_id, after={"id": rate_id, **given},
                permission_used=Cap.FINANCE_TAX_RATES_MANAGE, society_id=society_id)
