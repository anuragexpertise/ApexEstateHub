"""Ratification register and rule-application register (Plan v3, tasks 2.3 and 2.4).

Ratification: an irregular item (spend before approval, emergency spend, arrears write-off, interest waiver) stands for
a limited time and then needs a ratifying decision. Rejected or expired items have their postings reversed through
fn_post_reversal_journal (in the database), and show in the register as reversed.

Rule applications: each posting is linked to the rule key, layer, decision, resolution number, advocate-opinion
reference and effective dates it was made under. The register is append-only and exportable.
"""
from __future__ import annotations

import csv
import io

KINDS = ("spend_before_approval", "emergency_spend", "arrears_writeoff", "interest_waiver")
KIND_LABEL = {"spend_before_approval": "Spend before approval", "emergency_spend": "Emergency spend",
              "arrears_writeoff": "Arrears write-off", "interest_waiver": "Interest waiver"}


class RatificationRefused(RuntimeError):
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


def _clean(exc) -> str:
    if "uq_ratification_items_source" in str(exc):
        return "This item is already in the register."
    msg = str(exc).split("\n")[0]
    return msg.replace("ERROR:", "").strip() or "Could not save."


def raise_item(society_id, kind, description, amount, user_id, source_table=None, source_id=None, ratify_by=None, db=None) -> int:
    d = _db(db)
    if kind not in KINDS:
        raise RatificationRefused("Choose what kind of irregular item this is.")
    if not _may_act(d, society_id, user_id):
        raise RatificationRefused("Only the administrator or a serving office-bearer can record this.")
    try:
        r = d._execute("SELECT fn_raise_ratification(%s,%s,%s,%s,%s,%s,%s,%s) AS id",
                       (society_id, kind, source_table, source_id, amount, description, user_id, ratify_by), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise RatificationRefused(_clean(exc)) from exc
    return r["id"]


def decide(society_id, item_id, ratify: bool, resolution_id, user_id, note=None, db=None) -> str:
    d = _db(db)
    if not _may_act(d, society_id, user_id):
        raise RatificationRefused("Only the administrator or a serving office-bearer can decide this.")
    if not d._execute("SELECT 1 FROM ratification_items WHERE id=%s AND society_id=%s", (item_id, society_id), fetch_one=True):
        raise RatificationRefused("Item not found.")
    try:
        r = d._execute("SELECT fn_decide_ratification(%s,%s,%s,%s,%s) AS msg", (item_id, ratify, resolution_id, user_id, note), fetch_one=True)
    except Exception as exc:                                              # noqa: BLE001
        raise RatificationRefused(_clean(exc)) from exc
    return r["msg"]


def register(society_id, db=None) -> list[dict]:
    return _db(db)._execute(
        """SELECT i.*, r.body AS resolution_text FROM ratification_items i LEFT JOIN resolutions r ON r.id = i.resolution_id
            WHERE i.society_id=%s ORDER BY (i.status='pending') DESC, i.ratify_by, i.id""", (society_id,), fetch_all=True) or []


def emergency_verify_expense(society_id, expense_id, user_id, reason, db=None) -> str:
    """Post an expense that is above the approval limit without the committee's signatures, as an EMERGENCY spend that
    must be ratified within 90 days or it is reversed. Needs a written reason."""
    d = _db(db)
    if len((reason or "").strip()) < 10:
        raise RatificationRefused("Say why this could not wait for approval (at least 10 characters).")
    if not _may_act(d, society_id, user_id):
        raise RatificationRefused("Only the administrator or a serving office-bearer can do this.")
    e = d._execute("SELECT id, amount, particulars, status FROM expenses WHERE id=%s AND society_id=%s", (expense_id, society_id), fetch_one=True)
    if not e or e["status"] != "pending":
        raise RatificationRefused("Only a pending expense can be posted as an emergency spend.")
    from app.dash_apps.drilldown import loaders
    ok, msg = loaders.verify_expense(int(expense_id), confirmed_by=user_id, emergency=True)
    if not ok:
        raise RatificationRefused(msg)
    raise_item(society_id, "emergency_spend", f"Expense #{expense_id}: {e['particulars']} - {reason.strip()}", e["amount"], user_id,
               "expenses", expense_id, db=d)
    return "Posted as an emergency spend. It must be ratified within 90 days or it will be reversed."


# ── rule-application register ───────────────────────────────────────────────────────────────────────────────────
def record_rule_application(society_id, source_table, source_id, rule_key, decision, user_id=None, layer=None, resolution_id=None,
                            resolution_ref=None, advocate_opinion_ref=None, effective_from=None, effective_to=None,
                            journal_id=None, db=None) -> int:
    d = _db(db)
    if journal_id is None:
        j = d._execute("SELECT MIN(journal_id) AS j FROM transactions WHERE society_id=%s AND source_table=%s AND source_id=%s",
                       (society_id, source_table, source_id), fetch_one=True)
        journal_id = (j or {}).get("j")
    r = d._execute("""INSERT INTO rule_applications (society_id, source_table, source_id, journal_id, rule_key, layer, decision,
                         resolution_id, resolution_ref, advocate_opinion_ref, effective_from, effective_to, applied_by)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s, CURRENT_DATE),%s,%s) RETURNING id""",
                   (society_id, source_table, source_id, journal_id, rule_key, layer, decision, resolution_id, resolution_ref,
                    advocate_opinion_ref, effective_from, effective_to, user_id), fetch_one=True)
    return r["id"]


def rule_register(society_id, source_table=None, source_id=None, db=None) -> list[dict]:
    sql, p = "SELECT * FROM v_rule_application_register WHERE society_id=%s", [society_id]
    if source_table:
        sql += " AND source_table=%s"; p.append(source_table)
    if source_id:
        sql += " AND source_id=%s"; p.append(int(source_id))
    return _db(db)._execute(sql + " ORDER BY applied_at DESC, id DESC", p, fetch_all=True) or []


_EXPORT_COLS = ["id", "applied_at", "source_table", "source_id", "journal_id", "rule_key", "layer", "decision", "resolution_id",
                "resolution_ref", "advocate_opinion_ref", "effective_from", "effective_to", "journal_debits"]


def export_rule_register_csv(society_id, db=None) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(_EXPORT_COLS)
    for r in rule_register(society_id, db=db):
        w.writerow([r.get(c, "") for c in _EXPORT_COLS])
    return out.getvalue()
