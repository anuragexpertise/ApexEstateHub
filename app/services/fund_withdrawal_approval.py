"""Fund withdrawals awaiting approval (Plan v4, C.5).

A withdrawal from a Capital, Reserve, Sinking, Repair or Corpus fund that needs more than one signature stays 'pending'
until enough different serving office-bearers have approved it. Approving and declining go through
document_signing.sign (kind 'fund_withdrawal'): the signer re-enters their own login password, a wrong password
approves nothing, an approval counts towards the withdrawal in the database (which posts it on the last one), and a
decline cancels it. This module only lists what is waiting and says who may look at it.
"""
from __future__ import annotations

from app.services import document_signing as ds


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def may_view(society_id: int, user_id: int | None, role: str | None, db=None) -> bool:
    """The administrator (who requests withdrawals) and serving office-bearers (who approve them)."""
    if not user_id:
        return False
    return role == "admin" or bool(ds.serving_offices(society_id, user_id, db=_db(db)))


def pending(society_id: int, db=None) -> list[dict]:
    """Withdrawals still waiting for approvals, oldest first, with how many have been given."""
    return _db(db)._execute(
        """SELECT fu.id, fu.amount, fu.mode, fu.particulars, fu.approval_ref, fu.approval_date, fu.signatories_required, fu.created_at,
                  fa.name AS fund_name, u.name AS requested_by,
                  (SELECT COUNT(*) FROM fund_utilization_signoffs s WHERE s.utilization_id = fu.id) AS approvals
             FROM fund_utilizations fu
             LEFT JOIN accounts fa ON fa.id = fu.fund_acc_id AND fa.society_id = fu.society_id
             LEFT JOIN users u ON u.id = fu.user_id
            WHERE fu.society_id = %s AND fu.status = 'pending'
            ORDER BY fu.created_at, fu.id""", (society_id,), fetch_all=True) or []


def state(util_id: int, db=None) -> str | None:
    r = _db(db)._execute("SELECT status FROM fund_utilizations WHERE id=%s", (util_id,), fetch_one=True)
    return r["status"] if r else None
