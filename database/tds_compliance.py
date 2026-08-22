# database/tds_compliance.py
"""
Indian CHS/RWA TDS compliance helpers (Phase 4 / 4d / 5).

These are thin wrappers over the matching SQL functions in estatehub.sql
(fn_compute_tds_pct, fn_vendor_tds_cumulative_fy, fn_tds_section_rate,
fn_is_capital_account, fn_tds_summary_fy). They are the single choke point
the expense-form autofill callback, the expense-save handler, and the 26Q
export all call through, so the "does TDS apply, at what rate, on what
basis" logic lives in exactly one place and is unit-testable without a live
PG16 instance (the FakeDB in test/fake_db.py mirrors these functions).

All functions are read-only except where noted; none of them post ledger
rows.
"""
from __future__ import annotations

from typing import Any


def _fy_from_date(d) -> str:
    """FY START year for a date (e.g. 2026-05-01 -> '2026', 2027-01-15 -> '2026')."""
    if hasattr(d, "year"):
        yr, mo = d.year, d.month
    else:
        s = str(d)
        yr = int(s[:4])
        mo = int(s[5:7]) if len(s) > 6 else 1
    return str(yr if mo >= 4 else yr - 1)


def get_section_rate(db, society_id: int, section: str, as_of=None) -> dict | None:
    """Resolve the active CBDT rate row for a TDS section, or None if the
    section isn't configured for this society. Returns
    {rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold}."""
    if not section:
        return None
    row = db._execute(
        "SELECT * FROM fn_tds_section_rate(%s,%s,%s)",
        (society_id, section, as_of), fetch_one=True,
    )
    if not row or row.get("rate") is None:
        return None
    return row


def vendor_cumulative_tds(
    db, society_id: int, vendor_id: int, section: str, fy: str,
    exclude_expense_id: int | None = None,
) -> float:
    """Sum of confirmed, TDS-deducted expense amounts for one vendor/section
    within FY `fy` (start-year string), excluding `exclude_expense_id`."""
    if not vendor_id or not section:
        return 0.0
    row = db._execute(
        "SELECT fn_vendor_tds_cumulative_fy(%s,%s,%s,%s,%s) AS cum",
        (society_id, vendor_id, section, fy, exclude_expense_id), fetch_one=True,
    )
    return float((row or {}).get("cum", 0) or 0)


def compute_tds_pct(
    db, society_id: int, vendor_id: int | None, section: str | None, fy: str,
    amount: float, pan_captured: bool = True,
) -> dict:
    """Decide whether TDS applies to one bill and at what rate.

    Returns {tds_pct, applies, basis} — mirrors fn_compute_tds_pct exactly.
    `basis` is one of: 'single-bill', 'annual-aggregate', 'below-threshold',
    'section-not-configured', 'no-section-or-zero-amount'.
    """
    if not section or not amount:
        return {"tds_pct": 0.0, "applies": False, "basis": "no-section-or-zero-amount"}
    row = db._execute(
        "SELECT * FROM fn_compute_tds_pct(%s,%s,%s,%s,%s,%s)",
        (society_id, vendor_id, section, fy, amount, pan_captured), fetch_one=True,
    ) or {}
    return {
        "tds_pct": float(row.get("tds_pct", 0) or 0),
        "applies": bool(row.get("applies", False)),
        "basis": row.get("basis", "below-threshold"),
    }


def vendor_has_pan(db, vendor_id: int) -> bool:
    """True when the vendor has a non-empty PAN captured."""
    if not vendor_id:
        return False
    row = db._execute(
        "SELECT pan_number FROM vendors WHERE id=%s", (vendor_id,), fetch_one=True,
    )
    pan = (row or {}).get("pan_number")
    return bool(pan and str(pan).strip())


def no_pan_action(db, society_id: int) -> str:
    """'warn' or 'block' — what to do when a TDS-relevant vendor has no PAN.
    Defaults to 'warn' (recommended: don't block legitimate small-vendor
    payments — TDS is still deducted at the higher 206AA rate)."""
    row = db._execute(
        "SELECT tds_no_pan_action FROM society_compliance_settings WHERE society_id=%s",
        (society_id,), fetch_one=True,
    )
    return (row or {}).get("tds_no_pan_action") or "warn"


def is_capital_account(db, society_id: int, acc_id: int) -> bool:
    """True when acc_id sits on the Balance-Sheet branch (asset/liability)
    rather than the Income & Expenditure (P&L) branch → a capital expense."""
    if not acc_id:
        return False
    row = db._execute(
        "SELECT fn_is_capital_account(%s,%s) AS cap", (society_id, acc_id),
        fetch_one=True,
    )
    return bool((row or {}).get("cap", False))


def account_is_depreciable(db, society_id: int, acc_id: int) -> dict:
    """Return {is_capital, is_depreciable, depreciation_percent} for an
    account, so the expense form can prompt for a depreciation-rate
    confirmation (Phase 5.2) when a capital asset is being booked."""
    if not acc_id:
        return {"is_capital": False, "is_depreciable": False, "depreciation_percent": 0.0}
    row = db._execute(
        "SELECT depreciation_percent, is_depreciable FROM accounts WHERE id=%s AND society_id=%s",
        (acc_id, society_id), fetch_one=True,
    ) or {}
    return {
        "is_capital": is_capital_account(db, society_id, acc_id),
        "is_depreciable": bool(row.get("is_depreciable", False)),
        "depreciation_percent": float(row.get("depreciation_percent", 0) or 0),
    }


def suggest_expense_tax_fields(
    db, society_id: int, acc_id: int | None, vendor_id: int | None,
    amount: float, expense_date=None, exclude_expense_id: int | None = None,
) -> dict:
    """All-in-one helper for the expense form: given the chosen account,
    vendor, and amount, return the auto-suggested TDS %/section plus the
    capital/depreciation flags and any no-PAN warning.

    Returns:
        {
          "tds_pct": float,           # suggested % (0 if not applicable)
          "tds_section": str|None,    # inherited from the account
          "tds_applies": bool,
          "tds_basis": str,
          "pan_captured": bool,
          "pan_action": "warn"|"block",
          "pan_warning": str|None,    # populated when TDS applies & no PAN
          "is_capital": bool,
          "is_depreciable": bool,
          "depreciation_percent": float,
        }
    """
    fy = _fy_from_date(expense_date) if expense_date else str(_fy_from_date(__import__("datetime").date.today()))

    # Inherit TDS section from the chosen account (Phase 1.3).
    section_row = db._execute(
        "SELECT tds_section FROM accounts WHERE id=%s AND society_id=%s",
        (acc_id, society_id), fetch_one=True,
    ) if acc_id else None
    section = (section_row or {}).get("tds_section") or None

    pan_captured = vendor_has_pan(db, vendor_id) if vendor_id else False
    comp = compute_tds_pct(db, society_id, vendor_id, section, fy, amount, pan_captured)

    result = {
        "tds_pct": comp["tds_pct"],
        "tds_section": section,
        "tds_applies": comp["applies"],
        "tds_basis": comp["basis"],
        "pan_captured": pan_captured,
        "pan_action": no_pan_action(db, society_id),
        "pan_warning": None,
        "is_capital": False,
        "is_depreciable": False,
        "depreciation_percent": 0.0,
    }

    # No-PAN warning/block only matters when TDS actually applies.
    if comp["applies"] and not pan_captured:
        action = result["pan_action"]
        rate_note = f"Section 206AA higher rate applies (no PAN on file)."
        if action == "block":
            result["pan_warning"] = (
                f"BLOCKED: vendor has no PAN and society policy is 'block'. "
                f"Capture the vendor's PAN before recording this TDS-relevant payment. ({rate_note})"
            )
        else:
            result["pan_warning"] = (
                f"This vendor has no PAN on file — TDS will be deducted at the "
                f"higher no-PAN rate. ({rate_note})"
            )

    dep = account_is_depreciable(db, society_id, acc_id) if acc_id else {
        "is_capital": False, "is_depreciable": False, "depreciation_percent": 0.0}
    result["is_capital"] = dep["is_capital"]
    result["is_depreciable"] = dep["is_depreciable"]
    result["depreciation_percent"] = dep["depreciation_percent"]

    return result
