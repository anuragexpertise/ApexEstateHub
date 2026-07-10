# app/dash_apps/drilldown/loaders.py
"""
THIN LOADERS — Database queries only, no business logic.
All heavy calculations are done in PostgreSQL functions.

Entity map for load_list():
  apartments      → fn_apartments_list
  vendors         → fn_vendors_list
  security        → fn_security_list
  events          → fn_events_list
  concerns        → concerns table
  gate_logs       → fn_gate_logs_named
  receipts        → fn_receipts_list
  expenses        → fn_expenses_list
  cashbook        → fn_cashbook_paired
  receivables     → fn_receivables_named   (read-only, all portals)
  payables        → fn_payables_named      (read-only, all portals)
  assets          → fn_asset_list          (admin CRUD + view)
  accounts        → fn_accounts_list
  societies       → fn_societies_list
  apt_charges     → fn_apt_charges_list
  ven_charges     → fn_ven_charges_list
"""

from __future__ import annotations
from datetime import date
from database.db_manager import db

PAGE_SIZE = 15

DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operationalerror",
]


def _is_db_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(kw in s for kw in DB_ERROR_KEYWORDS)


def _sid(f): return f.get("society_id")
def _apt_id(f): return f.get("apartment_id")
def _ven_id(f): return f.get("vendor_id")
def _eid(f): return f.get("entity_id")
def _sec_id(f): return f.get("security_id")


# ════════════════════════════════════════════════════════════════════════════
# LOAD LIST
# ════════════════════════════════════════════════════════════════════════════

def load_list(
    entity: str,
    filters: dict,
    page: int = 1,
    search: str = "",
    page_size: int = PAGE_SIZE,
) -> tuple[list, int]:
    sid    = _sid(filters)
    apt_id = _apt_id(filters)
    ven_id = _ven_id(filters)
    sec_id = _sec_id(filters)
    eid    = _eid(filters)
    offset = (page - 1) * page_size
    s      = search or None

    try:
        # ── APARTMENTS ──────────────────────────────────────────────────────
        if entity == "apartments":
            # Portal scoping: apartment portal sees only their own flat
            pdues_filter = filters.get("pending_dues", {})
            if isinstance(pdues_filter, dict):
                if "gt" in pdues_filter:
                    p_has_dues = True
                elif "eq" in pdues_filter:
                    p_has_dues = pdues_filter.get("eq", 0.0) != 0.0
                else:
                    p_has_dues = False
            else:
                p_has_dues = bool(pdues_filter)
            p_has_dues_sql = "TRUE" if p_has_dues else "FALSE"
            p_apt_id = _apt_id(filters)
            if p_apt_id:
                rows = db._execute(
                    "SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") WHERE id=%s",
                    (sid, s, p_apt_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_apartments_list(%s,NULL," + p_has_dues_sql + ")", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VENDORS ─────────────────────────────────────────────────────────
        if entity == "vendors":
            app_filter = filters.get("active_passes", {})
            if isinstance(app_filter, dict):
                p_has_passes = "gt" in app_filter
            else:
                p_has_passes = bool(app_filter)
            p_has_passes_sql = "TRUE" if p_has_passes else "FALSE"
            p_ven_id = _ven_id(filters)
            if p_ven_id:
                rows = db._execute(
                    "SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") WHERE id=%s",
                    (sid, s, p_ven_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_vendors_list(%s,NULL," + p_has_passes_sql + ")", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SECURITY ────────────────────────────────────────────────────────
        if entity == "security":
            p_sec_id = _sec_id(filters)
            if p_sec_id:
                rows = db._execute(
                    "SELECT * FROM fn_security_list(%s,%s) WHERE id=%s",
                    (sid, s, p_sec_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_security_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_security_list(%s,NULL)", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EVENTS ──────────────────────────────────────────────────────────
        if entity == "events":
            rows = db._execute(
                "SELECT * FROM fn_events_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM events WHERE society_id=%s AND event_date>=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CONCERNS ────────────────────────────────────────────────────────
        if entity == "concerns":
            extra, params = "", [sid]
            if apt_id:
                flat_r = db._execute(
                    "SELECT flat_number FROM apartments WHERE id=%s AND society_id=%s",
                    (apt_id, sid), fetch_one=True,
                )
                flat_no = (flat_r or {}).get("flat_number")
                if flat_no:
                    extra = " AND c.flat_no=%s"
                    params.append(flat_no)
            if s:
                extra += " AND (c.flat_no ILIKE %s OR c.concern_type ILIKE %s)"
                params += [f"%{s}%", f"%{s}%"]
            rows = db._execute(
                "SELECT c.* FROM concerns c WHERE c.society_id=%s "
                "AND c.status IN ('open','in_progress')" + extra +
                " ORDER BY c.created_at DESC LIMIT %s OFFSET %s",
                params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM concerns c WHERE c.society_id=%s "
                "AND c.status IN ('open','in_progress')" + extra, params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── GATE LOGS ───────────────────────────────────────────────────────
        if entity == "gate_logs":
            rows = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s,%s,CURRENT_DATE) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM gate_access WHERE society_id=%s AND time_in::DATE=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIPTS ────────────────────────────────────────────────────────
        if entity == "receipts":
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            rows = db._execute(
                "SELECT * FROM fn_receipts_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receipts_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EXPENSES ────────────────────────────────────────────────────────
        if entity == "expenses":
            p_eid   = eid or ven_id or sec_id or apt_id
            p_etype = (
                "vendor" if ven_id and not eid else
                "security" if sec_id and not eid else
                "apartment" if apt_id and not eid else None
            )
            rows = db._execute(
                "SELECT * FROM fn_expenses_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_expenses_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CASHBOOK ────────────────────────────────────────────────────────
        if entity == "cashbook":
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            rows = db._execute(
                "SELECT * FROM fn_cashbook_paired(%s,%s,%s,%s,NULL,NULL) LIMIT %s OFFSET %s",
                (sid, p_eid, p_etype, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_cashbook_paired(%s,%s,%s,NULL,NULL,NULL)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIVABLES (read-only, all portals) ─────────────────────────
        if entity == "receivables":
            p_status = filters.get("status")
            # Portal scoping: apartment portal sees only own receivables
            p_eid    = eid or apt_id or ven_id or sec_id
            p_etype  = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            rows = db._execute(
                "SELECT * FROM fn_receivables_named(%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_status, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receivables_named(%s,NULL,%s,%s,%s)",
                (sid, p_status, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── payables (read-only, all portals) ────────────────────────────
        if entity == "payables":
            p_status = filters.get("status")
            # Portal scoping: without this, a vendor-portal view of
            # "payables" would fall through to p_etype=None below, which
            # (per fn_payables_named) returns ALL society payables
            # unfiltered — including security payroll rows a vendor has no
            # business seeing. Added when vendor was granted a view-only
            # "payables" permission in _PORTAL_PERMS.
            #
            # NOTE: fn_payables_named only takes 4 params (society_id,
            # search, status, entity_role) — unlike fn_receivables_named,
            # it has no entity_id parameter, so we can filter OUT other
            # roles' rows at the DB level but can't filter IN only this
            # specific vendor's own rows there. Post-filtering by entity_id
            # in Python below closes that gap; if per-vendor row counts
            # grow large, fn_payables_named should get a p_entity_id param
            # added to match fn_receivables_named's signature instead.
            p_eid   = ven_id or sec_id
            p_etype = filters.get("role") or (
                "vendor" if ven_id else "security" if sec_id else None
            )
            rows = db._execute(
                "SELECT * FROM fn_payables_named(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_status, p_etype, page_size, offset), fetch_all=True,
            ) or []
            if p_eid:
                rows = [r for r in rows if r.get("entity_id") == p_eid]
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_payables_named(%s,NULL,%s,%s)",
                (sid, p_status, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── ASSETS (admin CRUD + view elsewhere) ─────────────────────────
        if entity == "assets":
            disposed = filters.get("disposed", False)
            rows = db._execute(
                "SELECT * FROM fn_asset_list(%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, disposed, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM asset_register WHERE society_id=%s AND disposed=%s",
                (sid, disposed), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── ACCOUNTS ────────────────────────────────────────────────────────
        if entity == "accounts":
            rows = db._execute(
                "SELECT * FROM fn_accounts_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE society_id=%s", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SOCIETIES ───────────────────────────────────────────────────────
        if entity == "societies":
            rows = db._execute(
                "SELECT * FROM fn_societies_list(%s) LIMIT %s OFFSET %s",
                (s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute("SELECT COUNT(*) AS n FROM societies", (), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── APT_CHARGES ─────────────────────────────────────────────────────
        if entity == "apt_charges":
            rows = db._execute(
                "SELECT * FROM fn_apt_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, apt_id, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM apt_charges_fines_basis WHERE society_id=%s AND apt_status=TRUE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VEN_CHARGES ─────────────────────────────────────────────────────
        if entity == "ven_charges":
            rows = db._execute(
                "SELECT * FROM fn_ven_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, ven_id, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM ven_charges_fines_basis WHERE society_id=%s AND ven_status=TRUE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
         # ── receipts alias ─────────────────────────────────────────
        if entity == "receipts":
            entity = "receipts"   # redirect to existing branch below
            # fall through — Python won't re-evaluate elif, so call directly:
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            p_status = filters.get("status")
            if p_status:
                # fn_receipts_list has no status parameter — filter/paginate
                # here (e.g. kpi_receipts_pending → status='pending').
                all_rows = db._execute(
                    "SELECT * FROM fn_receipts_list(%s,%s,%s,%s)",
                    (sid, s, p_eid, p_etype), fetch_all=True,
                ) or []
                status_rows = [r for r in all_rows if r.get("status") == p_status]
                total = len(status_rows)
                return status_rows[offset: offset + page_size], total

            rows = db._execute(
                "SELECT * FROM fn_receipts_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receipts_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── expenses alias ─────────────────────────────────────────
        if entity == "expenses":
            p_eid   = eid or ven_id or sec_id or apt_id
            p_etype = (
                "vendor"   if ven_id and not eid else
                "security" if sec_id and not eid else
                "apartment" if apt_id and not eid else None
            )
            rows = db._execute(
                "SELECT * FROM fn_expenses_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_expenses_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── ATTENDANCE ─────────────────────────────────────────────────
        if entity == "attendance":
            extra_sql, extra_params = "", []
            if sec_id:
                extra_sql = " AND g.entity_id=%s"
                extra_params.append(sec_id)
            rows = db._execute(
                "SELECT g.*, COALESCE(s.name,'') AS staff_name "
                "FROM gate_access g "
                "LEFT JOIN security_staff s ON s.id=g.entity_id AND g.role='s' "
                "WHERE g.society_id=%s AND g.role='s'" + extra_sql +
                " ORDER BY g.time_in DESC LIMIT %s OFFSET %s",
                [sid] + extra_params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM gate_access "
                "WHERE society_id=%s AND role='s'" + extra_sql,
                [sid] + extra_params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SECURITY ROSTER (duty/shift assignment) ─────────────────────
        if entity == "security_roster":
            extra_sql, extra_params = "", []
            if sec_id:
                extra_sql = " AND sr.security_id=%s"
                extra_params.append(sec_id)
            rows = db._execute(
                "SELECT sr.*, "
                "COALESCE(ss.name,'Unknown') AS security_name, "
                "COALESCE(au.email,'') AS assigned_by_name "
                "FROM security_roster sr "
                "JOIN security_staff ss ON ss.id=sr.security_id "
                "LEFT JOIN users au ON au.id=sr.assigned_by "
                "WHERE sr.society_id=%s" + extra_sql +
                " ORDER BY sr.roster_date DESC, sr.id DESC LIMIT %s OFFSET %s",
                [sid] + extra_params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM security_roster sr "
                "WHERE sr.society_id=%s" + extra_sql,
                [sid] + extra_params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        return [], 0

    except Exception as e:
        print(f"❌ load_list({entity}): {e}")
        return [], 0


# ════════════════════════════════════════════════════════════════════════════
# LOAD PROFILE
# ════════════════════════════════════════════════════════════════════════════

def load_profile(entity_singular: str, pk, society_id=None) -> dict | None:
    try:
        # ── APARTMENT ───────────────────────────────────────────────────
        if entity_singular == "apartment":
            try:
                r = db._execute(
                    "SELECT a.*, d.pending_dues, d.overdue_dues, d.gate_pass, d.noc_eligible "
                    "FROM apartments a "
                    "JOIN v_apartment_dues d ON d.apartment_id=a.id "
                    "WHERE a.id=%s AND a.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT a.*, 0 AS pending_dues, 0 AS overdue_dues, "
                    "FALSE AS gate_pass, FALSE AS noc_eligible "
                    "FROM apartments a WHERE a.id=%s AND a.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None
 
        # ── VENDOR ─────────────────────────────────────────────────────
        if entity_singular == "vendor":
            try:
                r = db._execute(
                    "SELECT u.id, u.email, u.society_id, "
                    "  v.id AS vendor_id, v.name, v.service_type, v.mobile, "
                    "  v.active, v.logo, v.license, v.photo, v.service_description, v.created_at, "
                    "  vp.pass_expiry, vp.gate_pass "
                    "FROM users u "
                    "JOIN vendors v ON v.id=u.linked_id "
                    "JOIN v_vendor_pass_status vp ON vp.user_id=u.id "
                    "WHERE u.id=%s AND u.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT u.id, u.email, u.society_id, "
                    "  v.id AS vendor_id, v.name, v.service_type, v.mobile, "
                    "  v.active, v.logo, v.license, v.photo, v.created_at, "
                    "  NULL AS pass_expiry, FALSE AS gate_pass "
                    "FROM users u "
                    "JOIN vendors v ON v.id=u.linked_id "
                    "WHERE u.id=%s AND u.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None
 
        # ── SECURITY ───────────────────────────────────────────────────
        if entity_singular == "security":
            try:
                r = db._execute(
                    "SELECT u.id, u.email, u.society_id, "
                    "  s.id AS staff_id, s.name, s.mobile, s.shift, "
                    "  s.active, s.joining_date, s.salary_per_shift, "
                    "  s.photo, s.id_proof, s.created_at, "
                    "  vs.shift_count, vs.gate_pass "
                    "FROM users u "
                    "JOIN security_staff s ON s.id=u.linked_id "
                    "JOIN v_security_status vs ON vs.user_id=u.id "
                    "WHERE u.id=%s AND u.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT u.id, u.email, u.society_id, "
                    "  s.id AS staff_id, s.name, s.mobile, s.shift, "
                    "  s.active, s.joining_date, s.salary_per_shift, "
                    "  s.photo, s.id_proof, s.created_at, "
                    "  0 AS shift_count, FALSE AS gate_pass "
                    "FROM users u "
                    "JOIN security_staff s ON s.id=u.linked_id "
                    "WHERE u.id=%s AND u.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── EVENT ─────────────────────────────────────────────────────────────
        if entity_singular == "event":
            r = db._execute("SELECT * FROM fn_event_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── CONCERN ──────────────────────────────────────────────────────────
        if entity_singular == "concern":
            r = db._execute("SELECT * FROM fn_concern_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── SOCIETY ──────────────────────────────────────────────────────────
        if entity_singular == "society":
            r = db._execute("SELECT * FROM fn_society_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── ACCOUNT ──────────────────────────────────────────────────────────
        if entity_singular == "account":
            r = db._execute("SELECT * FROM fn_account_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── GATE LOG ─────────────────────────────────────────────────────────
        if entity_singular == "gate_log":
            r = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT * FROM gate_access WHERE id=%s AND society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── RECEIPT ──────────────────────────────────────────────────────────
        if entity_singular == "receipt":
            r = db._execute(
                "SELECT r.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  CASE WHEN r.role='apartment' "
                "    THEN ap.flat_number||' — '||COALESCE(ap.owner_name,'') "
                "    WHEN r.role='vendor' THEN v.name "
                "    WHEN r.role='security' THEN s.name "
                "    ELSE 'Other' END AS entity_name "
                "FROM receipts r "
                "LEFT JOIN accounts a ON a.id=r.acc_id "
                "LEFT JOIN apartments ap ON ap.id=r.entity_id AND r.role='apartment' "
                "LEFT JOIN vendors v ON v.id=r.entity_id AND r.role='vendor' "
                "LEFT JOIN security_staff s ON s.id=r.entity_id AND r.role='security' "
                "WHERE r.id=%s AND r.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EXPENSE ──────────────────────────────────────────────────────────
        if entity_singular == "expense":
            r = db._execute(
                "SELECT e.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  CASE WHEN e.role='vendor' THEN v.name "
                "    WHEN e.role='security' THEN s.name "
                "    WHEN e.role='assets' "
                "      THEN COALESCE(ar.asset_name,'Asset #'||e.entity_id::TEXT) "
                "    ELSE 'Other' END AS entity_name "
                "FROM expenses e "
                "LEFT JOIN accounts a ON a.id=e.acc_id "
                "LEFT JOIN vendors v ON v.id=e.entity_id AND e.role='vendor' "
                "LEFT JOIN security_staff s ON s.id=e.entity_id AND e.role='security' "
                "LEFT JOIN asset_register ar ON ar.id=e.entity_id AND e.role='assets' "
                "WHERE e.id=%s AND e.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── RECEIVABLE (read-only profile) ───────────────────────────────────
        if entity_singular == "receivable":
            r = db._execute(
                "SELECT * FROM fn_receivables_named(%s,NULL,NULL,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT r.*, COALESCE(a.name,'') AS account_name "
                    "FROM receivables r LEFT JOIN accounts a ON a.id=r.acc_id "
                    "WHERE r.id=%s AND r.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── PAYMENT (read-only profile) ──────────────────────────────────────
        if entity_singular == "payment":
            r = db._execute(
                "SELECT * FROM fn_payables_named(%s,NULL,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT p.*, COALESCE(a.name,'') AS account_name "
                    "FROM payables p LEFT JOIN accounts a ON a.id=p.acc_id "
                    "WHERE p.id=%s AND p.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── ASSET (admin CRUD + view) ─────────────────────────────────────────
        if entity_singular == "asset":
            r = db._execute(
                "SELECT ar.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  COALESCE(a.depreciation_percent, ar.depreciation_rate, 100) AS dep_rate, "
                "  GREATEST(ar.purchase_value * "
                "    (1 - COALESCE(ar.depreciation_rate,a.depreciation_percent,100)/100), 0) "
                "    AS book_value "
                "FROM asset_register ar "
                "LEFT JOIN accounts a ON a.id=ar.acc_id "
                "WHERE ar.id=%s AND ar.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── APT CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "apt_charge":
            r = db._execute(
                "SELECT * FROM fn_apt_charges_list(%s, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT acf.*, COALESCE(a.flat_number,'ALL') AS flat_number "
                    "FROM apt_charges_fines_basis acf "
                    "LEFT JOIN apartments a ON a.id=acf.apt_id "
                    "WHERE acf.id=%s AND acf.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── VEN CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "ven_charge":
            r = db._execute(
                "SELECT * FROM fn_ven_charges_list(%s, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT vcf.*, COALESCE(v.name,'ALL') AS vendor_name "
                    "FROM ven_charges_fines_basis vcf "
                    "LEFT JOIN vendors v ON v.id=vcf.ven_id "
                    "WHERE vcf.id=%s AND vcf.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── SECURITY ROSTER ──────────────────────────────────────────────
        if entity_singular == "security_roster":
            r = db._execute(
                "SELECT sr.*, "
                "COALESCE(ss.name,'Unknown') AS security_name, "
                "COALESCE(au.email,'') AS assigned_by_name "
                "FROM security_roster sr "
                "JOIN security_staff ss ON ss.id=sr.security_id "
                "LEFT JOIN users au ON au.id=sr.assigned_by "
                "WHERE sr.id=%s AND sr.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None
        return None

    except Exception as e:
        print(f"❌ load_profile({entity_singular}, {pk}): {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# GATE PASS EVALUATION  (replaces old v_apartment_dues / view-based check)
# ════════════════════════════════════════════════════════════════════════════

def evaluate_gate_pass(role: str, entity_id: int) -> dict:
    """
    Call fn_evaluate_gate_pass and return {passed, reason, amount_due}.
    role: 'apartment' | 'vendor' | 'security'
    entity_id:
      apartment → apartments.id
      vendor    → users.id  (the vendor login row)
      security  → users.id  (the security login row)
    """
    try:
        r = db._execute(
            "SELECT * FROM fn_evaluate_gate_pass(%s, %s)",
            (role, entity_id), fetch_one=True,
        )
        return dict(r) if r else {"passed": False, "reason": "Evaluation error", "amount_due": 0}
    except Exception as e:
        return {"passed": False, "reason": str(e), "amount_due": 0}


# ════════════════════════════════════════════════════════════════════════════
# NOC ELIGIBILITY
# ════════════════════════════════════════════════════════════════════════════

def check_noc_eligibility(apartment_id: int) -> dict:
    """Return {eligible, reason, outstanding} from fn_check_noc_eligibility."""
    try:
        r = db._execute(
            "SELECT * FROM fn_check_noc_eligibility(%s)", (apartment_id,), fetch_one=True,
        )
        return dict(r) if r else {"eligible": False, "reason": "Error", "outstanding": 0}
    except Exception as e:
        return {"eligible": False, "reason": str(e), "outstanding": 0}


# ════════════════════════════════════════════════════════════════════════════
# DELETE ENTITY
# ════════════════════════════════════════════════════════════════════════════

def delete_entity(entity_plural: str, pk, society_id=None) -> tuple[bool, str]:
    try:
        if entity_plural == "apartments":
            # Trigger will block if outstanding dues > 0
            db._execute(
                "UPDATE apartments SET active=FALSE WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Apartment deactivated"

        if entity_plural == "vendors":
            db._execute(
                "UPDATE vendors v SET active=FALSE FROM users u "
                "WHERE v.id=u.linked_id AND u.id=%s AND u.society_id=%s",
                (pk, society_id),
            )
            return True, "Vendor deactivated"

        if entity_plural == "security":
            db._execute(
                "UPDATE security_staff s SET active=FALSE FROM users u "
                "WHERE s.id=u.linked_id AND u.id=%s AND u.society_id=%s",
                (pk, society_id),
            )
            return True, "Security staff deactivated"

        if entity_plural == "events":
            db._execute("DELETE FROM events WHERE id=%s AND society_id=%s", (pk, society_id))
            return True, "Event deleted"

        if entity_plural == "concerns":
            db._execute(
                "UPDATE concerns SET status='closed' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Concern closed"

        if entity_plural == "receipts":
            db._execute(
                "UPDATE receipts SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Receipt cancelled"

        if entity_plural == "expenses":
            db._execute(
                "UPDATE expenses SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Expense cancelled"

        if entity_plural == "receivables":
            db._execute(
                "UPDATE receivables SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Receivable cancelled"

        if entity_plural == "payables":
            # Only pending payables can be cancelled; verified ones are locked in transactions
            db._execute(
                "UPDATE payables SET status='cancelled' "
                "WHERE id=%s AND society_id=%s AND status='pending'",
                (pk, society_id),
            )
            return True, "Payment cancelled (if it was still pending)"

        if entity_plural == "assets":
            # Hard-delete only if not yet disposed and has no linked transactions
            trx_count = db._execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE source_table='expenses' AND entity_id=%s",
                (pk,), fetch_one=True,
            )
            if (trx_count or {}).get("n", 0) > 0:
                return False, "Cannot delete asset with existing transactions"
            db._execute(
                "DELETE FROM asset_register WHERE id=%s AND society_id=%s AND disposed=FALSE",
                (pk, society_id),
            )
            return True, "Asset deleted"

        if entity_plural == "cashbook":
            return False, "Transactions are immutable — cashbook is read-only"

        if entity_plural == "accounts":
            db._execute(
                "DELETE FROM accounts WHERE id=%s AND society_id=%s", (pk, society_id)
            )
            return True, "Account deleted"

        if entity_plural == "societies":
            db._execute(
                "UPDATE societies SET plan_validity=CURRENT_DATE-1 WHERE id=%s", (pk,)
            )
            return True, "Society plan expired"

        return False, f"No delete handler for '{entity_plural}'"

    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIVABLE / PAYMENT  (admin-only action buttons)
# ════════════════════════════════════════════════════════════════════════════

def verify_receivable(receivable_id: int, confirmed_by: int, mode: str = "cash") -> tuple[bool, str]:
    try:
        r = db._execute(
            "SELECT fn_verify_receivable(%s,%s,%s) AS msg",
            (receivable_id, confirmed_by, mode), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)


def verify_payment(payment_id: int, confirmed_by: int, mode: str = "cash") -> tuple[bool, str]:
    try:
        r = db._execute(
            "SELECT fn_verify_payment(%s,%s,%s) AS msg",
            (payment_id, confirmed_by, mode), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# FIFO PAYMENT (Pay Dues button from apartment profile)
# ════════════════════════════════════════════════════════════════════════════

def pay_apartment_dues_fifo(
    apartment_id: int,
    amount: float,
    mode: str = "cash",
    confirmed_by: int = None,
    particulars: str = None,
) -> tuple[bool, str, dict]:
    """
    Returns (ok, message, {transaction_id, allocated, unallocated}).
    unallocated > 0 means an advance-credit row was created.
    """
    try:
        r = db._execute(
            "SELECT * FROM fn_pay_apartment_dues_fifo(%s,%s,%s,%s,%s)",
            (apartment_id, amount, mode, confirmed_by, particulars),
            fetch_one=True,
        )
        if not r:
            return False, "No result from payment function", {}
        result = dict(r)
        unalloc = float(result.get("unallocated") or 0)
        msg = f"Rs.{float(result.get('allocated',0)):,.2f} applied"
        if unalloc > 0:
            msg += f"; Rs.{unalloc:,.2f} credited as advance"
        return True, msg, result
    except Exception as e:
        return False, str(e), {}

# ════════════════════════════════════════════════════════════════════════════
# LOAD VENDOR PASS RATES
# ════════════════════════════════════════════════════════════════════════════
def load_vendor_pass_rates(vendor_user_id: int, society_id: int) -> dict:
    """Return {"1day": rate, "7day": rate, "1mth": rate, "free_1mth": 0.0} from ven_charges_fines_basis."""
    try:
        # Get vendors.id from users.linked_id
        u = db._execute(
            "SELECT linked_id FROM users WHERE id=%s AND society_id=%s",
            (vendor_user_id, society_id), fetch_one=True,
        )
        vendor_id = (u or {}).get("linked_id")

        row = db._execute(
            "SELECT vendor_1day, vendor_7day, vendor_1mth FROM ven_charges_fines_basis "
            "WHERE society_id=%s AND ven_status=TRUE "
            "AND (ven_id=%s OR ven_id IS NULL) "
            "ORDER BY ven_id NULLS LAST, start_date DESC LIMIT 1",
            (society_id, vendor_id), fetch_one=True,
        ) or {}
        return {
            "1day": float(row.get("vendor_1day") or 0),
            "7day": float(row.get("vendor_7day") or 0),
            "1mth": float(row.get("vendor_1mth") or 0),
            "free_1mth": 0.0,
        }
    except Exception as e:
        print(f"❌ load_vendor_pass_rates: {e}")
        return {"1day": 0, "7day": 0, "1mth": 0, "free_1mth": 0.0}

# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIPT
# ════════════════════════════════════════════════════════════════════════════

def verify_receipt(receipt_id: int, confirmed_by: int, mode: str = None) -> tuple[bool, str]:
    """Admin verifies a pending receipt (created by security) → posts to transactions."""
    try:
        r = db._execute(
            "SELECT fn_verify_receipt(%s,%s,%s) AS msg",
            (receipt_id, confirmed_by, mode),
            fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)
# ════════════════════════════════════════════════════════════════════════════
# ACCOUNT DROPDOWN OPTIONS
# ════════════════════════════════════════════════════════════════════════════

def load_entity_options(role: str, society_id: int) -> list[dict]:
    """
    Return [{label, value}] for dropdowns in New/Edit forms.
    role: 'apartments' | 'vendors' | 'security' |
          'accounts_cr' | 'accounts_dr' | 'accounts_all'
    """
    try:
        if role == "apartments":
            rows = db._execute(
                "SELECT id, flat_number, owner_name FROM apartments "
                "WHERE society_id=%s AND active=TRUE ORDER BY flat_number",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['flat_number']} — {r.get('owner_name','')}", "value": r["id"]}
                for r in rows
            ]

        if role == "vendors":
            rows = db._execute(
                "SELECT u.id, v.name, v.service_type FROM users u "
                "JOIN vendors v ON v.id=u.linked_id "
                "WHERE u.society_id=%s AND u.role='vendor' AND v.active=TRUE ORDER BY v.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('service_type','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]

        if role == "security":
            rows = db._execute(
                "SELECT u.id, s.name, s.shift FROM users u "
                "JOIN security_staff s ON s.id=u.linked_id "
                "WHERE u.society_id=%s AND u.role='security' AND s.active=TRUE ORDER BY s.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('shift','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]

        # Receipt accounts: Cr + NULL/empty (assets, bank, investments)
        if role == "accounts_cr":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s AND (drcr_account='Cr' OR drcr_account IS NULL OR drcr_account='') "
                "ORDER BY CASE WHEN drcr_account='Cr' THEN 1 ELSE 2 END, tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # Expense accounts: Dr + NULL/empty (assets, bank, investments)
        if role == "accounts_dr":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s AND (drcr_account='Dr' OR drcr_account IS NULL OR drcr_account='') "
                "ORDER BY CASE WHEN drcr_account='Dr' THEN 1 ELSE 2 END, tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # All asset-class accounts (NULL/empty drcr) for asset register
        if role == "accounts_asset":
            rows = db._execute(
                "SELECT id, tab_name, name FROM accounts "
                "WHERE society_id=%s AND (drcr_account IS NULL OR drcr_account='') "
                "ORDER BY tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # All accounts
        if role == "accounts_all":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s ORDER BY tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {
                    "label": f"{r['id']} — {r.get('tab_name','')} — {r['name']} "
                             f"[{r.get('drcr_account') or 'Asset'}]",
                    "value": r["id"],
                }
                for r in rows
            ]

        return []
    except Exception as e:
        print(f"❌ load_entity_options({role}): {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# EXPORT CSV
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return ""
    import csv, io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
