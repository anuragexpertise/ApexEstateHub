"""Disputed / under-protest bills (Plan v3, task 1.5).

A member disputes an apartment bill. The administrator or a serving office-bearer records the dispute with a reason and
the resolution it is held under. While it is open the bill accrues no interest and does not count towards default
status (the database enforces this; see receivable_disputes in estatehub.sql). Deciding it either ends the hold or, if
upheld, reverses the bill's accrual journals and cancels it. All rules live in the database functions; this module
checks who may act, turns database refusals into messages that are safe to show, and writes the audit row.
"""
from __future__ import annotations

OUTCOMES = ("upheld", "dismissed", "withdrawn")
OUTCOME_LABEL = {"upheld": "Upheld (bill cancelled)", "dismissed": "Dismissed (bill stands)", "withdrawn": "Withdrawn (bill stands)"}


class DisputeRefused(RuntimeError):
    """Safe to show to the user."""


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def _may_act(d, society_id, user_id) -> bool:
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") == "admin":
        return True
    from app.services import document_signing as ds
    return bool(ds.serving_offices(society_id, user_id, db=d))


def may_act(society_id, user_id, db=None) -> bool:
    """Who may hold or decide a bill: the administrator, or a serving office-bearer."""
    return bool(user_id and society_id and _may_act(_db(db), society_id, user_id))


def holdable_bills(society_id, db=None, limit: int = 200) -> list[dict]:
    """Unpaid apartment bills that are not already held, oldest due date first: what the 'hold a bill' list offers."""
    return _db(db)._execute(
        """SELECT r.id, r.description, r.due_date, r.amount - r.paid_amount AS outstanding, a.flat_number, a.owner_name
             FROM receivables r
             LEFT JOIN apartments a ON a.id = r.entity_id
            WHERE r.society_id = %s AND r.role = 'apartment' AND r.status IN ('pending', 'partial')
              AND r.amount - r.paid_amount > 0
              AND NOT EXISTS (SELECT 1 FROM receivable_disputes d WHERE d.receivable_id = r.id AND d.status = 'open')
            ORDER BY r.due_date, r.id
            LIMIT %s""", (society_id, limit), fetch_all=True) or []


def _clean(exc) -> str:
    msg = str(exc).split("\n")[0].replace("ERROR:", "").strip()
    if "uq_receivable_dispute_open" in msg:
        return "This bill is already under dispute."
    return msg or "Could not save."


def _audit(action, dispute_id, society_id, user_id, after, reason):
    try:
        from app.security.service_guard import audit_event
        audit_event(action, "receivable_disputes", dispute_id, after=after, reason=reason, society_id=society_id)
    except Exception:                                                     # noqa: BLE001  (an audit outage must not hide the result)
        pass


def raise_dispute(society_id, receivable_id, user_id, reason, resolution_ref, db=None) -> int:
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise DisputeRefused("Only the administrator or a serving office-bearer can hold a bill.")
    try:
        r = d._execute("SELECT fn_raise_receivable_dispute(%s,%s,%s,%s,%s) AS id",
                       (society_id, receivable_id, user_id, reason, resolution_ref), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise DisputeRefused(_clean(exc)) from exc
    _audit("receivable.dispute.raise", r["id"], society_id, user_id, {"receivable_id": receivable_id, "resolution_ref": resolution_ref}, reason)
    return r["id"]


def decide(society_id, dispute_id, outcome, user_id, reason, resolution_ref, db=None) -> str:
    d = _db(db)
    if outcome not in OUTCOMES:
        raise DisputeRefused("Decide it as upheld, dismissed or withdrawn.")
    if not _may_act(d, society_id, user_id):
        raise DisputeRefused("Only the administrator or a serving office-bearer can decide a dispute.")
    try:
        r = d._execute("SELECT fn_decide_receivable_dispute(%s,%s,%s,%s,%s,%s) AS msg",
                       (society_id, dispute_id, outcome, user_id, reason, resolution_ref), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise DisputeRefused(_clean(exc)) from exc
    _audit("receivable.dispute.decide", dispute_id, society_id, user_id, {"outcome": outcome, "resolution_ref": resolution_ref}, reason)
    return r["msg"]


def register(society_id, db=None) -> list[dict]:
    """Every dispute of the society, open ones first, with the flat and the bill it concerns."""
    return _db(db)._execute(
        """SELECT d.*, r.description AS bill, r.due_date, r.amount AS bill_amount, a.flat_number, a.owner_name
             FROM receivable_disputes d
             JOIN receivables r ON r.id = d.receivable_id
             LEFT JOIN apartments a ON a.id = r.entity_id AND r.role = 'apartment'
            WHERE d.society_id = %s
            ORDER BY (d.status = 'open') DESC, d.raised_on DESC, d.id DESC""", (society_id,), fetch_all=True) or []
