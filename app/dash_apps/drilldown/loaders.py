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

DB_ERROR_KEYWORDS = ["no database connection", "error in processing", "error in querying", "operationalerror"]

def _is_db_error(e: Exception) -> bool:
    """Check if exception indicates a database connection or query error."""
    error_str = str(e).lower()
    return any(kw in error_str for kw in DB_ERROR_KEYWORDS)
 
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
    Returns ([], 0) on database error.
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
            params_c: dict = {"society_id": sid, "status": "open"}
            if apt_id:
                flat_r = db._execute(
                    "SELECT flat_number FROM apartments WHERE id=:apt_id AND society_id=:society_id",
                    {"apt_id": apt_id, "society_id": sid}, fetch_one=True)
                flat_no = (flat_r or {}).get("flat_number")
                if flat_no:
                    extra = " AND c.flat_no = :flat_no"
                    params_c["flat_no"] = flat_no
            rows = db._execute(
                "SELECT c.* FROM concerns c "
                "WHERE c.society_id=:society_id AND c.status IN (:status,'in_progress')"
                + extra +
                " ORDER BY c.created_at DESC LIMIT :page_size OFFSET :offset",
                {**params_c, "page_size": page_size, "offset": offset},
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM concerns c "
                "WHERE c.society_id=:society_id AND c.status IN ('open','in_progress')"
                + extra,
                params_c,
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
                "SELECT acf.*, COALESCE(a.flat_number, 'ALL') AS flat_number "
                "FROM apt_charges_fines_basis acf "
                "LEFT JOIN apartments a ON a.id = acf.apt_id "
                "WHERE acf.society_id=%s AND acf.apt_status=TRUE "
                "ORDER BY acf.apt_id NULLS FIRST, acf.start_date DESC LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM apt_charges_fines_basis "
                "WHERE society_id=%s AND apt_status=TRUE",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))
 
# ── VEN_CHARGES ─────────────────────────────────────────────────────
        if entity == "ven_charges":
            rows = db._execute(
                "SELECT vcf.*, COALESCE(v.name, 'ALL') AS vendor_name FROM ven_charges_fines_basis vcf "
                "LEFT JOIN vendors v ON v.id = vcf.ven_id "
                "WHERE vcf.society_id=%s "
                "ORDER BY vcf.ven_id NULLS FIRST, vcf.start_date DESC LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM ven_charges_fines_basis WHERE society_id=%s",
                (sid,), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SEC_CHARGES ─────────────────────────────────────────────────────
        if entity == "sec_charges":
            rows = db._execute(
                "SELECT scf.*, COALESCE(s.name, 'ALL') AS security_name FROM sec_charges_fines_basis scf "
                "LEFT JOIN security_staff s ON s.id = scf.sec_id "
                "WHERE scf.society_id=%s "
                "ORDER BY scf.sec_id NULLS FIRST, scf.start_date DESC LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM sec_charges_fines_basis WHERE society_id=%s",
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

