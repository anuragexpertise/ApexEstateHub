# app/dash_apps/drilldown/renderers.py
"""
COMPLETE RENDERERS - All Card Types for All 5 Portals
======================================================
- Works with OOP models from loaders
- Implements RBAC checks
- Handles image upload/storage
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
    "primary":    "#1d74d8",
    "success":    "#17976e",
    "warning":    "#e59620",
    "danger":     "#de5c52",
    "info":       "#0ea5a8",
    "muted":      "#7d8ea3",
}

# ════════════════════════════════════════════════════════════════════════════
# IMAGE URL RESOLUTION
# ════════════════════════════════════════════════════════════════════════════

def get_image_url(image_path: str | None, society_id: int | None = None,
                  entity: str = None, pk: int | None = None) -> str | None:
    """Convert stored filename to full asset URL."""
    if not image_path or str(image_path).strip() == "":
        return None
    
    path = str(image_path).strip()
    
    # Already a full URL or data URI
    if path.startswith(('http://', 'https://', 'data:image', '/assets/')):
        return path
    
    # Just a filename - construct the correct path
    if '/' not in path and '\\' not in path:
        # SPECIAL CASE: Societies use their own ID
        if entity == "society" and pk:
            return f"/assets/{pk}/{path}"
        
        # Entity with society + pk
        elif society_id and pk:
            if entity in ("apartment", "vendor", "security", "concern", "event"):
                return f"/assets/{society_id}/{entity}/{pk}/{path}"
            else:
                return f"/assets/{society_id}/{entity}_{pk}/{path}"
        
        # New record (temp folder)
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
    """Render a KPI card with optional click navigation."""
    return html.Div(
        [
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
                            html.Div(
                                value,
                                style={
                                    "fontSize": "24px", "fontWeight": "800",
                                    "color": "#15304f", "lineHeight": "1",
                                },
                            ),
                            html.Div(
                                title,
                                style={
                                    "fontSize": "11px", "fontWeight": "600",
                                    "color": "#7d8ea3", "marginTop": "4px",
                                    "textTransform": "uppercase",
                                },
                            ),
                            html.Div(subtitle, style={
                                "fontSize": "10px", "color": "#aaa", "marginTop": "2px",
                            }) if subtitle else None,
                        ],
                        style={
                            "padding": "14px",
                            "textAlign": "center",
                        }
                    ),
                    html.Div(
                        style={
                            "position": "absolute", "left": 0, "top": 0,
                            "bottom": 0, "width": "4px", "background": color,
                            "borderRadius": "4px 0 0 4px",
                        }
                    ),
                ],
                style={
                    "position": "relative",
                    "cursor": "pointer" if clickable else "default",
                    "border": f"1px solid {color}22",
                    "boxShadow": f"0 4px 12px {color}18",
                    "borderRadius": "12px",
                    "overflow": "hidden",
                    "background": f"linear-gradient(135deg, rgba(255,255,255,0.95), rgba(248,251,255,0.9))",
                    "backdropFilter": "blur(10px)",
                },
            ),
        ]
    )

# ════════════════════════════════════════════════════════════════════════════
# LIST CARD RENDERER
# ════════════════════════════════════════════════════════════════════════════

def render_list_card(card_id: str, title: str, icon: str,
                     columns: list[dict], rows: list[dict],
                     entity: str, page: int = 1, total_rows: int = 0,
                     page_size: int = 15, auth_data: dict | None = None) -> html.Div:
    """Generic list card with pagination, search, and actions."""
    auth_data = auth_data or {}
    user_role = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")
    
    total_pages = max(1, -(-total_rows // page_size))
    
    # ── Header cells ──
    # Handle flexible column format: {"label": "X", "field": "y"} or {"name": "X", "field": "y"}
    header_cells = []
    for c in columns:
        col_label = c.get("label") or c.get("name") or c.get("field", "").title()
        header_cells.append(html.Th(col_label, style={
            "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3"
        }))
    header_cells.append(html.Th("Actions", style={
        "fontSize": "11px", "fontWeight": "700", "color": "#7d8ea3"
    }))
    
    # ── Data rows ──
    body_rows = []
    for row in rows:
        row_dict = row.to_dict(include_calculated=True) if hasattr(row, 'to_dict') else row
        pk_val = row_dict.get("id")
        
        cells = []
        for c in columns:
            field_key = c.get("field") or c.get("name") or list(row_dict.keys())[0]
            val = str(row_dict.get(field_key, "—") or "—")
            cells.append(html.Td(
                val,
                style={"fontSize": "12px", "verticalAlign": "middle"},
            ))
        
        # Action buttons
        can_view = RBACManager.has_permission(user_role, f"profile_{entity}", Permission.VIEW, society_id)
        can_edit = RBACManager.has_permission(user_role, f"form_{entity}_edit", Permission.EDIT, society_id)
        can_delete = RBACManager.has_permission(user_role, f"form_{entity}_edit", Permission.DELETE, society_id)
        
        actions = []
        if can_view:
            actions.append(
                dbc.Button(
                    html.I(className="fas fa-eye"),
                    id={"type": "list-view", "entity": entity, "pk": str(pk_val)},
                    size="sm", color="info", outline=True, style={"fontSize": "11px"},
                )
            )
        if can_edit:
            actions.append(
                dbc.Button(
                    html.I(className="fas fa-edit"),
                    id={"type": "list-edit", "entity": entity, "pk": str(pk_val)},
                    size="sm", color="primary", outline=True, style={"fontSize": "11px"},
                )
            )
        if can_delete:
            actions.append(
                dbc.Button(
                    html.I(className="fas fa-trash"),
                    id={"type": "list-delete", "entity": entity, "pk": str(pk_val)},
                    size="sm", color="danger", outline=True, style={"fontSize": "11px"},
                )
            )
        
        cells.append(html.Td(
            html.Div(actions, style={"display": "flex", "gap": "4px"}),
        ))
        
        body_rows.append(html.Tr(cells))
    
    if not body_rows:
        body_rows = [html.Tr(html.Td(
            html.Div([
                html.I(className="fas fa-inbox me-2", style={"color": "#ccc"}),
                "No records found"
            ]),
            colSpan=len(columns) + 1,
            className="text-center text-muted",
            style={"padding": "32px"},
        ))]
    
    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div([
                    html.I(className=f"fas {icon} me-2", style={"color": COLORS["primary"]}),
                    html.Strong(title),
                    dbc.Badge(str(total_rows), color="primary", className="ms-2"),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div([
                    dbc.Input(
                        id={"type": "list-search", "entity": entity},
                        placeholder="Search…", size="sm", debounce=True,
                        style={"width": "140px", "fontSize": "12px", "borderRadius": "8px"},
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-download me-1"), "CSV"],
                        id={"type": "btn-csv", "entity": entity},
                        size="sm", color="success", outline=True,
                        style={"fontSize": "11px", "borderRadius": "8px"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "6px"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
            style={"padding": "10px 16px", "background": "linear-gradient(180deg, rgba(255,255,255,0.85), rgba(248,251,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div(
                dbc.Table([
                    html.Thead(html.Tr(header_cells)),
                    html.Tbody(body_rows),
                ], hover=True, responsive=True, size="sm", style={"marginBottom": 0}),
                style={"overflowX": "auto", "maxHeight": "420px", "overflowY": "auto"},
            ),
            html.Div([
                html.Small(f"Page {page} of {total_pages}", style={"color": "#aaa", "fontSize": "11px"}),
                html.Div([
                    dbc.Button(
                        html.I(className="fas fa-chevron-left"),
                        id={"type": "list-prev", "entity": entity},
                        size="sm", disabled=(page <= 1),
                        style={"fontSize": "11px"},
                    ),
                    html.Span(f"{page} / {total_pages}", style={"padding": "0 10px", "fontSize": "12px"}),
                    dbc.Button(
                        html.I(className="fas fa-chevron-right"),
                        id={"type": "list-next", "entity": entity},
                        size="sm", disabled=(page >= total_pages),
                        style={"fontSize": "11px"},
                    ),
                ], style={"display": "flex", "alignItems": "center", "gap": "4px"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                     "padding": "8px 0 0", "borderTop": "1px solid rgba(120,148,181,0.1)", "marginTop": "8px"}),
        ], style={"padding": "12px"}),
    ], style={"borderRadius": "16px", "border": "1px solid rgba(255,255,255,0.65)",
             "boxShadow": "0 10px 30px rgba(15,23,42,0.08)", "overflow": "hidden"})

# ════════════════════════════════════════════════════════════════════════════
# PROFILE CARD RENDERER
# ════════════════════════════════════════════════════════════════════════════

def render_profile_card(card_id: str, title: str, icon: str,
                       entity: str, record,
                       fields: list[dict], actions: list[dict] | None = None,
                       color: str = "#1d74d8", auth_data: dict | None = None) -> html.Div:
    """Render profile card with image support."""
    auth_data = auth_data or {}
    user_role = auth_data.get("role", "guest")
    society_id = auth_data.get("society_id")
    
    record_dict = record.to_dict(include_calculated=True) if hasattr(record, 'to_dict') else record
    pk_val = record_dict.get("id", "")
    
    # Determine society_id for image resolution
    if entity == "society":
        img_society_id = pk_val
    else:
        img_society_id = record_dict.get("_image_society_id") or record_dict.get("society_id")
    
    # Build field rows
    field_rows = []
    for f in fields:
        field_type = f.get("type", "text")
        
        if field_type == "image":
            image_path = record_dict.get(f["field"])
            if image_path:
                full_url = get_image_url(image_path, img_society_id, entity, pk_val)
                field_rows.append(
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-image me-2", style={"color": "#aaa", "width": "14px"}),
                            html.Span(f["label"], style={"color": "#7d8ea3", "fontSize": "11px", "fontWeight": "600"}),
                        ], style={"marginBottom": "8px"}),
                        html.Img(
                            src=full_url,
                            style={
                                "maxWidth": "300px", "maxHeight": "200px",
                                "borderRadius": "8px", "border": "1px solid #ddd",
                                "objectFit": "contain", "background": "#fff", "padding": "4px",
                                "paddingLeft": "22px",
                            },
                        ),
                    ], style={"marginBottom": "14px"})
                )
            continue
        
        # Regular field
        val = record_dict.get(f["field"])
        if val is None:
            val = "—"
        elif isinstance(val, bool):
            val = "✓ Yes" if val else "✗ No"
        elif isinstance(val, (date, datetime)):
            val = val.strftime("%d %b %Y") if hasattr(val, 'strftime') else str(val)
        elif isinstance(val, Decimal):
            val = f"₹{val:,.2f}"
        else:
            val = str(val)
        
        field_rows.append(html.Div([
            html.Div([
                html.I(className=f.get("icon", "fas fa-circle-dot"), style={"color": "#aaa", "width": "14px"}),
                html.Span(f["label"], style={"color": "#7d8ea3", "fontSize": "11px", "fontWeight": "600"}),
            ], style={"marginBottom": "2px"}),
            html.Div(val, style={"fontSize": "14px", "fontWeight": "500", "color": "#15304f", "paddingLeft": "22px"}),
        ], style={"marginBottom": "14px"}))
    
    # Action buttons
    action_btns = []
    for act in (actions or []):
        can_do = RBACManager.has_permission(
            user_role,
            f"{act.get('target_card', '')}",
            Permission.EDIT,
            society_id
        )
        if can_do:
            action_btns.append(
                dbc.Button(
                    [html.I(className=f"fas {act.get('icon', 'fa-bolt')} me-2"), act["label"]],
                    id={"type": "profile-action", "entity": entity, "pk": str(pk_val), "action": act.get("action_id", "")},
                    n_clicks=0, color=act.get("color", "primary"), size="sm",
                    className="me-2 mb-2", style={"borderRadius": "10px", "fontWeight": "600"},
                )
            )
    
    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div([
                    html.Div(
                        html.I(className=f"fas {icon}", style={"color": "#fff", "fontSize": "16px"}),
                        style={
                            "width": "38px", "height": "38px", "borderRadius": "10px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center", "justifyContent": "center",
                            "marginRight": "12px", "flexShrink": "0",
                        },
                    ),
                    html.Div([
                        html.Strong(title, style={"fontSize": "14px"}),
                        html.Div(record_dict.get("subtitle", f"ID: {pk_val}"), style={"fontSize": "11px", "color": "#999"}),
                    ]),
                ], style={"display": "flex", "alignItems": "center"}),
                dbc.Button(
                    html.I(className="fas fa-edit"),
                    id={"type": "profile-edit", "entity": entity, "pk": str(pk_val)},
                    size="sm", color="primary", outline=True,
                ),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
            style={"padding": "12px 16px", "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div(field_rows),
            html.Hr(style={"margin": "8px 0", "opacity": "0.3"}) if action_btns else None,
            html.Div(action_btns, style={"display": "flex", "flexWrap": "wrap"}),
        ], style={"padding": "16px", "maxHeight": "600px", "overflowY": "auto"}),
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
    """Generic form card with dynamic field types."""
    prefill = prefill or {}
    current_pk = prefill.get("id") or ""
    form_rows = []
    
    for f in fields:
        fid = f["id"]
        pre_val = prefill.get(fid)
        ftype = f.get("type", "text")
        required = f.get("required", False)
        label_txt = f["label"] + (" *" if required else "")
        
        if ftype == "select":
            opts = [{"label": o.title(), "value": o} for o in f.get("options", [])]
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=opts, value=pre_val, placeholder=f"Select {f['label']}…",
                clearable=not required, style={"fontSize": "13px"},
            )
        elif ftype == "textarea":
            ctrl = dbc.Textarea(
                id={"type": "form-field", "entity": entity, "field": fid},
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"], rows=3, style={"fontSize": "13px", "borderRadius": "10px"},
            )
        elif ftype == "date":
            ctrl = dcc.DatePickerSingle(
                id={"type": "form-field", "entity": entity, "field": fid},
                date=str(pre_val) if pre_val else None,
                style={"width": "100%"},
            )
        elif ftype == "image_upload":
            ctrl = html.Div([
                dcc.Upload(
                    id={"type": "form-upload", "entity": entity, "field": fid},
                    children=html.Div([
                        html.I(className="fas fa-cloud-upload-alt me-2"),
                        "Drag & Drop or Click"
                    ]),
                    style={
                        "width": "100%", "height": "80px", "lineHeight": "80px",
                        "borderWidth": "2px", "borderStyle": "dashed", "borderRadius": "10px",
                        "textAlign": "center", "borderColor": "#667eea",
                        "background": "rgba(102,126,234,0.05)", "cursor": "pointer",
                        "fontSize": "13px", "color": "#667eea",
                    },
                    multiple=False, accept="image/*",
                ),
                dcc.Input(
                    id={"type": "form-field-hidden", "entity": entity, "field": fid},
                    type="hidden", value=pre_val or "",
                ),
            ])
        else:
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type=ftype, value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"], style={"fontSize": "13px", "borderRadius": "10px"},
            )
        
        form_rows.append(dbc.Row([
            dbc.Col(
                dbc.Label(label_txt, style={"fontSize": "12px", "fontWeight": "500", "color": "#555"}),
                width=4, style={"paddingTop": "6px"},
            ),
            dbc.Col(ctrl, width=8),
        ], className="mb-2"))
    
    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.Div(
                    html.I(className=f"fas {icon}", style={"color": "#fff", "fontSize": "15px"}),
                    style={
                        "width": "34px", "height": "34px", "borderRadius": "9px",
                        "background": f"linear-gradient(135deg,{color},{color}aa)",
                        "display": "flex", "alignItems": "center", "justifyContent": "center",
                        "marginRight": "10px", "flexShrink": "0",
                    },
                ),
                html.Strong(title, style={"fontSize": "13px"}),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "10px 16px", "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
        ),
        dbc.CardBody([
            html.Div(form_rows),
            dbc.Button(
                [html.I(className="fas fa-check me-2"), submit_label],
                id={"type": "form-submit", "entity": entity, "card_id": card_id},
                n_clicks=0, color="success", className="mt-3 w-100",
                style={"borderRadius": "12px", "fontWeight": "700"},
            ),
        ], style={"padding": "16px", "maxHeight": "480px", "overflowY": "auto"}),
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
    """Render navigation breadcrumb."""
    items = []
    for i, entry in enumerate(nav_stack):
        is_last = i == len(nav_stack) - 1
        label = entry.get("entity_label") or entry.get("label", "?")
        
        if is_last:
            items.append(html.Li([
                html.I(className="fas fa-circle me-1", style={"fontSize": "6px", "color": COLORS["primary"]}),
                html.Span(label, style={"fontWeight": "700"}),
            ], className="breadcrumb-item active"))
        else:
            items.append(html.Li(
                html.A(label, href="#", style={"color": COLORS["primary"], "textDecoration": "none"},
                       id={"type": "breadcrumb", "index": i}, n_clicks=0),
                className="breadcrumb-item",
            ))
    
    return html.Nav(
        html.Ol(items, className="breadcrumb", style={"margin": 0, "padding": 0}),
        style={
            "background": "rgba(255,255,255,0.7)", "backdropFilter": "blur(8px)",
            "padding": "8px 16px", "borderRadius": "12px", "marginBottom": "16px",
            "border": "1px solid rgba(255,255,255,0.5)",
        },
    )

# ════════════════════════════════════════════════════════════════════════════
# UTILITY
# ════════════════════════════════════════════════════════════════════════════

def model_to_display(record: any) -> dict:
    """Convert OOP model to display dict."""
    if hasattr(record, 'to_dict'):
        return record.to_dict(include_calculated=True)
    return record if isinstance(record, dict) else {}
