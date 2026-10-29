"""Classify the society's income and fund accounts for GST (Plan v4, C.6; ER.md X-02).

The GST turnover worksheet (s.2(6) CGST Act) counts a credit account as a taxable or an exempt supply, or leaves it out as
"not a supply" or "tax". The software never guesses: a head that is not unambiguous stays UNCLASSIFIED, and while the
threshold falls between the classified and the unclassified amounts GST is not charged to members and a compliance flag
is raised. Until now only fn_set_gst_supply_class from SQL could classify an account. This is the service behind the screen
that lets the CA (or the Treasurer, or the Secretary when no Treasurer is seated: the people who may edit TDS and GST rates)
do it without SQL.

The database function checks the account is a credit account of this society, and the table's own check demands a
reference to the CA's or advocate's advice for every class except 'taxable'. This module adds who may act, a clear message
for each refusal, and the audit row.
"""
from __future__ import annotations

from datetime import date

CLASSES = (
    ("taxable", "Taxable supply"),
    ("exempt", "Exempt supply (counts towards turnover)"),
    ("not_a_supply", "Not a supply (capital, liability, fund)"),
    ("tax", "GST payable (does not count)"),
)
LABEL = dict(CLASSES)
NEEDS_REF = ("exempt", "not_a_supply", "tax")
MIN_REF = 5
RESOURCE = "gst_supply_class"


def _db(db=None):
    if db is not None:
        return db
    from database.db_manager import db as _d
    return _d


def current_fy(today: date | None = None) -> int:
    """The financial year (starting 1 April) that `today` falls in."""
    today = today or date.today()
    return today.year if today.month >= 4 else today.year - 1


def accounts(society_id: int, fy: int | None = None, db=None) -> list[dict]:
    """Every credit-natured account of the society with its class, where the class came from, and the year's movement.
    Unclassified accounts that carry money come first: they are what the CA has to decide."""
    fy = fy or current_fy()
    return _db(db)._execute(
        """WITH mv AS (
               SELECT t.acc_id, SUM(CASE WHEN t.entry_side = 'Cr' THEN t.amount ELSE -t.amount END)::NUMERIC(15,2) AS net
                 FROM transactions t
                WHERE t.society_id = %s AND t.status = 'paid'
                  AND t.trx_date BETWEEN MAKE_DATE(%s, 4, 1) AND MAKE_DATE(%s + 1, 3, 31)
                GROUP BY t.acc_id)
           SELECT a.id, a.name, a.tab_name, a.gst_supply_class AS own_class, a.gst_class_ref AS ref,
                  COALESCE(a.gst_supply_class, CASE WHEN a.is_gst_exempt_supply THEN 'exempt' END,
                           fn_gst_default_supply_class(a.tab_name)) AS supply_class,
                  CASE WHEN a.gst_supply_class IS NOT NULL THEN 'society'
                       WHEN a.is_gst_exempt_supply THEN 'legacy flag'
                       WHEN fn_gst_default_supply_class(a.tab_name) IS NOT NULL THEN 'default'
                       ELSE 'unclassified' END AS class_source,
                  COALESCE(mv.net, 0) AS amount
             FROM accounts a LEFT JOIN mv ON mv.acc_id = a.id
            WHERE a.society_id = %s AND a.drcr_account = 'Cr'
            ORDER BY (COALESCE(a.gst_supply_class, CASE WHEN a.is_gst_exempt_supply THEN 'exempt' END,
                               fn_gst_default_supply_class(a.tab_name)) IS NULL) DESC,
                     (COALESCE(mv.net, 0) <> 0) DESC, a.tab_name, a.id""", (society_id, fy, fy, society_id), fetch_all=True) or []


def gate(society_id: int, fy: int | None = None, db=None) -> dict:
    """The three-state turnover gate for the year: taxable, exempt, unclassified, bounds, threshold, state."""
    row = _db(db)._execute("SELECT * FROM fn_gst_turnover_gate(%s,%s)", (society_id, fy or current_fy()), fetch_one=True)
    return dict(row) if row else {}


def classify(society_id: int, acc_id: int, supply_class: str | None, ref: str | None, db=None, allowed: tuple[bool, str] | None = None) -> str:
    """Set (or, with supply_class None, clear) an account's class. Raises PermissionError or ValueError with a message that is
    safe to show. `allowed` lets a caller pass the permission decision it already made; by default it is asked here."""
    if allowed is None:
        from app.services import tax_rate_service as trs
        allowed = trs.may_edit_tax_rates(society_id)
    if not allowed[0]:
        from app.security.service_guard import audit_event
        audit_event("authz.denied", RESOURCE, society_id, reason=allowed[1])
        raise PermissionError(allowed[1])
    supply_class = (supply_class or "").strip() or None
    ref = (ref or "").strip() or None
    if supply_class is not None and supply_class not in LABEL:
        raise ValueError("Choose taxable, exempt, not a supply, or GST payable.")
    if supply_class in NEEDS_REF and (ref is None or len(ref) < MIN_REF):
        raise ValueError(f"Give the reference to the CA's or advocate's advice (at least {MIN_REF} characters): "
                         f"{LABEL[supply_class].split(' (')[0].lower()} needs one.")
    d = _db(db)
    before = d._execute("SELECT gst_supply_class, gst_class_ref FROM accounts WHERE society_id=%s AND id=%s", (society_id, acc_id), fetch_one=True)
    try:
        d._execute("SELECT fn_set_gst_supply_class(%s,%s,%s,%s)", (society_id, int(acc_id), supply_class, ref), fetch_one=True)
    except Exception as exc:                                               # noqa: BLE001
        first = str(exc).strip().splitlines()[0].replace("ERROR:", "").strip() if str(exc).strip() else "Could not save."
        raise ValueError("Only a credit-natured account of this society can be classified." if "No credit-natured account" in first else first) from exc
    try:
        from app.security.service_guard import audit_event
        audit_event("gst.class.set", RESOURCE, acc_id, before=dict(before) if before else None,
                    after={"gst_supply_class": supply_class, "gst_class_ref": ref}, society_id=society_id)
    except Exception:                                                      # noqa: BLE001  an audit outage must not hide the result
        pass
    return "Classification cleared; the default for the ledger head applies." if supply_class is None else f"Saved as {LABEL[supply_class].split(' (')[0].lower()}."
