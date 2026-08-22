# app/services/kpi_rule_links_service.py
"""
KPI Rule Links service — CRUD for external "Rules & Regulations" links
surfaced in the compliance-settings banner.

Links are scoped by:
  - category: which compliance setting they relate to (sinking_fund, gst_registered, etc.)
  - state: 'ALL' for Union-law links (CBIC, Income Tax), 2-letter code for state statutes

At render time, _compliance_rules_banner() fetches links matching the active
state (from societies.address or a new state column) plus 'ALL', so a UP
society sees both the UP Apartment Act links AND the CBIC/Income Tax links.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from database.db_manager import db


@dataclass
class KpiRuleLink:
    id: Optional[int] = None
    category: str = "other"
    state: str = "ALL"
    label: str = ""
    url: str = ""
    description: str = ""
    sort_order: int = 100
    is_active: bool = True
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


_CATEGORIES = {
    "sinking_fund": "Sinking Fund / Repair Fund Rate Basis",
    "repair_fund": "Repair Fund",
    "fund_gst": "Fund GST Exempt",
    "fund_interest": "Fund Charges Interest",
    "gst_registered": "GST Registered / GSTIN / Filing Cadence",
    "tds_no_pan": "TDS No-PAN Action",
    "rera": "RERA",
    "apartment_act": "Apartment Act / AOAs",
    "cooperative_act": "Cooperative Societies Act",
    "income_tax_mutuality": "Income Tax — Mutuality Principle",
    "other": "Other",
}

VALID_STATES = {
    "ALL", "UP", "MH", "KA", "TN", "DL", "RJ", "MP", "WB", "GJ",
    "TS", "AP", "BR", "HR", "PB", "KL",
}


def list_links(
    category: str | None = None,
    state: str | None = None,
    active_only: bool = True,
) -> list[KpiRuleLink]:
    """Return rule links, optionally filtered by category / state."""
    sql = "SELECT * FROM kpi_rule_links WHERE 1=1"
    params: list = []

    if active_only:
        sql += " AND is_active = TRUE"
        sql += " AND (effective_from IS NULL OR effective_from <= CURRENT_DATE)"
        sql += " AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)"
    if category:
        sql += " AND category = %s"
        params.append(category)
    if state:
        sql += " AND state = %s"
        params.append(state)

    sql += " ORDER BY sort_order ASC, label ASC"

    rows = db._execute(sql, tuple(params) if params else None, fetch_all=True) or []
    return [_row_to_link(r) for r in rows]


def get_links_for_categories(
    categories: list[str],
    state: str = "ALL",
) -> dict[str, list[KpiRuleLink]]:
    """Return {category: [link, ...]} for the given categories, including
    both state-specific and 'ALL' links, sorted by sort_order."""
    if not categories:
        return {}

    placeholders = ",".join(["%s"] * len(categories))
    sql = f"""
        SELECT * FROM kpi_rule_links
        WHERE category IN ({placeholders})
          AND is_active = TRUE
          AND (effective_from IS NULL OR effective_from <= CURRENT_DATE)
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
          AND state IN (%s, 'ALL')
        ORDER BY sort_order ASC, label ASC
    """
    params = tuple(categories) + (state,)

    rows = db._execute(sql, params, fetch_all=True) or []
    result: dict[str, list[KpiRuleLink]] = {cat: [] for cat in categories}
    for r in rows:
        link = _row_to_link(r)
        result.setdefault(link.category, []).append(link)
    return result


def get_link(link_id: int) -> KpiRuleLink | None:
    row = db._execute(
        "SELECT * FROM kpi_rule_links WHERE id = %s", (link_id,), fetch_one=True
    )
    return _row_to_link(row) if row else None


def create_link(link: KpiRuleLink) -> int:
    row = db._execute(
        """INSERT INTO kpi_rule_links
           (category, state, label, url, description, sort_order, is_active,
            effective_from, effective_to)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (
            link.category, link.state, link.label, link.url, link.description,
            link.sort_order, link.is_active, link.effective_from, link.effective_to,
        ),
        fetch_one=True,
    )
    return row["id"] if row else 0


def update_link(link: KpiRuleLink) -> bool:
    if not link.id:
        return False
    db._execute(
        """UPDATE kpi_rule_links SET
             category=%s, state=%s, label=%s, url=%s, description=%s,
             sort_order=%s, is_active=%s, effective_from=%s, effective_to=%s,
             updated_at=NOW()
           WHERE id=%s""",
        (
            link.category, link.state, link.label, link.url, link.description,
            link.sort_order, link.is_active, link.effective_from, link.effective_to,
            link.id,
        ),
    )
    return True


def delete_link(link_id: int) -> bool:
    db._execute("DELETE FROM kpi_rule_links WHERE id = %s", (link_id,))
    return True


def set_link_active(link_id: int, active: bool) -> bool:
    db._execute(
        "UPDATE kpi_rule_links SET is_active = %s, updated_at = NOW() WHERE id = %s",
        (active, link_id),
    )
    return True


def get_categories() -> dict[str, str]:
    return dict(_CATEGORIES)


def get_states() -> dict[str, str]:
    return {
        "ALL": "All India (Union law)",
        "UP": "Uttar Pradesh",
        "MH": "Maharashtra",
        "KA": "Karnataka",
        "TN": "Tamil Nadu",
        "DL": "Delhi",
        "RJ": "Rajasthan",
        "MP": "Madhya Pradesh",
        "WB": "West Bengal",
        "GJ": "Gujarat",
        "TS": "Telangana",
        "AP": "Andhra Pradesh",
        "BR": "Bihar",
        "HR": "Haryana",
        "PB": "Punjab",
        "KL": "Kerala",
    }


def _row_to_link(r: dict) -> KpiRuleLink:
    return KpiRuleLink(
        id=r.get("id"),
        category=r.get("category", "other"),
        state=r.get("state", "ALL"),
        label=r.get("label", ""),
        url=r.get("url", ""),
        description=r.get("description", "") or "",
        sort_order=r.get("sort_order", 100),
        is_active=r.get("is_active", True),
        effective_from=r.get("effective_from"),
        effective_to=r.get("effective_to"),
    )
