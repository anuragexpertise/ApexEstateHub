"""Approval ladder for expenses (Plan v3, task 2.5; bye-law 49).

At or below the society's threshold (default Rs 20,000) an administrator verifies as before. Above it the expense needs
the Managing Committee: a resolution reference, and signatures (password-confirmed, document_signing) from at least
`min_signers` DIFFERENT serving office-bearers. Safeguards:
  * one person counts once, and a signer must hold a serving office on the day (document_signing);
  * nobody signs a payment to their own flat;
  * payments to the same payee within 30 days are added together, so a large bill cannot be split to stay under the limit;
  * if the Treasurer's seat is vacant the other eligible offices may still sign (nothing here requires the Treasurer).
"""
from __future__ import annotations

from decimal import Decimal

from app.services import document_signing as ds

DEFAULT_THRESHOLD = Decimal("20000")
DEFAULT_MIN = 2
AGGREGATE_DAYS = 30


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def get_policy(society_id: int, db=None) -> dict:
    r = _db(db)._execute("SELECT threshold, min_signers, require_resolution FROM expense_approval_policy WHERE society_id=%s",
                         (society_id,), fetch_one=True)
    return dict(r) if r else {"threshold": DEFAULT_THRESHOLD, "min_signers": DEFAULT_MIN, "require_resolution": True}


def set_policy(society_id: int, threshold, min_signers: int, require_resolution: bool, actor_id: int, db=None) -> None:
    if Decimal(str(threshold)) < 0 or not (1 <= int(min_signers) <= 5):
        raise ds.SigningRefused("Threshold must be zero or more and the number of signers 1 to 5.")
    _db(db)._execute("""INSERT INTO expense_approval_policy (society_id, threshold, min_signers, require_resolution, updated_by)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (society_id) DO UPDATE SET threshold=EXCLUDED.threshold,
                        min_signers=EXCLUDED.min_signers, require_resolution=EXCLUDED.require_resolution,
                        updated_by=EXCLUDED.updated_by, updated_at=NOW()""",
                     (society_id, threshold, int(min_signers), bool(require_resolution), actor_id))


def effective_amount(expense: dict, db=None) -> Decimal:
    """This expense plus the same payee's other live expenses in the 30 days either side (aggregation rule)."""
    r = _db(db)._execute(
        """SELECT COALESCE(SUM(amount),0) AS t FROM expenses
            WHERE society_id=%s AND entity_id=%s AND role=%s AND status <> 'cancelled' AND id <> %s
              AND expense_date BETWEEN %s::date - %s AND %s::date + %s""",
        (expense["society_id"], expense["entity_id"], expense["role"], expense["id"],
         expense["expense_date"], AGGREGATE_DAYS, expense["expense_date"], AGGREGATE_DAYS), fetch_one=True)
    return Decimal(str(expense["amount"])) + Decimal(str((r or {}).get("t") or 0))


def required_signers(expense_id: int, db=None) -> tuple[int, str]:
    """(signatures needed, why). 0 means an administrator may verify without the committee."""
    d = _db(db)
    e = d._execute("SELECT id, society_id, entity_id, role, amount, expense_date FROM expenses WHERE id=%s", (expense_id,), fetch_one=True)
    if not e:
        raise ds.SigningRefused("Expense not found.")
    pol = get_policy(e["society_id"], d)
    eff = effective_amount(e, d)
    if eff <= Decimal(str(pol["threshold"])):
        return 0, ""
    return int(pol["min_signers"]), (f"Rs {eff:,.2f} (this bill plus the same payee's bills within {AGGREGATE_DAYS} days) is above "
                                     f"Rs {Decimal(str(pol['threshold'])):,.2f}")


def gate(expense_id: int, db=None) -> tuple[bool, str]:
    """May this expense be verified (money posted) now? Returns (ok, reason when not)."""
    d = _db(db)
    need, why = required_signers(expense_id, d)
    if need == 0:
        return True, ""
    e = d._execute("SELECT society_id, approval_resolution_ref FROM expenses WHERE id=%s", (expense_id,), fetch_one=True)
    pol = get_policy(e["society_id"], d)
    if pol["require_resolution"] and not (e["approval_resolution_ref"] or "").strip():
        return False, f"{why}. It needs a Managing Committee resolution reference before it can be approved."
    st = ds.status("expense", expense_id, d)
    if st["declined"]:
        return False, "An office-bearer has declined this expense; see the reason in its signatures."
    if st["people_signed"] < need:
        return False, f"{why}. It needs {need} different office-bearers to approve; {st['people_signed']} so far."
    return True, ""


def save_resolution_ref(expense_id: int, society_id: int, user_id: int, ref: str, db=None) -> None:
    """Record the MC resolution that approved a spend. Only a serving office-bearer or the society admin, only while pending."""
    d = _db(db)
    ref = (ref or "").strip()[:255]
    if len(ref) < 3:
        raise ds.SigningRefused("Enter the resolution reference (for example the meeting date and resolution number).")
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    if u.get("role") != "admin" and not ds.serving_offices(society_id, user_id, db=d):
        raise ds.SigningRefused("Only the administrator or a serving office-bearer can record this.")
    n = d._execute("UPDATE expenses SET approval_resolution_ref=%s WHERE id=%s AND society_id=%s AND status='pending' RETURNING id",
                   (ref, expense_id, society_id), fetch_one=True)
    if not n:
        raise ds.SigningRefused("Only a pending expense can take a resolution reference.")
