# app/dash_apps/drilldown/loaders.py
"""
THIN LOADERS - Just database queries, no business logic
All calculations done in PostgreSQL functions
"""

from __future__ import annotations
from datetime import date
from database.db_manager import db
from app.models import (
    dict_to_apartment, dict_to_vendor, dict_to_security, dict_to_society,
    dict_to_account, dict_to_event, dict_to_concern, dict_to_transaction,
    dict_to_receivable, Apartment, Vendor, SecurityStaff, Society, Account,
    Event, Concern, Transaction, Receivable
)

PAGE_SIZE = 15
 
def _society(filters: dict):
    return filters.get("society_id")
 
 
def _apt_id(filters: dict):
    return filters.get("apartment_id")
 
 
def _ven_id(filters: dict):
    return filters.get("vendor_id")
 

# ════════════════════════════════════════════════════════════════════════════
# GENERIC DISPATCHERS - Work with any entity
# ════════════════════════════════════════════════════════════════════════════

def load_list(entity: str, filters: dict,
              page: int = 1, search: str = "",
              page_size: int = PAGE_SIZE) -> tuple[list, int]:
    """
    Return (rows, total_count) for the given entity + filters.
    Rows are plain dicts.
    """
    sid    = _society(filters)
    apt_id = _apt_id(filters)
    ven_id = _ven_id(filters)
    offset = (page - 1) * page_size
    s      = f"%{search}%" if search else None
 
    try:
        # ── APARTMENTS ──────────────────────────────────────────────────────
        if entity == "apartments":
            base_where = "a.society_id = %s"
            params: list = [sid]
            if apt_id:                          # apartment portal: own unit only
                base_where += " AND a.id = %s"
                params.append(apt_id)
            if s:
                base_where += " AND (a.flat_number ILIKE %s OR a.owner_name ILIKE %s)"
                params += [s, s]
 
            # Use the DB function when no extra portal filter
            if not apt_id and not s:
                rows = db._execute(
                    "SELECT * FROM fn_apartments_list(%s, %s, NULL) "
                    "LIMIT %s OFFSET %s",
                    (sid, search or None, page_size, offset),
                    fetch_all=True,
                ) or []
                total_r = db._execute(
                    "SELECT COUNT(*) AS n FROM fn_apartments_list(%s, NULL, NULL)",
                    (sid,), fetch_one=True)
                return rows, int((total_r or {}).get("n", len(rows)))
 
            rows = db._execute(
                f"SELECT a.*, "
                f"  COALESCE(("
                f"    SELECT SUM(p.amount) FROM payments p "
                f"    WHERE p.entity_id=a.id AND p.entity_type='apartment' "
                f"          AND p.status='pending'"
                f"  ),0) AS pending_dues "
                f"FROM apartments a "
                f"WHERE {base_where} "
                f"ORDER BY a.flat_number "
                f"LIMIT %s OFFSET %s",
                params + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM apartments a WHERE {base_where}",
                params, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── VENDORS ─────────────────────────────────────────────────────────
        if entity == "vendors":
            if ven_id:
                rows = db._execute(
                    "SELECT u.id, u.email, v.name, v.service_type, v.mobile, "
                    "       v.active, "
                    "       COALESCE(("
                    "         SELECT SUM(p.amount) FROM payments p "
                    "         WHERE p.user_id=u.id AND p.entity_type='vendor' "
                    "               AND p.status='pending'"
                    "       ),0) AS pending_dues "
                    "FROM users u JOIN vendors v ON v.id=u.linked_id "
                    "WHERE u.society_id=%s AND v.id=%s",
                    (sid, ven_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_vendors_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, search or None, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_vendors_list(%s, NULL)",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── SECURITY ────────────────────────────────────────────────────────
        if entity == "security":
            rows = db._execute(
                "SELECT * FROM fn_security_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, search or None, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_security_list(%s, NULL)",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── EVENTS ──────────────────────────────────────────────────────────
        if entity == "events":
            rows = db._execute(
                "SELECT * FROM fn_events_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, search or None, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM events "
                "WHERE society_id=%s AND event_date>=CURRENT_DATE",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── CONCERNS ────────────────────────────────────────────────────────
        if entity == "concerns":
            extra = ""
            params_c: list = [sid, "open"]
            if apt_id:
                # apartment portal: only concerns from their flat
                flat_r = db._execute(
                    "SELECT flat_number FROM apartments WHERE id=%s AND society_id=%s",
                    (apt_id, sid), fetch_one=True)
                flat_no = (flat_r or {}).get("flat_number")
                if flat_no:
                    extra = " AND c.flat_no = %s"
                    params_c.append(flat_no)
            rows = db._execute(
                "SELECT c.* FROM concerns c "
                "WHERE c.society_id=%s AND c.status IN (%s,'in_progress')"
                + extra +
                " ORDER BY c.created_at DESC LIMIT %s OFFSET %s",
                params_c + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM concerns c "
                "WHERE c.society_id=%s AND c.status IN ('open','in_progress')"
                + extra,
                params_c[:len(params_c)],
                fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── RECEIPTS_TBL ────────────────────────────────────────────────────
        if entity == "receipts_tbl":
            where = "t.society_id=%s"
            params_r: list = [sid]
            if apt_id:
                where += " AND t.entity_id=%s"
                params_r.append(apt_id)
            elif ven_id:
                where += " AND t.entity_id=%s"
                params_r.append(ven_id)
            rows = db._execute(
                f"SELECT t.*, a.name AS account_id, "
                f"       COALESCE(ap.flat_number, v.name, '') AS entity_name, "
                f"       a.drcr_account, "
                f"       a.tab_name AS acc_particulars "
                f"FROM transactions t "
                f"JOIN accounts a ON a.id=t.acc_id "
                f"LEFT JOIN apartments ap ON ap.id=t.entity_id AND a.drcr_account='Cr' "
                f"LEFT JOIN vendors v ON v.id=t.entity_id "
                f"WHERE {where} AND a.drcr_account='Cr' "
                f"ORDER BY t.trx_date DESC LIMIT %s OFFSET %s",
                params_r + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM transactions t "
                f"JOIN accounts a ON a.id=t.acc_id "
                f"WHERE {where} AND a.drcr_account='Cr'",
                params_r, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── EXPENSES_TBL ────────────────────────────────────────────────────
        if entity == "expenses_tbl":
            where = "t.society_id=%s"
            params_e: list = [sid]
            rows = db._execute(
                f"SELECT t.*, a.name AS account_id "
                f"FROM transactions t "
                f"JOIN accounts a ON a.id=t.acc_id "
                f"WHERE {where} AND a.drcr_account='Dr' "
                f"ORDER BY t.trx_date DESC LIMIT %s OFFSET %s",
                params_e + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM transactions t "
                f"JOIN accounts a ON a.id=t.acc_id "
                f"WHERE {where} AND a.drcr_account='Dr'",
                params_e, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── CASHBOOK ────────────────────────────────────────────────────────
        if entity == "cashbook":
            eid = filters.get("entity_id")
            where = "t.society_id=%s"
            params_cb: list = [sid]
            if eid:
                where += " AND t.entity_id=%s"
                params_cb.append(eid)
            elif apt_id:
                where += " AND t.entity_id=%s"
                params_cb.append(apt_id)
            elif ven_id:
                where += " AND t.entity_id=%s"
                params_cb.append(ven_id)
            rows = db._execute(
                f"SELECT t.*, a.name AS account_name, a.drcr_account "
                f"FROM transactions t JOIN accounts a ON a.id=t.acc_id "
                f"WHERE {where} AND t.status='paid' "
                f"ORDER BY t.trx_date DESC LIMIT %s OFFSET %s",
                params_cb + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM transactions t "
                f"JOIN accounts a ON a.id=t.acc_id "
                f"WHERE {where} AND t.status='paid'",
                params_cb, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── ACCOUNTS ────────────────────────────────────────────────────────
        if entity == "accounts":
            rows = db._execute(
                "SELECT * FROM fn_accounts_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, search or None, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE society_id=%s",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── GATE_LOGS ───────────────────────────────────────────────────────
        if entity == "gate_logs":
            where = "g.society_id=%s AND g.time_in>=CURRENT_DATE"
            params_g: list = [sid]
            rows = db._execute(
                f"SELECT g.* FROM gate_access g "
                f"WHERE {where} ORDER BY g.time_in DESC LIMIT %s OFFSET %s",
                params_g + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM gate_access g WHERE {where}",
                params_g, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── SOCIETIES (master) ───────────────────────────────────────────────
        if entity == "societies":
            rows = db._execute(
                "SELECT * FROM fn_societies_list(%s) LIMIT %s OFFSET %s",
                (search or None, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute("SELECT COUNT(*) AS n FROM societies",
                               (), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── APT_CHARGES ─────────────────────────────────────────────────────
        if entity == "apt_charges":
            rows = db._execute(
                "SELECT acf.*, a.flat_number FROM apt_charges_fines acf "
                "JOIN apartments a ON a.id=acf.apt_id "
                "WHERE acf.society_id=%s AND acf.apt_status=TRUE "
                "ORDER BY a.flat_number LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM apt_charges_fines "
                "WHERE society_id=%s AND apt_status=TRUE",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── VEN_CHARGES ─────────────────────────────────────────────────────
        if entity == "ven_charges":
            rows = db._execute(
                "SELECT vcf.*, v.name FROM ven_charges_fines vcf "
                "JOIN vendors v ON v.id=vcf.ven_id "
                "WHERE vcf.society_id=%s AND vcf.ven_status=TRUE "
                "ORDER BY v.name LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM ven_charges_fines "
                "WHERE society_id=%s AND ven_status=TRUE",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── SEC_CHARGES ─────────────────────────────────────────────────────
        if entity == "sec_charges":
            rows = db._execute(
                "SELECT scf.*, s.name FROM security_charges_fines scf "
                "JOIN security_staff s ON s.id=scf.sec_id "
                "WHERE scf.society_id=%s AND scf.sec_status=TRUE "
                "ORDER BY s.name LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM security_charges_fines "
                "WHERE society_id=%s AND sec_status=TRUE",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── RECEIVABLES ─────────────────────────────────────────────────────
        if entity == "receivables":
            where = "r.society_id=%s AND r.status='pending'"
            params_rv: list = [sid]
            if apt_id:
                where += " AND r.entity_id=%s AND r.entity_type='apartment'"
                params_rv.append(apt_id)
            elif ven_id:
                where += " AND r.entity_id=%s AND r.entity_type='vendor'"
                params_rv.append(ven_id)
            rows = db._execute(
                f"SELECT * FROM receivables r WHERE {where} "
                f"ORDER BY r.due_date ASC LIMIT %s OFFSET %s",
                params_rv + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM receivables r WHERE {where}",
                params_rv, fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
        return [], 0
 
    except Exception as e:
        print(f"❌ load_list({entity}): {e}")
        return [], 0
 
 
# ────────────────────────────────────────────────────────────────────────────
# load_profile
# ────────────────────────────────────────────────────────────────────────────
 
def load_profile(entity_singular: str, pk, society_id=None) -> dict | None:
    """Return a single record as a plain dict, or None if not found."""
    try:
        if entity_singular == "apartment":
            r = db._execute(
                "SELECT a.*, "
                "  COALESCE(("
                "    SELECT SUM(p.amount) FROM payments p "
                "    WHERE p.entity_id=a.id AND p.entity_type='apartment' "
                "          AND p.status='pending'"
                "  ),0) AS pending_dues "
                "FROM apartments a "
                "WHERE a.id=%s AND a.society_id=%s",
                (pk, society_id), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "vendor":
            r = db._execute(
                "SELECT u.id, u.email, v.name, v.service_type, v.mobile, "
                "       v.active, "
                "       COALESCE(("
                "         SELECT SUM(p.amount) FROM payments p "
                "         WHERE p.user_id=u.id AND p.entity_type='vendor' "
                "               AND p.status='pending'"
                "       ),0) AS pending_dues "
                "FROM users u JOIN vendors v ON v.id=u.linked_id "
                "WHERE u.id=%s AND u.society_id=%s",
                (pk, society_id), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "security":
            r = db._execute(
                "SELECT u.id, u.email, s.name, s.mobile, s.shift, "
                "       s.active, s.joining_date, s.salary_per_shift "
                "FROM users u JOIN security_staff s ON s.id=u.linked_id "
                "WHERE u.id=%s AND u.society_id=%s",
                (pk, society_id), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "event":
            r = db._execute(
                "SELECT * FROM fn_event_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "concern":
            r = db._execute(
                "SELECT * FROM fn_concern_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "society":
            r = db._execute(
                "SELECT * FROM fn_society_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "account":
            r = db._execute(
                "SELECT * FROM fn_account_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "gate_log":
            r = db._execute(
                "SELECT * FROM gate_access WHERE id=%s AND society_id=%s",
                (pk, society_id), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular in ("receipt_entry", "expense_entry", "transaction"):
            r = db._execute(
                "SELECT t.*, a.name AS account_name "
                "FROM transactions t JOIN accounts a ON a.id=t.acc_id "
                "WHERE t.id=%s AND t.society_id=%s",
                (pk, society_id), fetch_one=True)
            return dict(r) if r else None
 
        if entity_singular == "receivable":
            r = db._execute(
                "SELECT * FROM fn_receivable_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None
 
        # Generic fallback
        return None
 
    except Exception as e:
        print(f"❌ load_profile({entity_singular}, {pk}): {e}")
        return None
 
 
# ────────────────────────────────────────────────────────────────────────────
# delete_entity
# ────────────────────────────────────────────────────────────────────────────
 
def delete_entity(entity_plural: str, pk, society_id=None) -> tuple[bool, str]:
    """
    Soft-delete (set active=FALSE) where possible, hard-delete otherwise.
    Returns (ok, message).
    """
    try:
        if entity_plural == "apartments":
            db._execute(
                "UPDATE apartments SET active=FALSE "
                "WHERE id=%s AND society_id=%s",
                (pk, society_id))
            return True, "Apartment deactivated"
 
        if entity_plural == "vendors":
            db._execute(
                "UPDATE vendors v SET active=FALSE "
                "FROM users u WHERE v.id=u.linked_id "
                "AND u.id=%s AND u.society_id=%s",
                (pk, society_id))
            return True, "Vendor deactivated"
 
        if entity_plural == "security":
            db._execute(
                "UPDATE security_staff s SET active=FALSE "
                "FROM users u WHERE s.id=u.linked_id "
                "AND u.id=%s AND u.society_id=%s",
                (pk, society_id))
            return True, "Security staff deactivated"
 
        if entity_plural == "events":
            db._execute(
                "DELETE FROM events WHERE id=%s AND society_id=%s",
                (pk, society_id))
            return True, "Event deleted"
 
        if entity_plural == "concerns":
            db._execute(
                "UPDATE concerns SET status='closed' "
                "WHERE id=%s AND society_id=%s",
                (pk, society_id))
            return True, "Concern closed"
 
        if entity_plural in ("receipts_tbl", "expenses_tbl", "cashbook"):
            db._execute(
                "UPDATE transactions SET status='cancelled' "
                "WHERE id=%s AND society_id=%s",
                (pk, society_id))
            return True, "Transaction cancelled"
 
        if entity_plural == "accounts":
            db._execute(
                "DELETE FROM accounts WHERE id=%s AND society_id=%s",
                (pk, society_id))
            return True, "Account deleted"
 
        if entity_plural == "societies":
            # Master admin only — soft delete via plan expiry
            db._execute(
                "UPDATE societies SET plan_validity=CURRENT_DATE-1 WHERE id=%s",
                (pk,))
            return True, "Society plan expired"
 
        return False, f"No delete handler for '{entity_plural}'"
 
    except Exception as e:
        return False, str(e)
 
 
# ────────────────────────────────────────────────────────────────────────────
# export_csv
# ────────────────────────────────────────────────────────────────────────────
 
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

# ════════════════════════════════════════════════════════════════════════════
# SQL INTROSPECTION - For Customize Tab
# ════════════════════════════════════════════════════════════════════════════

def get_function_sql(function_name: str) -> str:
    """Get SQL definition of a PostgreSQL function"""
    try:
        row = db._execute(
            "SELECT get_function_sql(%s) as sql",
            (function_name,),
            fetch_one=True
        )
        return row['sql'] if row else "Function not found"
    except Exception as e:
        return f"Error: {str(e)}"


def get_kpi_functions() -> list[dict]:
    """Get all KPI functions with their definitions"""
    try:
        rows = db._execute(
            "SELECT * FROM get_kpi_functions()",
            fetch_all=True
        ) or []
        return rows
    except Exception as e:
        print(f"❌ Error fetching KPI functions: {e}")
        return []


def get_portal_kpis(portal: str = None) -> list[dict]:
    """Get all KPIs for a portal with their metadata"""
    try:
        if portal:
            rows = db._execute(
                "SELECT * FROM get_portal_kpis(%s)",
                (portal,),
                fetch_all=True
            ) or []
        else:
            rows = db._execute(
                "SELECT * FROM get_portal_kpis()",
                fetch_all=True
            ) or []
        return rows
    except Exception as e:
        print(f"❌ Error fetching portal KPIs: {e}")
        return []

# ════════════════════════════════════════════════════════════════════════════
# APARTMENTS
# ════════════════════════════════════════════════════════════════════════════

def load_apartments_list(
    society_id: int,
    search: str = "",
    has_dues: bool = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Apartment], int]:
    """Load apartment list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_apartments_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    # Filter by has_dues if specified
    if has_dues is not None:
        rows = [r for r in rows if (has_dues and r['grand_total'] > 0) or 
                (not has_dues and r['grand_total'] == 0)]
    
    # Get total count
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_apartments_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    apartments = [dict_to_apartment(r) for r in rows]
    return apartments, total

def load_apartment_profile(apartment_id: int) -> Apartment | None:
    """Load apartment profile"""
    row = db._execute(
        "SELECT * FROM apartments WHERE id = %s",
        (apartment_id,),
        fetch_one=True
    )
    return dict_to_apartment(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# VENDORS
# ════════════════════════════════════════════════════════════════════════════

def load_vendors_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Vendor], int]:
    """Load vendor list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_vendors_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_vendors_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    vendors = [dict_to_vendor(r) for r in rows]
    return vendors, total

def load_vendor_profile(vendor_id: int) -> Vendor | None:
    """Load vendor profile"""
    row = db._execute(
        """SELECT u.id, u.email, u.society_id, v.name, v.logo, v.license,
                  v.photo, v.service_type, v.mobile, v.service_description,
                  v.active, v.created_at
           FROM users u
           LEFT JOIN vendors v ON v.id = u.linked_id
           WHERE u.id = %s AND u.role = 'vendor'""",
        (vendor_id,),
        fetch_one=True
    )
    return dict_to_vendor(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# SECURITY STAFF
# ════════════════════════════════════════════════════════════════════════════

def load_security_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[SecurityStaff], int]:
    """Load security staff list using SQL function"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_security_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_security_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    security = [dict_to_security(r) for r in rows]
    return security, total

def load_security_profile(security_id: int) -> SecurityStaff | None:
    """Load security profile"""
    row = db._execute(
        """SELECT u.id, u.email, u.society_id, s.name, s.photo, s.id_proof,
                  s.mobile, s.joining_date, s.shift, s.salary_per_shift, s.active,
                  s.created_at
           FROM users u
           LEFT JOIN security_staff s ON s.id = u.linked_id
           WHERE u.id = %s AND u.role = 'security'""",
        (security_id,),
        fetch_one=True
    )
    return dict_to_security(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# SOCIETIES
# ════════════════════════════════════════════════════════════════════════════

def load_societies_list(
    search: str = "",
    plan: str = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Society], int]:
    """Load societies list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_societies_list(%s, %s) LIMIT %s OFFSET %s",
        (search if search else None, plan, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_societies_list(%s, %s)",
        (search if search else None, plan),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    societies = [dict_to_society(r) for r in rows]
    return societies, total

def load_society_profile(society_id: int) -> Society | None:
    """Load society profile"""
    row = db._execute(
        "SELECT * FROM fn_society_profile(%s)",
        (society_id,),
        fetch_one=True
    )
    return dict_to_society(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# ACCOUNTS
# ════════════════════════════════════════════════════════════════════════════

def load_accounts_list(
    society_id: int,
    search: str = "",
    tab_name: str = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Account], int]:
    """Load accounts list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_accounts_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, tab_name, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_accounts_list(%s, %s, %s)",
        (society_id, search if search else None, tab_name),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    accounts = [dict_to_account(r) for r in rows]
    return accounts, total

def load_account_profile(account_id: int) -> Account | None:
    """Load account profile"""
    row = db._execute(
        "SELECT * FROM fn_account_profile(%s)",
        (account_id,),
        fetch_one=True
    )
    return dict_to_account(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# EVENTS
# ════════════════════════════════════════════════════════════════════════════

def load_events_list(
    society_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Event], int]:
    """Load events list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_events_list(%s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_events_list(%s, %s)",
        (society_id, search if search else None),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    events = [dict_to_event(r) for r in rows]
    return events, total

def load_event_profile(event_id: int) -> Event | None:
    """Load event profile"""
    row = db._execute(
        "SELECT * FROM fn_event_profile(%s)",
        (event_id,),
        fetch_one=True
    )
    return dict_to_event(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# CONCERNS
# ════════════════════════════════════════════════════════════════════════════

def load_concerns_list(
    society_id: int,
    search: str = "",
    status: str = "open",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Concern], int]:
    """Load concerns list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_concerns_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, status, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_concerns_list(%s, %s, %s)",
        (society_id, search if search else None, status),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    concerns = [dict_to_concern(r) for r in rows]
    return concerns, total

def load_concern_profile(concern_id: int) -> Concern | None:
    """Load concern profile"""
    row = db._execute(
        "SELECT * FROM fn_concern_profile(%s)",
        (concern_id,),
        fetch_one=True
    )
    return dict_to_concern(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# RECEIVABLES
# ════════════════════════════════════════════════════════════════════════════

def load_receivables_list(
    society_id: int,
    search: str = "",
    status: str = "pending",
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Receivable], int]:
    """Load receivables list"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_receivables_list(%s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, status, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_receivables_list(%s, %s, %s)",
        (society_id, search if search else None, status),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    receivables = [dict_to_receivable(r) for r in rows]
    return receivables, total

def load_receivable_profile(receivable_id: int) -> Receivable | None:
    """Load receivable profile"""
    row = db._execute(
        "SELECT * FROM fn_receivable_profile(%s)",
        (receivable_id,),
        fetch_one=True
    )
    return dict_to_receivable(row) if row else None

# ════════════════════════════════════════════════════════════════════════════
# CASHBOOK
# ════════════════════════════════════════════════════════════════════════════

def load_cashbook_list(
    society_id: int,
    search: str = "",
    start_date = None,
    end_date = None,
    page: int = 1,
    page_size: int = PAGE_SIZE
) -> tuple[list[Transaction], int]:
    """Load cashbook transactions"""
    offset = (page - 1) * page_size
    
    rows = db._execute(
        "SELECT * FROM fn_cashbook_list(%s, %s, %s, %s) LIMIT %s OFFSET %s",
        (society_id, search if search else None, start_date, end_date, page_size, offset),
        fetch_all=True
    ) or []
    
    count_row = db._execute(
        "SELECT COUNT(*) as cnt FROM fn_cashbook_list(%s, %s, %s, %s)",
        (society_id, search if search else None, start_date, end_date),
        fetch_one=True
    )
    total = count_row['cnt'] if count_row else 0
    
    transactions = [dict_to_transaction(r) for r in rows]
    return transactions, total

def load_cashbook_profile(transaction_id: int) -> Transaction | None:
    """Load transaction profile"""
    row = db._execute(
        "SELECT * FROM fn_cashbook_profile(%s)",
        (transaction_id,),
        fetch_one=True
    )
    return dict_to_transaction(row) if row else None


