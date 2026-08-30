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

"accounts" (2026-08) is special-cased rather than going through the
generic single-query-plus-group_fn path every other table uses: its
Level-2 grouping is the account's own PARENT account (accounts.
parent_account_id — the real chart-of-accounts hierarchy; tab_name is
just "Excel ledger tab grouping", per its own column comment in
estatehub.sql, and isn't reliable for this), and only genuine leaf
accounts (never themselves someone else's parent) are selectable —
exactly what app/utils/account_picker.py's now-removed
list_account_hierarchy() did, minus the header sub-level (kept to a
2-tap flow like every other drill-in field instead of a 3-tap one, by
using the parent's name as the single group label). Resolving a leaf's
parent name can require a cross-side lookup (e.g. a Dr expense leaf's
parent is a Cr rollup account, "Income Expenditure A/c"), so it needs
the whole society's accounts fetched once up front — that's what
_fetch_account_leaves() does — rather than fitting the single filtered
SELECT + pure-per-row-group_fn shape the other tables use.
"""

from __future__ import annotations

import re
from database.db_manager import db

# Physical tables this module is allowed to query. Mirrors the allowlist
# guard in schema_introspect.load_fk_options() — never interpolate a
# caller-controlled table name that isn't in this set.
# "accounts" added (2026-08) for receipts.acc_id / expenses.acc_id /
# events.account_id — see DRILLIN_CONFIG below.
_ALLOWED_TABLES = {"apartments", "vendors", "security_staff", "assets", "accounts"}


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


# Per-target-table rendering + grouping rules. "accounts" only needs
# icon/color/label here — its actual group/item queries are special-cased
# in list_drillin_groups/list_drillin_items (see _fetch_account_leaves).
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
    "accounts": {
        "label_col": "name",
        "sub_col": None,
        "icon": "fas fa-book",
        "color": "#c9822e",
        "search_cols": ["name"],
        "group_fn": "special",   # handled directly in list_drillin_groups/items
        "group_label": "Category",
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
    # acc_id (2026-08): reuses the same "single" drill-in flow as asset_id
    # above, grouped by the account's parent (see module docstring),
    # scoped to the correct normal-balance side per form so a receipt can
    # only pick a Cr (income) account and an expense can only pick a Dr
    # (expense) one — identical scoping to the plain dropdown it replaces
    # (renderers.py's old account_dropdown_receipt/expense branch).
    ("receipts", "acc_id"): {
        "mode": "single",
        "table": "accounts",
        "label": "Income Account",
        "filter": "drcr_account='Cr'",
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
    ("expenses", "acc_id"): {
        "mode": "single",
        "table": "accounts",
        "label": "Expense Account",
        "filter": "drcr_account='Dr'",
    },
    # events.account_id (2026-08) — the income account event ticket sales
    # post to (fn_sell_event_ticket). Same accounts/Cr picker as
    # receipts.acc_id, just on a different table/field pair.
    ("events", "account_id"): {
        "mode": "single",
        "table": "accounts",
        "label": "Ticket Income Account",
        "filter": "drcr_account='Cr'",
    },
    # event_tickets.entity_id (2026-08, Tweak 1) — admin's "Sell Tickets"
    # buyer picker. All three roles are listed here; which ones actually
    # show as cards is narrowed per-event at open time in
    # drillin_callbacks.py's drillin_navigate() (special-cased there,
    # keyed off this same (table, field) pair), scoped to that specific
    # event's open_to ('all' / 'members_only' / 'residents_only') — not
    # something a static config entry can express on its own since the
    # same entry is shared by every event regardless of its open_to.
    ("event_tickets", "entity_id"): {
        "mode": "role",
        "role_field": "role",
        "roles": {
            "apartment": {"table": "apartments", "label": "Apartment"},
            "vendor":    {"table": "vendors",    "label": "Vendor"},
            "security":  {"table": "security_staff", "label": "Security"},
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
    sub_col = rules.get("sub_col")
    sub = row.get(sub_col, "") if sub_col else ""
    return str(label), str(sub or "")


def _parse_drcr_filter(extra_filter: str | None) -> str | None:
    """Pull 'Cr'/'Dr' out of a "drcr_account='Cr'"-shaped extra_filter
    string. Returns None (no side restriction) for anything else."""
    if not extra_filter:
        return None
    m = re.search(r"drcr_account\s*=\s*'(Cr|Dr)'", extra_filter)
    return m.group(1) if m else None


def _fetch_account_leaves(society_id: int, drcr: str | None) -> list[dict]:
    """All selectable ("leaf") accounts for the picker, each tagged with
    its group (its own direct parent account's name — falls back to the
    account's own tab_name, then "Other", if it has no parent or the
    parent lookup misses). A leaf is any account on the requested
    drcr_account side that is not itself the parent of another account
    (excludes rollup/header accounts like "Income Expenditure A/c").

    Fetches the whole society's chart of accounts unfiltered first
    (rather than pre-filtering by drcr_account in SQL) because a leaf's
    immediate parent can legitimately sit on the OTHER side — e.g. the
    Dr expense leaf "Depreciation" (231) is a child of the Cr rollup
    "Income Expenditure A/c" (23) — so the parent-name lookup needs
    both sides in memory regardless of which side the caller asked for.
    """
    try:
        all_rows = db._execute(
            "SELECT id, name, tab_name, parent_account_id, drcr_account "
            "FROM accounts WHERE society_id=%s",
            (society_id,), fetch_all=True,
        ) or []
    except Exception as e:
        print(f"⚠️  _fetch_account_leaves: {e}")
        return []

    by_id = {r["id"]: r for r in all_rows}
    parent_ids = {r["parent_account_id"] for r in all_rows if r.get("parent_account_id") is not None}

    leaves = []
    for r in all_rows:
        if drcr and r.get("drcr_account") != drcr:
            continue
        if r["id"] in parent_ids:
            continue  # this account is itself a parent — not a postable leaf
        parent = by_id.get(r.get("parent_account_id"))
        group_label = (parent["name"] if parent else None) or r.get("tab_name") or "Other"
        leaves.append({**r, "_group": group_label})
    return leaves


def list_drillin_groups(
    target_table: str,
    society_id: int,
    search: str | None = None,
    extra_filter: str | None = None,
) -> list[dict]:
    """Level-2 group cards for a target table (e.g. apartment blocks,
    vendor service types, account parent categories). Returns [] if the
    table has no grouping rule (caller should skip straight to the item
    list) or on any DB error."""
    if target_table not in _ALLOWED_TABLES:
        return []
    rules = _TABLE_RULES.get(target_table, {})

    if target_table == "accounts":
        leaves = _fetch_account_leaves(society_id, _parse_drcr_filter(extra_filter))
        if search:
            s = search.strip().lower()
            leaves = [r for r in leaves
                      if s in str(r.get("name", "")).lower() or s in str(r.get("_group", "")).lower()]
        counts: dict[str, int] = {}
        for r in leaves:
            counts[r["_group"]] = counts.get(r["_group"], 0) + 1
        return [{"key": k, "label": k, "count": c} for k, c in sorted(counts.items())]

    if not rules.get("group_fn"):
        return []
    # NOTE (2026-08 fix): this used to hardcode "AND disposed=TRUE"
    # unconditionally for every target table. apartments/vendors/
    # security_staff have no disposed column at all, so that raised an
    # exception on every call (caught below, silently returning []) —
    # the Apartment/Vendor/Security drill-in groups/items were empty in
    # production regardless of data. For assets, it also collided with
    # the DRILLIN_CONFIG "disposed=FALSE" filter (AND disposed=TRUE AND
    # disposed=FALSE = always zero rows). Only apply a filter when the
    # field's own config supplies one via extra_filter.
    query = f"SELECT * FROM {target_table} WHERE society_id=%s"
    params: list = [society_id]
    if extra_filter:
        query += f" AND {extra_filter}"
    try:
        rows = db._execute(query, tuple(params), fetch_all=True) or []
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

    if target_table == "accounts":
        leaves = _fetch_account_leaves(society_id, _parse_drcr_filter(extra_filter))
        if group_key:
            leaves = [r for r in leaves if r["_group"] == group_key]
        if search:
            s = search.strip().lower()
            leaves = [r for r in leaves
                      if s in str(r.get("name", "")).lower() or s in str(r.get("_group", "")).lower()]
        items = [{
            "id": r["id"],
            "label": r.get("name") or f"#{r['id']}",
            "sub": r["_group"],
            "icon": rules.get("icon", "fas fa-book"),
            "color": rules.get("color", "#c9822e"),
        } for r in leaves]
        items.sort(key=lambda x: x["label"].lower())
        return items

    # Same 2026-08 fix as list_drillin_groups() above — no more hardcoded
    # "AND disposed=TRUE"; only extra_filter (from the field's own
    # DRILLIN_CONFIG entry) scopes the query now.
    query = f"SELECT * FROM {target_table} WHERE society_id=%s"
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
