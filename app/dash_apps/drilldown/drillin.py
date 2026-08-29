# app/dash_apps/drilldown/drillin.py
"""
Generic "Drill-in" Entity Picker
=================================
Replaces raw numeric entity_id inputs / long flat FK dropdowns on
schema-driven forms (New Receipt, New Expense, New Concern, and others)
with a tap-through card picker, on the same UX pattern already proven by
the Concerns "Invite to Bid" modal (role card -> searchable list).

Two drill modes, selected per (table, field) in DRILLIN_CONFIG:

  "role"   — the field is a polymorphic entity_id paired with a sibling
             role/type column (e.g. receipts.entity_id + receipts.role).
             Level 1 = role cards (Apartment / Vendor / Security / ...).
             Level 2 = optional group cards (e.g. vendors by service_type).
             Level 3 = searchable item list -> tap to select.
             A role may map to None (e.g. "other") meaning no entity is
             linked; picking it clears entity_id and closes the modal.

  "single" — the field is an ordinary FK into one fixed table (e.g.
             concerns.apartment_id -> apartments). Same Level 2/3 flow,
             just without the role-card step.

Adding a new field to the picker is one DRILLIN_CONFIG entry — no new
callback wiring required, the modal + callbacks in drillin_callbacks.py
are fully generic over this config.
"""

from __future__ import annotations

import re
from database.db_manager import db

# Physical tables this module is allowed to query. Mirrors the allowlist
# guard in schema_introspect.load_fk_options() — never interpolate a
# caller-controlled table name that isn't in this set.
_ALLOWED_TABLES = {"apartments", "vendors", "security_staff", "assets"}


def _apartment_block(flat_number: str | None) -> str:
    """Best-effort block/wing grouping parsed from a flat number like
    'A-101', 'B204', 'Tower2-305' -> leading letters/word, else 'General'.
    Purely a UI grouping convenience — never written back to the DB."""
    if not flat_number:
        return "General"
    m = re.match(r"\s*([A-Za-z][A-Za-z0-9]*?)[\s\-_/]?\d", flat_number.strip())
    if m and m.group(1):
        return m.group(1).upper()
    return "General"


# Per-target-table rendering + grouping rules.
_TABLE_RULES = {
    "apartments": {
        "label_col": "flat_number",
        "sub_col": "owner_name",
        "icon": "fas fa-home",
        "color": "#1d74d8",
        "search_cols": ["flat_number", "owner_name", "mobile"],
        "group_fn": lambda row: _apartment_block(row.get("flat_number")),
        "group_label": "Block",
    },
    "vendors": {
        "label_col": "business_name",
        "label_fallback_col": "name",
        "sub_col": "mobile",
        "icon": "fas fa-truck",
        "color": "#17976e",
        "search_cols": ["business_name", "name", "mobile"],
        "group_fn": lambda row: (row.get("service_type") or "Unspecified"),
        "group_label": "Service Type",
    },
    "security_staff": {
        "label_col": "name",
        "sub_col": "mobile",
        "icon": "fas fa-shield-alt",
        "color": "#e59620",
        "search_cols": ["name", "mobile"],
        "group_fn": lambda row: (row.get("shift") or "Unspecified"),
        "group_label": "Shift",
    },
    "assets": {
        "label_col": "asset_name",
        "sub_col": "company_name",
        "icon": "fas fa-boxes",
        "color": "#8e6fce",
        "search_cols": ["asset_name", "company_name", "asset_sno"],
        "group_fn": None,   # flat list — no natural grouping
        "group_label": None,
    },
}


# ══════════════════════════════════════════════════════════════════════════
# DRILLIN_CONFIG — the single source of truth for which (table, field)
# pairs use the drill-in picker instead of a plain number/select input.
# ══════════════════════════════════════════════════════════════════════════
DRILLIN_CONFIG: dict[tuple[str, str], dict] = {
    ("receipts", "entity_id"): {
        "mode": "role",
        "role_field": "role",
        "roles": {
            "apartment": {"table": "apartments", "label": "Apartment"},
            "vendor":    {"table": "vendors",    "label": "Vendor"},
            "security":  {"table": "security_staff", "label": "Security"},
            "other":     None,
        },
    },
    ("receipts", "asset_id"): {
        "mode": "single",
        "table": "assets",
        "label": "Asset (Not Disposed)",
        "filter": "disposed=FALSE",
    },
    ("expenses", "entity_id"): {
        "mode": "role",
        "role_field": "role",
        "roles": {
            "vendor":    {"table": "vendors",    "label": "Vendor"},
            "security":  {"table": "security_staff", "label": "Security"},
            "assets":    {"table": "assets",     "label": "Asset"},
            "other":     None,
        },
    },
    ("receivables", "entity_id"): {
        "mode": "role",
        "role_field": "role",
        "roles": {
            "apartment": {"table": "apartments", "label": "Apartment"},
            "vendor":    {"table": "vendors",    "label": "Vendor"},
            "security":  {"table": "security_staff", "label": "Security"},
        },
    },
    ("concerns", "apartment_id"): {
        "mode": "single",
        "table": "apartments",
        "label": "Apartment",
    },
}


# Convenience lookup for renderers.py — (icon, color) per target table,
# used both for the closed picker button and for item cards inside the
# modal, so both stay visually consistent with zero duplication.
TABLE_ICON_COLOR: dict[str, tuple[str, str]] = {
    t: (r.get("icon", "fas fa-circle"), r.get("color", "#7d8ea3"))
    for t, r in _TABLE_RULES.items()
}


def get_drillin_config(table: str, field: str) -> dict | None:
    return DRILLIN_CONFIG.get((table, field))


def role_target_table(config: dict, role_key: str) -> dict | None:
    """Resolve a role card's target table info, or None for a
    no-entity role (e.g. 'other')."""
    return (config.get("roles") or {}).get(role_key)


def _label_and_sub(rules: dict, row: dict) -> tuple[str, str]:
    label = row.get(rules["label_col"]) or row.get(rules.get("label_fallback_col") or "", "")
    label = label or f"#{row.get('id')}"
    sub = row.get(rules.get("sub_col") or "", "") or ""
    return str(label), str(sub)


def list_drillin_groups(target_table: str, society_id: int, search: str | None = None) -> list[dict]:
    """Level-2 group cards for a target table (e.g. apartment blocks,
    vendor service types). Returns [] if the table has no grouping rule
    (caller should skip straight to the item list) or on any DB error."""
    if target_table not in _ALLOWED_TABLES:
        return []
    rules = _TABLE_RULES.get(target_table, {})
    if not rules.get("group_fn"):
        return []
    try:
        rows = db._execute(
            f"SELECT * FROM {target_table} WHERE society_id=%s AND active=TRUE",
            (society_id,), fetch_all=True,
        ) or []
    except Exception as e:
        print(f"⚠️  list_drillin_groups({target_table}): {e}")
        return []

    if search:
        s = search.strip().lower()
        cols = rules.get("search_cols", [])
        rows = [r for r in rows if any(s in str(r.get(c, "") or "").lower() for c in cols)]

    counts: dict[str, int] = {}
    for r in rows:
        key = rules["group_fn"](r) or "Unspecified"
        counts[key] = counts.get(key, 0) + 1

    return [
        {"key": k, "label": k, "count": c}
        for k, c in sorted(counts.items())
    ]


def list_drillin_items(
    target_table: str,
    society_id: int,
    group_key: str | None = None,
    search: str | None = None,
    extra_filter: str | None = None,
) -> list[dict]:
    """Level-3 tappable item cards for a target table, optionally scoped
    to a Level-2 group. Returns [{id, label, sub, icon, color}]."""
    if target_table not in _ALLOWED_TABLES:
        return []
    rules = _TABLE_RULES.get(target_table, {})
    query = f"SELECT * FROM {target_table} WHERE society_id=%s AND active=TRUE"
    params: list = [society_id]
    if extra_filter:
        query += f" AND {extra_filter}"
    try:
        rows = db._execute(query, tuple(params), fetch_all=True) or []
    except Exception as e:
        print(f"⚠️  list_drillin_items({target_table}): {e}")
        return []

    if group_key and rules.get("group_fn"):
        rows = [r for r in rows if (rules["group_fn"](r) or "Unspecified") == group_key]

    if search:
        s = search.strip().lower()
        cols = rules.get("search_cols", [])
        rows = [r for r in rows if any(s in str(r.get(c, "") or "").lower() for c in cols)]

    items = []
    for r in rows:
        label, sub = _label_and_sub(rules, r)
        items.append({
            "id": r.get("id"),
            "label": label,
            "sub": sub,
            "icon": rules.get("icon", "fas fa-circle"),
            "color": rules.get("color", "#7d8ea3"),
        })
    items.sort(key=lambda x: x["label"].lower())
    return items


def drillin_label_for(target_table: str, entity_id, society_id: int) -> str | None:
    """Resolve a single entity's display label — used to show the
    currently-selected value on an Edit form without re-opening the
    modal, and to re-populate the picker button's text on load."""
    if not entity_id or target_table not in _ALLOWED_TABLES:
        return None
    rules = _TABLE_RULES.get(target_table, {})
    try:
        row = db._execute(
            f"SELECT * FROM {target_table} WHERE id=%s AND society_id=%s",
            (entity_id, society_id), fetch_one=True,
        )
    except Exception as e:
        print(f"⚠️  drillin_label_for({target_table}): {e}")
        return None
    if not row:
        return None
    label, _sub = _label_and_sub(rules, row)
    return label
