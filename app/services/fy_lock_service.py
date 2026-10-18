"""
Locking a financial year: the service behind the lock panel on the FY Closing card.

A lock is irreversible (fy_locks is append-only and nothing can post into a locked year), so this is the one
step in the year-end routine that cannot be undone. The service therefore:

  1. re-runs the read-only preview server-side and refuses on any blocker (the browser is never trusted);
  2. requires a written reason, and an explicit acknowledgement that the lock is permanent;
  3. anchors and signs the ledger chain BEFORE locking (app/security/ledger_anchor.py), so the evidence of what the
     ledger held when the year was frozen is recorded, and a chain that does not verify blocks the lock;
  4. calls fn_lock_fy, which re-checks the hard conditions in the database and records the anchor against the lock;
  5. writes an audit_events row.

Who may lock: the capability finance.period.close (Cap.FINANCE_PERIOD_CLOSE), held by the Treasurer alone. That is
enforced at the callback (@require_action); this module does not know who is calling.
"""
from __future__ import annotations

import logging

from app.security import ledger_anchor

log = logging.getLogger(__name__)

MIN_REASON = 10


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _default
    return _default


def fy_label(fy) -> str:
    f = int(fy)
    return f"{f}-{str(f + 1)[-2:]}"


def get_lock_state(society_id: int, fy: int, db=None) -> dict:
    """Everything the panel shows: the read-only preview, the locks to date and, for the selected year, its anchor."""
    d = _db(db)
    preview = d._execute("SELECT * FROM fn_fy_lock_preview(%s, %s)", (society_id, fy), fetch_one=True) or {}
    locks = d._execute(
        """SELECT l.id, l.locked_through, l.locked_at, l.notes, l.resolution_id, l.anchor_id,
                  u.name AS locked_by_name
             FROM fy_locks l LEFT JOIN users u ON u.id = l.locked_by
            WHERE l.society_id = %s ORDER BY l.locked_through DESC""", (society_id,), fetch_all=True) or []
    this = next((l for l in locks if int(l["locked_through"]) == int(fy)), None)
    anchor = None
    if this and this.get("anchor_id"):
        anchor = d._execute(
            """SELECT a.*, fn_anchor_message(a.id) AS message FROM ledger_chain_anchors a
                WHERE a.id = %s AND a.society_id = %s""", (this["anchor_id"], society_id), fetch_one=True)
    return {"preview": dict(preview), "locks": [dict(l) for l in locks], "this_lock": this,
            "anchor": dict(anchor) if anchor else None}


def lock_fy(society_id: int, fy: int, user_id: int | None, reason: str, understood: bool,
            resolution_id: int | None = None, db=None) -> tuple[bool, str, dict]:
    """Lock the year. -> (ok, message, details). Never raises for an expected refusal."""
    d = _db(db)
    try:
        fy = int(fy)
    except (TypeError, ValueError):
        return False, "No financial year is selected.", {}
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        return False, f"Give the reason for locking the year (at least {MIN_REASON} characters), for the audit trail.", {}
    if not understood:
        return False, "Tick the box to confirm you understand that a locked year can never be reopened.", {}

    pv = d._execute("SELECT * FROM fn_fy_lock_preview(%s, %s)", (society_id, fy), fetch_one=True)
    if not pv:
        return False, "The year could not be checked.", {}
    if not pv["can_lock"]:
        return False, f"FY {fy_label(fy)} cannot be locked: {pv['blockers']}.", {"preview": dict(pv)}

    anchor = None
    anchor_note = ""
    try:
        anchor = ledger_anchor.anchor_society(society_id, user_id, "fy_lock", d)
    except Exception as exc:                                   # noqa: BLE001 - decided below
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else "unknown error"
        if "no ledger entries" in first:
            anchor_note = " The ledger has no entries, so there was nothing to anchor."
        else:
            return False, f"The ledger could not be anchored, so the year was NOT locked: {first}", {}

    try:
        row = d._execute("SELECT fn_lock_fy(%s, %s, %s, %s, %s, %s) AS id",
                         (society_id, fy, user_id, resolution_id, reason, anchor["anchor_id"] if anchor else None),
                         fetch_one=True)
    except Exception as exc:                                   # noqa: BLE001 - the database's message is human-readable
        first = str(exc).strip().splitlines()[0]
        log.warning("FY lock refused (society=%s fy=%s): %s", society_id, fy, first)
        return False, first, {"anchor": anchor}

    lock_id = row["id"] if row else None
    try:
        from app.security import service_guard
        service_guard.audit_event(
            "fy.lock", "fy_lock", f"{society_id}:{fy}",
            after={"financial_year": fy, "lock_id": lock_id, "anchor_id": anchor["anchor_id"] if anchor else None,
                   "resolution_id": resolution_id},
            reason=reason, permission_used="finance.period.close", society_id=society_id)
    except Exception:                                          # noqa: BLE001 - the lock stands; the failure is logged
        log.exception("audit row for FY lock %s/%s was not written", society_id, fy)

    return True, (f"FY {fy_label(fy)} is locked. No entry can be posted into it or any earlier year, and the lock "
                  f"cannot be undone.{anchor_note}"), {"lock_id": lock_id, "anchor": anchor}
