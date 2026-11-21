"""MSME (Micro, Small & Medium Enterprises) payment compliance for the
application (Plan Streamlining_Brought_Forward, section 6 / ICAI3 G10).

Wraps the three SQL functions that already exist in database/estatehub.sql:

* fn_vendor_outstanding(society_id, vendor_id, asof)  - bills vs payments
* fn_vendor_aging(society_id, vendor_id, asof)        - 45/90-day buckets
* fn_msme_payment_compliance(society_id, vendor_id, asof) - s.15/s.16 MSMED Act 2006

Pure service layer: no Dash, no Flask. Returns plain dicts/lists so a route
or a card can consume them without knowing SQL.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from database.db_manager import db


def _asof(asof: Optional[date]) -> date:
    return asof or date.today()


def vendor_outstanding(society_id: int, vendor_id: int,
                       asof: Optional[date] = None) -> dict:
    """Per-vendor outstanding as at ``asof`` (bills - confirmed payments)."""
    rows = db.execute(
        "SELECT * FROM fn_vendor_outstanding(%s, %s, %s)",
        (society_id, vendor_id, _asof(asof)), fetch_all=True)
    return rows[0] if rows else {}


def vendor_aging(society_id: int, vendor_id: int,
                 asof: Optional[date] = None) -> dict:
    """Aging buckets (current / 46-90 / 90+) for a vendor's outstanding bills."""
    rows = db.execute(
        "SELECT * FROM fn_vendor_aging(%s, %s, %s)",
        (society_id, vendor_id, _asof(asof)), fetch_all=True)
    return rows[0] if rows else {}


def msme_payment_compliance(society_id: int, vendor_id: int,
                            asof: Optional[date] = None) -> dict:
    """MSME 45-day payment compliance and interest exposure for a vendor.

    Mirrors fn_msme_payment_compliance: compliant/reason/interest_exposure.
    Non-MSME-registered vendors are reported compliant with a note that the
    45-day rule does not apply.
    """
    rows = db.execute(
        "SELECT * FROM fn_msme_payment_compliance(%s, %s, %s)",
        (society_id, vendor_id, _asof(asof)), fetch_all=True)
    return rows[0] if rows else {}
