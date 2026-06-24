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

from app.models import (
    Apartment, Vendor, SecurityStaff, Society, Account,
    Event, Concern, Receivable, Transaction
)
from app.security.rbac import RBACManager, Permission

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
# PORTAL PERMISSION MATRIX
# key = (role, entity)  →  set of allowed actions
# ════════════════════════════════════════════════════════════════════════════

_PORTAL_PERMS: dict[tuple[str, str], set[str]] = {
    # ── ADMIN: full CRUD on everything ───────────────────────────────────────
    ("admin", "*"):            {"view", "edit", "delete", "new"},

    # ── MASTER: societies only (view + edit + new), no delete ─────────────
    ("master", "societies"):   {"view", "edit", "new"},
    ("master", "*"):           {"view"},

    # ── APARTMENT: view own data only, can raise concern / pay ────────────
    ("apartment", "apartments"):  {"view"},
    ("apartment", "concerns"):    {"view", "new"},
    ("apartment", "events"):      {"view"},
    ("apartment", "gate_logs"):   {"view"},
    ("apartment", "receipts_tbl"):{"view"},
    ("apartment", "cashbook"):    {"view"},
    ("apartment", "*"):           set(),

    # ── VENDOR: view own data + can see events/concerns ───────────────────
    ("vendor", "vendors"):        {"view"},
    ("vendor", "events"):         {"view"},
    ("vendor", "concerns"):       {"view"},
    ("vendor", "gate_logs"):      {"view"},
    ("vendor", "receipts_tbl"):   {"view"},
    ("vendor", "cashbook"):       {"view"},
    ("vendor", "*"):              set(),

    # ── SECURITY: view most lists + can create receipts ───────────────────
    ("security", "apartments"):   {"view"},
    ("security", "vendors"):      {"view"},
    ("security", "security"):     {"view"},
    ("security", "events"):       {"view"},
    ("security", "concerns"):     {"view"},
    ("security", "gate_logs"):    {"view"},
    ("security", "receipts_tbl"): {"view", "new"},   # create receipt
    ("security", "cashbook"):     {"view"},
    ("security", "*"):            set(),
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
}

def _display_value(field_key: str, row_dict: dict):
    alt_key = _FK_HUMAN_ALIASES.get(field_key)
    if alt_key:
        alt_val = row_dict.get(alt_key)
        if alt_val not in (None, ""):
            return alt_val
    return row_dict.get(field_key)


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
        if entity == "society" and pk:
            return f"/assets/{pk}/{path}"
        elif society_id and pk:
            if entity in ("apartment", "vendor", "security", "concern", "event"):
                return f"/assets/{society_id}/{entity}/{pk}/{path}"
            else:
                return f"/assets/{society_id}/{entity}_{pk}/{path}"
        elif society_id or entity:
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
        children=[
            html.Button(
                id={"type": "kpi-card", "card_id": card_id},
                n_clicks=0,
                style={"display": "none"},
            ),
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

def render_list_card(card_id: str, title: str, icon: str,
                     columns: list[dict], rows: list[dict],
                     entity: str, page: int = 1, total_rows: int = 0,
                     page_size: int = 15, auth_data: dict | None = None,
                     filters: dict | None = None) -> html.Div:

    auth_data  = auth_data or {}
    role  = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")

    # ── Resolve permissions for this role × entity ─────────────────────────
    allowed = _perms_for(role, entity)
    hidden = _context_hidden_fields(filters)
    visible_columns = [
        c for c in columns
        if (c.get("field") or c.get("name") or "") not in hidden
        and _field_visible(entity, c.get("field") or c.get("name") or "", role)
    ]
    total_pages = max(1, -(-total_rows // page_size))

    # ── Header row ──────────────────────────────────────────────────────────
    header_cells = []
    for c in visible_columns:
        col_label = c.get("label") or c.get("name") or c.get("field", "").title()
        header_cells.append(html.Th(col_label, style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
            "padding": "10px 8px", "whiteSpace": "nowrap",
        }))
    if allowed:
        header_cells.append(html.Th("Actions", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
            "padding": "10px 8px",
        }))

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
            if fmt in _FIELD_FORMATTERS and val is not None:
                val = _FIELD_FORMATTERS[fmt](val)
            if isinstance(val, bool):
                val = html.Span(
                    ["✓" if val else "✗"],
                    style={"color": "#17976e" if val else "#de5c52", "fontWeight": "700"},
                )
            elif isinstance(val, (date, datetime)):
                val = val.strftime("%d %b %Y") if val else "—"
            
            elif val is None:
                val = "—"
            else:
                val = str(val)
            cells.append(html.Td(val, style={
                "fontSize": "12px", "verticalAlign": "middle", "padding": "8px 8px",
            }))

        # ── Action buttons scoped by portal permissions ──────────────────
        if allowed:
            action_btns = []

            if "view" in allowed:
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-eye"),
                    id={"type": "list-view", "entity": entity, "pk": pk_val},
                    size="sm", color="info", outline=True,
                    title="View details",
                    style={"fontSize": "11px", "padding": "3px 7px",
                           "borderRadius": "7px"},
                ))

            if "edit" in allowed:
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-edit"),
                    id={"type": "list-edit", "entity": entity, "pk": pk_val},
                    size="sm", color="primary", outline=True,
                    title="Edit record",
                    style={"fontSize": "11px", "padding": "3px 7px",
                           "borderRadius": "7px"},
                ))

            if "delete" in allowed:
                action_btns.append(dbc.Button(
                    html.I(className="fas fa-trash-alt"),
                    id={"type": "list-delete", "entity": entity, "pk": pk_val},
                    size="sm", color="danger", outline=True,
                    title="Delete record",
                    style={"fontSize": "11px", "padding": "3px 7px",
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
                style={"cursor": "pointer", "transition": "background 0.12s ease"},
                title="Click to open profile",
            )
        )
        

    if not body_rows:
        span = len(columns) + (1 if allowed else 0)
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
            "receipts_tbl": "form_receipt_new",
            "expenses_tbl": "form_expense_new",
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

    header_right += [
        dbc.Input(
            id={"type": "list-search", "entity": entity},
            placeholder="Search…", size="sm", debounce=True,
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

    return dbc.Card([
        dbc.CardHeader(
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
        dbc.CardBody([
            html.Div(
                dbc.Table([
                    html.Thead(html.Tr(header_cells),
                               style={"position": "sticky", "top": 0,
                                      "zIndex": 1,
                                      "background": "rgba(248,251,255,0.97)"}),
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
            or record_dict.get("_image_society_id")
            or society_id                        # ← key fix: use auth society_id
        )
        img_entity_pk = pk_val

    # ── Split fields into image fields and text fields ───────────────────
    visible_fields = [
        f for f in fields
        if f.get("field") not in hidden
        and _field_visible(entity_plural, f.get("field"), role)
    ]
    image_fields = [f for f in visible_fields if f.get("type") == "image"]
    text_fields  = [f for f in visible_fields if f.get("type") != "image"]

    # ── Image gallery (full-width, above the 2-col grid) ────────────────
    image_section = []
    for f in image_fields:
        image_path = record_dict.get(f["field"])
        print(f"[IMG DEBUG] field={f['field']} value={image_path!r} "
              f"entity={entity} pk={img_entity_pk} sid={img_society_id}")  # remove after fix confirmed
        if not image_path or str(image_path).strip() in ("", "None"):
            continue
        full_url = get_image_url(
            str(image_path).strip(),
            img_society_id,
            entity,
            img_entity_pk,          # ← was pk_val but now named consistently
        )
        print(f"[IMG DEBUG] resolved URL={full_url!r}")  # remove after fix confirmed
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
    def _field_cell(f: dict) -> html.Div:
        val = _display_value(f["field"], record_dict)
        if val is None:
            val = "—"
        elif isinstance(val, bool):
            val = html.Span("✓ Active" if val else "✗ Inactive",
                            style={"color": "#17976e" if val else "#de5c52", "fontWeight": "600"})
        elif isinstance(val, (date, datetime)):
            val = val.strftime("%d %b %Y")
        elif isinstance(val, Decimal):
            val = f"₹{val:,.2f}"
        else:
            val = str(val)

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
        })

    text_cells = [_field_cell(f) for f in text_fields]

    # ── Action buttons filtered by role ─────────────────────────────────
    action_btns = []
    for act in (actions or []):
        act_id = act.get("action_id", "")
        if act_id == "edit"   and "edit"   not in allowed: continue
        if act_id == "delete" and "delete" not in allowed: continue
        action_btns.append(dbc.Button(
            [html.I(className=f"fas {act.get('icon', 'fa-bolt')} me-2"),
             act["label"]],
            id={"type": "profile-action", "entity": entity, "pk": str(pk_val),
                "action": act_id, "target": act.get("target_card", "")},
            n_clicks=0, color=act.get("color", "primary"), size="sm",
            className="me-2 mb-2",
            style={"borderRadius": "10px", "fontWeight": "600"},
        ))

    return dbc.Card([
        dbc.CardHeader(
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
        dbc.CardBody([

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
    prefill = prefill or {}
    entity_plural = to_plural(entity)
    fields = [f for f in fields if _field_visible(entity_plural, f.get("id"), role or "admin")]
    form_rows = []

    for f in fields:
        fid      = f["id"]
        pre_val  = prefill.get(fid)
        ftype    = f.get("type", "text")
        required = f.get("required", False)
        label_txt = f["label"] + (" *" if required else "")

        if ftype == "select" and f.get("options_from"):
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
            opts = [{"label": o.title(), "value": o} for o in f.get("options", [])]
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
            from datetime import datetime as _dt
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type="date",
                value=str(pre_val) if pre_val else _dt.today().strftime("%Y-%m-%d"),
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

        elif ftype == "time":
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type="time",
                value=str(pre_val) if pre_val else "",
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

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
                        "WHERE society_id=%s AND (drcr_account=%s OR drcr_account IS NULL) "
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
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type=ftype,
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"],
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

        # Store entity PK for image uploads
        form_rows.append(
            dcc.Input(
                id={"type": "form-entity-pk", "entity": entity},
                type="hidden",
                value=str(prefill.get("id", "")),
            ) if not form_rows else None  # only add once
        )

        form_rows.append(dbc.Row([
            dbc.Col(
                dbc.Label(label_txt,
                          style={"fontSize": "12px", "fontWeight": "500",
                                 "color": "#555"}),
                width=4, style={"paddingTop": "6px"},
            ),
            dbc.Col(ctrl, width=8),
        ], className="mb-2"))

    # Filter out None (the PK input was only added once)
    form_rows = [r for r in form_rows if r is not None]

    return dbc.Card([
        dbc.CardHeader(
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
        ),
        dbc.CardBody([
            html.Div(form_rows),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), submit_label],
                id={"type": "form-submit", "entity": entity,
                    "card_id": card_id},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"padding": "16px", "maxHeight": "520px",
                  "overflowY": "auto"}),
    ], style={
        "borderRadius": "16px", "border": f"1px solid {color}22",
        "boxShadow": f"0 10px 30px {color}18",
        "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
        "overflow": "hidden",
    })

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
) -> html.Div:
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

    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div(html.I(className="fas fa-rupee-sign",
                                style={"color": "#fff", "fontSize": "16px"}),
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
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            dues_summary,
            dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                f"Payment applied FIFO — oldest dues first. "
                f"Excess beyond ₹{pending_dues:,.2f} credited as advance.",
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
                dbc.Col(dbc.Label("Amount (₹) *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Input(
                    id={"type": "form-field", "entity": "pay_due", "field": "amount"},
                    type="number", value=str(prefill_amount) if prefill_amount else "",
                    min=1, step=0.01, style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            # Mode
            dbc.Row([
                dbc.Col(dbc.Label("Payment Mode *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dcc.Dropdown(
                    id={"type": "form-field", "entity": "pay_due", "field": "mode"},
                    options=[
                        {"label": "Cash",          "value": "cash"},
                        {"label": "Bank Transfer", "value": "bank_transfer"},
                        {"label": "UPI",           "value": "upi"},
                        {"label": "Cheque",        "value": "cheque"},
                        {"label": "Other",         "value": "other"},
                    ],
                    value=prefill_mode, clearable=False,
                    style={"fontSize": "13px"},
                ), width=8),
            ], className="mb-2"),
            # Particulars
            dbc.Row([
                dbc.Col(dbc.Label("Particulars *",
                                  style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                        width=4, style={"paddingTop": "6px"}),
                dbc.Col(dbc.Textarea(
                    id={"type": "form-field", "entity": "pay_due", "field": "particulars"},
                    value=prefill_particulars, rows=2,
                    style={"fontSize": "13px", "borderRadius": "10px"},
                ), width=8),
            ], className="mb-2"),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), "Apply Payment (FIFO)"],
                id={"type": "form-submit", "entity": "pay_due", "card_id": "form_pay_dues_new"},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"padding": "16px"}),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})


# ════════════════════════════════════════════════════════════════════════════
# NOC CARD  — rich-text editor with eligibility banner + Print/PDF/Email
# ════════════════════════════════════════════════════════════════════════════

def render_noc_card(apt: dict, society: dict,
                    eligible: bool = True, reason: str = "",
                    outstanding: float = 0) -> html.Div:
    from datetime import date as _date
    color     = "#15304f"
    flat_no   = apt.get("flat_number", "____")
    owner     = apt.get("owner_name", "____")
    society_nm = society.get("name", "____")
    sec_name  = society.get("secretary_name") or society.get("contact_person", "____")
    today     = _date.today().strftime("%d %B %Y")

    noc_text = (
        f"NO OBJECTION CERTIFICATE\n"
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
                    html.Div(f"Flat {flat_no} — {owner}",
                             style={"fontSize": "11px", "color": "#999"}),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "12px 16px",
                   "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            elig_banner,
            # Editable NOC textarea — no Dash ID, driven purely by JS
            dbc.Label("Edit NOC text below before printing:",
                      style={"fontSize": "11px", "color": "#7d8ea3",
                             "fontWeight": "600", "marginBottom": "4px"}),
            html.Textarea(
                noc_text,
                className="noc-editor-ta",
                style={
                    "width": "100%",
                    "minHeight": "400px",
                    "border": "1px solid #d0dae8",
                    "borderRadius": "10px",
                    "padding": "24px",
                    "fontSize": "13px",
                    "lineHeight": "1.9",
                    "fontFamily": "Georgia, 'Times New Roman', serif",
                    "background": "#fff",
                    "resize": "vertical",
                    "boxShadow": "inset 0 1px 4px rgba(0,0,0,0.04)",
                },
            ),
            # Action buttons — onclick JS, no Dash IDs needed
            html.Div([
                html.Button(
                    [html.I(className="fas fa-print me-2"), "Print"],
                    className="btn btn-outline-primary noc-btn-print",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-file-pdf me-2"), "Save as PDF"],
                    className="btn btn-outline-danger noc-btn-pdf",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
                html.Button(
                    [html.I(className="fas fa-envelope me-2"), "Email NOC"],
                    className="btn btn-outline-info noc-btn-email",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "marginTop": "16px", "paddingTop": "14px",
                      "borderTop": "1px solid rgba(120,148,181,0.15)"}),
        ], style={"padding": "16px"}),

        # Inline script — uses class selectors so no Dash ID conflicts
        html.Script(f"""
(function(){{
  var card = document.currentScript.parentElement;
  var ta   = card.querySelector('.noc-editor-ta');
  function getText(){{ return ta ? ta.value : ''; }}
  function toHtml(txt){{
    return txt.split('\\n').map(function(l){{
      return '<p style="margin:4px 0">'+(l||'&nbsp;')+'</p>';
    }}).join('');
  }}
  var btnPrint = card.querySelector('.noc-btn-print');
  var btnPdf   = card.querySelector('.noc-btn-pdf');
  var btnEmail = card.querySelector('.noc-btn-email');
  if(btnPrint) btnPrint.addEventListener('click', function(){{
    var w = window.open('','_blank');
    w.document.write('<html><head><title>NOC</title><style>body{{font-family:Georgia,serif;padding:60px;font-size:13pt;line-height:1.9;max-width:700px;margin:auto}}</style></head><body>');
    w.document.write(toHtml(getText()));
    w.document.write('</body></html>');
    w.document.close(); w.focus();
    setTimeout(function(){{ w.print(); }}, 400);
  }});
  if(btnPdf) btnPdf.addEventListener('click', function(){{
    var blob = new Blob([
      '<html><head><style>body{{font-family:Georgia,serif;padding:60px;font-size:13pt;line-height:1.9;max-width:700px;margin:auto}}</style></head><body>'+toHtml(getText())+'</body></html>'
    ],{{type:'text/html'}});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'NOC_{flat_no_safe}.html';
    a.click();
  }});
  if(btnEmail) btnEmail.addEventListener('click', function(){{
    window.location.href = 'mailto:?subject=No+Objection+Certificate&body='+encodeURIComponent(getText());
  }});
}})();
"""),
    ], style={"borderRadius": "16px", "border": f"1px solid {color}22",
              "boxShadow": f"0 10px 30px {color}18", "overflow": "hidden"})
