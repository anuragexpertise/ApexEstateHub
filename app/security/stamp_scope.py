# app/security/stamp_scope.py
"""
Ownership-scoped "printed / emailed" stamping.

The ten stamp callbacks (receipts, expenses, NOCs, agreements, event
tickets) used to update a row by id + society_id only, so any logged-in user
in a society could mark any other member's document as printed/emailed.
`stamp_document()` keeps the tenant filter and adds an owner filter derived
from the SERVER session (role / user id / linked id):

  admin            any document in their society
  apartment/vendor/security
                   receipts & expenses: documents addressed to their own
                   entity (role + entity_id) or created by them (user_id)
                   NOCs: their own apartment's NOCs
                   event tickets: tickets they bought (event_tickets.user_id)
                   agreements: admin only
  master / no session
                   nothing (the master portal has no society to stamp in)

Only whitelisted (table, column) pairs are accepted, because the names are
interpolated into SQL.
"""

from __future__ import annotations

from app.security.audit_context import (
    get_current_linked_id,
    get_current_society_id,
    get_current_user_id,
    get_current_user_role,
)

_STAMP_COLUMNS = {"last_printed_at", "last_emailed_at"}
_STAMP_TABLES = {
    "receipts", "expenses", "nocs", "society_agreements", "event_ticket_items",
}


def _owner_clause(table: str, role: str, uid: int, linked_id):
    """Return (sql_fragment, params) restricting a non-admin to own rows,
    or None if this role may not stamp this table at all."""
    if table in ("receipts", "expenses"):
        if role not in ("apartment", "vendor", "security"):
            return None
        if linked_id is None:
            return "user_id = %s", (uid,)
        return "((role = %s AND entity_id = %s) OR user_id = %s)", (role, linked_id, uid)
    if table == "nocs":
        if role == "apartment" and linked_id is not None:
            return "apartment_id = %s", (linked_id,)
        return None
    if table == "event_ticket_items":
        if role not in ("apartment", "vendor", "security"):
            return None
        return ("event_ticket_id IN (SELECT id FROM event_tickets "
                "WHERE user_id = %s)"), (uid,)
    # society_agreements: admin only
    return None


def stamp_document(table: str, doc_id, column: str, db=None) -> bool:
    """Set `column = NOW()` on one document if the session user may.
    Returns True when a row was updated."""
    if table not in _STAMP_TABLES or column not in _STAMP_COLUMNS:
        raise ValueError(f"stamp not allowed: {table}.{column}")
    try:
        doc_id = int(doc_id)
    except (TypeError, ValueError):
        return False

    sid = get_current_society_id()
    uid = get_current_user_id()
    role = get_current_user_role()
    if not sid or uid is None or not role:
        return False

    sql = f"UPDATE {table} SET {column} = NOW() WHERE id = %s AND society_id = %s"
    params: tuple = (doc_id, sid)
    if role != "admin":
        scoped = _owner_clause(table, role, uid, get_current_linked_id())
        if scoped is None:
            return False
        frag, extra = scoped
        sql += f" AND {frag}"
        params = params + tuple(extra)
    sql += " RETURNING id"

    if db is None:
        from database.db_manager import db as _db
        db = _db
    row = db._execute(sql, params, fetch_one=True)
    return bool(row)
