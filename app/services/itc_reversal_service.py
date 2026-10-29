"""Proportionate ITC reversal for exempt supplies (Plan v3, task 1.7; CGST Rules, Rule 42).

PROVISIONAL until the CA signs the formula off (task 0.3): a working can be computed any time, but it is posted only
once the CA's confirmation (name, reference, date) and the two journal accounts the CA chose are on file. All
arithmetic is in the database (fn_itc_rule42) so the books and any export can never disagree; this module checks who
may act, turns database refusals into messages that are safe to show, and writes the audit row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

HEADS = ("cgst", "sgst", "igst")
KINDS = ("period", "annual")


class ItcRefused(RuntimeError):
    """Safe to show to the user."""


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def _may_act(d, society_id, user_id) -> bool:
    from app.services import receivable_dispute_service as rds
    return rds.may_act(society_id, user_id, db=d)


def _is_admin(d, society_id, user_id) -> bool:
    u = d._execute("SELECT role FROM users WHERE id=%s AND society_id=%s", (user_id, society_id), fetch_one=True) or {}
    return u.get("role") == "admin"


def _clean(exc) -> str:
    msg = str(exc).split("\n")[0].replace("ERROR:", "").strip()
    if "uq_itc_register_live" in msg:
        return "A row for this year, period and tax head already exists. Discard the draft or reverse the posted row first."
    if "ck_itc_period_dates" in msg:
        return "The period must fall inside the financial year (1 April to 31 March)."
    return msg or "Could not save."


def _audit(action, row_id, society_id, user_id, after, reason):
    try:
        from app.security.service_guard import audit_event
        audit_event(action, "itc_reversal_register", row_id, after=after, reason=reason, society_id=society_id)
    except Exception:                                                     # noqa: BLE001  (an audit outage must not hide the result)
        pass


def _d(v) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(f"'{v}' is not a number.") from exc


def formula_status(society_id, db=None) -> dict:
    """Is the formula confirmed by the CA, and what has been set up for posting?"""
    r = _db(db)._execute(
        """SELECT itc_reversal_confirmed_by AS by, itc_reversal_confirmed_ref AS ref, itc_reversal_confirmed_on AS on_date,
                  itc_reversal_debit_acc_id AS debit_acc_id, itc_reversal_credit_acc_id AS credit_acc_id,
                  itc_reversal_nonbusiness_pct AS nonbusiness_pct
             FROM society_compliance_settings WHERE society_id=%s""", (society_id,), fetch_one=True) or {}
    r["confirmed"] = bool(r.get("by"))
    r["postable"] = bool(r.get("by") and r.get("debit_acc_id") and r.get("credit_acc_id"))
    r["status"] = "confirmed" if r["confirmed"] else "provisional"
    return r


def record_ca_confirmation(society_id, user_id, by, ref, on_date, debit_acc_id, credit_acc_id, nonbusiness_pct=0, db=None) -> None:
    """The administrator records that the CA has signed the formula off, and the two accounts the CA chose for the journal."""
    d = _db(db)
    if not _is_admin(d, society_id, user_id):
        raise ItcRefused("Only the administrator can record the CA's confirmation.")
    if not (by or "").strip() or not (ref or "").strip():
        raise ItcRefused("Record who confirmed it (the CA's name) and the reference of the confirmation.")
    if not debit_acc_id or not credit_acc_id or int(debit_acc_id) == int(credit_acc_id):
        raise ItcRefused("Choose two different accounts for the journal (debit and credit).")
    pct = _d(nonbusiness_pct)
    if pct < 0 or pct > 100:
        raise ItcRefused("The non-business percentage must be between 0 and 100.")
    try:
        d._execute("""UPDATE society_compliance_settings SET itc_reversal_confirmed_by=%s, itc_reversal_confirmed_ref=%s,
                             itc_reversal_confirmed_on=%s, itc_reversal_debit_acc_id=%s, itc_reversal_credit_acc_id=%s,
                             itc_reversal_nonbusiness_pct=%s, updated_at=NOW() WHERE society_id=%s""",
                   (by.strip(), ref.strip(), on_date or date.today(), int(debit_acc_id), int(credit_acc_id), pct, society_id))
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(_clean(exc)) from exc
    _audit("itc.formula.confirm", society_id, society_id, user_id, {"by": by, "ref": ref}, "CA confirmation recorded")


def compute(society_id, user_id, kind, fy, tax_head, t, t1, t2, t3, t4, e, f, basis,
            period_start=None, period_end=None, db=None) -> int:
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise ItcRefused("Only the administrator or a serving office-bearer can work out an ITC reversal.")
    if kind not in KINDS:
        raise ItcRefused("Choose a monthly period or the annual true-up.")
    if tax_head not in HEADS:
        raise ItcRefused("Choose CGST, SGST or IGST.")
    try:
        r = d._execute("SELECT fn_compute_itc_reversal(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS id",
                       (society_id, kind, int(fy), period_start, period_end, tax_head,
                        _d(t), _d(t1), _d(t2), _d(t3), _d(t4), _d(e), _d(f), basis or "", user_id), fetch_one=True)
    except ItcRefused:
        raise
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(_clean(exc)) from exc
    _audit("itc.reversal.compute", r["id"], society_id, user_id, {"kind": kind, "fy": fy, "head": tax_head}, basis)
    return r["id"]


def post(society_id, user_id, register_id, db=None):
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise ItcRefused("Only the administrator or a serving office-bearer can post an ITC reversal.")
    try:
        r = d._execute("SELECT fn_post_itc_reversal(%s,%s,%s) AS j", (society_id, register_id, user_id), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(_clean(exc)) from exc
    _audit("itc.reversal.post", register_id, society_id, user_id, {"journal_id": r["j"]}, "posted")
    return r["j"]


def reverse(society_id, user_id, register_id, reason, db=None):
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise ItcRefused("Only the administrator or a serving office-bearer can reverse an ITC reversal.")
    try:
        r = d._execute("SELECT fn_reverse_itc_reversal(%s,%s,%s,%s) AS j", (society_id, register_id, user_id, reason or ""), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(_clean(exc)) from exc
    _audit("itc.reversal.reverse", register_id, society_id, user_id, {"reversal_journal_id": r["j"]}, reason)
    return r["j"]


def discard(society_id, user_id, register_id, db=None) -> None:
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise ItcRefused("Only the administrator or a serving office-bearer can discard a draft.")
    try:
        d._execute("SELECT fn_discard_itc_draft(%s,%s)", (society_id, register_id), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise ItcRefused(_clean(exc)) from exc


def register(society_id, fy=None, db=None) -> list[dict]:
    return _db(db)._execute(
        """SELECT * FROM itc_reversal_register WHERE society_id=%s AND (%s::INT IS NULL OR financial_year=%s)
            ORDER BY financial_year DESC, tax_head, kind DESC, period_start NULLS LAST, id""",
        (society_id, fy, fy), fetch_all=True) or []
