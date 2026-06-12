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
                     page_size: int = 15, auth_data: dict | None = None) -> html.Div:

    auth_data  = auth_data or {}
    user_role  = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")

    # ── Resolve permissions for this role × entity ─────────────────────────
    allowed = _perms_for(user_role, entity)

    total_pages = max(1, -(-total_rows // page_size))

    # ── Header row ──────────────────────────────────────────────────────────
    header_cells = []
    for c in columns:
        col_label = c.get("label") or c.get("name") or c.get("field", "").title()
        header_cells.append(html.Th(col_label, style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
            "padding": "10px 8px", "whiteSpace": "nowrap",
        }))
    if allowed:                         # only show Actions col if ≥1 action
        header_cells.append(html.Th("Actions", style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3",
            "padding": "10px 8px",
        }))

    # ── Data rows ────────────────────────────────────────────────────────────
    body_rows = []
    for row in rows:
        row_dict = (row.to_dict(include_calculated=True)
                    if hasattr(row, "to_dict") else dict(row))
        pk_val = str(row_dict.get("id") or row_dict.get("ID") or "0")

        cells = []
        for c in columns:
            field_key = c.get("field") or c.get("name") or ""
            val = row_dict.get(field_key)
            # Format booleans & dates nicely
            if isinstance(val, bool):
                val = html.Span(
                    ["✓" if val else "✗"],
                    style={"color": "#17976e" if val else "#de5c52",
                           "fontWeight": "700"},
                )
            elif isinstance(val, (date, datetime)):
                val = val.strftime("%d %b %Y") if val else "—"
            elif val is None:
                val = "—"
            else:
                val = str(val)
            cells.append(html.Td(val, style={
                                     "fontSize": "12px", "verticalAlign": "middle",
                                     "padding": "8px 8px",
                                    }
                ))

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
                        auth_data: dict | None = None) -> html.Div:
    auth_data  = auth_data or {}
    user_role  = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")
    allowed    = _perms_for(user_role, entity)

    record_dict = (record.to_dict(include_calculated=True)
                   if hasattr(record, "to_dict") else record)
    pk_val = record_dict.get("id", "")

    if entity == "society":
        img_society_id = pk_val
    else:
        img_society_id = (record_dict.get("_image_society_id")
                          or record_dict.get("society_id"))

    # ── Fields ──────────────────────────────────────────────────────────────
    field_rows = []
    for f in fields:
        field_type = f.get("type", "text")
        if field_type == "image":
            image_path = record_dict.get(f["field"])
            if image_path:
                full_url = get_image_url(image_path, img_society_id,
                                         entity, pk_val)
                field_rows.append(html.Div([
                    html.Div([
                        html.I(className="fas fa-image me-2",
                               style={"color": "#aaa", "width": "14px"}),
                        html.Span(f["label"], style={"color": "#7d8ea3",
                                                     "fontSize": "11px",
                                                     "fontWeight": "600"}),
                    ], style={"marginBottom": "8px"}),
                    html.Img(src=full_url, style={
                        "maxWidth": "300px", "maxHeight": "200px",
                        "borderRadius": "8px", "border": "1px solid #ddd",
                        "objectFit": "contain", "background": "#fff",
                        "padding": "4px", "paddingLeft": "22px",
                    }),
                ], style={"marginBottom": "14px"}))
            continue

        val = record_dict.get(f["field"])
        if val is None:
            val = "—"
        elif isinstance(val, bool):
            val = html.Span("✓ Active" if val else "✗ Inactive",
                            style={"color": "#17976e" if val else "#de5c52",
                                   "fontWeight": "600"})
        elif isinstance(val, (date, datetime)):
            val = val.strftime("%d %b %Y")
        elif isinstance(val, Decimal):
            val = f"₹{val:,.2f}"
        else:
            val = str(val)

        field_rows.append(html.Div([
            html.Div([
                html.I(className=f.get("icon", "fas fa-circle-dot"),
                       style={"color": color, "width": "14px",
                              "fontSize": "10px"}),
                html.Span(f["label"],
                          style={"color": "#7d8ea3", "fontSize": "11px",
                                 "fontWeight": "600", "marginLeft": "6px"}),
            ], style={"marginBottom": "2px"}),
            html.Div(val, style={"fontSize": "14px", "fontWeight": "500",
                                 "color": "#15304f", "paddingLeft": "22px"}),
        ], style={"marginBottom": "14px"}))

    # ── Action buttons filtered by role ─────────────────────────────────────
    action_btns = []
    for act in (actions or []):
        # Skip edit/delete actions for roles that don't have that permission
        act_id = act.get("action_id", "")
        if act_id == "edit" and "edit" not in allowed:
            continue
        if act_id == "delete" and "delete" not in allowed:
            continue
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
            html.Div(field_rows),
            html.Hr(style={"margin": "8px 0", "opacity": "0.3"})
            if action_btns else None,
            html.Div(action_btns,
                     style={"display": "flex", "flexWrap": "wrap"}),
        ], style={"padding": "16px", "maxHeight": "600px",
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
                     society_id: int | None = None) -> html.Div:
    prefill = prefill or {}
    form_rows = []

    for f in fields:
        fid      = f["id"]
        pre_val  = prefill.get(fid)
        ftype    = f.get("type", "text")
        required = f.get("required", False)
        label_txt = f["label"] + (" *" if required else "")

        if ftype == "select":
            opts = [{"label": o.title(), "value": o}
                    for o in f.get("options", [])]
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
            ctrl = dcc.DatePickerSingle(
                id={"type": "form-field", "entity": entity, "field": fid},
                date=str(pre_val) if pre_val else None,
                style={"width": "100%"},
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
                        id={"type": "form-field", "entity": entity,
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
        elif ftype == "account_dropdown_expense":
            ctrl = html.Div([
                dcc.Dropdown(
                    id={"type": "form-field", "entity": entity, "field": fid},
                    options=[], value=pre_val,
                    placeholder="Select expense account…",
                    style={"fontSize": "13px"},
                ),
                dcc.Store(
                    id={"type": "account-filter-store", "entity": entity,
                        "field": fid},
                    data={"filter": "Dr", "society_id": society_id},
                ),
            ])
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
