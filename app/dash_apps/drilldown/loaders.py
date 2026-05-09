# app/dash_apps/drilldown/loaders.py
"""
Data Loaders + delete_entity
=============================
Fetches data for list/profile cards and exports CSV.
Also provides delete_entity() used by drilldown_callbacks.
"""

from __future__ import annotations
from datetime import datetime, date
import csv
import io
from  ..callbacks.card_catalogue_callbacks import _execute

def _db():
    from database.db_manager import db
    return db


PAGE_SIZE = 15


# ════════════════════════════════════════════════════════════════════════════
# DELETE HELPER  (used by drilldown_callbacks.route_drilldown)
# ════════════════════════════════════════════════════════════════════════════

def delete_entity(entity_plural: str, pk, society_id=None) -> tuple:
    """Delete a record. Returns (ok, message)."""
    db = _db()
    TABLE_MAP = {
        "apartments": ("apartments",   "id"),
        "vendors":    ("users",        "id"),
        "security":   ("users",        "id"),
        "events":     ("events",       "id"),
        "concerns":   ("concerns",     "id"),
        "gate_logs":  ("gate_access",  "id"),
        "receipts":   ("transactions", "id"),
        "expenses":   ("transactions", "id"),
        "cashbook":   ("transactions", "id"),
        "societies":  ("societies",    "id"),
        "accounts":   ("accounts",     "id"),
    }
    if entity_plural not in TABLE_MAP:
        return False, f"No delete handler for '{entity_plural}'"

    table, pk_col = TABLE_MAP[entity_plural]
    try:
        if society_id and table not in ("societies", "users"):
            _execute(
                f"DELETE FROM {table} WHERE {pk_col} = %s AND society_id = %s",
                (pk, society_id),
            )
        else:
            _execute(
                f"DELETE FROM {table} WHERE {pk_col} = %s", (pk,),
            )
        return True, "Record deleted"
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# LIST LOADERS
# ════════════════════════════════════════════════════════════════════════════

def load_list(entity: str, filters: dict, page: int = 1,
              search: str = "", page_size: int = PAGE_SIZE) -> tuple:
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
        "expenses":   _list_receipts,   # reuse
    }
    fn = loaders.get(entity)
    if fn is None:
        return [], 0
    return fn(filters, page, search, page_size)


def _list_apartments(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    where, params = ["a.society_id=%s"], [sid]
    if filters.get("has_dues") is True:
        where.append("EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if filters.get("has_dues") is False:
        where.append("NOT EXISTS(SELECT 1 FROM payments p WHERE p.apartment_id=a.id AND p.status='pending')")
    if search:
        where.append("(a.flat_number ILIKE %s OR a.owner_name ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    ws = " AND ".join(where)
    count = _execute(f"SELECT COUNT(*) AS c FROM apartments a WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT a.id,a.flat_number,a.owner_name,a.mobile,a.apartment_size,a.active,"
        f"COALESCE(SUM(p.amount),0) AS pending_dues "
        f"FROM apartments a LEFT JOIN payments p ON p.apartment_id=a.id AND p.status='pending' "
        f"WHERE {ws} GROUP BY a.id ORDER BY a.flat_number LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_vendors(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    where, params = ["u.society_id=%s", "u.role='vendor'"], [sid]
    if search:
        where.append("u.email ILIKE %s"); params.append(f"%{search}%")
    ws = " AND ".join(where)
    count = _execute(f"SELECT COUNT(*) AS c FROM users u WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT u.id,u.email,u.email AS name,'—' AS service_type,'—' AS mobile,"
        f"COALESCE(SUM(p.amount),0) AS pending_dues "
        f"FROM users u LEFT JOIN payments p ON p.user_id=u.id AND p.status='pending' "
        f"WHERE {ws} GROUP BY u.id ORDER BY u.id DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_security(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    where, params = ["u.society_id=%s", "u.role='security'"], [sid]
    if search:
        where.append("u.email ILIKE %s"); params.append(f"%{search}%")
    ws = " AND ".join(where)
    count = _execute(f"SELECT COUNT(*) AS c FROM users u WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT u.id,u.email,u.email AS name,'—' AS shift,'—' AS mobile,TRUE AS active "
        f"FROM users u WHERE {ws} ORDER BY u.id DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_events(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    where, params = ["society_id=%s"], [sid]
    if search:
        where.append("title ILIKE %s"); params.append(f"%{search}%")
    ws = " AND ".join(where)
    count = _execute(f"SELECT COUNT(*) AS c FROM events WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,event_date,title,venue,open_to,created_at FROM events WHERE {ws} "
        f"ORDER BY event_date DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_concerns(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    where, params = ["society_id=%s"], [sid]
    if search:
        where.append("(flat_no ILIKE %s OR description ILIKE %s)")
        params += [f"%{search}%", f"%{search}%"]
    ws = " AND ".join(where)
    count = _execute(f"SELECT COUNT(*) AS c FROM concerns WHERE {ws}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,flat_no,concern_type,description,status,assigned_to,created_at "
        f"FROM concerns WHERE {ws} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_gate_logs(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    params = [sid]; extra = ""
    if search:
        extra = "AND entity_id::text ILIKE %s"; params.append(f"%{search}%")
    count = _execute(
        f"SELECT COUNT(*) AS c FROM gate_access WHERE society_id=%s {extra}",
        params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,role,entity_id,time_in,time_out,"
        f"EXTRACT(EPOCH FROM (COALESCE(time_out,NOW())-time_in))/3600 AS hours "
        f"FROM gate_access WHERE society_id=%s {extra} "
        f"ORDER BY time_in DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_receipts(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    params = [sid]; extra = ""
    if search:
        extra = "AND acc_particulars ILIKE %s"; params.append(f"%{search}%")
    count = _execute(
        f"SELECT COUNT(*) AS c FROM transactions WHERE society_id=%s AND status='paid' {extra}",
        params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,trx_date,acc_particulars,amount,mode,status "
        f"FROM transactions WHERE society_id=%s AND status='paid' {extra} "
        f"ORDER BY trx_date DESC LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_cashbook(filters, page, search, page_size):
    return _list_receipts(filters, page, search, page_size)


def _list_societies(filters, page, search, page_size):
    db = _db(); offset = (page - 1) * page_size
    params = []; extra = ""
    if filters.get("plan"):
        extra = "WHERE plan=%s"; params.append(filters["plan"])
    if search:
        extra += " AND " if extra else "WHERE "
        extra += "name ILIKE %s"; params.append(f"%{search}%")
    count = _execute(f"SELECT COUNT(*) AS c FROM societies {extra}", params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,name,email,phone,plan,created_at FROM societies {extra} "
        f"ORDER BY name LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


def _list_accounts(filters, page, search, page_size):
    db = _db(); sid = filters.get("society_id")
    if not sid: return [], 0
    offset = (page - 1) * page_size
    params = [sid]; extra = ""
    if search:
        extra = "AND (name ILIKE %s OR tab_name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    count = _execute(
        f"SELECT COUNT(*) AS c FROM accounts WHERE society_id=%s {extra}",
        params, fetch_one=True) or {"c": 0}
    rows  = _execute(
        f"SELECT id,name,tab_name,header,drcr_account,bf_amount "
        f"FROM accounts WHERE society_id=%s {extra} ORDER BY name LIMIT %s OFFSET %s",
        params + [page_size, offset], fetch_all=True) or []
    return rows, int(count.get("c", 0))


# ════════════════════════════════════════════════════════════════════════════
# PROFILE LOADER
# ════════════════════════════════════════════════════════════════════════════

def load_profile(entity: str, pk, society_id=None) -> dict | None:
    db = _db()
    try:
        if entity == "apartment":
            row = _execute(
                "SELECT a.*,COALESCE(SUM(p.amount),0) AS pending_dues "
                "FROM apartments a LEFT JOIN payments p ON p.apartment_id=a.id AND p.status='pending' "
                "WHERE a.id=%s GROUP BY a.id", (pk,), fetch_one=True)
            if row: row["subtitle"] = f"Flat {row.get('flat_number','?')}"
            return row
        if entity in ("vendor", "security"):
            return _execute("SELECT * FROM users WHERE id=%s", (pk,), fetch_one=True)
        if entity == "event":
            return _execute("SELECT * FROM events WHERE id=%s", (pk,), fetch_one=True)
        if entity == "concern":
            return _execute("SELECT * FROM concerns WHERE id=%s", (pk,), fetch_one=True)
        if entity == "society":
            return _execute("SELECT * FROM societies WHERE id=%s", (pk,), fetch_one=True)
        if entity in ("receipt", "expense", "transaction"):
            return _execute("SELECT * FROM transactions WHERE id=%s", (pk,), fetch_one=True)
        if entity == "gate_log":
            return _execute("SELECT * FROM gate_access WHERE id=%s", (pk,), fetch_one=True)
        if entity == "account":
            return _execute("SELECT * FROM accounts WHERE id=%s", (pk,), fetch_one=True)
    except Exception as e:
        print(f"load_profile({entity},{pk}) error: {e}")
    return None


# ════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return "No data"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys(), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {k: (v.isoformat() if isinstance(v, (datetime, date)) else v)
                for k, v in row.items()}
        writer.writerow(safe)
    return buf.getvalue()
