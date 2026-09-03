# app/dash_apps/drilldown/renderers.py
"""
COMPLETE RENDERERS - All Card Types for All 5 Portals
======================================================
Portal-aware CRUD buttons:
  admin     → New, View, Edit, Delete on every list
  apartment → View only (own records filtered by apartment_id)
  vendor    → View only (own records filtered by vendor_id / user_id)
  security  → View on most lists + Create Receipt on cashbook/receipts
  master    → View, Edit, Delete on societies list
"""

from __future__ import annotations
from datetime import datetime, date
from pathlib import Path
from decimal import Decimal

from dash import html, dcc, no_update
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS

# ════════════════════════════════════════════════════════════════════════════
# COLORS & STYLES
# ════════════════════════════════════════════════════════════════════════════

COLORS = {
    "primary":  "#1d74d8",
    "success":  "#17976e",
    "warning":  "#e59620",
    "danger":   "#de5c52",
    "info":     "#0ea5a8",
    "muted":    "#7d8ea3",
}

# ════════════════════════════════════════════════════════════════════════════
# ENTITY BANNERS
# Universal descriptions shown on all forms and profiles for contextual clarity.
# ════════════════════════════════════════════════════════════════════════════

_ENTITY_BANNERS = {
    "society": "Manage top-level society details, plan validity, and default settings.",
    "societies": "Manage top-level society details, plan validity, and default settings.",
    "apartment": "Manage apartment details including owner information, flat size, and occupancy status.",
    "apartments": "Manage apartment details including owner information, flat size, and occupancy status.",
    "vendor": "Manage vendor profiles, daily pass validity, and account balances.",
    "vendors": "Manage vendor profiles, daily pass validity, and account balances.",
    "security": "Manage security staff profiles, shift assignments, and gate access.",
    "security_staff": "Manage security staff profiles, shift assignments, and gate access.",
    "event": "Manage society events, event dates, and ticketing capacities.",
    "events": "Manage society events, event dates, and ticketing capacities.",
    "concern": "Track and manage resident issues, maintenance requests, and their resolution status.",
    "concerns": "Track and manage resident issues, maintenance requests, and their resolution status.",
    "account": "Manage financial chart of accounts, opening balances, and categorization.",
    "accounts": "Manage financial chart of accounts, opening balances, and categorization.",
    "asset": "Track physical assets of the society, their purchase value, and lifecycle status.",
    "assets": "Track physical assets of the society, their purchase value, and lifecycle status.",
    "receipt": "Record and track incoming payments against receivables or direct income.",
    "receipts": "Record and track incoming payments against receivables or direct income.",
    "expense": "Record and track outgoing payments against vendor payables or direct expenses.",
    "expenses": "Record and track outgoing payments against vendor payables or direct expenses.",
    "poll": "Create and manage society-wide polls and track voting results.",
    "polls": "Create and manage society-wide polls and track voting results.",
    "channel": "Manage communication channels, subscriptions, and automated alert rules.",
    "channels": "Manage communication channels, subscriptions, and automated alert rules.",
    "compliance_setting": "Manage tax, regulatory, and fund compliance parameters for the society.",
    "compliance_settings": "Manage tax, regulatory, and fund compliance parameters for the society.",
    "apt_charge": "This profile defines the recurring maintenance and fine structures applicable to apartments. Fields display the billing frequency, rate per square foot, flat amounts, and late fee percentages.",
    "apt_charges": "This profile defines the recurring maintenance and fine structures applicable to apartments. Fields display the billing frequency, rate per square foot, flat amounts, and late fee percentages.",
    "ven_charge": "This profile defines the recurring charges and fee structures applicable to vendors. Fields display the billing frequency, standard rates, flat amounts, and any relevant deductions.",
    "ven_charges": "This profile defines the recurring charges and fee structures applicable to vendors. Fields display the billing frequency, standard rates, flat amounts, and any relevant deductions.",
    "patrol_location": "Manage NFC/QR checkpoints for security guard patrol tracking.",
    "patrol_locations": "Manage NFC/QR checkpoints for security guard patrol tracking.",
    "event_ticket": "View details of this purchased event ticket.",
    "event_ticket_items": "View details of this purchased event ticket.",
}

# ════════════════════════════════════════════════════════════════════════════
# PORTAL PERMISSION MATRIX
# key = (role, entity)  →  set of allowed actions
# ════════════════════════════════════════════════════════════════════════════

_PORTAL_PERMS: dict[tuple[str, str], set[str]] = {
    # ── ADMIN: full CRUD on everything ───────────────────────────────────────
    ("admin", "*"):            {"view", "edit", "delete", "new"},
    # Societies are platform-level records: an admin may VIEW their own society
    # (scoped server-side to society_id) and EDIT its properties, but must NOT
    # create a new society or delete/expire the row they belong to. Master
    # retains full control via ("master","societies") below.
    ("admin", "societies"):    {"view", "edit"},
    ("admin", "receivables"):  {"view"},
    ("admin", "payables"):     {"view"},
    ("admin","gate_logs"):     {"view"},
    ("admin", "security_roster"): {"view"},
    ("admin", "ledger"):       {"view"},
    # FY Closing Report (fn_fy_closing_report) — read-only for every role
    # that can reach it; there's nothing to create/edit/delete here, it's
    # a derived report. Custom-rendered (not the generic schema-driven
    # list/profile pipeline), so this entry is mostly documentation / a
    # safety net if it's ever routed through that pipeline later.
    ("admin", "financials"):   {"view"},
    # Cashbook rows are derived/paired display of `transactions`, which
    # loaders.delete_entity() already refuses to touch ("Transactions are
    # immutable — cashbook is read-only"). Without this explicit entry,
    # admin fell through to ("admin","*") = full CRUD, which showed
    # Edit/Delete buttons that would only ever fail. "new" is kept — it's
    # the "+ New" shortcut into the receipt form, a deliberate convenience.
    ("admin", "cashbook"):     {"view", "new"},
    ("admin", "accounts"):     {"view", "edit", "delete", "new"},
    # Channels: admin creates; subscribe/trigger/approve-deny go through
    # profile actions with server-side guards (alert_service.py).
    ("admin", "channels"):     {"view", "new"},
    # ── MASTER: societies only (view + edit + new), no delete ─────────────
    ("master", "societies"):   {"view", "edit", "new"},
    ("master", "receivables"): {"view"},
    ("master", "payables"):    {"view"},
    ("master", "security_roster"): {"view"},
    ("master", "ledger"):      set(),
    ("master", "*"):           {"view"},

    # ── APARTMENT: view own data only, can raise concern / pay ────────────
    # "edit" here is self-service profile editing (e.g. mobile number via
    # Settings) — FIELD_VISIBILITY still restricts *which* columns a form
    # exposes to this role, this only grants the action itself.
    ("apartment", "apartments"):  {"view", "edit"},
    ("apartment", "concerns"):    {"view", "new", "edit"},
    ("apartment", "events"):      {"view"},
    ("apartment", "gate_logs"):   {"view"},
    ("apartment", "receipts"):{"view", "new"},
    ("apartment", "cashbook"):    {"view"},
    ("apartment", "receivables"): {"view"},
    ("apartment", "payables"):    {"view"},
    ("apartment", "ledger"):      set(),
    ("apartment", "financials"):  {"view"},
    # Apartments view channels and subscribe from the profile; create/approve/deny
    # are profile actions with server-side guards.
    ("apartment", "channels"):    {"view", "new"},
    ("apartment", "*"):           set(),

    # ── VENDOR: view own data + can see events/concerns ───────────────────
    # "edit" here is self-service profile editing, same rationale as above.
    # Vendors can view concerns, invite/bid on them (server-side actions),
    # and resolve their own assignments — the _PORTAL_PERMS "view" entry
    # controls which UI actions appear; the actual server-side action
    # guards are in the callback handlers.
    ("vendor", "vendors"):        {"view", "edit"},
    ("vendor", "events"):         {"view"},
    ("vendor", "concerns"):       {"view", "new"},
    ("vendor", "gate_logs"):      {"view"},
    ("vendor", "receipts"):   {"view", "new"},
    ("vendor", "cashbook"):       {"view"},
    ("vendor", "receivables"):    {"view"},
    ("vendor", "payables"):       {"view"},
    ("vendor", "ledger"):         set(),
    ("vendor", "financials"):     {"view"},
    ("vendor", "*"):              set(),

    # ── SECURITY: view most lists + can create receipts ───────────────────
    ("security", "apartments"):   {"view"},
    ("security", "vendors"):      {"view"},
    # "edit" here is self-service profile editing, same rationale as above.
    ("security", "security"):     {"view", "edit"},
    ("security", "events"):       {"view"},
    ("security", "concerns"):     {"view"},
    ("security", "gate_logs"):    {"view"},
    # Visitable via gate QR scan / subscriber alert cards (read-only context).
    ("security", "visitors"):           {"view"},
    ("security", "patrol_locations"):   {"view"},
    ("security", "event_ticket_items"): {"view"},
    ("security", "receipts"): {"view", "new"},
    ("security", "channels"):     {"view"},
    # Owner portal: bought event tickets are visible (list + profile) so the
    # owner can see/verify what they bought; admin covered by ("admin","*").
    ("apartment", "event_ticket_items"): {"view"},
    ("security", "cashbook"):     {"view"},
    ("security", "ledger"):       set(),
    # ("security", "financials") removed (2026-08) along with the tab —
    # see card_catalogue.py / portal_pages.py / app_shell.py.
    ("security", "*"):            set(),
    ("apartment", "polls"):       {"view"},
    ("vendor", "polls"):          {"view"},
    ("security", "polls"):        {"view"},
}


def _perms_for(role: str, entity: str) -> set[str]:
    """Return allowed action set for role × entity."""
    key_specific = (role, entity)
    key_star     = (role, "*")
    if key_specific in _PORTAL_PERMS:
        return _PORTAL_PERMS[key_specific]
    if key_star in _PORTAL_PERMS:
        return _PORTAL_PERMS[key_star]
    return set()

# ── Human-readable FK resolution ────────────────────────────────────────
# Prefer a joined alias from the row (e.g. fn_apt_charges returns
# 'flat_number' next to apt_id) over the raw foreign key value. Falls back
# to the raw id if the loader hasn't been enriched with that alias yet.
_FK_HUMAN_ALIASES = {
    "apt_id": "flat_number", "ven_id": "vendor_name", "sec_id": "security_name",
    "acc_id": "account_name", "vendor_id": "vendor_name",
    "security_id": "security_name", "apartment_id": "flat_number",
    "entity_id": "entity_name", "account_id": "account_name",
    "apt_maintenance_acc_id": "maintenance_account_name",
    "apt_interest_acc_id": "interest_account_name",
    "ven_pass_acc_id": "pass_account_name",
    # fn_accounts_list already self-joins accounts to return this — it was
    # just never registered here, so the accounts list was showing the raw
    # parent_account_id FK (or nothing) instead of the resolved name.
    "parent_account_id": "parent_account_name",
}

_FIELD_FORMATTERS = {
    "shift_count": lambda v: f"{int(v)} shift{'s' if int(v) != 1 else ''}",
    "gate_pass": lambda v: html.Span(
        "✓ Pass" if v else "✗ Fail",
        style={"color": "#17976e" if v else "#de5c52", "fontWeight": "600"},
    ),
    "duty_status": lambda v: html.Span(
        "✓ On Duty" if v else "✗ Off Duty",
        style={"color": "#17976e" if v else "#de5c52", "fontWeight": "600"},
    ),
    "noc_eligible": lambda v: html.Span(
        "✓ Eligible" if v else "✗ Not Eligible",
        style={"color": "#17976e" if v else "#de5c52", "fontWeight": "600"},
    ),
    "currency": lambda v: html.Span(
        f"₹{float(v):,.2f}" if v is not None else "—",
        style={"fontWeight": "600", "textAlign": "right", "display": "block"}
    ),
}

import re as _re
_SNAKE_CASE_RE = _re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")


def _humanize_string(val: str) -> str:
    """
    Turn raw snake_case enum/status text ('in_progress', 'bank')
    into readable Title Case ('In Progress', 'Bank Transfer').
    Only touches strings that look like a code/enum value (all-lowercase,
    underscore-separated) so real data — emails, names, flat numbers,
    free-text particulars — passes through untouched.
    """
    if isinstance(val, str) and _SNAKE_CASE_RE.match(val):
        return val.replace("_", " ").title()
    return val


# Unified date/datetime display format per app-wide convention: dd/mm/yyyy hh:mm:ss
# Plain `date` values (no time component, e.g. due_date, start_date) are shown
# as dd/mm/yyyy only — appending a synthetic 00:00:00 would be misleading.
def _format_datetime(val) -> str:
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M:%S")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, str):
        # Be resilient to backend date strings that arrive as text.
        s = val.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y",
                    "%d-%m-%Y", "%Y/%m/%d"):
            try:
                d = datetime.strptime(s, fmt)
                return d.strftime("%d/%m/%Y %H:%M:%S" if " " in fmt else "%d/%m/%Y")
            except ValueError:
                continue
    return str(val) if val is not None else "—"


def _format_date_entry(val) -> str:
    """Render a date/datetime/string as dd/mm/yyyy for a date-entry input."""
    if val in (None, ""):
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, str):
        s = val.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y",
                    "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
    return str(val)


def _parse_date_entry(val):
    """Parse a user-entered date string into the canonical yyyy-mm-dd string.

    Accepts dd/mm/yyyy (the app-wide entry convention) plus a few fallbacks.
    Returns None when the value is not a recognisable date.
    """
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _display_value(field_key: str, row_dict: dict):
    alt_key = _FK_HUMAN_ALIASES.get(field_key)
    if alt_key:
        alt_val = row_dict.get(alt_key)
        if alt_val not in (None, ""):
            return alt_val
    return row_dict.get(field_key)


# State-code patterns for _resolve_society_state — ordered so multi-word
# states (e.g. "uttar pradesh") match before their 2-letter abbreviation
# could false-positive on some other substring.
_STATE_ADDR_PATTERNS: dict[str, list[str]] = {
    "UP": ["uttar pradesh", ", up ", " up -", ",up-", " up "],
    "MH": ["maharashtra", ", mh ", " mh -", ",mh-", " mh "],
    "KA": ["karnataka", ", ka ", " ka -", ",ka-", " ka "],
    "TN": ["tamil nadu", ", tn ", " tn -", ",tn-", " tn "],
    "DL": ["delhi", ", dl ", " dl -", ",dl-", "new delhi"],
    "RJ": ["rajasthan", ", rj ", " rj -", ",rj-", " rj "],
    "MP": ["madhya pradesh", ", mp ", " mp -", ",mp-", " mp "],
    "WB": ["west bengal", ", wb ", " wb -", ",wb-", " wb "],
    "GJ": ["gujarat", ", gj ", " gj -", ",gj-", " gj "],
    "TS": ["telangana", ", ts ", " ts -", ",ts-", " ts "],
    "AP": ["andhra pradesh", ", ap ", " ap -", ",ap-", " ap "],
    "BR": ["bihar", ", br ", " br -", ",br-", " br "],
    "HR": ["haryana", ", hr ", " hr -", ",hr-", " hr "],
    "PB": ["punjab", ", pb ", " pb -", ",pb-", " pb "],
    "KL": ["kerala", ", kl ", " kl -", ",kl-", " kl "],
}


def _resolve_society_state(record_dict: dict, society_id: int | None) -> str:
    """Best-effort extraction of a society's 2-letter state code from its
    stored address or a state column. Falls back to 'ALL' when unknown —
    the banner then shows only Union-law links."""
    if not society_id:
        return "ALL"
    state = (record_dict or {}).get("state")
    if state and isinstance(state, str) and len(state) == 2:
        return state.upper()
    address = (record_dict or {}).get("address", "") or ""
    addr_lower = address.lower()
    for code, patterns in _STATE_ADDR_PATTERNS.items():
        for pat in patterns:
            if pat in addr_lower:
                return code
    return "ALL"



# ── Fields hidden because the current view is already scoped to them ──────
def _context_hidden_fields(filters: dict | None) -> set[str]:
    filters = filters or {}
    hidden = {"society_id"}
    if filters.get("apartment_id"):
        hidden |= {"apartment_id", "apt_id", "entity_id", "role"}
    if filters.get("vendor_id"):
        hidden |= {"vendor_id", "ven_id", "entity_id", "role"}
    if filters.get("security_id"):
        hidden |= {"security_id", "sec_id", "entity_id", "role"}
    return hidden


def _field_visible(entity_plural: str, field: str, role: str) -> bool:
    from app.dash_apps.drilldown.profile_actions import FIELD_VISIBILITY
    restriction = FIELD_VISIBILITY.get(entity_plural, {}).get(field)
    return True if restriction is None else role in restriction



# ════════════════════════════════════════════════════════════════════════════
# IMAGE URL RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

def get_image_url(image_path: str | None, society_id: int | None = None,
                  entity: str = None, pk: int | None = None) -> str | None:
    if not image_path or str(image_path).strip() == "":
        return None
    path = str(image_path).strip()
    if path.startswith(('http://', 'https://', 'data:image', '/assets/')):
        return path
    if '/' not in path and '\\' not in path:
        if entity == "society" and pk is not None:
            return f"/assets/{pk}/{path}"
        elif society_id is not None and pk is not None:
            if entity in ("apartment", "vendor", "security", "concern", "event"):
                return f"/assets/{society_id}/{entity}/{pk}/{path}"
            else:
                return f"/assets/{society_id}/{entity}_{pk}/{path}"
        elif society_id is not None or entity is not None:
            return f"/assets/default/{entity or 'file'}/{path}"
        else:
            return f"/assets/default/{path}"
    return f"/assets/{path}"

# ════════════════════════════════════════════════════════════════════════════
# KPI CARD RENDERER
# ════════════════════════════════════════════════════════════════════════════

def render_kpi_card(card_id: str, title: str, icon: str, value: str,
                    color: str = "#1d74d8", subtitle: str = "",
                    clickable: bool = True) -> html.Div:
    return html.Div(
        id={"type": "kpi-card-div", "card_id": card_id},
        n_click=0,
        children=[
            dbc.Card(
                [
                    html.Div(
                        [
                            html.Div(
                                html.I(className=f"fas {icon}",
                                       style={"color": color, "fontSize": "22px"}),
                                style={"marginBottom": "8px"},
                            ),
                            html.Div(value, style={
                                "fontSize": "24px", "fontWeight": "800",
                                "color": "#15304f", "lineHeight": "1",
                            }),
                            html.Div(title, style={
                                "fontSize": "11px", "fontWeight": "600",
                                "color": "#7d8ea3", "marginTop": "4px",
                                "textTransform": "uppercase",
                            }),
                            html.Div(subtitle, style={
                                "fontSize": "10px", "color": "#aaa", "marginTop": "2px",
                            }) if subtitle else None,
                        ],
                        style={"padding": "14px", "textAlign": "center"},
                    ),
                    html.Div(style={
                        "position": "absolute", "left": 0, "top": 0,
                        "bottom": 0, "width": "4px", "background": color,
                        "borderRadius": "4px 0 0 4px",
                    }),
                ],
                style={
                    "position": "relative",
                    "cursor": "pointer" if clickable else "default",
                    "border": f"1px solid {color}22",
                    "boxShadow": f"0 4px 12px {color}18",
                    "borderRadius": "12px", "overflow": "hidden",
                    "background": "linear-gradient(135deg, rgba(255,255,255,0.95), rgba(248,251,255,0.9))",
                    "backdropFilter": "blur(10px)",
                },
            ),
        ],
        style={"padding": "6px"},
    )

# ════════════════════════════════════════════════════════════════════════════
# LIST CARD RENDERER  — portal-aware action buttons
# ════════════════════════════════════════════════════════════════════════════

def _build_accounts_tree(rows: list[dict]) -> list[dict]:
    """Turns fn_accounts_hierarchy's flat depth-first row list into a
    nested {row, children} tree. Relies on the rows already being in
    depth-first order (guaranteed by that function's own sort_path
    ORDER BY) — for any row at depth D, its parent is always the most
    recently seen row at depth D-1, since depth-first traversal always
    finishes emitting a node's own row immediately before descending into
    its first child."""
    roots: list[dict] = []
    children_at_depth: dict[int, list[dict]] = {-1: roots}
    for r in rows:
        row_dict = r.to_dict(include_calculated=True) if hasattr(r, "to_dict") else dict(r)
        depth = row_dict.get("depth") or 0
        node = {"row": row_dict, "children": []}
        parent_children = children_at_depth.get(depth - 1, roots)
        parent_children.append(node)
        children_at_depth[depth] = node["children"]
    return roots


def _fmt_account_amount(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    sign = "-" if v < 0 else ""
    return f"{sign}₹{abs(v):,.2f}"


def _render_account_tree_node(node: dict, entity: str) -> html.Details:
    """One <details>/<summary> tree node, recursing into node['children'].
    Reuses the same {"type": "list-row", "entity": entity, "pk": ...}
    click target every other list card's table row already uses for
    navigation (see the html.Tr construction earlier in this file) — the
    existing drilldown_callbacks.py handler for that pattern needs no
    changes to work here too, since it only cares about the id shape, not
    which component fired it."""
    r = node["row"]
    depth = r.get("depth") or 0
    children = node["children"]
    pk_val = str(r.get("id") or "0")

    label_bits = [
        html.Span(r.get("tab_name") or r.get("name") or "", style={"fontWeight": "700"}),
        html.Span(f"  {r.get('name') or ''}", style={"color": "#8a97a8", "fontSize": "11px"}),
    ]
    if r.get("has_bf"):
        label_bits.append(dbc.Badge("BF", color="info", className="ms-2",
                                     style={"fontSize": "9px"}))
    if r.get("is_depreciable"):
        label_bits.append(dbc.Badge("Dep", color="secondary", className="ms-1",
                                     style={"fontSize": "9px"}))

    summary = html.Summary(
        html.Div([
            html.Div(label_bits, style={"display": "flex", "alignItems": "center"}),
            html.Small(_fmt_account_amount(r.get("current_balance")),
                       style={"color": "#15304f", "fontWeight": "600"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "gap": "10px"}),
        id={"type": "list-row", "entity": entity, "pk": pk_val},
        n_clicks=0,
        style={"cursor": "pointer", "padding": "5px 8px", "borderRadius": "6px",
               "listStyle": "none"},
    )

    body = [summary]
    if children:
        body.append(html.Div(
            [_render_account_tree_node(c, entity) for c in children],
            style={"paddingLeft": "18px",
                   "borderLeft": "1px dashed rgba(120,148,181,0.3)",
                   "marginLeft": "6px"},
        ))

    return html.Details(
        body,
        open=(depth < 2),  # root + first level expanded by default; deeper nodes collapsed
        style={"marginBottom": "1px"},
    )


def render_accounts_tree_card(title: str, icon: str, rows: list[dict], entity: str,
                               total_rows: int, header_right: list) -> html.Div:
    """TreeView for the Accounts list card — parent/child nodes nested by
    fn_accounts_hierarchy's depth column, native <details>/<summary>
    (zero extra JS/CSS dependency — every browser supports these
    natively) rather than a third-party tree-view package. No pagination:
    the whole chart of accounts (a few dozen rows, typically) renders at
    once, since a tree doesn't nest sensibly across a page boundary."""
    tree = _build_accounts_tree(rows)
    if not tree:
        body_content = html.Div([
            html.I(className="fas fa-inbox me-2", style={"color": "#ccc", "fontSize": "20px"}),
            html.Div("No accounts found", style={"color": "#aaa", "fontSize": "13px", "marginTop": "4px"}),
        ], className="text-center", style={"padding": "28px 0"})
    else:
        body_content = html.Div([_render_account_tree_node(n, entity) for n in tree])

    return html.Div([
        html.Div(
            html.Div([
                html.Div([
                    html.I(className=f"fas {icon} me-2", style={"color": COLORS["primary"]}),
                    html.Strong(title, style={"fontSize": "13px"}),
                    dbc.Badge(str(total_rows), color="primary", className="ms-2",
                              style={"fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div(header_right,
                         style={"display": "flex", "alignItems": "center",
                                "gap": "6px", "flexWrap": "wrap"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "flexWrap": "wrap", "gap": "8px"}),
            style={"padding": "10px 16px",
                   "background": "linear-gradient(180deg,rgba(255,255,255,0.85),rgba(248,251,255,0.95))"},
        ),
        html.Div(body_content, style={"padding": "12px 16px", "maxHeight": "560px",
                                       "overflowY": "auto"}),
    ], style={
        "borderRadius": "16px",
        "border": "1px solid rgba(255,255,255,0.65)",
        "boxShadow": "0 10px 30px rgba(15,23,42,0.08)",
        "overflow": "hidden",
    })


def render_list_card(card_id: str, title: str, icon: str,
                      columns: list[dict], rows: list[dict],
                      entity: str, page: int = 1, total_rows: int = 0,
                      page_size: int = 15, auth_data: dict | None = None,
                      filters: dict | None = None,
                      sort: dict | None = None,
                      col_filters: dict | None = None,
                      filter_options: dict | None = None,
                      fy_options: list[int] | None = None,
                      selected_fy: int | None = None,
                      month_options: list[dict] | None = None,
                      selected_month: int | None = None,
                      account_options: list[dict] | None = None,
                      selected_account_id: int | None = None) -> html.Div:

    auth_data  = auth_data or {}
    role  = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")

    sort = sort or {}
    sort_col   = sort.get("column")
    sort_dir   = (sort.get("direction") or "asc").lower()
    col_filters = {k: v for k, v in (col_filters or {}).items() if v not in (None, "")}

    # ── Resolve permissions for this role × entity ─────────────────────────
    allowed = _perms_for(role, entity)
    # cashbook/ledger rows are paired display constructs from
    # fn_cashbook_paired_v3 / fn_account_ledger_fy — they carry no single
    # `id` column, so a per-row View/Edit/Delete button would resolve to
    # pk="0" for every row and silently open the same (wrong) profile
    # each time. These two are read-only reports; row-level actions never
    # made sense for them. `allowed` (unmodified) still drives header-level
    # actions like the "New" shortcut on cashbook.
    row_actions_allowed = allowed if entity not in ("cashbook", "ledger") else set()
    hidden = _context_hidden_fields(filters)
    visible_columns = [
        c for c in columns
        if (c.get("field") or c.get("name") or "") not in hidden
        and _field_visible(entity, c.get("field") or c.get("name") or "", role)
    ]
    total_pages = max(1, -(-total_rows // page_size))

    # ── Header row (sortable) ──────────────────────────────────────────────
    header_cells = []
    filter_cells = []
    for c in visible_columns:
        field_key = c.get("field") or c.get("name") or ""
        col_label = c.get("label") or c.get("name") or field_key.title()

        # Sort indicator: active column shows ▲/▼, others show a faint ⇅ hint
        is_sorted = (sort_col == field_key)
        if is_sorted:
            arrow = "▲" if sort_dir == "asc" else "▼"
            arrow_style = {"color": COLORS["primary"], "fontSize": "10px",
                           "marginLeft": "4px", "fontWeight": "700"}
        else:
            arrow = "⇅"
            arrow_style = {"color": "#c2cdda", "fontSize": "10px",
                           "marginLeft": "4px", "fontWeight": "400"}
        indicator = html.Span(arrow, style=arrow_style)

        header_cells.append(html.Th(
            html.Div([
                html.Span(col_label),
                indicator,
            ], style={"display": "flex", "alignItems": "center",
                      "gap": "2px", "cursor": "pointer",
                      "whiteSpace": "nowrap"}),
            id={"type": "list-sort", "entity": entity, "column": field_key},
            n_clicks=0,
            style={
                "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
                "padding": "10px 8px", "userSelect": "none",
                "background": "rgba(248,251,255,0.97)",
            },
        ))

        # Per-column filter dropdown: "All" + distinct values for this column
        opts = [{"label": "All", "value": "__ALL__"}]
        for v in (filter_options or {}).get(field_key, []):
            opts.append({"label": str(v), "value": str(v)})
        cur_val = col_filters.get(field_key)
        filter_cells.append(html.Td(
            dcc.Dropdown(
                id={"type": "list-filter", "entity": entity, "column": field_key},
                options=opts,
                value=cur_val if cur_val else "__ALL__",
                clearable=False,
                searchable=False,
                style={"fontSize": "11px", "width": "100%"},
            ),
            style={"padding": "4px 6px", "background": "#f4f7fb"},
        ))

    if row_actions_allowed:
        header_cells.append(html.Th("Actions", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
            "padding": "10px 8px",
        }))
        filter_cells.append(html.Td(
            "", style={"padding": "4px 6px", "background": "#f4f7fb"}))

    body_rows = []
    for row in rows:
        row_dict = (row.to_dict(include_calculated=True)
                    if hasattr(row, "to_dict") else dict(row))
        pk_val = str(row_dict.get("id") or row_dict.get("ID") or "0")

        cells = []
        for c in visible_columns:
            field_key = c.get("field") or c.get("name") or ""
            val = _display_value(field_key, row_dict)
            fmt = c.get("format")
            is_formatted = False
            if fmt in _FIELD_FORMATTERS and val is not None:
                val = _FIELD_FORMATTERS[fmt](val)
                is_formatted = True  # val is now a Dash component — don't re-coerce below

            # Highlight the winning choice once a poll's results are
            # declared — winning_choice comes from fn_polls_list and is
            # NULL on a tie/no votes, so nothing gets highlighted then.
            is_winning_choice = False
            if entity == "polls" and field_key.startswith("choice_") and val not in (None, ""):
                try:
                    choice_num = int(field_key.rsplit("_", 1)[1])
                except (ValueError, IndexError):
                    choice_num = None
                is_winning_choice = (
                    row_dict.get("status") == "results_declared"
                    and choice_num is not None
                    and row_dict.get("winning_choice") == choice_num
                )

            if is_formatted:
                pass
            elif is_winning_choice:
                val = html.Span(
                    [html.I(className="fas fa-trophy me-1", style={"color": "#e6a817"}),
                     _humanize_string(str(val))],
                    style={"color": "#17976e", "fontWeight": "800"},
                )
                is_formatted = True
            elif isinstance(val, bool):
                val = html.Span(
                    ["✓" if val else "✗"],
                    style={"color": "#17976e" if val else "#de5c52", "fontWeight": "700"},
                )
            elif isinstance(val, (date, datetime)):
                val = _format_datetime(val)
            elif val is None:
                val = "—"
            elif isinstance(val, str):
                val = _humanize_string(val)
            else:
                val = str(val)
            cells.append(html.Td(val, style={
                "fontSize": "12px", "verticalAlign": "middle", "padding": "8px 8px",
            }))

        # ── Action buttons scoped by portal permissions ──────────────────
        if row_actions_allowed:
            action_btns = []

            # "view" button is always shown when an actions column is present —
            # it is now the sole way to open a profile since html.Tr no longer
            # carries n_clicks (removing the bubbling conflict with delete/edit).
            action_btns.append(dbc.Button(
                html.I(className="fas fa-eye"),
                id={"type": "list-view", "entity": entity, "pk": pk_val},
                size="sm", color="info", outline=True,
                title="View details",
                style={"fontSize": "11px", "padding": "3px 7px",
                       "borderRadius": "7px"},
            ))

            if "edit" in row_actions_allowed:
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-edit"),
                    id={"type": "list-edit", "entity": entity, "pk": pk_val},
                    size="sm", color="primary", outline=True,
                    title="Edit record",
                    style={"fontSize": "11px", "padding": "3px 7px",
                           "borderRadius": "7px"},
                ))

            if "delete" in row_actions_allowed:
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-trash-alt"),
                    id={"type": "list-delete", "entity": entity, "pk": pk_val},
                    size="sm", color="danger", outline=True,
                    title="Delete record",
                    style={"fontSize": "11px", "padding": "3px 7px",
                           "borderRadius": "7px"},
                ))

            if entity == "receipts" and role == "admin" and row_dict.get("status") == "pending":
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-check"),
                    id={"type": "list-confirm", "entity": entity, "pk": pk_val},
                    size="sm", color="success", outline=True,
                    title="Confirm receipt",
                    style={"fontSize": "11px", "padding": "3px 7px",
                           "borderRadius": "7px"},
                ))

            if entity == "receivables" and role == "admin" and row_dict.get("status") == "unverified":
                bg_id = row_dict.get("bill_group_id")
                if bg_id:
                    action_btns.append(dbc.Button(
                        html.I(className="fas fa-check"),
                        id={"type": "list-confirm-bill-group", "entity": entity, "pk": str(bg_id)},
                        size="sm", color="success", outline=True,
                        title="Confirm bill group",
                        style={"fontSize": "11px", "padding": "3px 7px",
                               "borderRadius": "7px"},
                    ))
                    action_btns.append(dbc.Button(
                        html.I(className="fas fa-times"),
                        id={"type": "list-reject-bill-group", "entity": entity, "pk": str(bg_id)},
                        size="sm", color="danger", outline=True,
                        title="Reject bill group",
                        style={"fontSize": "11px", "padding": "3px 7px",
                               "borderRadius": "7px"},
                    ))

            # ── Quick-action buttons derived from PROFILE_ACTIONS ──
            # These let users perform logical actions directly from the
            # list card without opening the profile first.
            entity_actions = PROFILE_ACTIONS.get(entity, [])
            for act in entity_actions:
                act_id = act.get("action_id", "")
                act_roles = act.get("roles")
                if act_roles and role not in act_roles:
                    continue
                # Skip actions that already have dedicated buttons above
                if act_id in ("edit", "delete", "view"):
                    continue
                # Skip actions that are purely profile-scoped (no navigation
                # or server-side action that makes sense at list level)
                # All remaining actions are rendered as quick-action buttons.
                act_label = act.get("label", act_id)
                act_color = act.get("color", "primary")
                act_icon = act.get("icon", "fa-bolt")
                action_btns.append(dbc.Button(
                    [html.I(className=f"fas {act_icon} me-1"), act_label],
                    id={"type": "profile-action", "entity": entity,
                        "pk": pk_val, "action": act_id,
                        "target": act.get("target_card") or ""},
                    size="sm", color=act_color, outline=True,
                    title=act_label,
                    style={"fontSize": "10px", "padding": "2px 6px",
                           "borderRadius": "7px"},
                ))

            cells.append(html.Td(
                html.Div(action_btns, style={"display": "flex", "gap": "4px",
                                             "flexWrap": "nowrap"}),
                style={"padding": "6px 8px", "verticalAlign": "middle"},
            ))

        body_rows.append(
            html.Tr(
                cells,
                id={"type": "list-row", "entity": entity, "pk": str(pk_val)},
                n_clicks=0,
                style={"transition": "background 0.12s ease"},
            )
        )

    # Ledger row highlighting: BF in yellow, closing in green, negative balance in red.
    # fn_account_ledger_fy returns row_type ('bf' | 'txn' |
    # 'full_depreciation' | 'half_depreciation' | 'closing') and
    # particulars like 'Balance B/F' / 'Balance C/F -> X' — NOT an
    # is_closing boolean or the literal string 'Brought Forward' that this
    # block checked for previously, which meant the highlighting never
    # actually fired.
    if entity == "ledger" and rows:
        for i, row in enumerate(rows):
            if i >= len(body_rows):
                break
            row_dict = (row.to_dict(include_calculated=True)
                        if hasattr(row, "to_dict") else dict(row))
            row_type = row_dict.get("row_type")
            balance = float(row_dict.get("balance") or 0)
            if row_type == "closing":
                body_rows[i].style = {"backgroundColor": "#d4edda", "fontWeight": "700"}
            elif balance < 0:
                body_rows[i].style = {"backgroundColor": "#f8d7da"}
            elif row_type == "bf":
                body_rows[i].style = {"backgroundColor": "#fff3cd"}
            elif row_type in ("full_depreciation", "half_depreciation", "depreciation"):
                body_rows[i].style = {"backgroundColor": "#e2e3ff"}

    # Cashbook B/F ('CiH' opening) in yellow, C/F ('CiH' closing) in green.
    # Two shapes to detect (2026-08): the Month Selector view tags these
    # with row_type='bf'/'closing' (_shape_cashbook_month_rows() in
    # loaders.py); the whole-FY view (no month selected) gets them
    # straight from fn_cashbook_paired_v3 itself now, with no row_type at
    # all — detected there by cr_account_name/dr_account_name == 'CiH'
    # instead, matching the same detection drilldown_callbacks.py's
    # sort/filter path uses to keep these rows pinned.
    if entity == "cashbook" and rows:
        for i, row in enumerate(rows):
            if i >= len(body_rows):
                break
            row_dict = (row.to_dict(include_calculated=True)
                        if hasattr(row, "to_dict") else dict(row))
            row_type = row_dict.get("row_type")
            if row_type == "bf" or row_dict.get("cr_account_name") == "CiH":
                body_rows[i].style = {"backgroundColor": "#fff3cd", "fontWeight": "700"}
            elif row_type == "closing" or row_dict.get("dr_account_name") == "CiH":
                body_rows[i].style = {"backgroundColor": "#d4edda", "fontWeight": "700"}
        

    if not body_rows:
        span = len(columns) + (1 if row_actions_allowed else 0)
        body_rows = [html.Tr(html.Td(
            html.Div([
                html.I(className="fas fa-inbox me-2",
                       style={"color": "#ccc", "fontSize": "20px"}),
                html.Div("No records found",
                         style={"color": "#aaa", "fontSize": "13px",
                                "marginTop": "4px"}),
            ], className="text-center", style={"padding": "28px 0"}),
            colSpan=span,
        ))]

    # ── Card header (title + New button + search) ────────────────────────
    header_right = []

    # "New" button — only when role has 'new' permission
    if "new" in allowed:
        new_target = f"form_{entity.rstrip('s') if not entity.endswith('_tbl') else entity.replace('_tbl','')}_new"
        # Special cases
        _new_target_map = {
            "receipts": "form_receipt_new",
            "expenses": "form_expense_new",
            "cashbook":     "form_receipt_new",
        }
        new_target = _new_target_map.get(entity, new_target)

        header_right.append(dbc.Button(
            [html.I(className="fas fa-plus me-1"), "New"],
            id={"type": "btn-new", "entity": entity},
            size="sm", color="success", outline=True,
            style={"fontSize": "11px", "borderRadius": "8px",
                   "fontWeight": "600"},
        ))

        # "Bulk Enroll" — CSV upload for the three enroll-tab entities.
        # Uses the single global modal in app_shell.py (see
        # bulk_enroll_callbacks.py), not a per-card component, so it's just
        # a plain button id here — no pattern-matching MATCH/ALL needed.
        if entity in ("apartments", "vendors", "security"):
            header_right.append(dbc.Button(
                [html.I(className="fas fa-file-csv me-1"), "Bulk Enroll"],
                id={"type": "btn-bulk-enroll", "entity": entity},
                size="sm", color="success", outline=True,
                style={"fontSize": "11px", "borderRadius": "8px",
                       "fontWeight": "600"},
            ))

    # FY select + "Export" button for Cashbook / Ledger — these two are the
    # entities whose underlying query is itself FY-scoped (see
    # drilldown_callbacks.py's `list_` branch, which resolves fy_options /
    # selected_fy and merges financial_year into `filters` before the SQL
    # call). The dropdown here is the only place that FY can be changed —
    # previously there was none; both views silently defaulted to the
    # current FY with no way to look at a prior year on-screen (the plain
    # CSV/XLS buttons below export whatever page is currently on-screen,
    # not a full-FY workbook in the CB2025-2026.xlsx reference layout,
    # which is what the dedicated Export button produces instead).
    if entity in ("cashbook", "ledger") and fy_options:
        # Ledger Account selector — lets you switch which account's ledger
        # is showing directly from the card header, instead of only ever
        # being reachable by navigating back to Settings > Accounts and
        # drilling into a specific account's profile each time (the only
        # path that previously set filters["account_id"] at all — see
        # registry.py's profile_account "show_ledger" action). Indented by
        # depth (fn_accounts_hierarchy's tree order) so the flat <select>
        # still reads hierarchically even though a dropdown can't nest.
        if entity == "ledger" and account_options:
            header_right.append(dbc.Select(
                id={"type": "list-account-select", "entity": entity},
                options=[
                    {"label": ("\u00A0\u00A0" * a["depth"]) + a["label"], "value": a["id"]}
                    for a in account_options
                ],
                value=selected_account_id,
                size="sm",
                style={"width": "170px", "fontSize": "11px",
                       "borderRadius": "8px", "display": "inline-block"},
            ))
        header_right.append(dbc.Select(
            id={"type": "list-fy-select", "entity": entity},
            options=[{"label": f"FY {fy}-{str(fy + 1)[-2:]}", "value": fy}
                     for fy in fy_options],
            value=selected_fy,
            size="sm",
            style={"width": "110px", "fontSize": "11px",
                   "borderRadius": "8px", "display": "inline-block"},
        ))
        # Month Selector — cashbook only (ledger is a whole-FY account view,
        # not month-scoped). Narrows fn_cashbook_month_page to one calendar
        # month so month_opening_balance/month_closing_balance ('CiH' B/F
        # and C/F) can be computed and shown per the CB2025-2026.xlsx
        # reference layout — see loaders.py's cashbook branch and
        # _shape_cashbook_month_rows(). Includes a blank "All months"
        # option to fall back to the plain whole-FY fn_cashbook_paired_v3
        # view (no B/F/C/F rows, just the flat paired list).
        if entity == "cashbook" and month_options:
            header_right.append(dbc.Select(
                id={"type": "list-month-select", "entity": entity},
                options=[{"label": "All months", "value": ""}] + [
                    {"label": m["label"], "value": m["value"]} for m in month_options
                ],
                value=selected_month if selected_month else "",
                size="sm",
                style={"width": "100px", "fontSize": "11px",
                       "borderRadius": "8px", "display": "inline-block"},
            ))
        export_label = "Export Cashbook" if entity == "cashbook" else "Export Ledger"
        header_right.append(dbc.Button(
            [html.I(className="fas fa-file-excel me-1"), export_label],
            id={"type": "btn-fy-export", "entity": entity},
            size="sm", color="primary", outline=True,
            disabled=(entity == "ledger" and not (filters or {}).get("account_id")),
            title=("Open an account's ledger first" if entity == "ledger"
                   and not (filters or {}).get("account_id") else None),
            style={"fontSize": "11px", "borderRadius": "8px",
                   "fontWeight": "600"},
        ))
        header_right.append(dcc.Download(id={"type": "fy-export-trigger", "entity": entity}))

    header_right += [
        dbc.Input(
            id={"type": "list-search", "entity": entity},
            placeholder="Search…", size="sm", debounce=True,
            # fn_cashbook_month_page (Month Selector active) has no
            # p_search param — see loaders.py's cashbook branch — so the
            # box is disabled rather than silently accepting text that
            # does nothing.
            disabled=(entity == "cashbook" and bool(selected_month)),
            style={"width": "130px", "fontSize": "12px",
                   "borderRadius": "8px"},
        ),
        dbc.Button(
            [html.I(className="fas fa-download me-1"), "CSV"],
            id={"type": "btn-csv-download", "entity": entity},
            size="sm", color="secondary", outline=True,
            style={"fontSize": "11px", "borderRadius": "8px"},
        ),
        dcc.Download(id={"type": "csv-download-trigger", "entity": entity}),
        dcc.Download(id={"type": "xls-download-trigger", "entity": entity}),
    ]

    if col_filters:
        header_right.append(dbc.Button(
            [html.I(className="fas fa-times me-1"), "Clear Filters"],
            id={"type": "list-clear-filters", "entity": entity},
            size="sm", color="warning", outline=True,
            style={"fontSize": "11px", "borderRadius": "8px", "fontWeight": "600"},
        ))

    # Accounts renders as a TreeView (parent/child nodes nested by
    # fn_accounts_hierarchy's depth), not the flat sortable/paginated
    # table every other entity uses — a chart of accounts is inherently
    # hierarchical (accounts.parent_account_id), and a flat table with a
    # "Parent" column doesn't convey that structure the way actual nesting
    # does. header_right (search/CSV/New, built above) carries over
    # unchanged; only the body swaps from table+pager to tree.
    if entity == "accounts":
        return render_accounts_tree_card(title, icon, rows, entity, total_rows, header_right)

    return html.Div([
        html.Div(
            html.Div([
                html.Div([
                    html.I(className=f"fas {icon} me-2",
                           style={"color": COLORS["primary"]}),
                    html.Strong(title, style={"fontSize": "13px"}),
                    dbc.Badge(str(total_rows), color="primary",
                              className="ms-2",
                              style={"fontSize": "10px"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div(header_right,
                         style={"display": "flex", "alignItems": "center",
                                "gap": "6px", "flexWrap": "wrap"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "flexWrap": "wrap", "gap": "8px"}),
            style={"padding": "10px 16px",
                   "background": "linear-gradient(180deg,rgba(255,255,255,0.85),rgba(248,251,255,0.95))"},
        ),
        html.Div([
            html.Div(
                dbc.Table([
                    html.Thead([
                        html.Tr(header_cells,
                                style={"position": "sticky", "top": 0,
                                       "zIndex": 2,
                                       "background": "rgba(248,251,255,0.97)"}),
                        html.Tr(filter_cells,
                                style={"position": "sticky", "top": "38px",
                                       "zIndex": 1,
                                       "background": "#f4f7fb",
                                       "borderTop": "1px solid rgba(120,148,181,0.2)"}),
                    ]),
                    html.Tbody(body_rows),
                ], hover=True, responsive=True, size="sm",
                   style={"marginBottom": 0}),
                style={"overflowX": "auto", "maxHeight": "420px",
                       "overflowY": "auto"},
            ),
            # ── Pagination ──────────────────────────────────────────────
            html.Div([
                html.Small(
                    f"Showing {min((page-1)*page_size+1, total_rows)}–"
                    f"{min(page*page_size, total_rows)} of {total_rows}",
                    style={"color": "#aaa", "fontSize": "11px"},
                ),
                html.Div([
                    dbc.Button(
                        html.I(className="fas fa-chevron-left"),
                        id={"type": "list-page-prev", "entity": entity},
                        size="sm", disabled=(page <= 1),
                        style={"fontSize": "11px", "borderRadius": "8px"},
                    ),
                    html.Span(f"{page} / {total_pages}",
                              style={"padding": "0 12px", "fontSize": "12px",
                                     "fontWeight": "600", "color": "#15304f"}),
                    dbc.Button(
                        html.I(className="fas fa-chevron-right"),
                        id={"type": "list-page-next", "entity": entity},
                        size="sm", disabled=(page >= total_pages),
                        style={"fontSize": "11px", "borderRadius": "8px"},
                    ),
                ], style={"display": "flex", "alignItems": "center",
                          "gap": "4px"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "padding": "10px 0 0",
                      "borderTop": "1px solid rgba(120,148,181,0.1)",
                      "marginTop": "10px"}),
        ], style={"padding": "12px"}),
    ], style={
        "borderRadius": "16px",
        "border": "1px solid rgba(255,255,255,0.65)",
        "boxShadow": "0 10px 30px rgba(15,23,42,0.08)",
        "overflow": "hidden",
    })

# ════════════════════════════════════════════════════════════════════════════
# PROFILE CARD RENDERER
# ════════════════════════════════════════════════════════════════════════════

# Lifecycle stage labels for concerns_assigns.status — kept here (and mirrored
# in invite_to_callbacks.py / assign_to_callbacks.py) so the concern profile
# card can render a stage banner without a cross-module import.
# Stage legend: invited -> bid_submitted -> assigned -> accepted -> resolved -> closed
_CONCERN_STAGE_LABEL = {
    "invited":       ("Invited",            "#7d8ea3"),
    "bid_submitted": ("Bid submitted",      "#1d74d8"),
    "assigned":      ("Assigned",           "#e59620"),
    "accepted":      ("Accepted",           "#2563eb"),
    "resolved":      ("Resolved",           "#17976e"),
    "closed":        ("Closed",             "#64748b"),
}

_CONCERN_STATUS_BANNER = {
    "open":     ("New concern — awaiting invitation/assignment",  "#de5c52"),
    "assigned": ("Assigned — work in progress",                   "#e59620"),
    "resolved": ("Resolved — pending close",                      "#17976e"),
    "closed":   ("Closed — this concern is complete",             "#64748b"),
}

_CHANNEL_STATUS_BANNER = {
    True:  ("Active — accepting subscriptions and alerts",       "#17976e"),
    False: ("Inactive — no new alerts will be sent",             "#de5c52"),
}


def render_profile_card(card_id: str, title: str, icon: str,
                        entity: str, record,
                        fields: list[dict], actions: list[dict] | None = None,
                        color: str = "#1d74d8",
                        auth_data: dict | None = None,
                        filters: dict | None = None) -> html.Div:
    from app.dash_apps.drilldown.registry import to_plural

    auth_data  = auth_data or {}
    role  = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")
    allowed    = _perms_for(role, entity)
    entity_plural = to_plural(entity)
    hidden = _context_hidden_fields(filters)

    record_dict = (record.to_dict(include_calculated=True)
                   if hasattr(record, "to_dict") else record)
    pk_val = record_dict.get("id", "")

    # ── Resolve the society_id used for asset URL construction ───────────
    if entity == "society":
        img_society_id = pk_val
        img_entity_pk  = pk_val
    else:
        img_society_id = (
            record_dict.get("society_id")
            if record_dict.get("society_id") is not None
            else record_dict.get("_image_society_id")
            if record_dict.get("_image_society_id") is not None
            else society_id
        )
        img_entity_pk = pk_val

    # ── Split fields into image fields and text fields ───────────────────
    _IMAGE_FIELD_NAMES = {
        "photo", "photo_url", "image", "logo",
        "owner_photo", "id_proof", "secretary_sign", "login_background",
        "license", "payment_qr",
    }
    visible_fields = [
        f for f in fields
        if f.get("field") not in hidden
        and _field_visible(entity_plural, f.get("field"), role)
        and not (entity in ("concern", "event_ticket") and f.get("field") == "qr_payload")
    ]
    image_fields = [
        f for f in visible_fields
        if f.get("type") == "image" or f.get("field") in _IMAGE_FIELD_NAMES
    ]
    text_fields  = [f for f in visible_fields if f not in image_fields]

    # ── Concern QR code — rendered live from the stored qr_payload (society-
    # scoped "<society_id>-CON-<id>" string), not shown as a raw text field.
    # Scans dispatch to validate_concern_qr() in qr_service.py.
    concern_qr_section = []
    if entity == "concern" and pk_val:
        try:
            from app.services.qr_service import generate_qr_code
            qr_society_id = record_dict.get("society_id") or society_id
            qr_img, qr_payload = generate_qr_code(qr_society_id, "CON", pk_val)
            if qr_img:
                concern_qr_section.append(
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-qrcode",
                                   style={"color": "#aaa", "fontSize": "10px",
                                          "marginRight": "5px"}),
                            html.Span("Concern QR",
                                      style={"color": "#7d8ea3", "fontSize": "10px",
                                             "fontWeight": "600",
                                             "textTransform": "uppercase"}),
                        ], style={"marginBottom": "5px"}),
                        html.Img(
                            src=qr_img,
                            style={
                                "maxWidth": "160px", "maxHeight": "160px",
                                "borderRadius": "8px",
                                "border": "1px solid rgba(0,0,0,0.08)",
                                "objectFit": "contain", "background": "#fff",
                                "padding": "4px", "display": "block",
                            },
                        ),
                        html.Div(qr_payload, style={
                            "fontSize": "10px", "color": "#7d8ea3",
                            "fontFamily": "monospace", "marginTop": "4px",
                        }),
                    ], style={
                        "marginBottom": "12px", "padding": "10px",
                        "background": "rgba(248,251,255,0.7)",
                        "borderRadius": "10px",
                        "border": "1px solid rgba(200,215,235,0.4)",
                    })
                )
        except Exception as e:
            print(f"⚠️  concern QR render failed: {e}")

    # ── Event ticket QR — rendered live from the stored qr_payload so the
    # owner can hand the screen to security / admin to scan at the gate.
    # Scans dispatch to validate_event_ticket_qr() (qr_service.py). Mirrors the
    # concern QR section above.
    #
    # Branding (2026-08): also adds Print/Save as PDF/Email buttons — event
    # tickets previously had no print/download flow at all, only this
    # in-app QR view. Buttons reuse the same letterhead as receipts/NOCs
    # (print_letterhead.py); see event_ticket_callbacks.py.
    event_ticket_qr_section = []
    if entity == "event_ticket" and pk_val:
        try:
            from app.services.qr_service import generate_qr_code
            qr_society_id = record_dict.get("society_id") or society_id
            qr_img, qr_payload = generate_qr_code(qr_society_id, "EVT", pk_val)
            if qr_img:
                status = record_dict.get("status", "")
                color = "#27ae60" if status == "used" else ("#e74c3c" if status == "cancelled" else "#27ae60")

                from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, QR_CAPTION
                society_row = db._execute(
                    "SELECT name, address, logo, login_background, secretary_sign, secretary_name "
                    "FROM societies WHERE id = %s",
                    (qr_society_id,), fetch_one=True,
                ) or {}
                letterhead = get_letterhead_assets(society_row, qr_society_id)
                ticket_print_data = {
                    "id": pk_val,
                    "event_title": record_dict.get("event_title", "Event"),
                    "event_date": str(record_dict.get("event_date") or ""),
                    "event_time": str(record_dict.get("event_time") or ""),
                    "venue": record_dict.get("venue", ""),
                    "booking_reference": record_dict.get("booking_reference", ""),
                    "ticket_type": record_dict.get("ticket_type", ""),
                    "status": status,
                    "qr_url": qr_img, "qr_payload": qr_payload, "qr_caption": QR_CAPTION,
                    "society_name": letterhead["society_name"], "society_address": letterhead["society_address"],
                    "logo_url": letterhead["logo_url"], "background_url": letterhead["background_url"],
                    "signature_url": letterhead["signature_url"], "secretary_name": letterhead["secretary_name"],
                }

                event_ticket_qr_section.append(
                    html.Div([
                        dcc.Store(id="event-ticket-print-data", data=ticket_print_data, storage_type="memory"),
                        html.Div([
                            html.I(className="fas fa-qrcode",
                                   style={"color": "#aaa", "fontSize": "10px",
                                          "marginRight": "5px"}),
                            html.Span("Ticket QR",
                                      style={"color": "#7d8ea3", "fontSize": "10px",
                                             "fontWeight": "600",
                                             "textTransform": "uppercase"}),
                        ], style={"marginBottom": "5px"}),
                        html.Img(
                            src=qr_img,
                            style={
                                "maxWidth": "160px", "maxHeight": "160px",
                                "borderRadius": "8px",
                                "border": "1px solid rgba(0,0,0,0.08)",
                                "objectFit": "contain", "background": "#fff",
                                "padding": "4px", "display": "block",
                            },
                        ),
                        html.Div(qr_payload, style={
                            "fontSize": "10px", "color": "#7d8ea3",
                            "fontFamily": "monospace", "marginTop": "4px",
                        }),
                        html.Div(
                            f"Status: {status.title() if status else 'Active'}",
                            style={"fontSize": "10px", "color": color,
                                   "fontWeight": "600", "marginTop": "4px"},
                        ),
                        html.Div([
                            html.Button(
                                [html.I(className="fas fa-print me-2"), "Print"],
                                id="event-ticket-btn-print", n_clicks=0,
                                className="btn btn-outline-primary btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                            html.Button(
                                [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                                 id="event-ticket-btn-pdf", n_clicks=0,
                                className="btn btn-outline-danger btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                            html.Button(
                                [html.I(className="fas fa-envelope me-2"), "Email Ticket"],
                                id="event-ticket-btn-email", n_clicks=0,
                                className="btn btn-outline-info btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginTop": "10px"}),
                    ], style={
                        "marginBottom": "12px", "padding": "10px",
                        "background": "rgba(248,251,255,0.7)",
                        "borderRadius": "10px",
                        "border": "1px solid rgba(200,215,235,0.4)",
                    })
                )
        except Exception as e:
            print(f"⚠️  event ticket QR render failed: {e}")

    # ── Vendor Pass QR — rendered live for the active vendor pass so the
    # vendor can print/save a pass document with society branding.
    # Shown on the vendor profile (entity=="vendor", looks up the active
    # pass for that vendor) AND on the dedicated Vendor Pass profile
    # (entity=="vendor_pass", opened straight after a Sell/Buy Pass save).
    vendor_pass_section = []
    if entity in ("vendor", "vendor_pass") and pk_val:
        try:
            from app.services.qr_service import generate_qr_code
            from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, QR_CAPTION

            if entity == "vendor":
                vendor_pk = pk_val
                vendor_user_id = record_dict.get("user_id") or pk_val
                vendor_name = record_dict.get("name", "Vendor")
                service_type = record_dict.get("service_type", "")
                qr_society_id = record_dict.get("society_id") or society_id
                pass_row = db._execute(
                    "SELECT pass_type, issued_date, valid_until FROM vendor_passes "
                    "WHERE user_id=%s AND status='active' AND valid_until>=CURRENT_DATE "
                    "ORDER BY valid_until DESC LIMIT 1",
                    (vendor_user_id,),
                    fetch_one=True,
                ) or {}
            else:  # vendor_pass profile — pk_val is the vendor_passes row id
                vp_row = db._execute(
                    "SELECT vp.pass_type, vp.issued_date, vp.valid_until, vp.society_id, "
                    "u.id AS vendor_user_id, u.linked_id AS vendor_pk, "
                    "v.name AS vendor_name, v.service_type "
                    "FROM vendor_passes vp "
                    "JOIN users u ON u.id = vp.user_id "
                    "LEFT JOIN vendors v ON v.id = u.linked_id "
                    "WHERE vp.id = %s",
                    (pk_val,),
                    fetch_one=True,
                ) or {}
                vendor_pk = vp_row.get("vendor_pk") or pk_val
                vendor_user_id = vp_row.get("vendor_user_id") or vendor_pk
                vendor_name = vp_row.get("vendor_name", "Vendor")
                service_type = vp_row.get("service_type", "")
                qr_society_id = vp_row.get("society_id") or society_id
                pass_row = vp_row

            qr_img, qr_payload = generate_qr_code(qr_society_id, "VND", vendor_pk)
            if qr_img:
                society_row = db._execute(
                    "SELECT name, address, logo, login_background, secretary_sign, secretary_name "
                    "FROM societies WHERE id = %s",
                    (qr_society_id,),
                    fetch_one=True,
                ) or {}
                letterhead = get_letterhead_assets(society_row, qr_society_id)
                vendor_pass_print_data = {
                    "id": vendor_pk,
                    "vendor_name": vendor_name,
                    "service_type": service_type,
                    "pass_type": pass_row.get("pass_type",""),
                    "issued_date": str(pass_row.get("issued_date") or ""),
                    "valid_until": str(pass_row.get("valid_until") or ""),
                    "qr_url": qr_img, "qr_payload": qr_payload, "qr_caption": QR_CAPTION,
                    "society_name": letterhead["society_name"], "society_address": letterhead["society_address"],
                    "logo_url": letterhead["logo_url"], "background_url": letterhead["background_url"],
                    "signature_url": letterhead["signature_url"], "secretary_name": letterhead["secretary_name"],
                }
                vendor_pass_section.append(
                    html.Div([
                        dcc.Store(id="vendor-pass-print-data", data=vendor_pass_print_data, storage_type="memory"),
                        html.Div([
                            html.I(className="fas fa-id-card",
                                   style={"color": "#aaa", "fontSize": "10px",
                                          "marginRight": "5px"}),
                            html.Span("Vendor Pass",
                                      style={"color": "#7d8ea3", "fontSize": "10px",
                                             "fontWeight": "600",
                                             "textTransform": "uppercase"}),
                        ], style={"marginBottom": "5px"}),
                        html.Img(
                            src=qr_img,
                            style={
                                "maxWidth": "160px", "maxHeight": "160px",
                                "borderRadius": "8px",
                                "border": "1px solid rgba(0,0,0,0.08)",
                                "objectFit": "contain", "background": "#fff",
                                "padding": "4px", "display": "block",
                            },
                        ),
                        html.Div(qr_payload, style={
                            "fontSize": "10px", "color": "#7d8ea3",
                            "fontFamily": "monospace", "marginTop": "4px",
                        }),
                        html.Div([
                            html.Button(
                                [html.I(className="fas fa-print me-2"), "Print"],
                                id="vendor-pass-btn-print", n_clicks=0,
                                className="btn btn-outline-primary btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                            html.Button(
                            [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                            id="vendor-pass-btn-pdf", n_clicks=0,
                                className="btn btn-outline-danger btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                            html.Button(
                                [html.I(className="fas fa-envelope me-2"), "Email Pass"],
                                id="vendor-pass-btn-email", n_clicks=0,
                                className="btn btn-outline-info btn-sm",
                                style={"borderRadius": "10px", "fontWeight": "600"},
                            ),
                        ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginTop": "10px"}),
                    ], style={
                        "marginBottom": "12px", "padding": "10px",
                        "background": "rgba(248,251,255,0.7)",
                        "borderRadius": "10px",
                        "border": "1px solid rgba(200,215,235,0.4)",
                    })
                )
        except Exception as e:
            print(f"⚠️  vendor pass QR render failed: {e}")

    # ── Image gallery (full-width, above the 2-col grid) ────────────────
    image_section = list(concern_qr_section) + list(event_ticket_qr_section) + list(vendor_pass_section)
    for f in image_fields:
        image_path = record_dict.get(f["field"])
        if not image_path or str(image_path).strip() in ("", "None"):
            continue
        full_url = get_image_url(
            str(image_path).strip(),
            img_society_id,
            entity,
            img_entity_pk,          # ← was pk_val but now named consistently
        )
        if not full_url:
            continue
        size = f.get("size", "medium")
        max_h = {"small": "80px", "medium": "160px", "large": "260px"}.get(size, "160px")
        image_section.append(
            html.Div([
                html.Div([
                    html.I(className=f.get("icon", "fas fa-image"),
                           style={"color": "#aaa", "fontSize": "10px",
                                  "marginRight": "5px"}),
                    html.Span(f["label"],
                              style={"color": "#7d8ea3", "fontSize": "10px",
                                     "fontWeight": "600",
                                     "textTransform": "uppercase"}),
                ], style={"marginBottom": "5px"}),
                html.Img(
                    src=full_url,
                    style={
                        "maxWidth": "100%",
                        "maxHeight": max_h,
                        "borderRadius": "8px",
                        "border": "1px solid rgba(0,0,0,0.08)",
                        "objectFit": "contain",
                        "background": "#f8f9fa",
                        "padding": "4px",
                        "display": "block",
                    },
                ),
            ], style={
                "marginBottom": "12px",
                "padding": "10px",
                "background": "rgba(248,251,255,0.7)",
                "borderRadius": "10px",
                "border": "1px solid rgba(200,215,235,0.4)",
            })
        )

    # ── Text fields rendered as 2-column grid cells ──────────────────────
    _CONTACT_FIELDS = {
        "email":          ("mailto:", "fa-envelope", "#1d74d8"),
        "mobile":         ("tel:",     "fa-phone",    "#17976e"),
        "phone":          ("tel:",     "fa-phone",    "#17976e"),
        "contact_number": ("tel:",     "fa-phone",    "#17976e"),
        "telephone":      ("tel:",     "fa-phone",    "#17976e"),
        "owner_mobile":   ("tel:",     "fa-phone",    "#17976e"),
    }

    def _field_cell(f: dict) -> html.Div:
        val = _display_value(f["field"], record_dict)
        fmt = f.get("format")
        if fmt in _FIELD_FORMATTERS and val is not None:
            val = _FIELD_FORMATTERS[fmt](val)  # already a Dash component — skip below
        elif val is None:
            val = "—"
        elif isinstance(val, bool):
            val = html.Span("✓ Active" if val else "✗ Inactive",
                            style={"color": "#17976e" if val else "#de5c52", "fontWeight": "600"})
        elif isinstance(val, (date, datetime)):
            val = _format_datetime(val)
        elif isinstance(val, Decimal):
            val = f"₹{val:,.2f}"
        elif isinstance(val, str):
            val = _humanize_string(val)
        else:
            val = str(val)

        contact_href, contact_icon, contact_color = _CONTACT_FIELDS.get(f.get("field"), ("", "", ""))
        is_contact = bool(contact_href and isinstance(val, str) and val not in ("—", "", None))

        if is_contact:
            val = html.A(
                [val, html.I(className=f"fas {contact_icon} ms-1",
                             style={"fontSize": "10px", "color": contact_color})],
                href=f"{contact_href}{val}",
                style={"textDecoration": "none", "color": "inherit"},
            )

        cell_class = "profile-field-cell clickable" if is_contact else "profile-field-cell"

        return html.Div([
            html.Div([
                html.I(className=f.get("icon", "fas fa-circle-dot"),
                       style={"color": color, "fontSize": "9px",
                              "marginRight": "5px"}),
                html.Span(f["label"],
                          style={"color": "#7d8ea3", "fontSize": "10px",
                                 "fontWeight": "600",
                                 "textTransform": "uppercase"}),
            ], style={"marginBottom": "3px"}),
            html.Div(val, style={
                "fontSize": "13px", "fontWeight": "500", "color": "#15304f",
                "wordBreak": "break-word",
            }),
        ], style={
            "padding": "10px 12px",
            "background": "rgba(248,251,255,0.6)",
            "borderRadius": "10px",
            "border": "1px solid rgba(200,215,235,0.35)",
        }, className=cell_class)

    text_cells = [_field_cell(f) for f in text_fields]

    # ── Concern actions: scope actions to the caller's own concerns_assigns
    # stage ──────────────────────────────────────────────────────────────
    # NOTE (fixed 2026-08): these buttons used to be shown to every
    # vendor/security/admin caller on every concern regardless of their own
    # concerns_assigns.status — "Bid" and "Decline" only make sense at
    # 'invited' (submit_concern_bid()/decline_concern_assignment() both
    # require status='invited' or fail), vendor "Resolved" only at
    # 'assigned', and admin "Accept"/"Decline"/"Resolved" only at
    # 'assigned'/'assigned'/'accepted' respectively (loaders.py).
    my_concern_status = None
    if entity == "concern" and role in ("vendor", "security", "admin"):
        my_role_code = {"vendor": "VND", "security": "SEC", "admin": "ADM"}[role]
        my_entity_id = auth_data.get("user_id") if role == "admin" else auth_data.get("linked_id")
        for a in (record_dict.get("_assignments") or []):
            if a.get("role") == my_role_code and a.get("entity_id") == my_entity_id:
                my_concern_status = a.get("status")
                break

    # Security's "Resolved" is gated differently from vendor's: per the
    # Concerns workflow spec it's enabled once an ADMIN's row on this
    # concern reaches 'accepted' — not on security's own assignment status.
    any_admin_accepted = False
    if entity == "concern" and role == "security":
        for a in (record_dict.get("_assignments") or []):
            if a.get("role") == "ADM" and a.get("status") == "accepted":
                any_admin_accepted = True
                break

    # ── Action buttons filtered by role ─────────────────────────────────
    # renderers.py — render_profile_card(), action button loop
    action_btns = []
    for act in (actions or []):
        act_id = act.get("action_id", "")
        act_roles = act.get("roles")
        if act_roles and role not in act_roles:        # ← NEW: respects PROFILE_ACTIONS roles
            continue
        if act_id == "edit"   and "edit"   not in allowed: continue
        if act_id == "delete" and "delete" not in allowed: continue
        # ── Poll lifecycle guards ────────────────────────────────────────
        # Edit: only while the poll is still active AND nobody has voted
        # yet — changing choices out from under existing votes would
        # corrupt the tally (server-side guarded too, see fn_edit_poll).
        if act_id == "edit" and entity == "poll":
            if record_dict.get("status") != "active" or (record_dict.get("total_votes") or 0) > 0:
                continue
        # Close Poll only makes sense from 'active'.
        if act_id == "close_poll" and record_dict.get("status") != "active": continue
        # Declare Results is a no-op (and rejected server-side) once
        # already declared.
        if act_id == "declare_results" and record_dict.get("status") == "results_declared": continue
        if act_id == "save_bid" and my_concern_status != "invited": continue
        if act_id == "decline_concern" and my_concern_status != "invited": continue
        if act_id == "vendor_resolve":
            if role == "security":
                if not any_admin_accepted: continue
            elif my_concern_status != "assigned": continue
        if act_id == "accept_concern" and my_concern_status != "assigned": continue
        if act_id == "decline_concern_admin" and my_concern_status != "assigned": continue
        if act_id == "admin_resolve" and my_concern_status != "accepted": continue
        if act_id == "subscribe_channel":
            is_subscribed = record_dict.get("is_subscribed")
            act_label = "Subscribed" if is_subscribed else "Subscribe"
            act_color = "success" if is_subscribed else "outline-primary"
        else:
            act_label = act["label"]
            act_color = act.get("color", "primary")
        action_btns.append(dbc.Button(
            [html.I(className=f"fas {act.get('icon', 'fa-bolt')} me-2"),
            act_label],
            id={"type": "profile-action", "entity": entity, "pk": str(pk_val),
                "action": act_id, "target": act.get("target_card") or ""},
            n_clicks=0, color=act_color, size="sm",
            className="me-2 mb-2",
            style={"borderRadius": "10px", "fontWeight": "600"},
        ))

    # ── Concern lifecycle banners — only on the concern profile card ──────────
    # 4b: overall concern status banner
    _concern_banners = []
    if entity == "concern":
        _cstatus = record_dict.get("status")
        _stext, _scolor = _CONCERN_STATUS_BANNER.get(
            _cstatus, ("In progress", "#1d74d8"))
        _concern_banners.append(dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"), _stext],
            color="light",
            style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px",
                   "borderRadius": "8px", "marginBottom": "8px",
                   "borderColor": f"{_scolor}40"},
        ))
        # 4a: caller's own assignment stage banner
        if my_concern_status:
            _mlabel, _mcolor = _CONCERN_STAGE_LABEL.get(
                my_concern_status, (my_concern_status.title(), "#1d74d8"))
            _my_assign = None
            for _a in (record_dict.get("_assignments") or []):
                if _a.get("role") == my_role_code and _a.get("entity_id") == my_entity_id:
                    _my_assign = _a
                    break
            _bid = _my_assign.get("assign_bid_amount") if _my_assign else None
            _stage_txt = f"{_mlabel} · ₹{_bid:,.0f}" if _bid not in (None, "") else _mlabel
            _concern_banners.append(dbc.Alert(
                [html.I(className="fas fa-hourglass-half me-2"),
                 html.Span(["Your involvement: ", html.Strong(_stage_txt)])],
                color="light",
                style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px",
                       "borderRadius": "8px", "marginBottom": "8px",
                       "borderColor": f"{_mcolor}40"},
            ))

    # ── Channel lifecycle banners ──────────────────────────────────────────
    _channel_banners = []
    if entity == "channel" and pk_val:
        is_active = record_dict.get("active", True)
        _stext, _scolor = _CHANNEL_STATUS_BANNER.get(
            is_active, ("Unknown status", "#1d74d8"))
        _channel_banners.append(dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"), _stext],
            color="light",
            style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px",
                   "borderRadius": "8px", "marginBottom": "8px",
                   "borderColor": f"{_scolor}40"},
        ))
        pending_count = record_dict.get("pending_count", 0)
        if pending_count:
            _channel_banners.append(dbc.Alert(
                [html.I(className="fas fa-bell me-2"),
                 html.Strong(f"{pending_count} pending alert(s) awaiting response")],
                color="warning",
                style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px",
                       "borderRadius": "8px", "marginBottom": "8px"},
            ))

    # ── Poll UI: lifecycle banner + voting buttons + results under hr divider
    _poll_ui = []
    if entity == "poll" and pk_val:
        poll_status = record_dict.get("status", "")
        choice_count = record_dict.get("choice_count", 0)
        choices = [record_dict.get(f"choice_{i}") for i in range(1, choice_count + 1)]
        total_votes = record_dict.get("total_votes") or 0
        has_voted = record_dict.get("has_voted")
        user_vote = record_dict.get("user_vote")
        vote_counts = record_dict.get("vote_counts") or {}
        # Results only become visible once an admin has explicitly declared
        # them — Close Poll alone just stops new votes, it isn't a reveal.
        show_results = poll_status == "results_declared"
        can_vote = poll_status == "active" and not has_voted

        # Unmistakable status banner, mirroring the concern-status banner
        # pattern above — the bars further down are easy to miss on a
        # crowded profile card, this isn't.
        _poll_banner = {
            "results_declared": ("🏆 Results Declared", "#17976e"),
            "closed":            ("Voting Closed — results not yet declared", "#e59620"),
        }.get(poll_status)
        if _poll_banner:
            _btext, _bcolor = _poll_banner
            _poll_ui.append(dbc.Alert(
                [html.I(className="fas fa-poll me-2"), _btext],
                color="light",
                style={"fontSize": "12px", "fontWeight": "700", "padding": "8px 12px",
                       "borderRadius": "8px", "marginBottom": "8px",
                       "borderColor": f"{_bcolor}40", "color": _bcolor},
            ))

        if can_vote and choices:
            _poll_ui.append(
                html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"})
            )
            _poll_ui.append(
                html.Div([
                    html.Span("Cast your vote", style={
                        "fontSize": "13px", "fontWeight": "700",
                        "color": "#15304f", "marginBottom": "8px", "display": "block"
                    }),
                    html.Div([
                        dbc.Button(
                            [html.I(className="fas fa-check me-1"), f" {choice_text}"],
                            id={"type": "poll-vote-btn", "poll_id": str(pk_val), "choice": str(i)},
                            color="primary", size="sm", outline=False,
                            className="me-2 mb-2",
                            style={"borderRadius": "8px", "minWidth": "160px", "textAlign": "left"},
                        )
                        for i, choice_text in enumerate(choices, start=1)
                        if choice_text
                    ], style={"display": "flex", "flexWrap": "wrap", "gap": "6px"}),
                ], style={"marginBottom": "8px"})
            )

        if show_results and total_votes > 0:
            bars = []
            for i, choice_text in enumerate(choices, start=1):
                vote_count = vote_counts.get(f"choice_{i}", 0) or 0
                pct = (vote_count / total_votes * 100) if total_votes > 0 else 0
                bars.append(
                    html.Div([
                        html.Span(f"{choice_text}", style={"fontSize": "13px", "fontWeight": "600"}),
                        html.Div([
                            html.Div(
                                style={
                                    "height": "20px",
                                    "width": f"{pct}%",
                                    "backgroundColor": "#1859b8",
                                    "borderRadius": "4px",
                                    "transition": "width 0.3s ease",
                                }
                            ),
                        ], style={"flex": "1", "backgroundColor": "#eee", "borderRadius": "4px", "overflow": "hidden", "minWidth": "40px"}),
                        html.Span(f"{vote_count} ({pct:.1f}%)", style={"fontSize": "12px", "width": "80px", "textAlign": "right"}),
                    ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}),
                )
            _poll_ui.append(
                html.Div([
                    html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
                    html.H6("Results", style={"fontWeight": "700", "color": "#15304f", "fontSize": "14px", "marginBottom": "8px"}),
                    html.Div(bars),
                    html.Small(f"{total_votes} total vote(s)", style={"color": "#999", "fontSize": "12px"}),
                ])
            )
        elif show_results and total_votes == 0:
            _poll_ui.append(
                html.Div([
                    html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
                    html.Small("No votes yet.", style={"color": "#999"}),
                ])
            )

        if has_voted and user_vote:
            _poll_ui.append(
                html.Div([
                    html.I(className="fas fa-check-circle me-1", style={"color": "#2ecc71"}),
                    html.Span(f"You voted for: {choices[user_vote - 1]}", style={"fontWeight": "600", "color": "#15304f"}),
                ], className="text-success mt-2")
            )

    # ── Universal Entity Banner ──────────────────────────────────────────────────
    _entity_banner = []
    banner_text = _ENTITY_BANNERS.get(entity)
    if banner_text:
        _entity_banner.append(dbc.Alert(
            [
                html.I(className="fas fa-info-circle me-2"),
                banner_text
            ],
            color="info",
            style={"fontSize": "12px", "padding": "8px 12px", "borderRadius": "8px", "marginBottom": "8px"}
        ))

    return html.Div([
        html.Div(
            html.Div([
                html.Div([
                    html.Div(
                        html.I(className=f"fas {icon}",
                               style={"color": "#fff", "fontSize": "16px"}),
                        style={
                            "width": "38px", "height": "38px",
                            "borderRadius": "10px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center",
                            "marginRight": "12px", "flexShrink": "0",
                        },
                    ),
                    html.Div([
                        html.Strong(title, style={"fontSize": "14px"}),
                        html.Div(f"ID: {pk_val}",
                                 style={"fontSize": "11px", "color": "#999"}),
                    ]),
                ], style={"display": "flex", "alignItems": "center"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([

            # ── Concern lifecycle banners (status + caller's own stage) ─
            *(_concern_banners if _concern_banners else []),

            # ── Channel lifecycle banners (active/inactive + pending alerts) ─
            *(_channel_banners if _channel_banners else []),

            # ── Universal Entity banner ─
            *(_entity_banner if _entity_banner else []),

            # ── Compliance settings rule reference (RWA/CHS GST/TDS/fund banner) ─
            _compliance_rules_banner(entity_plural, _resolve_society_state(record_dict, society_id)),

            # ── Images (full-width, stacked) ─────────────────────────
            html.Div(image_section) if image_section else None,

            # ── Text fields in 2-column responsive grid ──────────────
            html.Div(
                text_cells,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, 1fr)",
                    "gap": "10px",
                    "marginBottom": "14px",
                },
            ) if text_cells else None,

            # ── Channel subscriber list ───────────────────────────────
            *(_render_channel_subscribers(record_dict) if entity == "channel" and pk_val else []),

            # ── Channel alert events history ──────────────────────────
            *(_render_channel_alert_events(record_dict) if entity == "channel" and pk_val else []),

            # ── Poll UI (voting + results) ───────────────────────────
            *(_poll_ui),

            # ── Action buttons ────────────────────────────────────────
            html.Div([
                html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
                html.Div(action_btns,
                         style={"display": "flex", "flexWrap": "wrap",
                                "gap": "6px"}),
            ]) if action_btns else None,

        ], style={"padding": "16px", "maxHeight": "620px",
                  "overflowY": "auto"}),
    ], style={
        "borderRadius": "16px", "border": f"1px solid {color}22",
        "boxShadow": f"0 10px 30px {color}18",
        "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
        "backdropFilter": "blur(12px)", "overflow": "hidden",
    })


def render_account_profile_card(card_id: str, title: str, icon: str,
                                entity: str, record: dict,
                                fields: list[dict], actions: list[dict] | None = None,
                                color: str = "#1d74d8",
                                auth_data: dict | None = None,
                                filters: dict | None = None,
                                ledger_rows: list[dict] | None = None,
                                fy_options: list | None = None,
                                selected_fy: int | None = None,
                                society_id: int | None = None) -> html.Div:
    """Account profile page that includes both the account fields and the
    ledger transaction table below it, matching the CB2024-2025.xlsx layout."""
    from app.dash_apps.drilldown.registry import to_plural

    auth_data  = auth_data or {}
    role  = auth_data.get("role", "guest")
    allowed    = _perms_for(role, entity)
    entity_plural = to_plural(entity)
    hidden = _context_hidden_fields(filters)

    record_dict = (record.to_dict(include_calculated=True)
                   if hasattr(record, "to_dict") else record)
    pk_val = record_dict.get("id", "")

    # ── Resolve the society_id used for asset URL construction ───────────
    img_society_id = (
        record_dict.get("society_id")
        if record_dict.get("society_id") is not None
        else society_id
    )
    img_entity_pk = pk_val

    visible_fields = [
        f for f in fields
        if f.get("field") not in hidden
        and _field_visible(entity_plural, f.get("field"), role)
    ]

    def _field_cell(f: dict) -> html.Div:
        val = _display_value(f["field"], record_dict)
        fmt = f.get("format")
        if fmt in _FIELD_FORMATTERS and val is not None:
            val = _FIELD_FORMATTERS[fmt](val)
        elif val is None:
            val = "—"
        elif isinstance(val, bool):
            val = html.Span("✓ Active" if val else "✗ Inactive",
                            style={"color": "#17976e" if val else "#de5c52", "fontWeight": "600"})
        elif isinstance(val, (date, datetime)):
            val = _format_datetime(val)
        elif isinstance(val, Decimal):
            val = f"₹{val:,.2f}"
        elif isinstance(val, str):
            val = _humanize_string(val)
        else:
            val = str(val)

        return html.Div([
            html.Div([
                html.I(className=f.get("icon", "fas fa-circle-dot"),
                       style={"color": color, "fontSize": "9px",
                              "marginRight": "5px"}),
                html.Span(f["label"],
                          style={"color": "#7d8ea3", "fontSize": "10px",
                                 "fontWeight": "600", "textTransform": "uppercase"}),
            ], style={"marginBottom": "3px"}),
            html.Div(val, style={
                "fontSize": "13px", "fontWeight": "500", "color": "#15304f",
                "wordBreak": "break-word",
            }),
        ], style={
            "padding": "10px 12px",
            "background": "rgba(248,251,255,0.6)",
            "borderRadius": "10px",
            "border": "1px solid rgba(200,215,235,0.35)",
        })

    text_cells = [_field_cell(f) for f in visible_fields]

    # ── Ledger table ────────────────────────────────────────────────────
    ledger_section = []
    if ledger_rows is not None:
        ledger_columns = [
            {"name": "Date", "field": "row_date"},
            {"name": "Account", "field": "account_name"},
            {"name": "Entity", "field": "entity_name"},
            {"name": "Particulars", "field": "particulars"},
            {"name": "CB Folio", "field": "cb_folio"},
            {"name": "Debit", "field": "debit", "format": "currency"},
            {"name": "Credit", "field": "credit", "format": "currency"},
            {"name": "Running Balance", "field": "running_balance", "format": "currency"},
        ]

        def _ledger_row(r):
            rd = r.to_dict(include_calculated=True) if hasattr(r, "to_dict") else dict(r)
            row_type = rd.get("row_type")
            style = {}
            if row_type == "bf":
                style = {"backgroundColor": "#fff3cd", "fontWeight": "700"}
            elif row_type == "closing":
                style = {"backgroundColor": "#d4edda", "fontWeight": "700"}
            elif row_type == "depreciation":
                style = {"backgroundColor": "#e2e3ff"}
            elif rd.get("running_balance", 0) < 0:
                style = {"backgroundColor": "#f8d7da"}

            cells = []
            for c in ledger_columns:
                field_key = c.get("field") or c.get("name") or ""
                val = _display_value(field_key, rd)
                fmt = c.get("format")
                if fmt in _FIELD_FORMATTERS and val is not None:
                    val = _FIELD_FORMATTERS[fmt](val)
                elif val is None:
                    val = "—"
                elif isinstance(val, (date, datetime)):
                    val = _format_datetime(val)
                elif isinstance(val, (Decimal, float)):
                    val = f"₹{float(val):,.2f}"
                elif isinstance(val, str):
                    val = _humanize_string(val)
                else:
                    val = str(val)
                cells.append(html.Td(val, style={
                    "fontSize": "12px", "verticalAlign": "middle", "padding": "6px 8px",
                }))
            return html.Tr(cells, style=style)

        header_cells = []
        for c in ledger_columns:
            header_cells.append(html.Th(c["name"], style={
                "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
                "padding": "8px",
            }))

        body_rows = [_ledger_row(r) for r in (ledger_rows or [])]
        if not body_rows:
            body_rows = [html.Tr(html.Td(
                html.Div([
                    html.I(className="fas fa-inbox me-2",
                           style={"color": "#ccc", "fontSize": "20px"}),
                    html.Div("No ledger entries found",
                             style={"color": "#aaa", "fontSize": "13px",
                                    "marginTop": "4px"}),
                ], className="text-center", style={"padding": "16px 0"}),
                colSpan=len(ledger_columns),
            ))]

        ledger_table = dbc.Table([
            html.Thead(html.Tr(header_cells)),
            html.Tbody(body_rows),
        ], bordered=False, hover=True, responsive=True, size="sm",
           style={"marginTop": "4px", "marginBottom": "0"})

        # FY selector + Export for ledger
        fy_opts = fy_options or []
        sel_fy = selected_fy
        ledger_header = html.Div([
            html.Div([
                html.I(className="fas fa-book me-2", style={"color": color}),
                html.Strong("Ledger", style={"fontSize": "13px"}),
                dbc.Badge(f"FY {sel_fy}-{str(sel_fy + 1)[-2:]}" if sel_fy else "—",
                          color="primary", className="ms-2",
                          style={"fontSize": "10px"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
            html.Div([
                dbc.Select(
                    id={"type": "list-fy-select", "entity": "ledger"},
                    options=[{"label": f"FY {fy}-{str(fy + 1)[-2:]}", "value": fy}
                             for fy in fy_opts],
                    value=sel_fy,
                    size="sm",
                    style={"width": "110px", "fontSize": "11px",
                           "borderRadius": "8px", "display": "inline-block"},
                ),
                dbc.Button(
                    [html.I(className="fas fa-file-excel me-1"), "Export Ledger"],
                    id={"type": "btn-fy-export", "entity": "ledger"},
                    size="sm", color="primary", outline=True,
                    disabled=(not pk_val),
                    title=("Open an account first" if not pk_val else None),
                    style={"fontSize": "11px", "borderRadius": "8px",
                           "fontWeight": "600"},
                ),
                dcc.Download(id={"type": "fy-export-trigger", "entity": "ledger"}),
            ], style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"}),
        ], style={"padding": "10px 16px",
                   "background": "linear-gradient(180deg,rgba(255,255,255,0.85),rgba(248,251,255,0.95))"})

        ledger_section = html.Div([
            ledger_header,
            html.Div(ledger_table, style={"overflowX": "auto", "maxHeight": "420px",
                                          "overflowY": "auto", "padding": "0 16px 12px"}),
        ], style={
            "borderRadius": "16px",
            "border": "1px solid rgba(255,255,255,0.65)",
            "boxShadow": "0 10px 30px rgba(15,23,42,0.08)",
            "overflow": "hidden",
            "marginTop": "16px",
        })

    # ── Action buttons filtered by role ─────────────────────────────────
    action_btns = []
    for act in (actions or []):
        act_id = act.get("action_id", "")
        act_roles = act.get("roles")
        if act_roles and role not in act_roles:
            continue
        if act_id == "edit" and "edit" not in allowed:
            continue
        if act_id == "delete" and "delete" not in allowed:
            continue
        act_label = act["label"]
        act_color = act.get("color", "primary")
        act_icon = act.get("icon", "fa-bolt")
        action_btns.append(dbc.Button(
            [html.I(className=f"fas {act_icon} me-2"), act_label],
            id={"type": "profile-action", "entity": entity, "pk": str(pk_val),
                "action": act_id, "target": act.get("target_card") or ""},
            n_clicks=0, color=act_color, size="sm",
            className="me-2 mb-2",
            style={"borderRadius": "10px", "fontWeight": "600"},
        ))

    return html.Div([
        html.Div(
            html.Div([
                html.Div([
                    html.Div(
                        html.I(className=f"fas {icon}",
                               style={"color": "#fff", "fontSize": "16px"}),
                        style={
                            "width": "38px", "height": "38px",
                            "borderRadius": "10px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "12px",
                        },
                    ),
                    html.Div([
                        html.Strong(title, style={"fontSize": "14px"}),
                        html.Div(f"ID: {pk_val}",
                                 style={"fontSize": "11px", "color": "#999"}),
                    ]),
                ], style={"display": "flex", "alignItems": "center"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
            html.Div(
                text_cells,
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(2, 1fr)",
                    "gap": "10px",
                    "marginBottom": "14px",
                },
            ) if text_cells else None,
            html.Div(ledger_section) if ledger_section else None,
            html.Div([
                html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
                html.Div(action_btns,
                         style={"display": "flex", "flexWrap": "wrap",
                                "gap": "6px"}),
            ]) if action_btns else None,
        ], style={"padding": "16px", "maxHeight": "620px",
                  "overflowY": "auto"}),
    ], style={
        "borderRadius": "16px", "border": f"1px solid {color}22",
        "boxShadow": f"0 10px 30px {color}18",
        "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
        "backdropFilter": "blur(12px)", "overflow": "hidden",
    })


# ════════════════════════════════════════════════════════════════════════════
# FORM CARD RENDERER
# ════════════════════════════════════════════════════════════════════════════

def render_form_card(card_id: str, title: str, icon: str,
                     entity: str, fields: list[dict],
                     submit_label: str = "Save",
                     prefill: dict | None = None,
                     color: str = "#17976e",
                     society_id: int | None = None,
                     role: str | None = None) -> html.Div:
    from app.dash_apps.drilldown.registry import to_plural
    prefill = dict(prefill or {})
    if not prefill.get("id"):
        # New-entry form (no existing row id) — layer _NEW_FORM_DEFAULTS
        # (schema_introspect.py) under whatever the caller already supplied,
        # so e.g. events.open_to defaults to "all" and asset disposal
        # fields default to their at-rest values, without ever overwriting
        # an explicit profile-scoped prefill the caller set intentionally.
        from app.dash_apps.drilldown.schema_introspect import _NEW_FORM_DEFAULTS
        for k, v in _NEW_FORM_DEFAULTS.get(to_plural(entity), {}).items():
            prefill.setdefault(k, v)
    entity_plural = to_plural(entity)
    fields = [f for f in fields if _field_visible(entity_plural, f.get("id"), role or "admin")]

    # Apply field_config visibility rules
    try:
        from app.utils.field_config import is_visible as fc_visible, get_tooltip, get_default
        fields = [f for f in fields if fc_visible(entity_plural, f.get("id"), role or "admin")]
    except ImportError:
        pass

    # Owner's self-service "Raise Concern" form shares its schema-driven
    # apartment_id field with Admin's "pick any flat" picker (see
    # _concern_wait_banner's docstring above) — that field is an ordinary
    # FK dropdown with no built-in role restriction, so an apartment-role
    # user could otherwise change it away from their own flat. The actual
    # value is always pinned server-side regardless (handle_form_submit in
    # drilldown_callbacks.py), but showing an editable picker that doesn't
    # do anything would just be confusing, so it's hidden here and replaced
    # with a short locked-flat note instead.
    _owner_locked_apartment_field = (
        entity_plural == "concerns" and (role or "admin") == "apartment"
    )
    if _owner_locked_apartment_field:
        fields = [f for f in fields if f.get("id") != "apartment_id"]

    # The society 'plan' is owned by the platform (master): a society admin can
    # see it on the list/profile (rendered read-only there) but must NOT change
    # it from the Edit form — plan changes are a master-only billing action.
    if entity == "society" and prefill.get("id") and (role or "admin") != "master":
        fields = [f for f in fields if f.get("id") != "plan"]

    # A "role"-mode drill-in field (e.g. receipts.entity_id + receipts.role)
    # sets BOTH columns from one tap in the picker modal — the sibling role
    # column would otherwise still render as its own plain CHECK-options
    # select, letting it drift out of sync with the picker's choice. Hide
    # it here; its value travels as a form-field-hidden input alongside the
    # drill-in field itself (see the "drillin" branch below).
    for f in fields:
        if f.get("type") == "drillin" and (f.get("drillin") or {}).get("mode") == "role":
            _role_fid = f["drillin"]["role_field"]
            fields = [x for x in fields if x.get("id") != _role_fid]
            break

    form_rows = [
          dcc.Input(id={"type":"form-entity-pk","entity":entity},
                    type="hidden", value=str(prefill.get("id",""))),
      ]

    # ── Universal Entity Banner ──────────────────────────────────────────────────
    banner_text = _ENTITY_BANNERS.get(entity)
    if banner_text:
        form_rows.append(dbc.Alert(
            [
                html.I(className="fas fa-info-circle me-2"),
                banner_text
            ],
            color="info",
            style={"fontSize": "12px", "padding": "8px 12px", "borderRadius": "8px", "marginBottom": "14px"}
        ))

    if _owner_locked_apartment_field and not prefill.get("id"):
        form_rows.append(dbc.Alert(
            [html.I(className="fas fa-lock me-2"),
             "This concern will be raised for your own flat."],
            color="secondary",
            style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px"},
        ))

    # ── Concern QR — Edit form only, never New (concern has no id yet, and
    # qr_payload isn't generated until _save_concern's INSERT completes) ──
    if entity == "concern" and prefill.get("id"):
        try:
            from app.services.qr_service import generate_qr_code
            qr_society_id = prefill.get("society_id") or society_id
            qr_img, qr_payload = generate_qr_code(qr_society_id, "CON", prefill["id"])
            if qr_img:
                form_rows.append(html.Div([
                    html.Div([
                        html.I(className="fas fa-qrcode",
                               style={"color": "#aaa", "fontSize": "10px", "marginRight": "5px"}),
                        html.Span("Concern QR", style={"color": "#7d8ea3", "fontSize": "10px",
                                                        "fontWeight": "600", "textTransform": "uppercase"}),
                    ], style={"marginBottom": "5px"}),
                    html.Img(src=qr_img, style={
                        "maxWidth": "140px", "maxHeight": "140px", "borderRadius": "8px",
                        "border": "1px solid rgba(0,0,0,0.08)", "objectFit": "contain",
                        "background": "#fff", "padding": "4px", "display": "block",
                    }),
                    html.Div(qr_payload, style={
                        "fontSize": "10px", "color": "#7d8ea3",
                        "fontFamily": "monospace", "marginTop": "4px",
                    }),
                ], style={
                    "marginBottom": "14px", "padding": "10px",
                    "background": "rgba(248,251,255,0.7)", "borderRadius": "10px",
                    "border": "1px solid rgba(200,215,235,0.4)",
                }))
        except Exception as e:
            print(f"⚠️  concern QR render failed on edit form: {e}")

    for f in fields:
        fid      = f["id"]
        pre_val  = prefill.get(fid)
        ftype    = f.get("type", "text")
        required = f.get("required", False)
        label_txt = f["label"] + (" *" if required else "")

        # Apply pre-fill from field_config if no explicit prefill
        if pre_val is None:
            try:
                from app.utils.field_config import get_default as fc_default
                pre_val = fc_default(entity_plural, fid)
            except ImportError:
                pass

        # Build label with tooltip
        label_children = [label_txt]
        try:
            from app.utils.field_config import get_tooltip as fc_tooltip, is_editable as fc_editable
            tooltip_text = fc_tooltip(entity_plural, fid)
            if tooltip_text:
                label_children.append(
                    html.Span("?", className="field-tooltip-icon", **{"data-tooltip": tooltip_text})
                )
            # Apply read-only if not editable
            if not fc_editable(entity_plural, fid, role or "admin"):
                ftype = "readonly"
        except ImportError:
            pass

        if ftype == "select" and f.get("dynamic_options"):
            from app.dash_apps.drilldown.schema_introspect import load_dynamic_select_options
            opts = load_dynamic_select_options(f["dynamic_options"], society_id)
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=opts, value=pre_val,
                placeholder=f"Select {f['label']}…",
                clearable=not required,
                style={"fontSize": "13px"},
            )
        elif ftype == "select" and f.get("options_from"):
            from app.dash_apps.drilldown.schema_introspect import load_fk_options
            opts = load_fk_options(f["options_from"])
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=opts, value=pre_val,
                placeholder=f"Select {f['label']}…",
                clearable=not required,
                style={"fontSize": "13px"},
            )
        elif ftype == "select":
            # Support both plain string options (existing behavior — e.g.
            # boolean true/false, CHECK-constraint values) and explicit
            # {"label":..., "value":...} dict options (added for
            # events.open_to via _EXPLICIT_SELECT_OPTIONS).
            opts = [
                o if isinstance(o, dict) else {"label": o.title(), "value": o}
                for o in f.get("options", [])
            ]
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=opts, value=pre_val,
                placeholder=f"Select {f['label']}…",
                clearable=not required,
                style={"fontSize": "13px"},
            )
        elif ftype == "textarea":
            ctrl = dbc.Textarea(
                id={"type": "form-field", "entity": entity, "field": fid},
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"], rows=3,
                style={"fontSize": "13px", "borderRadius": "10px"},
            )
        elif ftype == "date":
            # Native calendar picker (was a manually-typed DD/MM/YYYY text
            # field). Safe swap: handle_form_submit's dd/mm/yyyy→iso
            # normalisation (drilldown_callbacks.py) already runs every
            # string field through _parse_date_entry, which has always
            # accepted "%Y-%m-%d" — exactly what a native date input
            # submits — so no backend change was needed.
            _iso_pre = _parse_date_entry(pre_val) if isinstance(pre_val, str) else None
            if not _iso_pre and pre_val not in (None, ""):
                # pre_val may already be a date/datetime object (edit-form
                # prefill from the DB row) rather than a typed string.
                _iso_pre = _parse_date_entry(_format_date_entry(pre_val))
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type="date",
                value=_iso_pre or date.today().isoformat(),
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

        elif ftype == "time":
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type="time",
                value=str(pre_val) if pre_val else "",
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

        elif ftype == "drillin":
            # Tap-through card picker (New Receipt/Expense/Concern/… entity
            # selection) — replaces a raw numeric entity_id input or a long
            # flat FK dropdown. See app/dash_apps/drilldown/drillin.py and
            # drillin_callbacks.py for the modal + its wiring.
            from app.dash_apps.drilldown.drillin import (
                role_target_table, drillin_label_for, TABLE_ICON_COLOR,
            )
            drillin_cfg = f.get("drillin") or {}
            d_mode = drillin_cfg.get("mode")
            role_fid = drillin_cfg.get("role_field") if d_mode == "role" else None
            role_val = prefill.get(role_fid) if role_fid else None

            target_table = None
            if d_mode == "role" and role_val:
                _tt = role_target_table(drillin_cfg, role_val)
                target_table = _tt["table"] if _tt else None
            elif d_mode == "single":
                target_table = drillin_cfg.get("table")

            picked_label = None
            if pre_val and target_table:
                picked_label = drillin_label_for(target_table, pre_val, society_id)

            icon, color = (TABLE_ICON_COLOR.get(target_table, ("fas fa-hand-pointer", "#7d8ea3"))
                           if target_table else ("fas fa-hand-pointer", "#7d8ea3"))
            role_label = (drillin_cfg.get("roles", {}).get(role_val) or {}).get("label") if role_val else None
            if picked_label:
                display_text = f"{role_label + ': ' if role_label and d_mode == 'role' else ''}{picked_label}"
            else:
                display_text = "Tap to select…"

            hidden_inputs = [
                dcc.Input(
                    id={"type": "form-field-hidden", "entity": entity, "field": fid},
                    type="hidden", value=str(pre_val) if pre_val else "",
                ),
            ]
            if role_fid:
                hidden_inputs.append(dcc.Input(
                    id={"type": "form-field-hidden", "entity": entity, "field": role_fid},
                    type="hidden", value=str(role_val) if role_val else "",
                ))

            ctrl = html.Div([
                *hidden_inputs,
                html.Div([
                    html.I(className=f"{icon} me-2", style={"color": color}),
                    html.Span(display_text, style={
                        "flex": "1",
                        "color": "#2a3b52" if picked_label else "#9aa7b8",
                        "fontWeight": "600" if picked_label else "400",
                    }),
                    html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                ], id={"type": "drillin-trigger", "entity": entity, "field": fid},
                   n_clicks=0,
                   style={
                       "display": "flex", "alignItems": "center",
                       "padding": "10px 12px", "borderRadius": "10px",
                       "border": "1px solid #dbe3ee", "background": "#fff",
                       "cursor": "pointer", "fontSize": "13px",
                   }),
            ])

        elif ftype == "readonly":
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                value=str(pre_val) if pre_val is not None else "",
                disabled=True,
                style={"fontSize": "13px", "borderRadius": "10px",
                       "background": "#f5f7fa"},
            )
        elif ftype == "image_upload":
            cam_vid_id   = f"cam-vid-{entity}-{fid}"
            cam_cvs_id   = f"cam-cvs-{entity}-{fid}"
            cam_snap_id  = f"cam-snap-{entity}-{fid}"
            cam_stop_id  = f"cam-stop-{entity}-{fid}"
            cam_btn_id   = f"cam-btn-{entity}-{fid}"
            prev_img_id  = f"cam-prev-{entity}-{fid}"
            hidden_marker = f'"entity": "{entity}", "field": "{fid}"'
  
            _btn_base = {
                "display":       "inline-flex",
                "alignItems":    "center",
                "justifyContent":"center",
                "cursor":        "pointer",
                "userSelect":    "none",
                "borderRadius":  "8px",
                "fontSize":      "12px",
                "fontWeight":    "600",
                "padding":       "6px 14px",
                "border":        "none",
            }
  
            ctrl = [
                html.Div([
                    dcc.Upload(
                        id={"type": "form-upload", "entity": entity,
                            "field": fid},
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-1"),
                            "Upload / Drop",
                        ], style={"fontSize": "12px"}),
                        style={
                            "flex":         "1",
                            "height":       "42px",
                            "lineHeight":   "42px",
                            "borderWidth":  "2px",
                            "borderStyle":  "dashed",
                            "borderRadius": "10px",
                            "textAlign":    "center",
                            "borderColor":  "#667eea",
                            "background":   "rgba(102,126,234,0.04)",
                            "cursor":       "pointer",
                            "color":        "#667eea",
                            "minWidth":     "110px",
                        },
                        multiple=False, accept="image/*",
                    ),
  
                    html.Div(
                        [html.I(className="fas fa-camera me-1"), "Camera"],
                        id=cam_btn_id,
                        **{
                            "data-cam-video":  cam_vid_id,
                            "data-cam-canvas": cam_cvs_id,
                            "data-cam-snap":   cam_snap_id,
                            "data-cam-stop":   cam_stop_id,
                        },
                        style={
                            **_btn_base,
                            "flex":       "0 0 auto",
                            "height":     "42px",
                            "border":     "2px dashed #1abc9c",
                            "background": "rgba(26,188,156,0.06)",
                            "color":      "#1abc9c",
                            "padding":    "0 14px",
                        },
                    ),
                ], style={"display": "flex", "gap": "8px",
                          "marginBottom": "8px"}),
  
                html.Video(
                    id=cam_vid_id,
                    autoPlay=True, muted=True,
                    style={
                        "width":         "100%",
                        "maxHeight":     "200px",
                        "borderRadius":  "10px",
                        "display":       "none",
                        "objectFit":     "cover",
                        "background":    "#111",
                        "marginBottom":  "6px",
                    },
                ),
                html.Canvas(id=cam_cvs_id, style={"display": "none"}),
  
                html.Div([
                    html.Div(
                        [html.I(className="fas fa-circle me-1"), "Snap"],
                        id=cam_snap_id,
                        **{
                            "data-cam-video":     cam_vid_id,
                            "data-cam-canvas":    cam_cvs_id,
                            "data-cam-stop":      cam_stop_id,
                            "data-preview-id":    prev_img_id,
                            "data-hidden-marker": hidden_marker,
                        },
                        style={
                            **_btn_base,
                            "background": "#de5c52",
                            "color":      "#fff",
                            "display":    "none",
                        },
                    ),
                    html.Div(
                        [html.I(className="fas fa-stop me-1"), "Stop"],
                        id=cam_stop_id,
                        **{
                            "data-cam-video": cam_vid_id,
                            "data-cam-btn":   cam_btn_id,
                            "data-cam-snap":  cam_snap_id,
                        },
                        style={
                            **_btn_base,
                            "background": "#7d8ea3",
                            "color":      "#fff",
                            "display":    "none",
                        },
                    ),
                ], style={"display": "flex", "gap": "6px",
                          "justifyContent": "center",
                          "marginBottom":   "6px"}),
  
                dcc.Input(
                    id={"type": "form-field-hidden", "entity": entity,
                        "field": fid},
                    type="hidden", value=pre_val or "",
                ),
  
                html.Div(
                    id={"type": "image-preview", "entity": entity,
                        "field": fid},
                    style={"marginTop": "4px"},
                ),
  
                html.Img(
                    id=prev_img_id,
                    style={
                        "display":      "none",
                        "maxWidth":     "100%",
                        "maxHeight":    "160px",
                        "borderRadius": "8px",
                        "marginTop":    "6px",
                        "border":       "1px solid #ddd",
                    },
                ),
            ]
        elif ftype == "account_dropdown_event_ticket":
            # Only NULL, or the "Event Ticket" (2319) header itself, or one
            # of its direct children (e.g. "Holi" = 23191) — an event isn't
            # allowed to post to an unrelated account.
            _acc_opts = [{"label": "— None —", "value": ""}]
            if society_id:
                try:
                    _rows = db._execute(
                        "SELECT id, name FROM accounts "
                        "WHERE society_id=%s AND (id=2319 OR parent_account_id=2319) "
                        "ORDER BY (id=2319) DESC, name",
                        (society_id,),
                        fetch_all=True,
                    ) or []
                    _acc_opts += [
                        {"label": f"{r['id']} — {r['name']}", "value": r["id"]}
                        for r in _rows
                    ]
                except Exception as _e:
                    print(f"⚠️  event ticket account dropdown load error: {_e}")
            _pre_acc = int(pre_val) if pre_val not in (None, "", "None") else None
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=_acc_opts,
                value=_pre_acc,
                placeholder="Select Event Ticket account (optional)…",
                clearable=False,
                style={"fontSize": "13px"},
                optionHeight=40,
            )
        elif ftype in ("account_dropdown_receipt", "account_dropdown_expense"):
            # Cr accounts for receipts, Dr accounts for expenses
            _drcr = "Cr" if ftype == "account_dropdown_receipt" else "Dr"
            _ph   = "Select income account…" if _drcr == "Cr" else "Select expense account…"
            _acc_opts = []
            if society_id:
                try:
                    _rows = db._execute(
                        "SELECT id, COALESCE(tab_name,'') AS tab_name, name "
                        "FROM accounts "
                        "WHERE society_id=%s AND drcr_account=%s "
                        "ORDER BY tab_name, name",
                        (society_id, _drcr),
                        fetch_all=True,
                    ) or []
                    _acc_opts = [
                        {
                            "label": f"{r['id']} — {r['tab_name']} — {r['name']}",
                            "value": r["id"],
                        }
                        for r in _rows
                    ]
                except Exception as _e:
                    print(f"⚠️  account dropdown load error: {_e}")
            # Resolve pre_val: could be an int id already, or None
            _pre_acc = int(pre_val) if pre_val not in (None, "", "None") else None
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=_acc_opts,
                value=_pre_acc,
                placeholder=_ph,
                clearable=False,
                style={"fontSize": "13px"},
                optionHeight=40,
            )
        else:
            extra_props = {"step": "any"} if ftype == "number" else {}
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type=ftype,
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"],
                style={"fontSize": "13px", "borderRadius": "10px"},
                **extra_props
            )

        _row = dbc.Row([
            dbc.Col(
                dbc.Label(label_children,
                          style={"fontSize": "12px", "fontWeight": "500",
                                 "color": "#555"}),
                width=4, style={"paddingTop": "6px"},
            ),
            dbc.Col(ctrl, width=8),
        ], className="mb-2")

        # Payment-mode-conditional visibility: cheque_no only matters for
        # mode='cheque', transaction_id only for the reference-number modes
        # (upi/card/bank/crypto) — cash needs neither. Wrapped (rather than
        # left always-visible) so Receipts/Expenses don't ask for a cheque
        # number when the payer chose UPI, or vice versa. Initial display
        # is computed server-side from the current/prefilled mode (avoids
        # a flash of the wrong fields on load); mode_conditional_
        # callbacks.py's clientside callback keeps it in sync as the user
        # changes the Mode dropdown, entity-scoped via MATCH so it only
        # ever touches receipts/expenses rows.
        if fid in ("cheque_no", "transaction_id") and entity_plural in ("receipts", "expenses"):
            _cur_mode = prefill.get("mode")
            if _cur_mode is None:
                try:
                    from app.utils.field_config import get_default as _fc_default
                    _cur_mode = _fc_default(entity_plural, "mode")
                except ImportError:
                    _cur_mode = "cash"
            _visible = (
                (fid == "cheque_no" and _cur_mode == "cheque") or
                (fid == "transaction_id" and _cur_mode in ("upi", "card", "bank", "crypto"))
            )
            form_rows.append(html.Div(
                _row,
                id={"type": "mode-conditional-row", "entity": entity, "field": fid},
                style={} if _visible else {"display": "none"},
            ))
        else:
            form_rows.append(_row)

    # ── Expense-form TDS autofill plumbing (2026-09) ────────────────────────
    # A dcc.Store to carry the server-computed TDS suggestion (tds_pct,
    # tds_section, pan_captured, pan_warning, …) — see expense_tds_autofill()
    # in drilldown_callbacks.py — plus a banner placeholder right under the
    # entity_id drill-in field that expense_tds_pan_banner() fills in with a
    # PAN warning when TDS applies and no PAN is on file for the picked
    # vendor. Both previously had nowhere to render, so the computed
    # pan_warning payload never reached the UI.
    if entity_plural == "expenses":
        form_rows.append(dcc.Store(id={"type": "tds-autofill", "entity": "expense"}, data={}))
        form_rows.append(html.Div(id={"type": "tds-pan-banner", "entity": "expense"}))

    # Filter out None (the PK input was only added once)
    form_rows = [r for r in form_rows if r is not None]

    # Build form header
    form_header = html.Div(
        html.Div([
            html.Div(
                html.I(className=f"fas {icon}",
                       style={"color": "#fff", "fontSize": "15px"}),
                style={
                    "width": "34px", "height": "34px",
                    "borderRadius": "9px",
                    "background": f"linear-gradient(135deg,{color},{color}aa)",
                    "display": "flex", "alignItems": "center",
                    "justifyContent": "center",
                    "marginRight": "10px", "flexShrink": "0",
                },
            ),
            html.Strong(title, style={"fontSize": "13px"}),
        ], style={"display": "flex", "alignItems": "center"}),
        style={"padding": "10px 16px",
               "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
    )

    # Build form banner (user-friendly help text)
    form_banner = None
    try:
        from app.utils.field_config import get_banner
        mode = "edit" if prefill.get("id") else "new"
        banner_text = get_banner(entity_plural, mode)
        if banner_text:
            form_banner = html.Div(
                banner_text,
                className="form-banner",
            )
    except ImportError:
        pass

    return html.Div([
        form_header,
        form_banner,
        html.Div([
            html.Div([
                html.Div(form_rows),
                dbc.Button(
                    [html.I(className="fas fa-check me-2"), submit_label],
                    id={"type": "form-submit", "entity": entity,
                        "card_id": card_id},
                    n_clicks=0, color="success", className="mt-3 w-100",
                    style={"borderRadius": "12px", "fontWeight": "700"},
                ),
            ], style={"flex": "1", "minWidth": "260px"}),
            _payment_qr_banner(entity_plural, society_id, prefill),
            _concern_wait_banner(entity_plural, prefill),
            _compliance_rules_banner(entity_plural, _resolve_society_state(prefill, society_id)),
        ], style={"padding": "16px", "maxHeight": "520px",
                  "overflowY": "auto", "display": "flex",
                  "flexWrap": "wrap", "gap": "16px", "alignItems": "flex-start"}),
    ], style={
        "borderRadius": "16px", "border": f"1px solid {color}22",
        "boxShadow": f"0 10px 30px {color}18",
        "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
        "overflow": "hidden",
    })


# Generic (schema-driven) entities whose "New" form collects money that is
# credited to the society, and should therefore show the payment QR so the
# payer can scan-and-pay right there. "events" is included because an event's
# account_id can point at an income/Cr account (e.g. an "Event
# Ticket" account collecting entry fees) — see _account_is_credit() below
# for the narrower per-record check.
_QR_BANNER_ENTITIES = {"receipts", "events"}


def _concern_wait_banner(entity_plural: str, prefill: dict) -> html.Div | None:
    """
    Shows a short heads-up on the NEW concern form (Admin's 'Flat No' picker
    and Owner's self-service form both funnel through form_concern_new) so
    the person raising it knows the next step is bidding, not an instant fix.
    Not shown on Edit (prefill has an "id").
    """
    if entity_plural != "concerns" or prefill.get("id"):
        return None
    return dbc.Alert(
        [
            html.I(className="fas fa-hourglass-half me-2"),
            "After submitting, please wait for bids from vendors/security. Once bids arrive, the Invite and Assign buttons on the concern profile will let you pick a candidate.",
        ],
        color="info",
        style={"fontSize": "13px", "fontWeight": "600", "flex": "0 0 auto", "maxWidth": "260px"},
    )


def _account_is_credit(acc_id, society_id) -> bool:
    """True if accounts.drcr_account for acc_id is 'Cr' (money coming IN
    to the society), False otherwise (including when unset/unknown)."""
    if not acc_id or not society_id:
        return False
    try:
        row = db._execute(
            "SELECT drcr_account FROM accounts WHERE id = %s AND society_id = %s",
            (acc_id, society_id), fetch_one=True,
        )
        return (row or {}).get("drcr_account") == "Cr"
    except Exception as e:
        print(f"_account_is_credit error: {e}")
        return False


def render_payment_qr_widget(society_id, label: str = "Scan to pay the society") -> html.Div | None:
    """
    Renders the society's payment_qr image (societies.payment_qr), right-
    flex-floated, for use on any form that collects money credited to the
    society (New Receipt, Pay Dues, Buy Pass, Event-with-income-account,
    etc). Returns None (renders nothing) if the society hasn't uploaded a
    QR code yet.
    """
    if not society_id:
        return None
    try:
        row = db._execute(
            "SELECT payment_qr FROM societies WHERE id = %s",
            (society_id,), fetch_one=True,
        )
        qr_path = (row or {}).get("payment_qr")
        if not qr_path:
            return None
        qr_url = get_image_url(qr_path, society_id, "society", society_id)
        return html.Div([
            html.Div(label, style={
                "fontSize": "12px", "fontWeight": "700", "color": "#15304f",
                "textAlign": "center", "marginBottom": "8px",
            }),
            html.Img(
                src=qr_url,
                alt="Payment QR",
                style={
                    "display": "block", "margin": "0 auto 14px", "maxWidth": "180px",
                    "minHeight": "120px", "borderRadius": "10px",
                    "border": "1px solid #e2e8f0", "background": "#f4f6f9",
                    "objectFit": "contain",
                },
            ),
        ], style={"flex": "0 0 auto", "maxWidth": "220px", "float": "right"})
    except Exception as e:
        print(f"render_payment_qr_widget error: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# COMPLIANCE SETTINGS BANNER — plain-language rule reference for each toggle
# on society_compliance_settings, so the person setting them doesn't have to
# already know CHS/RWA tax law to set them correctly. General information
# only, not legal/tax advice — every section says so, and points at primary
# sources (CBIC, Income Tax Dept, state statutes) rather than asserting a
# definitive answer, since several of these (GST-on-funds treatment, TDS
# thresholds, state bye-law rates) are genuinely contested, revised
# periodically, or state-specific.
#
# External links are stored in kpi_rule_links (DB) and fetched per-category
# at render time, scoped to the society's state + 'ALL'. Admins can add /
# retire links without a code deploy via the KPI Rule Links admin page.
# ════════════════════════════════════════════════════════════════════════════

def _compliance_rules_banner(entity_plural: str, society_state: str = "ALL") -> html.Div | None:
    if entity_plural != "compliance_settings":
        return None

    from app.services.kpi_rule_links_service import get_links_for_categories, get_categories

    categories = get_categories()
    cat_keys = list(categories.keys())

    links_by_cat = get_links_for_categories(cat_keys, state=society_state)

    def _rule_block(title: str, body: list, cat_key: str) -> html.Div:
        links = links_by_cat.get(cat_key, [])
        link_elements = [
            html.A(label, href=url, target="_blank", rel="noopener noreferrer",
                   style={"fontSize": "11px", "marginRight": "12px",
                          "color": COLORS["info"], "textDecoration": "none"})
            for label, url in [(lk.label, lk.url) for lk in links]
        ]
        return html.Div([
            html.Div(title, style={"fontWeight": "700", "fontSize": "12.5px",
                                    "color": COLORS["primary"], "marginBottom": "3px"}),
            html.Div(body, style={"fontSize": "12px", "color": "#3a4a5c",
                                   "lineHeight": "1.5", "marginBottom": "4px"}),
            html.Div(link_elements) if link_elements else None,
        ], style={"marginBottom": "14px", "paddingBottom": "10px",
                   "borderBottom": "1px solid rgba(0,0,0,0.06)"})

    return html.Div([
        dbc.Alert([
            html.I(className="fas fa-scale-balanced me-2"),
            html.Strong("General information, not legal or tax advice. "),
            "These toggles change how the system calculates GST, TDS, and fund "
            "contributions — confirm each choice against your society's own "
            "registered bye-laws and your CA before relying on it for a filing.",
        ], color="warning", style={"fontSize": "12px", "padding": "8px 12px",
                                     "marginBottom": "12px"}),

        _rule_block(
            categories.get("sinking_fund", "Sinking Fund / Repair Fund Rate Basis"),
            [
                "Statutory minimums vary by state — Maharashtra's Model Bye-Laws "
                "set 0.25% of construction cost/year for the Sinking Fund and 0.75% "
                "for the Repair & Maintenance Fund, while UP's Apartment Rules 2011 "
                "set no fixed percentage (the rate is whatever the AOA's own bye-laws "
                "or General Body decide). Cooperative societies are a State subject — "
                "check your own state's Act and your society's registered bye-laws.",
            ],
            "sinking_fund",
        ),

        _rule_block(
            categories.get("fund_gst", "Fund GST Exempt"),
            [
                "Whether Sinking/Repair Fund collections sit outside GST at all, "
                "or are treated like any other RWA collection subject to the same "
                "₹7,500/member/month threshold below, is genuinely unsettled — "
                "CBIC's circular treats them as consideration for future services "
                "in some readings, contested in others. Default here is exempt; "
                "verify with a GST practitioner before filing on that basis.",
            ],
            "fund_gst",
        ),

        _rule_block(
            categories.get("fund_interest", "Fund Charges Interest"),
            [
                "Whether overdue Sinking/Repair Fund contributions accrue the "
                "same late-payment interest as overdue maintenance is a bye-law "
                "question, not a fixed rule — check what your society's own "
                "registered bye-laws specify.",
            ],
            "fund_interest",
        ),

        _rule_block(
            categories.get("gst_registered", "GST Registered / GSTIN / GST Filing Cadence"),
            [
                "GST applies only when BOTH hold: society turnover exceeds ₹20 "
                "lakh/year AND a member's own monthly maintenance exceeds ₹7,500. "
                "Both conditions must be crossed — one alone doesn't trigger it. "
                "Per CBIC's Circular 109/28/2019-GST, once a member's charge "
                "crosses ₹7,500, GST applies to the ENTIRE amount, not just the "
                "excess (a Madras HC ruling has gone the other way on this point — "
                "treat it as contested, not settled). Filing cadence (monthly vs. "
                "QRMP/quarterly) is chosen at GST registration, not decided by "
                "this system.",
            ],
            "gst_registered",
        ),

        _rule_block(
            categories.get("tds_no_pan", "TDS No-PAN Action (warn vs. block)"),
            [
                "Under Section 206AA, TDS can still be deducted from a vendor "
                "with no PAN on file — at the higher no-PAN rate (typically 20%) "
                "rather than the normal Section 194C/194J rate. That means "
                "\"warn\" is usually the right default: blocking the payment isn't "
                "legally required, and many small vendors (individual plumbers, "
                "local contractors) genuinely have no PAN. Current thresholds — "
                "194C: ₹30,000/bill or ₹1,00,000/year; 194J: recently raised to "
                "₹50,000/year (from ₹30,000) — are revised periodically, so check "
                "the official page rather than relying on a number fixed in this "
                "banner.",
            ],
            "tds_no_pan",
        ),

        _rule_block(
            categories.get("rera", "RERA"),
            [
                "The Real Estate (Regulation and Development) Act, 2016 operates "
                "alongside state apartment/cooperative laws. Homeowners can approach "
                "the state RERA authority for legal action on matters like builder "
                "maintenance obligations even where the state's own dispute-resolution "
                "mechanisms apply.",
            ],
            "rera",
        ),

        _rule_block(
            categories.get("apartment_act", "Apartment Act / AOAs"),
            [
                "State-specific apartment acts (e.g., UP Apartment Act 2010) regulate "
                "construction, ownership, and maintenance of apartment buildings with "
                "four or more units, mandating formation of an Apartment Owners "
                "Association (AOA). An AOA under such an Act isn't itself the "
                "registration mechanism — the Registrar of Societies registers it as "
                "a society under the Societies Registration Act 1860.",
            ],
            "apartment_act",
        ),

        _rule_block(
            categories.get("cooperative_act", "Cooperative Societies Act"),
            [
                "The older, parallel registration route for cooperative housing "
                "societies specifically (as opposed to apartment/condominium-style "
                "AOAs). Each state has its own Cooperative Societies Act providing "
                "for registration, operation, and management of cooperative societies.",
            ],
            "cooperative_act",
        ),

        _rule_block(
            categories.get("income_tax_mutuality", "Income Tax — Mutuality Principle"),
            [
                "Mutual (member-sourced: maintenance, parking, transfer fees) vs. "
                "non-mutual (tower rent, hall rental, FD interest) income "
                "classification is a judicially-developed doctrine (Principle of "
                "Mutuality), not a single numbered section — get this one checked "
                "against your society's actual income mix, since it determines "
                "what's taxable at all.",
            ],
            "income_tax_mutuality",
        ),
    ], style={
        "background": "linear-gradient(180deg,rgba(255,255,255,0.97),rgba(248,251,255,0.92))",
        "border": f"1px solid {COLORS['info']}33",
        "borderRadius": "12px", "padding": "14px 16px", "marginTop": "8px",
        "maxWidth": "420px", "maxHeight": "480px", "overflowY": "auto",
    })


def _payment_qr_banner(entity_plural: str, society_id, prefill: dict) -> html.Div | None:
    """
    Shows the society's payment_qr image (societies.payment_qr) at the top
    of NEW forms for entities that credit money to the society, so a payer
    filling it in has the scan code right there. Not shown on Edit (prefill
    has an "id").

    - receipts: always shown on New (every receipt records money in).
    - events: shown on New only when account_id already resolves to
      a Cr (income) account, e.g. an "Event Ticket" account — an event
      wired to an expense account doesn't collect money, so no QR.
    """
    if prefill.get("id") or not society_id or entity_plural not in _QR_BANNER_ENTITIES:
        return None
    if entity_plural == "events":
        acc_id = prefill.get("account_id")
        if not _account_is_credit(acc_id, society_id):
            return None
    return render_payment_qr_widget(society_id)

# ════════════════════════════════════════════════════════════════════════════
# BREADCRUMB RENDERER
# ════════════════════════════════════════════════════════════════════════════

def render_breadcrumb(nav_stack: list[dict]) -> html.Nav:
    items = []
    for i, entry in enumerate(nav_stack):
        is_last = i == len(nav_stack) - 1
        label = entry.get("entity_label") or entry.get("label", "?")
        if is_last:
            items.append(html.Li([
                html.I(className="fas fa-circle me-1",
                       style={"fontSize": "6px", "color": COLORS["primary"]}),
                html.Span(label, style={"fontWeight": "700"}),
            ], className="breadcrumb-item active"))
        else:
            items.append(html.Li(
                html.A(label, href="#",
                       style={"color": COLORS["primary"],
                              "textDecoration": "none"},
                       id={"type": "breadcrumb-click", "index": i},
                       n_clicks=0),
                className="breadcrumb-item",
            ))
    return html.Nav(
        html.Ol(items, className="breadcrumb",
                style={"margin": 0, "padding": 0}),
        style={
            "background": "rgba(255,255,255,0.7)",
            "backdropFilter": "blur(8px)",
            "padding": "8px 16px", "borderRadius": "12px",
            "marginBottom": "16px",
            "border": "1px solid rgba(255,255,255,0.5)",
        },
    )

# ════════════════════════════════════════════════════════════════════════════
# UTILITY
# ════════════════════════════════════════════════════════════════════════════

def model_to_display(record) -> dict:
    if hasattr(record, "to_dict"):
        return record.to_dict(include_calculated=True)
    return record if isinstance(record, dict) else {}


# ════════════════════════════════════════════════════════════════════════════
# LEDGER INDEX CARD — FY Closing Report as a tree with BF / Movement / Dep /
# Own Closing / Total Closing columns. Clicking a node opens that account's
# profile (which now includes its ledger table).
# ════════════════════════════════════════════════════════════════════════════

def render_ledger_index_card(rows: list[dict], fy_options: list[int], selected_fy: int | None,
                              society_id: int | None = None) -> html.Div:
    color = "#17976e"

    def _fy_label(fy):
        return f"{fy}-{str(fy + 1)[-2:]}"

    pills = html.Div([
        html.Div(
            _fy_label(fy),
            id={"type": "kpi-card-div", "card_id": f"kpi_fy_closing_report__{fy}"},
            n_clicks=0,
            style={
                "padding": "6px 14px", "borderRadius": "20px", "fontSize": "12px",
                "fontWeight": "700", "cursor": "pointer", "display": "inline-block",
                "marginRight": "8px", "marginBottom": "8px",
                "background": color if fy == selected_fy else "#fff",
                "color": "#fff" if fy == selected_fy else "#555",
                "border": f"1px solid {color}" if fy == selected_fy else "1px solid #e0e0e0",
            },
        )
        for fy in fy_options
    ], style={"marginBottom": "12px"})

    header = html.Div([
        html.Div([
            html.Div(html.I(className="fas fa-columns",
                            style={"color": "#fff", "fontSize": "16px"}),
                     style={"width": "38px", "height": "38px", "borderRadius": "10px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "12px"}),
            html.Div([
                html.Strong("Ledger Index", style={"fontSize": "14px"}),
                html.Div(f"FY {_fy_label(selected_fy)}" if selected_fy else "—",
                         style={"fontSize": "11px", "color": "#999"}),
            ]),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div([
            pills,
            dbc.Button(
                [html.I(className="fas fa-file-excel me-1"), "Export Ledger"],
                id={"type": "btn-fy-export", "entity": "ledger_index"},
                size="sm", color="primary", outline=True,
                style={"fontSize": "11px", "borderRadius": "8px", "fontWeight": "600"},
            ),
            dcc.Download(id={"type": "fy-export-trigger", "entity": "ledger_index"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"}),
    ], style={"padding": "12px 16px",
              "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"})

    if not rows:
        body = dbc.Alert("No accounts found for this financial year.", color="secondary",
                          style={"borderRadius": "10px"})
    else:
        tree = _build_accounts_tree(rows)

        # Single shared column template — used for the header AND every tree
        # row at every depth. Depth indentation is applied *inside* the
        # Account cell only (see `indent` below), never by shrinking a row's
        # own wrapping container, so the B/F..Dr/Cr columns land on the same
        # pixel positions as the header regardless of how deep a node is
        # nested.
        LEDGER_GRID_COLS = "2fr 1fr 1fr 1fr 1fr 1fr 0.8fr"
        LEDGER_INDENT_PX = 16  # indentation added to the Account cell per depth level

        def _node_amount(v):
            if v is None:
                return "—"
            v = float(v)
            sign = "-" if v < 0 else ""
            return f"{sign}₹{abs(v):,.2f}"

        def _render_node(node: dict) -> html.Details:
            r = node["row"]
            depth = r.get("depth") or 0
            children = node["children"]
            pk_val = str(r.get("account_id") or "0")
            display_side = r.get("display_side", "")
            total_closing = r.get("total_closing")

            label_bits = [
                html.Span(r.get("tab_name") or r.get("account_name") or "", style={"fontWeight": "700"}),
                html.Span(f"  {r.get('account_name') or ''}", style={"color": "#8a97a8", "fontSize": "11px"}),
            ]
            if r.get("has_bf"):
                label_bits.append(dbc.Badge("BF", color="info", className="ms-2",
                                             style={"fontSize": "9px"}))
            if r.get("is_depreciable"):
                label_bits.append(dbc.Badge("Dep", color="secondary", className="ms-1",
                                             style={"fontSize": "9px"}))

            side_color = "#17976e" if display_side == "Cr" else ("#c0392b" if display_side == "Dr" else "#15304f")

            # Explicit, always-rendered toggle icon (a "+"/"−" chip driven by
            # CSS via the `li-caret` class) rather than a CSS ::before marker
            # squeezed into leftover padding — that approach was getting
            # crowded out whenever a node's own padding shrank the space
            # reserved for it, making the toggle unreadable.
            caret = html.Span(className="li-caret" if children else "li-caret li-caret-leaf")

            account_cell = html.Div(
                [caret, html.Div(label_bits, style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"})],
                style={"display": "flex", "alignItems": "center",
                       "paddingLeft": f"{depth * LEDGER_INDENT_PX}px", "minWidth": 0},
            )

            row_cells = [
                account_cell,
                html.Div(_node_amount(r.get("own_bf")), style={"fontSize": "11px", "color": "#555", "textAlign": "right"}),
                html.Div(_node_amount(r.get("own_movement")), style={"fontSize": "11px", "color": "#555", "textAlign": "right"}),
                html.Div(_node_amount(r.get("depreciation_charge")), style={"fontSize": "11px", "color": "#555", "textAlign": "right"}),
                html.Div(_node_amount(r.get("own_closing")), style={"fontSize": "11px", "color": "#555", "textAlign": "right"}),
                html.Div(_node_amount(total_closing), style={"fontSize": "12px", "fontWeight": "700", "color": side_color, "textAlign": "right"}),
                html.Div(display_side, style={"fontSize": "11px", "fontWeight": "700", "color": side_color, "textAlign": "right"}),
            ]

            summary = html.Summary(
                html.Div(row_cells, style={"display": "grid", "gridTemplateColumns": LEDGER_GRID_COLS,
                                            "alignItems": "center", "columnGap": "8px", "padding": "6px 8px"}),
                id={"type": "list-row", "entity": "accounts", "pk": pk_val},
                n_clicks=0,
                className="ledger-node-summary",
            )

            body = [summary]
            if children:
                # No padding/margin/border on this wrapper — anything here
                # would shrink the available width for every descendant row
                # and throw off column alignment a little more at each
                # nesting level. All visual nesting instead comes from the
                # Account cell's own indentation above.
                body.append(html.Div([_render_node(c) for c in children]))

            return html.Details(
                body,
                open=(depth < 2),
                style={"marginBottom": "1px"},
            )

        tree_nodes = [_render_node(n) for n in tree] if tree else []

        header_row = html.Div([
            html.Div("Account", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "padding": "8px"}),
            html.Div("B/F", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
            html.Div("Movement", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
            html.Div("Dep", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
            html.Div("Own Closing", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
            html.Div("Total Closing", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
            html.Div("Dr/Cr", style={"fontWeight": "700", "fontSize": "11px", "color": "#7d8ea3", "textAlign": "right", "padding": "8px"}),
        ], style={"display": "grid", "gridTemplateColumns": LEDGER_GRID_COLS, "columnGap": "8px",
                  "borderBottom": "1px solid rgba(120,148,181,0.2)", "background": "rgba(248,251,255,0.97)"})

        body = html.Div(tree_nodes, className="ledger-index-tree", style={"padding": "8px 12px", "maxHeight": "560px", "overflowY": "auto"})

        content = html.Div([header_row, body], style={"borderTop": "1px solid rgba(120,148,181,0.2)"})

    return html.Div([
        header,
        html.Div(content if rows else body, style={"padding": "12px 16px"}),
    ], style={
        "borderRadius": "16px",
        "border": f"1px solid {color}22",
        "boxShadow": f"0 10px 30px {color}18",
        "overflow": "hidden",
    })


# ════════════════════════════════════════════════════════════════════════════
# FY CLOSING REPORT CARD — fn_fy_closing_report, full account-by-account detail
# ════════════════════════════════════════════════════════════════════════════

def render_fy_closing_card(rows: list, error: str | None,
                            fy_options: list, selected_fy,
                            mutuality_summary: dict | None = None) -> html.Div:
    """
    Read-only FY Closing Report — same account-by-account detail for every
    role that can reach it (Admin/Owner/Vendor/Security all confirmed the
    full-detail option). FY pills reuse the existing kpi-card-div click
    pipeline (id pattern "kpi_fy_closing_report__<fy>") rather than a new
    callback — see the special case in drilldown_callbacks.py.

    mutuality_summary (from loaders.get_income_tax_mutuality_summary) drives
    a small on-screen Income Tax — Mutuality KPI block plus an "Export
    Mutuality Summary" button, which streams the full Excel workbook via the
    same btn-fy-export/dcc.Download pattern as every other export on this
    card (cashbook/ledger/ledger_index) — not a standalone route.
    """
    color = "#17976e"

    def _fy_label(fy):
        return f"{fy}-{str(fy + 1)[-2:]}"

    pills = html.Div([
        html.Div(
            _fy_label(fy),
            id={"type": "kpi-card-div", "card_id": f"kpi_fy_closing_report__{fy}"},
            n_clicks=0,
            style={
                "padding": "6px 14px", "borderRadius": "20px", "fontSize": "12px",
                "fontWeight": "700", "cursor": "pointer", "display": "inline-block",
                "marginRight": "8px", "marginBottom": "8px",
                "background": color if fy == selected_fy else "#fff",
                "color": "#fff" if fy == selected_fy else "#555",
                "border": f"1px solid {color}" if fy == selected_fy else "1px solid #e0e0e0",
            },
        )
        for fy in fy_options
    ], style={"marginBottom": "12px"})

    header = html.Div([
        html.Div([
            html.Div(html.I(className="fas fa-file-invoice-dollar",
                            style={"color": "#fff", "fontSize": "16px"}),
                     style={"width": "38px", "height": "38px", "borderRadius": "10px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "12px"}),
            html.Div([
                html.Strong("FY Closing Report", style={"fontSize": "14px"}),
                html.Div(f"FY {_fy_label(selected_fy)}" if selected_fy else "—",
                         style={"fontSize": "11px", "color": "#999"}),
            ]),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
        html.Div([
            pills,
            html.Div([
                dbc.Button(
                    [html.I(className="fas fa-file-excel me-2"), "Export Mutuality Summary"],
                    id={"type": "btn-fy-export", "entity": "mutuality_summary"},
                    size="sm", color="success", outline=True,
                    style={"borderRadius": "10px", "fontWeight": "600", "fontSize": "11px",
                           "marginBottom": "12px"},
                ),
                dcc.Download(id={"type": "fy-export-trigger", "entity": "mutuality_summary"}),
            ]) if selected_fy else None,
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}),
    ], style={"padding": "12px 16px",
              "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"})

    mutuality_kpi = None
    if mutuality_summary:
        def _kpi_tile(label, value, tile_color):
            return html.Div([
                html.Div(label, style={"fontSize": "10px", "color": "#888",
                                        "fontWeight": "600", "textTransform": "uppercase"}),
                html.Div(f"₹{value:,.2f}", style={"fontSize": "15px", "fontWeight": "700",
                                                    "color": tile_color}),
            ], style={"flex": "1", "minWidth": "140px", "padding": "10px 12px",
                      "background": "#fff", "borderRadius": "10px",
                      "border": "1px solid #eee"})

        mutuality_kpi = html.Div([
            html.Div("Income Tax — Mutuality Summary", style={
                "fontSize": "12px", "fontWeight": "700", "color": "#444",
                "marginBottom": "8px",
            }),
            html.Div([
                _kpi_tile("Mutual Income (exempt)",
                          mutuality_summary.get("mutual_income", 0), "#17976e"),
                _kpi_tile("Non-Mutual Income (taxable)",
                          mutuality_summary.get("non_mutual_income", 0), "#c0392b"),
                _kpi_tile("Non-Mutual Expense",
                          mutuality_summary.get("non_mutual_expense", 0), "#555"),
                _kpi_tile("Est. Taxable Income",
                          mutuality_summary.get("taxable_estimate", 0), "#b8860b"),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
            html.Div(
                "Estimate only — verify against your CA before filing.",
                style={"fontSize": "10px", "color": "#999", "marginTop": "6px",
                       "fontStyle": "italic"},
            ),
        ], style={"padding": "12px 16px", "background": "#f8f9fb",
                  "borderTop": "1px solid #eee", "borderBottom": "1px solid #eee"})

    if error:
        return html.Div([
            header,
            mutuality_kpi,
            html.Div(
                dbc.Alert([html.I(className="fas fa-exclamation-triangle me-2"), error],
                          color="warning", style={"borderRadius": "10px"}),
                style={"padding": "16px"},
            ),
        ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
                  "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})

    if not rows:
        body = dbc.Alert("No accounts found for this financial year.", color="secondary",
                          style={"borderRadius": "10px"})
    else:
        head = html.Thead(html.Tr([
            html.Th("Account"), html.Th("B/F", className="text-end"),
            html.Th("Movement", className="text-end"), html.Th("Dep.", className="text-end"),
            html.Th("Own Closing", className="text-end"),
            html.Th("Total Closing", className="text-end"), html.Th("Dr/Cr"),
        ], style={"fontSize": "11px"}))

        def _row(r):
            is_root = not r.get("parent_account_id")
            return html.Tr([
                html.Td(r.get("account_name", ""),
                        style={"fontWeight": "700" if is_root else "400",
                               "paddingLeft": "8px" if is_root else "24px"}),
                html.Td(f"{float(r.get('own_bf') or 0):,.2f}", className="text-end"),
                html.Td(f"{float(r.get('own_movement') or 0):,.2f}", className="text-end"),
                html.Td(f"{float(r.get('depreciation_charge') or 0):,.2f}", className="text-end"),
                html.Td(f"{float(r.get('own_closing') or 0):,.2f}", className="text-end"),
                html.Td(f"{float(r.get('display_amount') or 0):,.2f}",
                        className="text-end", style={"fontWeight": "700"}),
                html.Td(
                    r.get("display_side", ""),
                    style={"color": "#17976e" if r.get("display_side") == "Cr" else "#c0392b",
                           "fontWeight": "700"},
                ),
            ], style={"fontSize": "12px",
                      "background": "#fafcff" if is_root else "transparent"})

        body = dbc.Table(
            [head, html.Tbody([_row(r) for r in rows])],
            bordered=False, hover=True, responsive=True, size="sm",
            style={"marginTop": "4px"},
        )

    return html.Div([
        header,
        mutuality_kpi,
        html.Div(body, style={"padding": "16px"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


# ════════════════════════════════════════════════════════════════════════════
# MY TRANSACTIONS CARD — member-facing Sundry Debtors passbook
# ════════════════════════════════════════════════════════════════════════════

def render_member_ledger_card(
    rows: list, total_count: int, error: str | None,
    member_label: str, color: str = "#18794e",
    page: int = 1, page_size: int = 50,
    fy_options: list[int] = None, selected_fy: int = None,
    entity_id: int = None
) -> html.Div:
    """
    Read-only "My Transactions" passbook (loaders.get_member_ledger) —
    every entry posted against this member's Sundry Debtors balance:
    Dr = billed, Cr = paid, with a running "amount currently owed"
    balance. member_label is the display name for the header, e.g. a
    flat number ("Flat A-101") — generic across apartment/vendor/
    security since the loader itself is role-agnostic.
    """
    header = html.Div([
        html.Div(html.I(className="fas fa-receipt",
                        style={"color": "#fff", "fontSize": "16px"}),
                 style={"width": "38px", "height": "38px", "borderRadius": "10px",
                        "background": f"linear-gradient(135deg,{color},{color}aa)",
                        "display": "flex", "alignItems": "center",
                        "justifyContent": "center", "marginRight": "12px"}),
        html.Div([
            html.Strong("My Transactions", style={"fontSize": "14px"}),
            html.Div(member_label or "", style={"fontSize": "11px", "color": "#999"}),
        ]),
    ], style={"padding": "12px 16px", "display": "flex", "alignItems": "center",
              "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"})

    if error:
        return html.Div([
            header,
            html.Div(
                dbc.Alert([html.I(className="fas fa-exclamation-triangle me-2"), error],
                          color="warning", style={"borderRadius": "10px"}),
                style={"padding": "16px"},
            ),
        ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
                  "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})

    if not rows:
        body = dbc.Alert("No transactions yet.", color="secondary",
                          style={"borderRadius": "10px"})
    else:
        head = html.Thead(html.Tr([
            html.Th("Date"), html.Th("Particulars"), html.Th("Breakdown"),
            html.Th("Billed (Dr)", className="text-end"),
            html.Th("Paid (Cr)", className="text-end"),
            html.Th("Balance Owed", className="text-end"),
        ], style={"fontSize": "11px"}))

        def _row(r):
            is_dr = r.get("entry_side") == "Dr"
            amt = float(r.get("amount") or 0)
            bal = float(r.get("running_balance") or 0)
            breakdown_str = r.get("breakdown") or ""
            
            return html.Tr([
                html.Td(str(r.get("trx_date") or ""), style={"whiteSpace": "nowrap"}),
                html.Td(r.get("acc_particulars", "")),
                html.Td(breakdown_str, style={"fontSize": "11px", "color": "#7d8ea3"}),
                html.Td(f"{amt:,.2f}" if is_dr else "",
                        className="text-end", style={"color": "#c0392b"}),
                html.Td(f"{amt:,.2f}" if not is_dr else "",
                        className="text-end", style={"color": "#17976e"}),
                html.Td(f"{bal:,.2f}", className="text-end", style={"fontWeight": "700"}),
            ], style={"fontSize": "12px"})

        body = dbc.Table(
            [head, html.Tbody([_row(r) for r in rows])],
            bordered=False, hover=True, responsive=True, size="sm",
            style={"marginTop": "4px"},
        )

    # ── Toolbar: FY Filter, Export, Pagination ──
    fy_opts = fy_options or []
    
    # Calculate final balance using the first row if available (since DESC order)
    # Wait, the SQL is ordered DESC, so rows[0] is the newest entry on the current page.
    final_balance = 0
    if rows and page == 1:
        final_balance = float(rows[0].get("running_balance") or 0)

    toolbar = html.Div([
        html.Div([
            dbc.Select(
                id={"type": "drill-filter", "field": "financial_year"},
                options=[{"label": f"FY {y}-{y+1}", "value": str(y)} for y in fy_opts]
                        + [{"label": "All Time", "value": ""}],
                value=str(selected_fy) if selected_fy else "",
                size="sm", style={"width": "140px", "fontSize": "12px", "borderRadius": "8px"}
            ) if fy_opts else None,
            dbc.Button(
                [html.I(className="fas fa-file-excel me-1"), "Export"],
                id={"type": "btn-fy-export", "entity": "member_ledger"},
                size="sm", color="light", outline=True,
                style={"fontSize": "12px", "borderRadius": "8px", "marginLeft": "8px",
                       "border": "1px solid #dce4ec", "color": "#15304f"}
            )
        ], style={"display": "flex", "alignItems": "center"}),
        
        html.Div([
            dbc.Button(
                "Pay Now", id={"type": "kpi-card-div", "card_id": "form_pay_dues_new"},
                size="sm", color="success",
                style={"fontSize": "12px", "borderRadius": "8px", "marginRight": "16px",
                       "fontWeight": "600"}
            ),
            
            dbc.ButtonGroup([
                dbc.Button(
                    html.I(className="fas fa-chevron-left"),
                    id={"type": "ledger-page-btn", "dir": "prev"},
                    disabled=(page <= 1), size="sm", outline=True, color="secondary"
                ),
                dbc.Button(
                    f"{page} / {max(1, (total_count + page_size - 1) // page_size)}",
                    disabled=True, size="sm", outline=True, color="secondary",
                    style={"fontSize": "12px", "color": "#555"}
                ),
                dbc.Button(
                    html.I(className="fas fa-chevron-right"),
                    id={"type": "ledger-page-btn", "dir": "next"},
                    disabled=(page * page_size >= total_count), size="sm", outline=True, color="secondary"
                ),
            ], size="sm")
        ], style={"display": "flex", "alignItems": "center"})
    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
              "padding": "12px 16px", "borderBottom": "1px solid #f0f3f8",
              "background": "#fbfcfd"})

    return html.Div([
        header,
        toolbar,
        html.Div(body, style={"padding": "16px"}),
        dcc.Download(id={"type": "fy-export-trigger", "entity": "member_ledger"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIVABLE CARD — amount-entry form (single-row confirm)
# ════════════════════════════════════════════════════════════════════════════

def render_verify_receivable_card(
    receivable_id,
    description: str,
    residual: float,
    prefill_amount: float,
    prefill_mode: str = "cash",
    society_id=None,
) -> html.Div:
    color = "#17976e"
    return html.Div([
        html.Div(
            html.Div([
                html.Div(html.I(className="fas fa-check-double",
                                style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong("Verify Receivable", style={"fontSize": "14px"}),
                    html.Div(description, style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
            dbc.Card([
                html.Div("Outstanding", style={"fontSize": "10px", "color": "#7d8ea3",
                                                "fontWeight": "600", "textTransform": "uppercase"}),
                html.Div(f"₹{residual:,.2f}", style={"fontSize": "20px", "fontWeight": "800",
                                                      "color": "#15304f"}),
            ], body=True, style={"borderRadius": "10px", "border": "1px solid #e8edf5",
                                  "textAlign": "center", "padding": "10px", "marginBottom": "12px"}),
            dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                "Enter the amount actually received. Leave as-is to confirm in full — "
                "a lower amount leaves the balance outstanding as 'partial'.",
            ], color="info", style={"fontSize": "12px", "padding": "8px 14px",
                                    "borderRadius": "10px", "marginBottom": "12px"}),
            dcc.Input(id={"type": "form-field", "entity": "verify_receivable_amt", "field": "entity_id"},
                      type="hidden", value=str(receivable_id or "")),
            dbc.Row([
                dbc.Col(dbc.Label("Amount Received (₹) *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=5, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "verify_receivable_amt", "field": "amount"},
                    type="number", value=str(prefill_amount) if prefill_amount else "",
                    min=0.01, max=residual if residual else None, step=0.01,
                    style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=7),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=5, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "verify_receivable_amt", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ],
                    value=prefill_mode, clearable=False,
                    style={"fontSize": "13px"},
                ), width=7),
            ], className="mb-2"),
            dcc.Input(
                id={"type": "form-field-hidden", "entity": "verify_receivable_amt", "field": "acc_id"},
                type="hidden", value="",
            ),
            dbc.Row([
                dbc.Col(dbc.Label("Income Account *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=5, style={"paddingTop": "6px"}),
                dbc.Col(html.Div([
                    html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                    html.Span("Receivable Account", style={"flex": "1", "color": "#2a3b52", "fontWeight": "600"}),
                    html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                ], id={"type": "drillin-trigger", "entity": "verify_receivable_amt", "field": "acc_id"}, n_clicks=0,
                style={"display": "flex", "alignItems": "center", "padding": "10px 12px", "borderRadius": "10px", "border": "1px solid #dbe3ee", "background": "#fff", "cursor": "pointer", "fontSize": "13px"}), width=7),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Particulars", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=5, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": "verify_receivable_amt", "field": "particulars"},
                    value="", rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=7),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Bounce Penalty (if rejecting) ₹",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=5, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "verify_receivable_amt", "field": "penalty_amount"},
                    type="number", value="", min=0, step=0.01,
                    style={"fontSize": "13px", "borderRadius": "10px"},
                    placeholder="Penalty amount",
                ), width=7),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Button(
                    [html.I(className="fas fa-times me-2"), "Reject Payment"],
                    id={"type": "form-submit", "entity": "reject_receivable_amt", "card_id": "form_verify_receivable"},
                    n_clicks=0, color="danger", className="mt-3 w-100",
                    style={"borderRadius": "12px", "fontWeight": "700"},
                ), width=6),
                dbc.Col(dbc.Button(
                    [html.I(className="fas fa-check me-2"), "Confirm Receipt"],
                    id={"type": "form-submit", "entity": "verify_receivable_amt", "card_id": "form_verify_receivable"},
                    n_clicks=0, color="success", className="mt-3 w-100",
                    style={"borderRadius": "12px", "fontWeight": "700"},
                ), width=6),
            ]),
        ], style={"padding": "16px", "flex": "1", "minWidth": "260px"}),
        render_payment_qr_widget(society_id),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden", "display": "flex", "flexWrap": "wrap", "gap": "16px", "alignItems": "flex-start"})


# ════════════════════════════════════════════════════════════════════════════
# PAY DUES CARD  — FIFO payment form prefilled from apartment dues
# ════════════════════════════════════════════════════════════════════════════

def render_pay_dues_card(
    entity_id,
    flat_number: str,
    owner_name: str,
    pending_dues: float,
    overdue_dues: float,
    prefill_amount: float,
    prefill_mode: str = "cash",
    prefill_particulars: str = "",
    society_id=None,
    bill_groups=None,
) -> html.Div:
    if bill_groups is None: bill_groups = []
    color = "#17976e"
    overdue_color = "#de5c52" if overdue_dues > 0 else "#17976e"

    dues_summary = dbc.Row([
        dbc.Col(dbc.Card([
            html.Div("Pending Dues", style={"fontSize": "10px", "color": "#7d8ea3",
                                            "fontWeight": "600", "textTransform": "uppercase"}),
            html.Div(f"₹{pending_dues:,.2f}", style={"fontSize": "20px", "fontWeight": "800",
                                                      "color": "#15304f"}),
        ], body=True, style={"borderRadius": "10px", "border": "1px solid #e8edf5",
                              "textAlign": "center", "padding": "10px"}), width=6),
        dbc.Col(dbc.Card([
            html.Div("Overdue Dues", style={"fontSize": "10px", "color": "#7d8ea3",
                                            "fontWeight": "600", "textTransform": "uppercase"}),
            html.Div(f"₹{overdue_dues:,.2f}", style={"fontSize": "20px", "fontWeight": "800",
                                                       "color": overdue_color}),
        ], body=True, style={"borderRadius": "10px", "border": f"1px solid {overdue_color}33",
                              "textAlign": "center", "padding": "10px"}), width=6),
    ], className="mb-3")

    fifo_tab = dbc.Tab(label="FIFO Pay", tab_id="fifo", children=[
        html.Div([
            dues_summary,
            dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                f"Payment applied FIFO — oldest dues first. "
                f"Excess beyond ₹{pending_dues:,.2f} credited as advance. ",
                html.Br(), html.Br(),
                html.Strong("Note: "),
                "Interest on overdue amounts is calculated on a daily pro-rata basis using a standard 30-day banking month."
            ], color="info", style={"fontSize": "12px", "padding": "8px 14px",
                                    "borderRadius": "10px", "marginBottom": "12px"}),
            # Hidden fields
            dcc.Input(id={"type": "form-field", "entity": "pay_due", "field": "entity_id"},
                      type="hidden", value=str(entity_id or "")),
            dcc.Input(id={"type": "form-field", "entity": "pay_due", "field": "role"},
                      type="hidden", value="apartment"),
            dcc.Input(id={"type": "form-entity-pk", "entity": "pay_due"},
                      type="hidden", value=str(entity_id or "")),
            # Amount
            dbc.Row([
                dbc.Col(dbc.Label("Amount (₹) *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due", "field": "amount"},
                    type="number", value=str(prefill_amount) if prefill_amount else "",
                    min=1, step=0.01, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            # Mode
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ],
                    value=prefill_mode, clearable=False, style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            # Particulars
            dbc.Row([
                dbc.Col(dbc.Label("Particulars", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": "pay_due", "field": "particulars"},
                    value=prefill_particulars, rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Cheque No.",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "pay_due", "field": "cheque_no"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "pay_due", "field": "cheque_no"},
               style={} if prefill_mode == "cheque" else {"display": "none"}),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Payment Gateway ID",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "pay_due", "field": "transaction_id"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "pay_due", "field": "transaction_id"},
               style={} if prefill_mode in ("upi", "bank", "card", "crypto") else {"display": "none"}),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Apply Payment (FIFO)"],
                id={"type": "form-submit", "entity": "pay_due", "card_id": "form_pay_dues_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"paddingTop": "15px"})
    ])

    bill_group_tab = dbc.Tab(label="Bill Group Pay", tab_id="bill_group", children=[
        html.Div([
            dbc.Row([
                dbc.Col(dbc.Label("Select Bill", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col([
                    dcc.Input(id={"type": "form-field-hidden", "entity": "pay_due_bg", "field": "bill_group_id"},
                              type="hidden", value=""),
                    html.Div([
                        html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                        html.Span("Tap to select bill…",
                                  style={"flex": "1", "color": "#9aa7b8", "fontWeight": "400"}),
                        html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                    ], id={"type": "drillin-trigger", "entity": "pay_due_bg", "field": "bill_group_id"},
                       n_clicks=0,
                       style={
                           "display": "flex", "alignItems": "center",
                           "padding": "10px 12px", "borderRadius": "10px",
                           "border": "1px solid #dbe3ee", "background": "#fff",
                           "cursor": "pointer", "fontSize": "13px",
                       }),
                ], width=8)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Amount (₹) *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "amount"},
                    type="number", min=1, step=0.01, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Mode *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ], value=prefill_mode, clearable=False, style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Reference", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due_bg", "field": "reference"},
                    type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8)
            ], className="mb-2"),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Cheque No.",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "pay_due_bg", "field": "cheque_no"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "pay_due_bg", "field": "cheque_no"},
               style={} if prefill_mode == "cheque" else {"display": "none"}),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Payment Gateway ID",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "pay_due_bg", "field": "transaction_id"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "pay_due_bg", "field": "transaction_id"},
               style={} if prefill_mode in ("upi", "bank", "card", "crypto") else {"display": "none"}),
            
            dcc.Input(id={"type": "form-field", "entity": "pay_due_bg", "field": "role"}, type="hidden", value="apartment"),
            dcc.Input(id={"type": "form-field", "entity": "pay_due_bg", "field": "entity_id"}, type="hidden", value=str(entity_id or "")),
            
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Report Payment (Bill Group)"],
                id={"type": "form-submit", "entity": "pay_due_bg", "card_id": "form_pay_dues_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"paddingTop": "15px"})
    ])

    return html.Div([
        html.Div(
            html.Div([
                html.Div(html.I(className="fas fa-rupee-sign", style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong("Pay Dues", style={"fontSize": "14px"}),
                    html.Div(f"Flat {flat_number}" + (f" — {owner_name}" if owner_name else ""),
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px", "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
            html.Div([
                dbc.Tabs([fifo_tab, bill_group_tab], active_tab="fifo", style={"borderBottom": f"2px solid {color}33"}),
            ], style={"flex": "1", "minWidth": "260px"}),
            render_payment_qr_widget(society_id),
        ], style={"padding": "16px", "display": "flex", "flexWrap": "wrap", "gap": "16px", "alignItems": "flex-start"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22", "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})



# ════════════════════════════════════════════════════════════════════════════
# VENDOR PASS CARD — Sell Pass (admin) / Buy Pass (vendor)
# ════════════════════════════════════════════════════════════════════════════

def render_vendor_pass_card(
    user_id,
    vendor_name: str,
    service_type: str,
    pass_expiry,
    active_passes: int,
    rates: dict,           # {"1day": float, "7day": float, "1mth": float}
    society_id=None,
    prefill_mode: str = "cash",
    caller_role: str = "admin",   # "admin" → Sell Pass, "vendor" → Buy Pass
) -> "html.Div":
    """
    Dedicated form card for Sell Vendor Pass (admin) / Buy Vendor Pass (vendor).
 
    entity name on all IDs = "vendor_pass" — matches _resolve_entity_singular guard
    and _save_entity("vendor_pass") → _save_vendor_pass() routing.
 
    Pass flow recorded in DB:
      vendor_passes  → one row per pass (society_id, user_id, pass_type, valid_until)
      receipts       → status='confirmed' (immediate) — acc_id = ven_pass_acc_id
      transactions   → source_table='receipts', source_id=receipt.id
    """
    from dash import html, dcc
    import dash_bootstrap_components as dbc
  
    color        = "#17976e"
    action_label = "Sell Pass" if caller_role in ("admin", "master") else "Buy Pass"
    entity_name  = "vendor_pass"   # MUST match _resolve_entity_singular guard
 
    # ── Pass status banner ────────────────────────────────────────────────
    if active_passes and int(active_passes) > 0:
        expiry_str = (
            pass_expiry.strftime("%d %b %Y")
            if hasattr(pass_expiry, "strftime")
            else str(pass_expiry or "")
        )
        banner = dbc.Alert([
            html.I(className="fas fa-id-card me-2"),
            f"Active pass — valid until {expiry_str}. Selling a new pass extends validity.",
        ], color="success", style={"fontSize": "12px", "borderRadius": "10px",
                                    "padding": "8px 14px", "marginBottom": "12px"})
    else:
        banner = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            "No active pass — this vendor will be denied at the gate.",
        ], color="warning", style={"fontSize": "12px", "borderRadius": "10px",
                                    "padding": "8px 14px", "marginBottom": "12px"})
 
    # ── Rate summary cards (clickable) ───────────────────────────────────
    rate_items = [("1day", "1-Day"), ("7day", "7-Day"), ("1mth", "Monthly"), ("free_1mth", "Free (1 Month)")]
    rate_cols  = []
    for pt, label in rate_items:
        rate = rates.get(pt, 0)
        if pt == "free_1mth":
            rate_display = "FREE"
            rate_color = "#17976e"
        else:
            rate_display = f"₹{float(rate):,.0f}" if rate else "—"
            rate_color = "#15304f" if rate else "#bbb"
        rate_cols.append(dbc.Col(
            html.Button([
                html.Div(f"{label} Pass",
                         style={"fontSize": "10px", "color": "#7d8ea3",
                                "fontWeight": "600", "textTransform": "uppercase",
                                "marginBottom": "4px"}),
                html.Div(
                    rate_display,
                    style={"fontSize": "20px", "fontWeight": "800",
                           "color": rate_color},
                ),
            ],
            id={"type": "pass-type-card", "entity": "vendor_pass", "field": "pass_type", "value": pt},
            n_clicks=0,
            style={
                "width": "100%", "height": "100%", "minHeight": "80px",
                "border": "2px solid #e8edf5",
                "borderRadius": "10px",
                "background": "white",
                "textAlign": "center",
                "padding": "10px",
                "cursor": "pointer",
                "display": "flex",
                "flexDirection": "column",
                "justifyContent": "center",
                "alignItems": "center",
            },
        ), width=3))
  
    # ── Pass type dropdown — shows rate inline ────────────────────────────
    pass_options = []
    for pt, label in rate_items:
        rate = rates.get(pt, 0)
        if pt == "free_1mth":
            rate_str = "  FREE"
        else:
            rate_str = f"  ₹{float(rate):,.0f}" if rate else "  (rate not set)"
        pass_options.append({"label": f"{label} Pass  {rate_str}", "value": pt})
 
    return html.Div([
        html.Div(
            html.Div([
                html.Div(
                    html.I(className="fas fa-id-card",
                           style={"color": "#fff", "fontSize": "16px"}),
                    style={"width": "38px", "height": "38px", "borderRadius": "10px",
                           "background": f"linear-gradient(135deg,{color},{color}aa)",
                           "display": "flex", "alignItems": "center",
                           "justifyContent": "center", "marginRight": "12px"},
                ),
                html.Div([
                    html.Strong(f"{action_label} — {vendor_name}",
                                style={"fontSize": "14px"}),
                    html.Div(service_type or "",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
          html.Div([
            banner,
            dbc.Row(rate_cols, className="g-3"),
 
            # ── Hidden identity fields ────────────────────────────────────
            # vendor_user_id: read by _save_vendor_pass as p_user_id
            dcc.Input(
                id={"type": "form-field", "entity": entity_name, "field": "vendor_user_id"},
                type="hidden", value=str(user_id or ""),
            ),
            dcc.Input(
                id={"type": "form-field", "entity": entity_name, "field": "role"},
                type="hidden", value="vendor",
            ),
            dcc.Input(
                id={"type": "form-entity-pk", "entity": entity_name},
                type="hidden", value=str(user_id or ""),
            ),
 
            # ── Pass type ─────────────────────────────────────────────────
            dbc.Row([
                dbc.Col(dbc.Label("Pass Type *",
                                  style={"fontSize": "12px", "fontWeight": "500",
                                         "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": entity_name, "field": "pass_type"},
                    options=pass_options,
                    value=None,
                    placeholder="Select pass type…",
                    clearable=False,
                    style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
 
            # ── Payment mode ──────────────────────────────────────────────
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *",
                                  style={"fontSize": "12px", "fontWeight": "500",
                                         "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": entity_name, "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "Cheque",        "value": "cheque"},
                    ],
                    value=prefill_mode,
                    clearable=False,
                    style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            dcc.Input(
                id={"type": "form-field-hidden", "entity": entity_name, "field": "acc_id"},
                type="hidden", value="",
            ),
            dbc.Row([
                dbc.Col(dbc.Label("Income Account *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(html.Div([
                    html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                    html.Span("Society Charge", style={"flex": "1", "color": "#2a3b52", "fontWeight": "600"}),
                    html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                ], id={"type": "drillin-trigger", "entity": entity_name, "field": "acc_id"}, n_clicks=0,
                style={"display": "flex", "alignItems": "center", "padding": "10px 12px", "borderRadius": "10px", "border": "1px solid #dbe3ee", "background": "#fff", "cursor": "pointer", "fontSize": "13px"}), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Particulars", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": entity_name, "field": "particulars"},
                    value="", rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            # ── Dummy anchor for the non-cash-field clientside toggle ───────
            # (a real Store prop, rather than borrowing an unrelated prop
            # like dcc.Dropdown's nonexistent "title" — see qr_callbacks.py).
            # Plain id (not pattern-matched) since only one vendor-pass
            # form card is ever active in the nav stack at a time.
            dcc.Store(id="vp-noncash-dummy", data=None),
            # ── Non-cash reference fields (shown via clientside toggle) ────
            html.Div(
                id={"type": "vp-noncash-wrap", "pk": str(user_id)},
                style={"display": "none"},
                children=[
                    dbc.Row([
                        dbc.Col(dbc.Label("Cheque No.",
                                          style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                                width=4, style={"paddingTop": "6px"}),
                        dbc.Col(dbc.Input(
                            id={"type": "form-field", "entity": entity_name, "field": "cheque_no"},
                            type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                        ), width=8),
                    ], className="mb-2"),
                    dbc.Row([
                        dbc.Col(dbc.Label("Payment Gateway ID",
                                          style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                                width=4, style={"paddingTop": "6px"}),
                        dbc.Col(dbc.Input(
                            id={"type": "form-field", "entity": entity_name, "field": "transaction_id"},
                            type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                        ), width=8),
                    ], className="mb-2"),
                ],
            ),
            # ── Submit ────────────────────────────────────────────────────
            dbc.Button(
                [html.I(className="fas fa-id-card me-2"), action_label],
                id={"type": "form-submit", "entity": entity_name,
                    "card_id": "form_vendor_pass_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
 
            # ── Pass recording info box ───────────────────────────────────
            html.Hr(style={"margin": "16px 0 10px", "opacity": "0.15"}),
            html.Div([
                html.I(className="fas fa-info-circle me-2",
                       style={"color": "#7d8ea3", "fontSize": "11px"}),
                html.Span(
                    "On submit: vendor_passes row created → receipt confirmed → "
                    "transaction posted to cashbook.",
                    style={"fontSize": "10px", "color": "#aaa"},
                ),
            ]),
          ], style={"flex": "1", "minWidth": "260px"}),
          render_payment_qr_widget(society_id),
        ], style={"padding": "16px", "display": "flex", "flexWrap": "wrap",
                  "gap": "16px", "alignItems": "flex-start"}),
    ], style={
        "borderRadius": "16px",
        "border":       f"1px solid {color}22",
        "boxShadow":    f"0 10px 30px {color}18",
        "overflow":     "hidden",
    })
 

# ════════════════════════════════════════════════════════════════════════════
# ASSET DISPOSE CARD — Sell / Dispose Asset
# ════════════════════════════════════════════════════════════════════════════

def render_asset_dispose_card(asset: dict, society_id=None) -> html.Div:
    """
    Dedicated form card for Sell / Dispose Asset (admin only).

    entity name on all IDs = "asset_dispose" — matches _resolve_entity_singular
    guard and _save_entity("asset_dispose") → _save_asset_dispose() routing.

    Asset disposal flow recorded in DB:
      assets      → marked disposed=TRUE
      receipts    → sale proceeds receipt (confirmed)
      transactions → double-entry (Dr cash/bank, Cr asset class, gain/loss)
    """
    from datetime import date as _date
    from dash import html, dcc
    import dash_bootstrap_components as dbc

    color        = "#de5c52"
    asset_id     = asset.get("id", "")
    asset_name   = asset.get("asset_name", "—")
    asset_sno    = asset.get("asset_SNo", "—")
    purchase_val = float(asset.get("purchase_value") or 0)
    sale_value   = asset.get("sale_value") or ""
    sale_date    = asset.get("disposed_at") or _date.today().isoformat()
    mode         = asset.get("mode", "cash") or "cash"
    particulars  = asset.get("particulars") or ""
    acc_id       = asset.get("acc_id") or ""
    acc_name     = asset.get("acc_name") or "Tap to select…"
    acc_color    = "#2a3b52" if acc_id else "#9aa7b8"

    today_str = _date.today().isoformat()

    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div(html.I(className="fas fa-sign-out-alt",
                                style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong("Sell / Dispose Asset", style={"fontSize": "14px"}),
                    html.Div(f"{asset_name} (S/N: {asset_sno})",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div([
                html.Small("Asset", style={"color": "#7d8ea3", "fontWeight": "600"}),
                html.Span(f"{asset_name} (S/N: {asset_sno})", style={"fontWeight": "500"}),
            ], className="mb-2", style={"fontSize": "12px"}),
            html.Div([
                html.Small("Purchase Value", style={"color": "#7d8ea3", "fontWeight": "600"}),
                html.Span(f"₹{purchase_val:,.2f}", style={"fontWeight": "500"}),
            ], className="mb-3", style={"fontSize": "12px"}),
            dcc.Input(id={"type": "form-field-hidden", "entity": "asset_dispose", "field": "asset_id"},
                      type="hidden", value=str(asset_id)),
            dcc.Input(id={"type": "form-field-hidden", "entity": "asset_dispose", "field": "role"},
                      type="hidden", value="assets"),
            dcc.Input(id={"type": "form-field-hidden", "entity": "asset_dispose", "field": "acc_id"},
                      type="hidden", value=str(acc_id)),
            dbc.Row([
                dbc.Col(dbc.Label("Income Account *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(html.Div([
                    html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                    html.Span(acc_name, style={"flex": "1", "color": acc_color, "fontWeight": "400" if not acc_id else "600"}),
                    html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                ], id={"type": "drillin-trigger", "entity": "asset_dispose", "field": "acc_id"}, n_clicks=0,
                style={"display": "flex", "alignItems": "center", "padding": "10px 12px", "borderRadius": "10px", "border": "1px solid #dbe3ee", "background": "#fff", "cursor": "pointer", "fontSize": "13px"}), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Sale Value (₹) *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Input(
                    id={"type": "form-field", "entity": "asset_dispose", "field": "sale_value"},
                    type="number", value=sale_value, min=0.01, step=0.01,
                    required=True, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Sale Date *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Input(
                    id={"type": "form-field", "entity": "asset_dispose", "field": "sale_date"},
                    type="text", value=sale_date, placeholder="YYYY-MM-DD",
                    style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Mode *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "asset_dispose", "field": "mode"},
                    options=[
                        {"label": "Cash", "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "UPI", "value": "upi"},
                        {"label": "Cheque", "value": "cheque"},
                        {"label": "Card", "value": "card"},
                    ],
                    value=mode, clearable=False, style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Particulars", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": "asset_dispose", "field": "particulars"},
                    value=particulars, rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Cheque No.",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "asset_dispose", "field": "cheque_no"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "asset_dispose", "field": "cheque_no"},
               style={} if mode == "cheque" else {"display": "none"}),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Payment Gateway ID",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": "asset_dispose", "field": "transaction_id"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": "asset_dispose", "field": "transaction_id"},
               style={} if mode in ("upi", "bank", "card", "crypto") else {"display": "none"}),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Confirm Sale & Generate Receipt"],
                id={"type": "form-submit", "entity": "asset_dispose", "card_id": "form_asset_dispose_new"},
                n_clicks=0, color="danger", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"padding": "16px", "flex": "1", "minWidth": "260px"}),
        render_payment_qr_widget(society_id),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden", "display": "flex", "flexWrap": "wrap", "gap": "16px", "alignItems": "flex-start"})


# ════════════════════════════════════════════════════════════════════════════
# EVENT TICKET CARD  — Sell Tickets (admin) / Buy Tickets (apartment)
# ════════════════════════════════════════════════════════════════════════════

def _qty_stepper_row(entity_name: str, field_id: str, label: str, initial: int, min_val: int = 0):
    """
    Touch-friendly '−  [qty]  +' quantity control (Tweak 2, 2026-08) —
    replaces a bare dbc.Input(type='number') for Adult/Child Qty. Buttons
    use the {"type":"qty-step","entity","field","dir"} id shape driven by
    qty_stepper_callbacks.py's generic clientside callback, so this same
    row shape is reusable for any other numeric field, not just event
    tickets.
    """
    import dash_bootstrap_components as dbc
    btn_style = {
        "width": "34px", "height": "34px", "padding": "0",
        "borderRadius": "8px", "fontWeight": "700", "fontSize": "16px",
        "lineHeight": "1",
    }
    return dbc.Row([
        dbc.Col(dbc.Label(label, style={"fontSize": "12px", "fontWeight": "500",
                                         "color": "#555"}),
                width=4, style={"paddingTop": "6px"}),
        dbc.Col(html.Div([
            dbc.Button("−", id={"type": "qty-step", "entity": entity_name,
                                 "field": field_id, "dir": "down"},
                       n_clicks=0, size="sm", color="light", outline=True,
                       style=btn_style),
            dbc.Input(
                id={"type": "form-field", "entity": entity_name, "field": field_id},
                type="number", value=str(initial), min=min_val, step=1,
                style={"fontSize": "13px", "borderRadius": "10px",
                       "textAlign": "center", "width": "56px",
                       "margin": "0 6px"},
            ),
            dbc.Button("+", id={"type": "qty-step", "entity": entity_name,
                                 "field": field_id, "dir": "up"},
                       n_clicks=0, size="sm", color="light", outline=True,
                       style=btn_style),
        ], style={"display": "flex", "alignItems": "center"}), width=8),
    ], className="mb-2")


def render_event_ticket_card(
    event_id,
    event_title: str,
    event_date,
    ticket_name: str = "",
    ticket_name2: str = "",
    ticket_price: float = 0.0,
    ticket_price2: float = 0.0,
    society_id=None,
    apt_user_id=None,
    flat_number: str = "",
    owner_name: str = "",
    buyer_label: str = "",
    open_to: str = "all",
    prefill_mode: str = "cash",
    caller_role: str = "admin",   # "admin" -> Sell Tickets, "apartment"/"vendor"/"security" -> Buy Tickets
) -> "html.Div":
    """
    Dedicated form card for Sell Event Ticket (admin) / Buy Event Ticket
    (apartment/vendor/security) -- mirrors render_vendor_pass_card's
    Sell/Buy Pass shape.

    entity name on all IDs = "event_ticket" -- matches _resolve_entity_singular
    guard and _save_entity("event_ticket") -> _save_event_ticket() routing.

    Ticket flow recorded in DB:
      event_tickets  -> one row per purchase (society_id, event_id, user_id, quantity_adult, quantity_child, amount)
      receipts       -> status='confirmed' (immediate) -- acc_id = events.account_id
      transactions   -> source_table='receipts', source_id=receipt.id

    2026-08: buyer side generalized from apartment-only to
    apartment/vendor/security (gated per-event by events.open_to --
    enforced in fn_sell_event_ticket, not here). `flat_number`/`owner_name`
    stay as the apartment-specific display fields; `buyer_label` is the
    generic one-line identity string used for vendor/security instead.

    2026-08 Tweak 1: admin's buyer field is now the entity_id/role
    drill-in (DRILLIN_CONFIG[("event_ticket_items","entity_id")]) instead of a
    flat apartment-only dropdown — which roles it offers is narrowed to
    this event's own open_to at the moment the picker is opened (see
    drillin_callbacks.py's drillin_navigate special-case), not computed
    here; `open_to` is only used below for the small caption under the
    picker button.
    """
    from dash import html, dcc
    import dash_bootstrap_components as dbc

    color        = "#c8781f"
    is_admin     = caller_role in ("admin", "master")
    action_label = "Sell Tickets" if is_admin else "Buy Tickets"
    entity_name  = "event_ticket"   # MUST match _resolve_entity_singular guard

    date_str = (
        event_date.strftime("%d %b %Y")
        if hasattr(event_date, "strftime")
        else str(event_date or "")
    )
    price_display = f"{float(ticket_price or 0):,.2f}"
    price_display2 = f"{float(ticket_price2 or 0):,.2f}"

    if ticket_price2 and float(ticket_price2 or 0) > 0:
        price_line = (
            f"{date_str} — {ticket_name}: Rs.{price_display}, "
            f"{ticket_name2}: Rs.{price_display2} per ticket"
        )
    elif ticket_price and float(ticket_price or 0) > 0:
        price_line = f"{date_str} — Rs.{price_display} ({ticket_name}) per ticket"
    else:
        price_line = f"{date_str} — Free entry, no payment required"

    banner = dbc.Alert([
        html.I(className="fas fa-ticket-alt me-2"),
        price_line,
    ], color="info", style={"fontSize": "12px", "borderRadius": "10px",
                             "padding": "8px 14px", "marginBottom": "12px"})

    _OPEN_TO_CAPTIONS = {
        "all": "Open to everyone",
        "members_only": "Open to members (apartments) only",
        "residents_only": "Open to residents (apartments + security) only",
    }

    # -- Buyer field: admin drills in to any eligible apartment/vendor/
    #    security (Tweak 1); apartment/vendor/security see their own
    #    identity --
    if is_admin:
        buyer_field = html.Div([
            dcc.Input(
                id={"type": "form-field-hidden", "entity": entity_name, "field": "entity_id"},
                type="hidden", value="",
            ),
            dcc.Input(
                id={"type": "form-field-hidden", "entity": entity_name, "field": "role"},
                type="hidden", value="",
            ),
            dbc.Label("Buyer *", style={"fontSize": "12px", "fontWeight": "500",
                                         "color": "#555", "marginBottom": "4px",
                                         "display": "block"}),
            html.Div([
                html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                html.Span("Tap to select…", style={"flex": "1", "color": "#9aa7b8"}),
                html.I(className="fas fa-chevron-right",
                       style={"color": "#c2cdda", "fontSize": "11px"}),
            ], id={"type": "drillin-trigger", "entity": entity_name, "field": "entity_id"},
               n_clicks=0,
               style={
                   "display": "flex", "alignItems": "center",
                   "padding": "10px 12px", "borderRadius": "10px",
                   "border": "1px solid #dbe3ee", "background": "#fff",
                   "cursor": "pointer", "fontSize": "13px",
               }),
            html.Small(_OPEN_TO_CAPTIONS.get(open_to, _OPEN_TO_CAPTIONS["all"]),
                       style={"color": "#9aa7b8", "fontSize": "10px",
                              "marginTop": "4px", "display": "block"}),
        ], style={"marginBottom": "10px"})
        pk_for_wrap = str(event_id)
    else:
        own_label = f"Flat {flat_number} — {owner_name}" if caller_role == "apartment" else buyer_label
        buyer_field = html.Div([
            dcc.Input(
                # NOTE: _save_event_ticket() never reads "role" — fn_sell_
                # event_ticket resolves the buyer's actual role server-side
                # from p_user_id via the users table. This is display-only.
                id={"type": "form-field", "entity": entity_name, "field": "role"},
                type="hidden", value=caller_role,
            ),
            html.Div(own_label, style={"fontSize": "13px", "fontWeight": "600",
                                        "color": "#15304f", "marginBottom": "10px"}),
        ])
        pk_for_wrap = str(apt_user_id or event_id)

    return html.Div([
        html.Div(
            html.Div([
                html.Div(
                    html.I(className="fas fa-ticket-alt",
                           style={"color": "#fff", "fontSize": "16px"}),
                    style={"width": "38px", "height": "38px", "borderRadius": "10px",
                           "background": f"linear-gradient(135deg,{color},{color}aa)",
                           "display": "flex", "alignItems": "center",
                           "justifyContent": "center", "marginRight": "12px"},
                ),
                html.Div([
                    html.Strong(f"{action_label} — {event_title}",
                                style={"fontSize": "14px"}),
                    html.Div(date_str, style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        html.Div([
          html.Div([
            banner,

            # -- Hidden identity fields --------------------------------------
            dcc.Input(
                id={"type": "form-field", "entity": entity_name, "field": "event_id"},
                type="hidden", value=str(event_id or ""),
            ),
            dcc.Input(
                id={"type": "form-entity-pk", "entity": entity_name},
                type="hidden", value=pk_for_wrap,
            ),
            # buyer's own user id -- hidden when buying for themselves.
            # Admin's equivalent (entity_id/role) comes from the drill-in's
            # own hidden fields, rendered inside buyer_field above.
            (dcc.Input(
                id={"type": "form-field", "entity": entity_name, "field": "apt_user_id"},
                type="hidden", value=str(apt_user_id or ""),
            ) if not is_admin else None),

            buyer_field,

            # -- Quantity (Adult / Child split) --
            _qty_stepper_row(entity_name, "quantity_adult", "Adult Qty *", 1, min_val=0),
            (_qty_stepper_row(entity_name, "quantity_child", "Child Qty", 0, min_val=0)
             if ticket_price2 and float(ticket_price2 or 0) > 0 else None),

            # -- Payment mode ---------------------------------------------------
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": entity_name, "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Bank Transfer", "value": "bank"},
                        {"label": "Cheque",        "value": "cheque"},
                    ],
                    value=prefill_mode,
                    clearable=False,
                    style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            dcc.Input(
                id={"type": "form-field-hidden", "entity": entity_name, "field": "acc_id"},
                type="hidden", value="",
            ),
            dbc.Row([
                dbc.Col(dbc.Label("Income Account *", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(html.Div([
                    html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
                    html.Span("Event Account", style={"flex": "1", "color": "#2a3b52", "fontWeight": "600"}),
                    html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
                ], id={"type": "drillin-trigger", "entity": entity_name, "field": "acc_id"}, n_clicks=0,
                style={"display": "flex", "alignItems": "center", "padding": "10px 12px", "borderRadius": "10px", "border": "1px solid #dbe3ee", "background": "#fff", "cursor": "pointer", "fontSize": "13px"}), width=8),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Particulars", style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}), width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": entity_name, "field": "particulars"},
                    value="", rows=2, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            # -- Tweak 3 (2026-08): Cash -> neither field. Cheque -> Cheque
            #    No. only. Anything else (UPI/Bank/Card) -> Payment Gateway
            #    ID only. Reuses the SAME generic mode-conditional-row /
            #    MATCH clientside callback (mode_conditional_callbacks.py)
            #    that already drives Receipts/Expenses — this card just
            #    needed to wrap these two rows with the same id shape
            #    (entity="event_ticket") to plug in automatically; the
            #    bespoke "et-noncash-wrap" toggle this replaced showed both
            #    fields together for every non-cash mode instead of
            #    splitting them, and is now removed (see qr_callbacks.py).
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Cheque No.",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": entity_name, "field": "cheque_no"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": entity_name, "field": "cheque_no"},
               style={} if prefill_mode == "cheque" else {"display": "none"}),
            html.Div([
                dbc.Row([
                    dbc.Col(dbc.Label("Payment Gateway ID",
                                      style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                            width=4, style={"paddingTop": "6px"}),
                    dbc.Col(dbc.Input(
                        id={"type": "form-field", "entity": entity_name, "field": "transaction_id"},
                        type="text", style={"fontSize": "13px", "borderRadius": "10px"},
                    ), width=8),
                ], className="mb-2"),
            ], id={"type": "mode-conditional-row", "entity": entity_name, "field": "transaction_id"},
               style={} if prefill_mode in ("upi", "bank", "card", "crypto") else {"display": "none"}),
            # -- Submit -----------------------------------------------------------
            dbc.Button(
                [html.I(className="fas fa-ticket-alt me-2"), action_label],
                id={"type": "form-submit", "entity": entity_name,
                    "card_id": "form_event_ticket_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),

            html.Hr(style={"margin": "16px 0 10px", "opacity": "0.15"}),
            html.Div([
                html.I(className="fas fa-info-circle me-2",
                       style={"color": "#7d8ea3", "fontSize": "11px"}),
                html.Span(
                    "On submit: event_tickets row created — receipt confirmed — "
                    "transaction posted to cashbook.",
                    style={"fontSize": "10px", "color": "#aaa"},
                ),
            ]),
          ], style={"flex": "1", "minWidth": "260px"}),
          render_payment_qr_widget(society_id),
        ], style={"padding": "16px", "display": "flex", "flexWrap": "wrap",
                  "gap": "16px", "alignItems": "flex-start"}),
    ], style={
        "borderRadius": "16px",
        "border":       f"1px solid {color}22",
        "boxShadow":    f"0 10px 30px {color}18",
        "overflow":     "hidden",
    })


# ════════════════════════════════════════════════════════════════════════════
# NOC CARD  — rich-text editor with eligibility banner + Print/PDF/Email
# ════════════════════════════════════════════════════════════════════════════

def render_noc_card(apt: dict, society: dict,
                    eligible: bool = True, reason: str = "",
                    outstanding: float = 0, noc_record: dict | None = None) -> html.Div:
    from datetime import date as _date
    color     = "#15304f"
    flat_no   = apt.get("flat_number", "____")
    owner     = apt.get("owner_name", "____")
    society_nm = society.get("name", "____")
    sec_name  = society.get("secretary_name") or society.get("contact_person", "____")
    today     = _date.today().strftime("%d %B %Y")
    cert_no   = (noc_record or {}).get("certificate_no") or "PREVIEW — not yet issued"

    # A reused (previously issued, still-valid) NOC keeps its original
    # wording rather than being regenerated with today's date — that's
    # what "certificate" means. A freshly-created record (body_text still
    # empty, written as '' by _get_or_create_active_noc) gets the text
    # below generated once and persisted back to that row.
    existing_text = (noc_record or {}).get("body_text") or ""
    if existing_text:
        noc_text = existing_text
    else:
        noc_text = (
            f"NO OBJECTION CERTIFICATE\n"
            f"Certificate No: {cert_no}\n"
            f"{society_nm}\n\n"
            f"Date: {today}\n\n"
            f"To Whom It May Concern,\n\n"
            f"This is to certify that {owner}, resident of Flat No. {flat_no}, "
            f"{society_nm}, has cleared all outstanding dues and has no pending "
            f"liabilities towards the Society as of the date of this certificate.\n\n"
            f"The Society has no objection to the above-named member undertaking any "
            f"legal, financial, or administrative transactions related to the said property.\n\n"
            f"This certificate is issued upon request and is valid for 30 days from "
            f"the date of issue.\n\n\n"
            f"Authorised Signatory\n\n"
            f"{sec_name}\n"
            f"Secretary / Authorised Representative\n"
            f"{society_nm}"
        )
        if noc_record and noc_record.get("id"):
            try:
                db._execute(
                    "UPDATE nocs SET body_text=%s WHERE id=%s",
                    (noc_text, noc_record["id"]),
                )
            except Exception as e:
                print(f"⚠️  NOC body_text persist failed: {e}")

    # Letterhead branding + verification QR (NOC role) — same shared
    # helper used by receipts; see print_letterhead.py. No QR is rendered
    # for a not-yet-eligible preview since there's no noc_record yet.
    from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, QR_CAPTION
    society_id = apt.get("society_id") or society.get("id")
    letterhead = get_letterhead_assets(society, society_id)
    qr_url = ""
    if noc_record and noc_record.get("id") and society_id:
        try:
            from app.services.qr_service import generate_qr_code
            qr_img, _payload = generate_qr_code(society_id, "NOC", noc_record["id"])
            qr_url = qr_img or ""
        except Exception as e:
            print(f"⚠️  NOC QR render failed: {e}")
    noc_letterhead_data = {
        "id": (noc_record or {}).get("id"),
        "society_name": society_nm, "society_address": society.get("address", ""),
        "logo_url": letterhead["logo_url"], "background_url": letterhead["background_url"],
        "signature_url": letterhead["signature_url"], "secretary_name": letterhead["secretary_name"],
        "qr_url": qr_url, "qr_caption": QR_CAPTION, "certificate_no": cert_no,
    }

    # Eligibility banner
    if not eligible:
        elig_banner = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            html.Strong("Outstanding dues detected. "),
            f"₹{float(outstanding):,.2f} pending — {reason}. ",
            "NOC issued below is for preview only. Clear dues before printing.",
        ], color="warning", style={"fontSize": "12px", "borderRadius": "10px",
                                   "padding": "8px 14px", "marginBottom": "12px"})
    else:
        elig_banner = dbc.Alert([
            html.I(className="fas fa-check-circle me-2"),
            "All dues cleared — this apartment is eligible for NOC.",
        ], color="success", style={"fontSize": "12px", "borderRadius": "10px",
                                   "padding": "8px 14px", "marginBottom": "12px"})

    flat_no_safe = flat_no.replace(" ", "_")

    return dbc.Card([
        dcc.Store(id="noc-flat-store", data=flat_no_safe, storage_type="memory"),
        dcc.Store(id="noc-letterhead-data", data=noc_letterhead_data, storage_type="memory"),
        dbc.CardHeader(
            html.Div([
                html.Div(html.I(className="fas fa-certificate",
                                style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong("No Objection Certificate", style={"fontSize": "14px"}),
                    html.Div(f"Flat {flat_no} — {owner} — {cert_no}",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div(elig_banner, style={"marginBottom": "8px"}),
            dbc.Label("Edit NOC text below before printing:",
                      style={"fontSize": "11px", "color": "#7d8ea3",
                             "fontWeight": "600", "marginBottom": "4px"}),
            dbc.Textarea(
                id="noc-textarea",
                value=noc_text,
                className="noc-editor-ta",
                style={
                    "width": "100%",
                    "minHeight": "220px",
                    "maxHeight": "360px",
                    "border": "1px solid #d0dae8",
                    "borderRadius": "10px",
                    "padding": "14px 16px",
                    "fontSize": "12px",
                    "lineHeight": "1.7",
                    "fontFamily": "Georgia, 'Times New Roman', serif",
                    "background": "#fff",
                    "resize": "vertical",
                    "boxShadow": "inset 0 1px 4px rgba(0,0,0,0.04)",
                },
            ),
            # Action buttons — clientside callbacks. Disabled when not
            # eligible: printing/saving/emailing a NOC for an apartment
            # with outstanding dues should not be possible from the UI,
            # even though the (preview) text is still shown above.
            html.Div([
                html.Button(
                    [html.I(className="fas fa-print me-2"), "Print"],
                    id="noc-btn-print",
                    n_clicks=0,
                    disabled=not eligible,
                    className="btn btn-outline-primary",
                    style={"borderRadius": "10px", "fontWeight": "600",
                           **({"opacity": "0.5", "cursor": "not-allowed"} if not eligible else {})},
                ),
                html.Button(
                    [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                    id="noc-btn-pdf",
                    n_clicks=0,
                    disabled=not eligible,
                    className="btn btn-outline-danger",
                    style={"borderRadius": "10px", "fontWeight": "600",
                           **({"opacity": "0.5", "cursor": "not-allowed"} if not eligible else {})},
                ),
                html.Button(
                    [html.I(className="fas fa-envelope me-2"), "Email NOC"],
                    id="noc-btn-email",
                    n_clicks=0,
                    disabled=not eligible,
                    className="btn btn-outline-info",
                    style={"borderRadius": "10px", "fontWeight": "600",
                           **({"opacity": "0.5", "cursor": "not-allowed"} if not eligible else {})},
                ),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "marginTop": "10px", "paddingTop": "10px",
                      "borderTop": "1px solid rgba(120,148,181,0.15)"}),
        ], style={"padding": "14px 16px"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


# ════════════════════════════════════════════════════════════════════════════
# RECEIPT CARD — formatted receipt preview + Print/Save/Email
# ════════════════════════════════════════════════════════════════════════════

def render_receipt_card(receipt: dict, society: dict) -> html.Div:
    """
    Read-only formatted receipt + Print/Save-as-HTML/Email buttons, same
    clientside-callback pattern as render_noc_card (see receipt_callbacks.py)
    but built from structured fields via a hidden JSON dcc.Store
    (id="receipt-print-data") rather than an editable textarea — a receipt
    is a record of what was already collected, not something to edit here.
    """
    from datetime import date as _date

    color      = "#17976e"
    receipt_no = receipt.get("id", "—")
    r_date     = receipt.get("receipt_date") or _date.today().isoformat()
    payer      = receipt.get("entity_name") or "—"
    role_lbl   = (receipt.get("role") or "").title() or "—"
    particulars = receipt.get("particulars", "—")
    account    = receipt.get("account_name", "—")
    amount     = float(receipt.get("amount") or 0)
    mode       = (receipt.get("mode") or "cash").title()
    ref        = receipt.get("transaction_id") or receipt.get("cheque_no") or ""
    status     = (receipt.get("status") or "confirmed").title()
    society_nm = society.get("name", "—")
    society_addr = society.get("address", "")
    society_id = receipt.get("society_id") or society.get("id")

    # Letterhead branding (logo / watermark background / secretary signature)
    # — shared with NOC and event-ticket prints, see print_letterhead.py.
    from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, QR_CAPTION
    letterhead = get_letterhead_assets(society, society_id)

    # Verification QR — RPT role, points scanners at validate_receipt_qr()
    # (already implemented in qr_service.py; previously generated for
    # security-gate lookups only, never rendered onto the printed receipt).
    qr_url = ""
    if receipt_no and receipt_no != "—" and society_id:
        try:
            from app.services.qr_service import generate_qr_code
            qr_img, _payload = generate_qr_code(society_id, "RPT", int(receipt_no))
            qr_url = qr_img or ""
        except Exception as e:
            print(f"⚠️  receipt QR render failed: {e}")

    print_data = {
        "receipt_no": receipt_no, "date": r_date, "payer": payer,
        "role": role_lbl, "particulars": particulars, "account": account,
        "amount": f"{amount:,.2f}", "mode": mode, "ref": ref, "status": status,
        "society_name": society_nm, "society_address": society_addr,
        "logo_url": letterhead["logo_url"], "background_url": letterhead["background_url"],
        "signature_url": letterhead["signature_url"], "secretary_name": letterhead["secretary_name"],
        "qr_url": qr_url, "qr_caption": QR_CAPTION,
        "is_provisional": (receipt.get("status") in ("pending", "unverified")),
    }

    def _row(label, value):
        return dbc.Row([
            dbc.Col(html.Small(label, style={"color": "#7d8ea3", "fontWeight": "600"}), width=4),
            dbc.Col(html.Span(str(value), style={"fontWeight": "500"}), width=8),
        ], className="mb-2", style={"fontSize": "12px"})

    return dbc.Card([
        dcc.Store(id="receipt-print-data", data=print_data, storage_type="memory"),
        dbc.CardHeader(
            html.Div([
                html.Div(html.I(className="fas fa-receipt",
                                style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong(f"Receipt #{receipt_no}", style={"fontSize": "14px"}),
                    html.Div(f"{payer} — {role_lbl}",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div([
                html.Div(society_nm, style={"fontWeight": "800", "fontSize": "15px"}),
                html.Div(society_addr, style={"fontSize": "11px", "color": "#999"}),
            ], style={"textAlign": "center", "marginBottom": "14px",
                      "paddingBottom": "10px", "borderBottom": "1px dashed #d0dae8"}),
            _row("Date", r_date),
            _row("Received From", f"{payer} ({role_lbl})"),
            _row("Particulars", particulars),
            _row("Account", account),
            _row("Amount", f"₹{amount:,.2f}"),
            _row("Mode", mode + (f" — Ref: {ref}" if ref else "")),
            _row("Status", html.Span([status, html.Strong(" (Provisional - Subject to realization of funds)", style={"color": "#dc3545", "marginLeft": "5px"})]) if receipt.get("status") in ("pending", "unverified") else status),
            html.Div([
                html.Button(
                    [html.I(className="fas fa-print me-2"), "Print"],
                    id="receipt-btn-print", n_clicks=0,
                    className="btn btn-outline-primary",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                    id="receipt-btn-pdf", n_clicks=0,
                    className="btn btn-outline-danger",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-envelope me-2"), "Email Receipt"],
                    id="receipt-btn-email", n_clicks=0,
                    className="btn btn-outline-info",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "marginTop": "16px", "paddingTop": "14px",
                      "borderTop": "1px solid rgba(120,148,181,0.15)"}),
        ], style={"padding": "16px"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


def render_expense_card(expense: dict, society: dict) -> html.Div:
    """
    Read-only formatted expense + Print/Save-as-HTML/Email buttons, same
    clientside-callback pattern as render_receipt_card (see expense_callbacks.py)
    built from structured fields via a hidden JSON dcc.Store
    (id="expense-print-data") rather than an editable textarea.
    """
    from datetime import date as _date

    color      = "#de5c52"
    expense_no = expense.get("id", "—")
    e_date     = expense.get("expense_date") or _date.today().isoformat()
    payee      = expense.get("entity_name") or "—"
    role_lbl   = (expense.get("role") or "").title() or "—"
    particulars = expense.get("particulars", "—")
    account    = expense.get("account_name", "—")
    amount     = float(expense.get("amount") or 0)
    mode       = (expense.get("mode") or "cash").title()
    ref        = expense.get("transaction_id") or expense.get("cheque_no") or ""
    status     = (expense.get("status") or "confirmed").title()
    society_nm = society.get("name", "—")
    society_addr = society.get("address", "")
    society_id = expense.get("society_id") or society.get("id")
    tds_pct    = expense.get("tds_pct")

    from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, QR_CAPTION
    letterhead = get_letterhead_assets(society, society_id)

    qr_url = ""
    if expense_no and expense_no != "—" and society_id:
        try:
            from app.services.qr_service import generate_qr_code
            qr_img, _payload = generate_qr_code(society_id, "EXP", int(expense_no))
            qr_url = qr_img or ""
        except Exception as e:
            print(f"⚠️  expense QR render failed: {e}")

    print_data = {
        "expense_no": expense_no, "date": e_date, "payee": payee,
        "role": role_lbl, "particulars": particulars, "account": account,
        "amount": f"{amount:,.2f}", "mode": mode, "ref": ref, "status": status,
        "society_name": society_nm, "society_address": society_addr,
        "logo_url": letterhead["logo_url"], "background_url": letterhead["background_url"],
        "signature_url": letterhead["signature_url"], "secretary_name": letterhead["secretary_name"],
        "qr_url": qr_url, "qr_caption": QR_CAPTION,
        "is_provisional": (expense.get("status") in ("pending", "unverified")),
        "tds_pct": tds_pct,
    }

    def _row(label, value):
        return dbc.Row([
            dbc.Col(html.Small(label, style={"color": "#7d8ea3", "fontWeight": "600"}), width=4),
            dbc.Col(html.Span(str(value), style={"fontWeight": "500"}), width=8),
        ], className="mb-2", style={"fontSize": "12px"})

    return dbc.Card([
        dcc.Store(id="expense-print-data", data=print_data, storage_type="memory"),
        dbc.CardHeader(
            html.Div([
                html.Div(html.I(className="fas fa-file-invoice-dollar",
                                style={"color": "#fff", "fontSize": "16px"}),
                         style={"width": "38px", "height": "38px", "borderRadius": "10px",
                                "background": f"linear-gradient(135deg,{color},{color}aa)",
                                "display": "flex", "alignItems": "center",
                                "justifyContent": "center", "marginRight": "12px"}),
                html.Div([
                    html.Strong(f"Expense #{expense_no}", style={"fontSize": "14px"}),
                    html.Div(f"{payee} — {role_lbl}",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div([
                html.Div(society_nm, style={"fontWeight": "800", "fontSize": "15px"}),
                html.Div(society_addr, style={"fontSize": "11px", "color": "#999"}),
            ], style={"textAlign": "center", "marginBottom": "14px",
                      "paddingBottom": "10px", "borderBottom": "1px dashed #d0dae8"}),
            _row("Date", e_date),
            _row("Paid To", f"{payee} ({role_lbl})"),
            _row("Particulars", particulars),
            _row("Account", account),
            _row("Amount", f"₹{amount:,.2f}"),
            _row("TDS %", f"{tds_pct}%" if tds_pct else "—"),
            _row("Mode", mode + (f" — Ref: {ref}" if ref else "")),
            _row("Status", html.Span([status, html.Strong(" (Provisional - Subject to realization of funds)", style={"color": "#dc3545", "marginLeft": "5px"})]) if expense.get("status") in ("pending", "unverified") else status),
            html.Div([
                html.Button(
                    [html.I(className="fas fa-print me-2"), "Print"],
                    id="expense-btn-print", n_clicks=0,
                    className="btn btn-outline-primary",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                    id="expense-btn-pdf", n_clicks=0,
                    className="btn btn-outline-danger",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-envelope me-2"), "Email Expense"],
                    id="expense-btn-email", n_clicks=0,
                    className="btn btn-outline-info",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "marginTop": "16px", "paddingTop": "14px",
                      "borderTop": "1px solid rgba(120,148,181,0.15)"}),
        ], style={"padding": "16px"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


# ════════════════════════════════════════════════════════════════════════════
# EVENT MOBILE TICKET PASS VIEW & SUBSCRIBABLE ALERTS RENDERERS
# ════════════════════════════════════════════════════════════════════════════

def render_event_mobile_ticket_view(booking: dict) -> "html.Div":
    """
    Renders an in-app, mobile-responsive view of an event booking ticket pass.
    Includes individual scannable QR ticket items (Adult & Child) for gate entry.
    """
    from dash import html, dcc
    import dash_bootstrap_components as dbc

    event_title = booking.get("event_title", "Event Pass")
    event_date = booking.get("event_date", "—")
    event_time = booking.get("event_time", "—")
    venue = booking.get("venue", "—")
    ref = booking.get("booking_reference", "—")
    total_amount = booking.get("total_amount", 0.0)
    items = booking.get("items", [])

    item_cards = []
    for idx, item in enumerate(items, start=1):
        ttype = item.get("ticket_type", "TICKET")
        status = (item.get("status") or "active").lower()
        qr_img = item.get("qr_img") or ""
        payload = item.get("qr_payload") or ""

        status_badge = (
            html.Span("USED", className="badge bg-secondary ms-2")
            if status == "used"
            else html.Span("VALID PASS", className="badge bg-success ms-2")
        )

        item_cards.append(
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.Strong(f"Pass #{idx}: {ttype} Ticket", style={"fontSize": "14px", "color": "#1d74d8"}),
                        status_badge,
                    ], className="d-flex justify-content-between align-items-center mb-2"),
                    html.Div([
                        html.Img(src=qr_img, style={"width": "160px", "height": "160px", "borderRadius": "8px", "border": "1px solid #ddd"})
                    ], className="text-center my-2") if qr_img else None,
                    html.Div(f"Payload: {payload}", style={"fontSize": "11px", "color": "#7d8ea3", "fontFamily": "monospace", "textAlign": "center"}),
                ], style={"padding": "12px"})
            ], className="mb-3", style={"borderRadius": "12px", "border": "1px dashed #1d74d855", "background": "#f8fafd"})
        )

    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fas fa-ticket-alt me-2", style={"fontSize": "20px", "color": "#1d74d8"}),
                html.Strong(event_title, style={"fontSize": "16px", "color": "#1e293b"}),
            ], className="d-flex align-items-center"),
            html.Span(f"Ref: {ref}", style={"fontSize": "12px", "color": "#64748b"}),
        ], className="d-flex justify-content-between align-items-center", style={"background": "#e0f2fe"}),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([html.Small("Date & Time", className="text-muted d-block"), html.Span(f"{event_date} {event_time}", style={"fontWeight": "600"})], width=6),
                dbc.Col([html.Small("Venue", className="text-muted d-block"), html.Span(venue, style={"fontWeight": "600"})], width=6),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([html.Small("Total Amount Paid", className="text-muted d-block"), html.Span(f"₹{total_amount:,.2f}", style={"fontWeight": "700", "color": "#16a34a"})], width=12),
            ], className="mb-3 pb-2", style={"borderBottom": "1px solid #e2e8f0"}),
            html.H6("Individual Entry QR Tickets", style={"fontWeight": "700", "fontSize": "13px", "marginBottom": "12px"}),
            html.Div(item_cards),
        ]),
    ], style={"borderRadius": "16px", "boxShadow": "0 4px 16px rgba(0,0,0,0.08)"})


def render_subscribable_alert_manager(channels: list, active_alerts: list, is_admin: bool = False, apartment_id=None, society_id=None) -> "html.Div":
    """
    Renders Subscribable Alert Manager + Gate KPI Alert Cards.
    Admin: active + inactive channels. Owner: active only + subscribe toggle.
    apartment_id: apartments.id of the logged-in owner.
    society_id: required (admin view) to populate the "Target Apartment"
    dropdown on the Create Channel form — Taxi/Visitor channels must be
    linked to a specific apartment_id so trigger_channel_alert() can resolve
    an owner to push-notify and respond_to_alert() can authorize that owner
    to approve/deny. Without this, apartment_id stays NULL forever and the
    alert is orphaned (no push, invisible on every owner's Channels page,
    rejected by the ownership check even if found). School Bus channels are
    broadcast-to-subscribers and don't need this field.
    """
    from dash import html
    import dash_bootstrap_components as dbc

    # For owner view, filter alerts to only show their apartment's alerts
    # plus any broadcast alerts (School Bus has no apartment_id).
    if not is_admin and apartment_id:
        apt_row = db._execute(
            "SELECT flat_number FROM apartments WHERE id=%s",
            (apartment_id,), fetch_one=True
        )
        owner_flat = (apt_row or {}).get("flat_number", "") if apt_row else ""
        filtered_alerts = [
            a for a in active_alerts
            if (a.get("flat_number") or "") == owner_flat
            or (a.get("type") == "school_bus")
        ]
        active_alerts = filtered_alerts

    kpi_cards = []
    for alert in active_alerts:
        color_map = {
            "yellow": {"bg": "#fef9c3", "border": "#eab308", "text": "#854d0e", "label": "PENDING"},
            "green":  {"bg": "#dcfce7", "border": "#22c55e", "text": "#15803d", "label": "PASS / ALLOWED"},
            "red":    {"bg": "#fee2e2", "border": "#ef4444", "text": "#b91c1c", "label": "DENIED"},
            "orange": {"bg": "#ffedd5", "border": "#f97316", "text": "#c2410c", "label": "CALLING OWNER"},
            "gray":   {"bg": "#f1f5f9", "border": "#94a3b8", "text": "#475569", "label": "INACTIVE"},
        }
        cstyle = color_map.get(alert["color"], color_map["gray"])
        phone = alert.get("owner_phone") or ""
        state_label = cstyle["label"]
        alert_type = alert.get("type", "")
        alert_event_id = alert.get("alert_event_id")
        state = alert.get("state", "pending")

        # Owner action buttons (Approve / Deny) for pending alerts
        owner_actions = None
        if not is_admin and state in ("pending", "calling") and alert_event_id:
            owner_actions = html.Div([
                dbc.Button(
                    [html.I(className="fas fa-check me-1"), "PASS"],
                    id={"type": "owner-approve-alert-btn", "alert_event_id": alert_event_id},
                    color="success",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px", "fontWeight": "700", "marginRight": "6px"},
                ),
                dbc.Button(
                    [html.I(className="fas fa-times me-1"), "Deny"],
                    id={"type": "owner-deny-alert-btn", "alert_event_id": alert_event_id},
                    color="danger",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px"},
                ),
            ], className="mt-2")

        kpi_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(alert["title"], style={"fontWeight": "700", "color": cstyle["text"], "margin": 0}),
                            html.Span(state_label, className="badge", style={"background": cstyle["border"], "color": "#fff", "fontSize": "11px"}),
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(f"Identifier/Flat: {alert.get('identifier') or alert.get('flat_number') or '—'}", style={"fontSize": "12px", "color": "#475569"}),
                        html.Div(f"Owner: {alert.get('owner_name') or 'N/A'}", style={"fontSize": "12px", "color": "#64748b"}) if alert.get("owner_name") else None,
                        html.A(
                            [html.I(className="fas fa-phone-alt me-2"), f"Call Owner for Verbal Confirm ({phone})"],
                            href=f"tel:{phone}",
                            className="btn btn-sm btn-warning w-100 mt-2 text-dark",
                            style={"borderRadius": "8px", "fontWeight": "700"}
                        ) if phone and alert.get("state") in ("pending", "calling") else None,
                        owner_actions,
                    ], style={"padding": "12px"})
                ], style={"borderRadius": "12px", "background": cstyle["bg"], "border": f"2px solid {cstyle['border']}"}),
            ], width=12, md=6, lg=4, className="mb-3")
        )

    # Channel Record KPI Cards
    channel_kpi_cards = []
    for ch in channels:
        ch_id = ch["id"]
        ch_type = ch.get("channel_type", "").replace("_", " ").title()
        ch_name = ch.get("name", "")
        identifier = ch.get("identifier", "")
        is_rec = ch.get("is_recurring")
        is_inactive = ch.get("is_inactive", False)
        sub_count = ch.get("subscriber_count", 0)
        subscribed = ch.get("is_subscribed")

        border_color = "#94a3b8" if is_inactive else "#1d74d8"
        bg_color = "#f8fafc" if is_inactive else "#ffffff"

        channel_kpi_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(ch_name, style={"fontWeight": "700", "color": "#1e293b", "margin": 0}),
                            dbc.Badge("Recurring" if is_rec else "One-Time", color="info" if is_rec else "warning", style={"fontSize": "10px"}),
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(f"Type: {ch_type} | Ref: {identifier or '—'}", style={"fontSize": "12px", "color": "#64748b"}),
                        html.Div([
                            html.Span(f"👥 {sub_count} Subscribers", style={"fontWeight": "600", "fontSize": "12px", "color": "#1d74d8"}),
                            dbc.Button(
                                "Subscribed" if subscribed else "Subscribe",
                                id={"type": "alert-sub-btn", "channel_id": ch_id},
                                color="success" if subscribed else "outline-primary",
                                size="sm",
                                style={"fontSize": "11px", "borderRadius": "6px", "padding": "2px 8px"}
                            ) if not is_admin and not is_inactive else None,
                        ], className="d-flex justify-content-between align-items-center mt-3"),
                        dbc.Button(
                            [html.I(className="fas fa-users me-1"), "View Subscriber Profiles & Status"],
                            id={"type": "view-subscribers-btn", "channel_id": ch_id},
                            color="link",
                            className="p-0 mt-2 text-decoration-none",
                            style={"fontSize": "11px", "fontWeight": "600"}
                        ),
                    ], style={"padding": "14px"})
                ], style={"borderRadius": "12px", "background": bg_color, "border": f"2px solid {border_color}", "boxShadow": "0 2px 8px rgba(0,0,0,0.04)"})
            ], width=12, md=6, lg=4, className="mb-3")
        )

    return html.Div([
        create_channel_card if is_admin else None,
        html.H5("Gate Entry Pass Status (Yellow = Pending | Green = PASS | Red = Denied)",
                style={"fontWeight": "700", "marginBottom": "14px"}),
        dbc.Row(kpi_cards) if kpi_cards else html.Div("No active gate entries evaluating.", className="text-muted mb-4"),
        html.H5("Channel Records (Click to View Subscribers & Status Profiles)",
                style={"fontWeight": "700", "marginTop": "20px", "marginBottom": "14px"}),
        dbc.Row(channel_kpi_cards) if channel_kpi_cards else html.Div("No channel records found.", className="text-muted"),
        html.Div(id="subscribers-modal-container"),
    ])


def render_channel_subscriber_profiles(channel_name: str, subscribers: list) -> "html.Div":
    """
    Renders subscriber profile cards for a channel.
    Border color indicates arrival status:
      Green (#22c55e): Approved / Arrived
      Yellow (#eab308): Pending
      Red (#ef4444): Denied
    """
    from dash import html
    import dash_bootstrap_components as dbc

    profile_cards = []
    for sub in subscribers:
        color = sub["border_color"]
        status_label = sub["status_label"]

        profile_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Strong(f"Flat {sub['flat_number']}", style={"fontSize": "15px", "color": "#1e293b"}),
                            html.Span(status_label, className="badge", style={"background": color, "color": "#fff", "fontSize": "10px"}),
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div([
                            html.I(className="fas fa-user me-2", style={"color": "#64748b"}),
                            html.Span(sub["owner_name"], style={"fontWeight": "600"}),
                        ], className="mb-1", style={"fontSize": "13px"}),
                        html.Div([
                            html.I(className="fas fa-phone-alt me-2", style={"color": "#64748b"}),
                            html.A(sub["phone"], href=f"tel:{sub['phone']}", style={"color": "#1d74d8", "textDecoration": "none"}),
                        ], className="mb-1", style={"fontSize": "12px"}),
                        html.Div([
                            html.I(className="fas fa-envelope me-2", style={"color": "#64748b"}),
                            html.Span(sub["email"], style={"color": "#64748b"}),
                        ], style={"fontSize": "12px"}),
                    ], style={"padding": "14px"})
                ], style={
                    "borderRadius": "10px",
                    "borderLeft": f"6px solid {color}",
                    "borderTop": "1px solid #e2e8f0",
                    "borderRight": "1px solid #e2e8f0",
                    "borderBottom": "1px solid #e2e8f0",
                    "background": "#ffffff",
                    "boxShadow": "0 2px 6px rgba(0,0,0,0.04)"
                })
            ], width=12, md=6, className="mb-3")
        )

    return dbc.Card([
        dbc.CardHeader([
            html.Strong(f"Subscribers for Channel: {channel_name}", style={"fontSize": "16px"}),
            html.Span(f"Total: {len(subscribers)} subscribers", className="badge bg-secondary ms-2"),
        ], className="d-flex justify-content-between align-items-center", style={"background": "#f1f5f9"}),
        dbc.CardBody([
            dbc.Row(profile_cards) if profile_cards else html.Div("No subscribers found for this channel.", className="text-muted")
        ])
    ], className="mt-3", style={"borderRadius": "12px", "border": "1px solid #cbd5e1"})


def _render_channel_subscribers(record_dict: dict) -> list:
    subscribers = record_dict.get("_subscribers") or []
    if not subscribers:
        return []
    rows = []
    for sub in subscribers:
        flat = sub.get("flat_number") or "—"
        name = sub.get("owner_name") or "—"
        rows.append(
            html.Tr([
                html.Td(flat, style={"fontSize": "13px"}),
                html.Td(name, style={"fontSize": "13px"}),
            ])
        )
    return [
        html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
        html.H6("Subscribers", style={"fontWeight": "700", "color": "#15304f", "fontSize": "14px", "marginBottom": "8px"}),
        dbc.Table([
            html.Thead(html.Tr([html.Th("Flat", style={"fontSize": "12px"}), html.Th("Owner", style={"fontSize": "12px"})])),
            html.Tbody(rows),
        ], bordered=False, striped=True, style={"fontSize": "13px"}),
        html.Small(f"{len(subscribers)} total subscriber(s)", style={"color": "#999", "fontSize": "12px"}),
    ]


def _render_channel_alert_events(record_dict: dict) -> list:
    events = record_dict.get("_alert_events") or []
    if not events:
        return []
    rows = []
    for ev in events:
        state = ev.get("state", "—")
        visitor = ev.get("visitor_name") or "—"
        created = ev.get("triggered_at", "")
        if isinstance(created, (datetime, date)):
            created = created.strftime("%d/%m/%Y %H:%M")
        rows.append(
            html.Tr([
                html.Td(html.Span(state.upper(), className="badge", style={
                    "background": "#e59620" if state == "pending" else "#17976e" if state == "resolved" else "#de5c52" if state == "denied" else "#64748b",
                    "color": "#fff", "fontSize": "10px"
                }), style={"fontSize": "13px"}),
                html.Td(visitor, style={"fontSize": "13px"}),
                html.Td(created, style={"fontSize": "13px"}),
            ])
        )
    return [
        html.Hr(style={"margin": "4px 0 12px", "opacity": "0.2"}),
        html.H6("Recent Alert Events", style={"fontWeight": "700", "color": "#15304f", "fontSize": "14px", "marginBottom": "8px"}),
        dbc.Table([
            html.Thead(html.Tr([
                html.Th("State", style={"fontSize": "12px"}),
                html.Th("Visitor", style={"fontSize": "12px"}),
                html.Th("Triggered", style={"fontSize": "12px"}),
            ])),
            html.Tbody(rows),
        ], bordered=False, striped=True, style={"fontSize": "13px"}),
        html.Small(f"{len(events)} most recent event(s)", style={"color": "#999", "fontSize": "12px"}),
    ]


def render_form_channel_new(society_id: int | None = None, apartment_options: list | None = None, caller_apartment_id: int | None = None) -> "html.Div":
    """
    Dedicated New Channel form for the drilldown system.
    Uses generic form-field pattern so handle_form_submit in
    drilldown_callbacks.py processes the submission.
    """
    from dash import html
    import dash_bootstrap_components as dbc

    apartment_options = apartment_options or []
    is_locked_apartment = bool(caller_apartment_id)

    return dbc.Card([
        dbc.CardHeader(html.H6("Create New Channel", style={"fontWeight": "700", "margin": 0})),
        dbc.CardBody([
            dbc.Alert(
                [html.I(className="fas fa-info-circle me-2"),
                 "New channels start active and can receive alerts right away."],
                color="info",
                style={"fontSize": "12px", "fontWeight": "600", "padding": "8px 12px",
                       "borderRadius": "8px", "marginBottom": "12px"},
            ),
            dcc.Input(id={"type": "form-entity-pk", "entity": "channel"}, type="hidden", value=""),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Channel Type"),
                    dcc.Dropdown(
                        id={"type": "form-field", "entity": "channel", "field": "channel_type"},
                        options=[
                            {"label": "School Bus", "value": "school_bus"},
                            {"label": "Taxi", "value": "taxi"},
                            {"label": "Visitor", "value": "visitor"},
                        ],
                        value="school_bus",
                        clearable=False,
                        style={"fontSize": "13px"},
                    ),
                ], width=4),
                dbc.Col([
                    dbc.Label("Channel Name"),
                    dcc.Input(
                        id={"type": "form-field", "entity": "channel", "field": "name"},
                        type="text",
                        placeholder="e.g. DPS Bus #12 or Uber Taxi",
                        style={"fontSize": "13px"},
                    ),
                ], width=5),
                dbc.Col([
                    dbc.Label("Identifier (Reg # / Ref)"),
                    dcc.Input(
                        id={"type": "form-field", "entity": "channel", "field": "identifier"},
                        type="text",
                        placeholder="e.g. MH-02-1234",
                        style={"fontSize": "13px"},
                    ),
                ], width=3),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Target Apartment (required for Taxi / Visitor)"),
                    dcc.Dropdown(
                        id={"type": "form-field", "entity": "channel", "field": "apartment_id"},
                        options=apartment_options,
                        value=caller_apartment_id if is_locked_apartment else None,
                        placeholder="Select flat…" if not is_locked_apartment else "Your flat (locked)",
                        clearable=not is_locked_apartment,
                        disabled=is_locked_apartment,
                        style={"fontSize": "13px"},
                    ),
                ], width=12),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    dbc.Switch(
                        id={"type": "form-field", "entity": "channel", "field": "is_recurring"},
                        label="Recurring Channel (ON = Daily Recurring | OFF = One-Time / Per-Day)",
                        value=True,
                    ),
                ], width=8),
                dbc.Col([
                    dbc.Button("Create Channel", id={"type": "form-submit", "entity": "channel", "card_id": "form_channel_new"},
                               color="primary", className="w-100",
                               style={"borderRadius": "8px", "fontWeight": "600"}),
                ], width=4),
            ]),
        ]),
    ], className="mb-4", style={"borderRadius": "12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"})
