# app/dash_apps/drilldown/loaders.py
"""
Data Loaders
============
Each loader fetches data for a specific list/profile card
and returns structured dicts ready for rendering.

All queries use parameterised filters from the navigation state.
"""

from __future__ import annotations
from datetime import datetime, date
import csv
import io


def _db():
    from database.db_manager import db
    return db


PAGE_SIZE = 15


# ════════════════════════════════════════════════════════════════════════════
# KPI LOADERS
# ════════════════════════════════════════════════════════════════════════════

def load_kpi_values(society_id: int | None, role: str = "admin") -> dict:
    """
    Return a dict of {kpi_card_id: formatted_value_string}.
    Called once per page render to populate all KPI cards.
    """
    if not society_id:
        # Master admin sees global KPIs
        return _load_master_kpis()
    return _load_society_kpis(society_id, role)


def _load_master_kpis() -> dict:
    db = _db()
    try:
        r = db.execute_query(
            """SELECT
               COUNT(*)                                              AS total,
               SUM(CASE WHEN plan='Paid' THEN 1 ELSE 0 END)         AS paid,
               SUM(CASE WHEN plan='Free' THEN 1 ELSE 0 END)         AS free_plan
               FROM societies""",
            fetch_one=True
        ) or {}
        apts = db.execute_query("SELECT COUNT(*) AS c FROM apartments WHERE active=TRUE", fetch_one=True) or {}
        vend = db.execute_query("SELECT COUNT(*) AS c FROM users WHERE role='vendor'", fetch_one=True) or {}
        sec  = db.execute_query("SELECT COUNT(*) AS c FROM users WHERE role='security'", fetch_one=True) or {}
        return {
            "kpi_societies_total": str(r.get("total", 0)),
            "kpi_societies_paid":  str(r.get("paid", 0)),
            "kpi_societies_free":  str(r.get("free_plan", 0)),
            "kpi_apartments_total":str(apts.get("c", 0)),
            "kpi_vendors_total":   str(vend.get("c", 0)),
            "kpi_security_total":  str(sec.get("c", 0)),
        }
    except Exception as e:
        print(f"Master KPI error: {e}")
        return {}


def _load_society_kpis(society_id: int, role: str) -> dict:
    db = _db()
    try:
        rows = db.execute_query(
            """SELECT
               (SELECT COUNT(*) FROM apartments WHERE society_id=%s AND active=TRUE)             AS apts_total,
               (SELECT COUNT(DISTINCT p.apartment_id) FROM payments p
                JOIN apartments a ON p.apartment_id=a.id
                WHERE a.society_id=%s AND p.status='pending')                                    AS apts_dues,
               (SELECT COUNT(*) FROM users WHERE society_id=%s AND role='vendor')                AS vendors_total,
               (SELECT COUNT(*) FROM users WHERE society_id=%s AND role='security')              AS security_total,
               (SELECT COUNT(*) FROM events WHERE society_id=%s AND event_date>=CURRENT_DATE)    AS events_total,
               (SELECT COUNT(*) FROM concerns WHERE society_id=%s AND status NOT IN ('closed','resolved')) AS concerns_open,
               (SELECT COUNT(*) FROM gate_access WHERE society_id=%s AND DATE(time_in)=CURRENT_DATE) AS gate_today,
               (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE society_id=%s AND status='paid'
                AND trx_date>=date_trunc('month',CURRENT_DATE))                                  AS receipts_month,
               (SELECT COALESCE(SUM(amount),0) FROM payments WHERE society_id=%s AND status='pending') AS pending_dues
            """,
            (society_id,) * 9,
            fetch_one=True,
        ) or {}

        def fmt_currency(v):
            try:
                return f"₹{int(float(v or 0)):,}"
            except Exception:
                return "₹0"

        return {
            "kpi_apartments_total":   str(rows.get("apts_total", 0)),
            "kpi_apartments_dues":    str(rows.get("apts_dues", 0)),
            "kpi_apartments_no_dues": str(int(rows.get("apts_total", 0) or 0) - int(rows.get("apts_dues", 0) or 0)),
            "kpi_vendors_total":      str(rows.get("vendors_total", 0)),
            "kpi_security_total":     str(rows.get("security_total", 0)),
            "kpi_events_total":       str(rows.get("events_total", 0)),
            "kpi_concerns_open":      str(rows.get("concerns_open", 0)),
            "kpi_gate_logs_today":    str(rows.get("gate_today", 0)),
            "kpi_receipts_month":     fmt_currency(rows.get("receipts_month", 0)),
            "kpi_balance":            fmt_currency(rows.get("receipts_month", 0)),
        }
    except Exception as e:
        print(f"Society KPI error: {e}")
        return {}


# ════════════════════════════════════════════════════════════════════════════
# LIST LOADERS
# ════════════════════════════════════════════════════════════════════════════

def load_list(entity: str, filters: dict, page: int = 1,
              search: str = "", page_size: int = PAGE_SIZE) -> tuple[list[dict], int]:
    """
    Generic list loader. Returns (rows, total_count).
    Dispatches to entity-specific loader.
    """
    loaders = {
        "apartments": _list_apartments,
        "vendors":    _list_vendors,
        "security":   _list_security,
        "events":     _list_events,
        "concerns":   _list_concerns,
        "gate_logs":  _list_gate_logs,
        "receipts":   _list_receipts,
        "cashbook":   _list_cashbook,
        "societies":  _list_societies,
        "accounts":   _list_accounts,
        "expenses":   _list_expenses,
    }
    fn = loaders.get(entity)
    if fn is None:
        return [], 0
    return fn(filters, page, search, page_size)


def _list_apartments(filters, page, search, page_size):
    db = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    where  = ["a.society_id=%s"]
    params = [sid]
    if filters.get("has_dues") is True:
        where.append("EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if filters.get("has_dues") is False:
        where.append("NOT EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if search:
        where.append("(a.flat_number ILIKE %s OR a.owner_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    where_sql = " AND ".join(where)

    count = db.execute_query(
        f"SELECT COUNT(*) AS c FROM apartments a WHERE {where_sql}", params, fetch_one=True
    ) or {"c": 0}
    rows  = db.execute_query(
        f"""SELECT a.id, a.flat_number, a.owner_name, a.mobile,
               a.apartment_size,
               a.active,
               COALESCE(SUM(p.amount),0) AS pending_dues
            FROM apartments a
            LEFT JOIN payments p ON p.apartment_id=a.id AND p.status='pending'
            WHERE {where_sql}
            GROUP BY a.id
            ORDER BY a.flat_number
            LIMIT %s OFFSET %s""",
        params + [page_size, offset],
        fetch_all=True,
    ) or []
    return rows, int(count.get("c", 0))


def _list_vendors(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    where  = ["u.society_id=%s", "u.role='vendor'"]
    params = [sid]
    if search:
        where.append("u.email ILIKE %s")
        params.append(f"%{search}%")
    where_sql = " AND ".join(where)
    count = db.execute_query(
        f"SELECT COUNT(*) AS c FROM users u WHERE {where_sql}", params, fetch_one=True
    ) or {"c": 0}
    rows  = db.execute_query(
        f"""SELECT u.id, u.email,
               COALESCE(v.name, u.email) AS name,
               COALESCE(v.service_type,'—') AS service_type,
               COALESCE(v.mobile,'—') AS mobile,
               COALESCE(SUM(p.amount),0) AS pending_dues
            FROM users u
            LEFT JOIN vendors v ON v.society_id=u.society_id
            LEFT JOIN payments p ON p.user_id=u.id AND p.status='pending'
            WHERE {where_sql}
            GROUP BY u.id, v.name, v.service_type, v.mobile
            ORDER BY u.id DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset],
        fetch_all=True,
    ) or []
    return rows, int(count.get("c", 0))


def _list_security(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    where  = ["u.society_id=%s", "u.role='security'"]
    params = [sid]
    if filters.get("on_duty") is True:
        where.append("EXISTS(SELECT 1 FROM gate_access g WHERE g.entity_id=u.id AND DATE(g.time_in)=CURRENT_DATE AND g.time_out IS NULL)")
    if search:
        where.append("u.email ILIKE %s")
        params.append(f"%{search}%")
    where_sql = " AND ".join(where)
    count = db.execute_query(
        f"SELECT COUNT(*) AS c FROM users u WHERE {where_sql}", params, fetch_one=True
    ) or {"c": 0}
    rows  = db.execute_query(
        f"""SELECT u.id, u.email,
               COALESCE(s.name,'—') AS name, COALESCE(s.shift,'—') AS shift,
               COALESCE(s.mobile,'—') AS mobile, s.active
            FROM users u
            LEFT JOIN security_staff s ON s.society_id=u.society_id
            WHERE {where_sql}
            ORDER BY u.id DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset],
        fetch_all=True,
    ) or []
    return rows, int(count.get("c", 0))


def _list_events(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    where  = ["society_id=%s"]
    params = [sid]
    if search:
        where.append("title ILIKE %s")
        params.append(f"%{search}%")
    where_sql = " AND ".join(where)
    count = db.execute_query(f"SELECT COUNT(*) AS c FROM events WHERE {where_sql}", params, fetch_one=True) or {"c": 0}
    rows  = db.execute_query(
        f"SELECT id, event_date, title, venue, open_to, created_at FROM events WHERE {where_sql} ORDER BY event_date DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


def _list_concerns(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    where  = ["society_id=%s"]
    params = [sid]
    if search:
        where.append("(flat_no ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    where_sql = " AND ".join(where)
    count = db.execute_query(f"SELECT COUNT(*) AS c FROM concerns WHERE {where_sql}", params, fetch_one=True) or {"c": 0}
    rows  = db.execute_query(
        f"SELECT id, flat_no, concern_type, description, status, assigned_to, created_at FROM concerns WHERE {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


def _list_gate_logs(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    params = [sid]
    extra  = ""
    if search:
        extra = "AND entity_id::text ILIKE %s"
        params.append(f"%{search}%")
    count = db.execute_query(
        f"SELECT COUNT(*) AS c FROM gate_access WHERE society_id=%s {extra}", params, fetch_one=True
    ) or {"c": 0}
    rows  = db.execute_query(
        f"""SELECT id, role, entity_id, time_in, time_out,
               EXTRACT(EPOCH FROM (COALESCE(time_out,NOW())-time_in))/3600 AS hours
            FROM gate_access WHERE society_id=%s {extra}
            ORDER BY time_in DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


def _list_receipts(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    params = [sid]
    extra  = ""
    if search:
        extra = "AND acc_particulars ILIKE %s"
        params.append(f"%{search}%")
    count = db.execute_query(
        f"SELECT COUNT(*) AS c FROM transactions WHERE society_id=%s AND status='paid' {extra}", params, fetch_one=True
    ) or {"c": 0}
    rows  = db.execute_query(
        f"""SELECT id, trx_date, acc_particulars, amount, mode, status
            FROM transactions WHERE society_id=%s AND status='paid' {extra}
            ORDER BY trx_date DESC LIMIT %s OFFSET %s""",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


def _list_expenses(filters, page, search, page_size):
    """For now reuse transactions with debit accounts."""
    return _list_receipts(filters, page, search, page_size)


def _list_cashbook(filters, page, search, page_size):
    return _list_receipts(filters, page, search, page_size)


def _list_societies(filters, page, search, page_size):
    db  = _db()
    offset = (page - 1) * page_size
    params = []
    extra  = ""
    if filters.get("plan"):
        extra = "WHERE plan=%s"
        params.append(filters["plan"])
    if search:
        extra += " AND " if extra else "WHERE "
        extra += "name ILIKE %s"
        params.append(f"%{search}%")
    count = db.execute_query(f"SELECT COUNT(*) AS c FROM societies {extra}", params, fetch_one=True) or {"c": 0}
    rows  = db.execute_query(
        f"SELECT id, name, email, phone, plan, created_at FROM societies {extra} ORDER BY name LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


def _list_accounts(filters, page, search, page_size):
    db  = _db()
    sid = filters.get("society_id")
    if not sid:
        return [], 0
    offset = (page - 1) * page_size
    params = [sid]
    extra  = ""
    if search:
        extra = "AND (name ILIKE %s OR tab_name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    count = db.execute_query(f"SELECT COUNT(*) AS c FROM accounts WHERE society_id=%s {extra}", params, fetch_one=True) or {"c": 0}
    rows  = db.execute_query(
        f"SELECT id, name, tab_name, header, drcr_account, bf_amount FROM accounts WHERE society_id=%s {extra} ORDER BY name LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True
    ) or []
    return rows, int(count.get("c", 0))


# ════════════════════════════════════════════════════════════════════════════
# PROFILE LOADERS
# ════════════════════════════════════════════════════════════════════════════

def load_profile(entity: str, pk, society_id: int | None = None) -> dict | None:
    """Fetch a single record for the profile card."""
    db = _db()
    try:
        if entity == "apartment":
            row = db.execute_query(
                """SELECT a.*, COALESCE(SUM(p.amount),0) AS pending_dues
                   FROM apartments a
                   LEFT JOIN payments p ON p.apartment_id=a.id AND p.status='pending'
                   WHERE a.id=%s
                   GROUP BY a.id""",
                (pk,), fetch_one=True
            )
            if row:
                row["subtitle"] = f"Flat {row.get('flat_number','?')}"
            return row
        if entity == "vendor":
            return db.execute_query(
                "SELECT * FROM users WHERE id=%s", (pk,), fetch_one=True
            )
        if entity == "security":
            return db.execute_query(
                "SELECT * FROM users WHERE id=%s", (pk,), fetch_one=True
            )
        if entity == "event":
            return db.execute_query(
                "SELECT * FROM events WHERE id=%s", (pk,), fetch_one=True
            )
        if entity == "concern":
            return db.execute_query(
                "SELECT * FROM concerns WHERE id=%s", (pk,), fetch_one=True
            )
        if entity == "society":
            return db.execute_query(
                "SELECT * FROM societies WHERE id=%s", (pk,), fetch_one=True
            )
        if entity in ("receipt", "transaction"):
            return db.execute_query(
                "SELECT * FROM transactions WHERE id=%s", (pk,), fetch_one=True
            )
        if entity == "gate_log":
            return db.execute_query(
                "SELECT * FROM gate_access WHERE id=%s", (pk,), fetch_one=True
            )
    except Exception as e:
        print(f"load_profile({entity},{pk}) error: {e}")
    return None


# ════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    """Generate CSV string for full (unpaginated) entity list."""
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return "No data"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys(), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {}
        for k, v in row.items():
            if isinstance(v, (datetime, date)):
                safe[k] = v.isoformat()
            else:
                safe[k] = v
        writer.writerow(safe)
    return buf.getvalue()
