# app/dash_apps/drilldown/renderers.py
"""
Card Renderers
==============
Renders the correct Dash layout for any card_id + filter combination.
All rendering is server-side; no client-side routing.

Each render_* function returns a html.Div subtree.
"""

from __future__ import annotations
from datetime import datetime

from dash import html, dcc
import dash_bootstrap_components as dbc

from .registry import DRILLDOWN_MAP


# ── Colour palette (matches app/assets/style.css CSS vars) ─────────────────
COLORS = {
    "primary": "#1d74d8",
    "success": "#17976e",
    "warning": "#e59620",
    "danger":  "#de5c52",
    "info":    "#0ea5a8",
    "muted":   "#7d8ea3",
}


# ════════════════════════════════════════════════════════════════════════════
# KPI CARD
# ════════════════════════════════════════════════════════════════════════════

def render_kpi_card(card_id: str, title: str, value: str,
                    icon: str, color: str, subtitle: str = "",
                    clickable: bool = True) -> html.Div:
    """
    Renders a single KPI card that navigates on click.

    Parameters
    ----------
    card_id   : matches a key in DRILLDOWN_MAP for click routing
    value     : formatted string value e.g. "42" or "₹1,23,456"
    icon      : font-awesome class e.g. "fa-home"
    color     : hex colour for the left border accent
    """
    cursor_style = "pointer" if clickable else "default"
    hover_title  = f"Click to view {DRILLDOWN_MAP.get(card_id, {}).get('label', title)}" if clickable else ""

    return html.Div(
        [
            # Invisible trigger button — Dash callback listens to n_clicks
            html.Button(
                id={"type": "kpi-card-div", "card_id": card_id},
                n_clicks=0,
                style={"display": "none"},
            ),

            # Visual card
            html.Div(
                [
                    # Accent bar
                    html.Div(style={
                        "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                        "width": "4px", "background": color, "borderRadius": "4px 0 0 4px",
                    }),

                    # Drag handle
                    html.Div("⠿", className="dnd-handle", style={
                        "position": "absolute", "top": "6px", "right": "8px",
                        "fontSize": "14px", "color": "#ccc", "cursor": "grab",
                        "userSelect": "none",
                    }),

                    # Icon
                    html.Div(
                        html.I(className=f"fas {icon}",
                               style={"color": color, "fontSize": "22px"}),
                        style={"marginBottom": "10px"},
                    ),

                    # Value
                    html.Div(
                        value,
                        id={"type": "kpi-value", "card_id": card_id},
                        style={
                            "fontSize": "26px", "fontWeight": "800",
                            "color": "#15304f", "lineHeight": "1",
                        },
                    ),

                    # Title
                    html.Div(title, style={
                        "fontSize": "11px", "fontWeight": "600",
                        "color": "#7d8ea3", "marginTop": "4px",
                        "textTransform": "uppercase", "letterSpacing": "0.5px",
                    }),

                    # Subtitle / trend
                    html.Div(subtitle, style={
                        "fontSize": "10px", "color": "#aaa", "marginTop": "2px",
                    }) if subtitle else None,

                    # Click arrow indicator
                    html.Div(
                        html.I(className="fas fa-arrow-right",
                               style={"fontSize": "10px", "color": color}),
                        style={
                            "position": "absolute", "bottom": "8px", "right": "12px",
                            "opacity": "0.6",
                        }
                    ) if clickable else None,
                ],
                title=hover_title,
                n_clicks=0,
                id={"type": "kpi-card-div", "card_id": card_id},
                style={
                    "position": "relative",
                    "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
                    "border": "1px solid rgba(255,255,255,0.7)",
                    "borderRadius": "16px",
                    "padding": "18px 14px 14px 18px",
                    "cursor": cursor_style,
                    "boxShadow": "0 10px 30px rgba(15,23,42,0.08)",
                    "transition": "transform 0.18s ease, box-shadow 0.18s ease",
                    "minHeight": "110px",
                    "backdropFilter": "blur(10px)",
                    "overflow": "hidden",
                },
            ),
        ],
        className="kpi-card",
    )


# ════════════════════════════════════════════════════════════════════════════
# BREADCRUMB BAR
# ════════════════════════════════════════════════════════════════════════════

def render_breadcrumb(nav_stack: list[dict]) -> html.Nav:
    """Render the drill-down breadcrumb bar with clickable items."""
    items = []
    for i, entry in enumerate(nav_stack):
        is_last = i == len(nav_stack) - 1
        label   = entry.get("entity_label") or entry.get("label", "?")

        if is_last:
            items.append(
                html.Li(
                    [
                        html.I(className="fas fa-circle me-1",
                               style={"fontSize": "6px", "verticalAlign": "middle",
                                      "color": COLORS["primary"]}),
                        html.Span(label, style={"fontWeight": "700"}),
                    ],
                    className="bc-item bc-item--active",
                )
            )
        else:
            items.append(
                html.Li(
                    html.A(
                        [
                            html.I(className="fas fa-home me-1") if i == 0 else None,
                            label,
                        ],
                        id={"type": "breadcrumb-click", "index": i},
                        href="#",
                        style={"color": COLORS["primary"], "textDecoration": "none",
                               "fontWeight": "500"},
                        n_clicks=0,
                    ),
                    className="bc-item",
                )
            )

    return html.Nav(
        html.Ol(items, className="breadcrumb",
                style={"margin": 0, "padding": 0, "listStyle": "none",
                       "display": "flex", "alignItems": "center", "gap": "8px",
                       "flexWrap": "wrap"}),
        className="glass-breadcrumb",
        style={
            "background": "rgba(255,255,255,0.7)",
            "backdropFilter": "blur(8px)",
            "padding": "8px 16px",
            "borderRadius": "12px",
            "marginBottom": "16px",
            "border": "1px solid rgba(255,255,255,0.5)",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# LIST CARD (generic)
# ════════════════════════════════════════════════════════════════════════════

def render_list_card(card_id: str, title: str, icon: str,
                     columns: list[dict], rows: list[dict],
                     entity: str, page: int = 1, total_rows: int = 0,
                     page_size: int = 15, filters: dict | None = None,
                     show_create_btn: bool = True,
                     create_card_id: str | None = None) -> html.Div:
    """
    Generic list card with:
      - Pagination
      - CSV download button
      - Search bar
      - Row double-click → profile navigation
      - Update / Delete action buttons per row
    """
    total_pages = max(1, -(-total_rows // page_size))  # ceiling division

    # ── Table header row ──────────────────────────────────────────────────
    header_cells = [html.Th(c["name"], style={"fontSize": "11px", "fontWeight": "700",
                                               "color": "#7d8ea3", "whiteSpace": "nowrap"})
                    for c in columns]
    header_cells.append(html.Th("Actions", style={"fontSize": "11px", "fontWeight": "700",
                                                    "color": "#7d8ea3", "width": "100px"}))

    # ── Table body rows ───────────────────────────────────────────────────
    body_rows = []
    for row in rows:
        cells = [html.Td(
            str(row.get(c["field"], "—") or "—"),
            style={"fontSize": "13px", "verticalAlign": "middle",
                   "maxWidth": "200px", "overflow": "hidden",
                   "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
        ) for c in columns]

        pk_val = row.get("id") or row.get(f"{entity}_id") or row.get("id")

        action_cell = html.Td(
            html.Div([
                html.Button(
                    html.I(className="fas fa-eye"),
                    id={"type": "list-row-view", "entity": entity, "pk": str(pk_val)},
                    n_clicks=0,
                    title="View details",
                    style=_action_btn_style(COLORS["info"]),
                ),
                html.Button(
                    html.I(className="fas fa-edit"),
                    id={"type": "list-row-edit", "entity": entity, "pk": str(pk_val)},
                    n_clicks=0,
                    title="Edit",
                    style=_action_btn_style(COLORS["primary"]),
                ),
                html.Button(
                    html.I(className="fas fa-trash"),
                    id={"type": "list-row-delete", "entity": entity, "pk": str(pk_val)},
                    n_clicks=0,
                    title="Delete",
                    style=_action_btn_style(COLORS["danger"]),
                ),
            ], style={"display": "flex", "gap": "4px"}),
            style={"verticalAlign": "middle"},
        )

        body_rows.append(
            html.Tr(
                cells + [action_cell],
                id={"type": "list-row", "entity": entity, "pk": str(pk_val)},
                n_clicks=0,
                style={"cursor": "pointer", "transition": "background 0.12s ease"},
                title="Double-click to open profile",
            )
        )

    if not body_rows:
        body_rows = [html.Tr(
            html.Td(
                [html.I(className="fas fa-inbox me-2", style={"color": "#ccc"}),
                 "No records found"],
                colSpan=len(columns) + 1,
                className="text-center text-muted",
                style={"padding": "32px", "fontSize": "13px"},
            )
        )]

    return html.Div(
        [
            dbc.Card(
                [
                    # ── Card Header ──────────────────────────────────────
                    dbc.CardHeader(
                        html.Div(
                            [
                                # Left: icon + title
                                html.Div(
                                    [
                                        html.I(className=f"fas {icon} me-2",
                                               style={"color": COLORS["primary"]}),
                                        html.Strong(title),
                                        dbc.Badge(
                                            str(total_rows),
                                            color="primary",
                                            className="ms-2",
                                            style={"fontSize": "10px"},
                                        ),
                                    ],
                                    style={"display": "flex", "alignItems": "center"},
                                ),
                                # Right: actions
                                html.Div(
                                    [
                                        # Search box
                                        dbc.Input(
                                            id={"type": "list-search", "entity": entity},
                                            placeholder="Search…",
                                            size="sm",
                                            debounce=True,
                                            style={"width": "160px", "fontSize": "12px",
                                                   "borderRadius": "8px"},
                                        ),
                                        # CSV download
                                        dbc.Button(
                                            [html.I(className="fas fa-download me-1"), "CSV"],
                                            id={"type": "btn-csv-download", "entity": entity},
                                            size="sm",
                                            color="success",
                                            outline=True,
                                            style={"fontSize": "11px", "borderRadius": "8px"},
                                        ),
                                        dcc.Download(
                                            id={"type": "csv-download-trigger", "entity": entity}
                                        ),
                                        # Create button
                                        dbc.Button(
                                            [html.I(className="fas fa-plus me-1"), "New"],
                                            id={"type": "btn-list-create", "entity": entity,
                                                "target": create_card_id or f"form_{entity}_new"},
                                            size="sm",
                                            color="primary",
                                            style={"fontSize": "11px", "borderRadius": "8px"},
                                        ) if show_create_btn else None,
                                    ],
                                    style={"display": "flex", "alignItems": "center",
                                           "gap": "6px"},
                                ),
                            ],
                            style={"display": "flex", "justifyContent": "space-between",
                                   "alignItems": "center", "flexWrap": "wrap", "gap": "8px"},
                        ),
                        style={"padding": "10px 16px",
                               "background": "linear-gradient(180deg,rgba(255,255,255,0.85),rgba(248,251,255,0.95))"},
                    ),

                    # ── Table ────────────────────────────────────────────
                    dbc.CardBody(
                        [
                            html.Div(
                                dbc.Table(
                                    [
                                        html.Thead(html.Tr(header_cells)),
                                        html.Tbody(
                                            body_rows,
                                            id={"type": "list-tbody", "entity": entity},
                                        ),
                                    ],
                                    hover=True,
                                    responsive=True,
                                    size="sm",
                                    style={"marginBottom": 0, "fontSize": "13px"},
                                ),
                                style={"overflowX": "auto", "maxHeight": "420px",
                                       "overflowY": "auto"},
                            ),
                            # ── Pagination ────────────────────────────────
                            html.Div(
                                [
                                    html.Small(
                                        f"Showing {len(rows)} of {total_rows} records",
                                        style={"color": "#aaa", "fontSize": "11px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Button(
                                                html.I(className="fas fa-chevron-left"),
                                                id={"type": "list-page-prev", "entity": entity},
                                                n_clicks=0,
                                                disabled=(page <= 1),
                                                style={**_page_btn_style(), "opacity": "0.5" if page <= 1 else "1"},
                                            ),
                                            html.Span(
                                                f"{page} / {total_pages}",
                                                style={"fontSize": "12px", "color": "#666",
                                                       "padding": "0 10px"},
                                            ),
                                            html.Button(
                                                html.I(className="fas fa-chevron-right"),
                                                id={"type": "list-page-next", "entity": entity},
                                                n_clicks=0,
                                                disabled=(page >= total_pages),
                                                style={**_page_btn_style(), "opacity": "0.5" if page >= total_pages else "1"},
                                            ),
                                        ],
                                        style={"display": "flex", "alignItems": "center"},
                                    ),
                                ],
                                style={"display": "flex", "justifyContent": "space-between",
                                       "alignItems": "center", "padding": "8px 4px 0",
                                       "borderTop": "1px solid rgba(120,148,181,0.1)",
                                       "marginTop": "8px"},
                            ),
                        ],
                        style={"padding": "12px"},
                    ),
                ],
                style={
                    "borderRadius": "18px",
                    "border": "1px solid rgba(255,255,255,0.65)",
                    "boxShadow": "0 10px 30px rgba(15,23,42,0.08)",
                    "background": "linear-gradient(180deg,rgba(255,255,255,0.9),rgba(248,251,255,0.85))",
                    "backdropFilter": "blur(12px)",
                    "overflow": "hidden",
                },
            )
        ]
    )


# ════════════════════════════════════════════════════════════════════════════
# PROFILE CARD (generic)
# ════════════════════════════════════════════════════════════════════════════

def render_profile_card(card_id: str, title: str, icon: str,
                        entity: str, record: dict,
                        fields: list[dict],
                        actions: list[dict] | None = None,
                        color: str = "#1d74d8") -> html.Div:
    """
    Generic profile card.

    fields = [{"label": "Flat Number", "field": "flat_number", "icon": "fa-home"}, ...]
    actions = [{"label": "Pay Dues", "target_card": "form_receipt_new",
                "color": "success", "icon": "fa-rupee-sign"}, ...]
    """
    pk_val = record.get("id", "")

    # ── Field rows ────────────────────────────────────────────────────────
    field_rows = []
    for f in fields:
        val = record.get(f["field"])
        if val is None:
            val = "—"
        elif isinstance(val, bool):
            val = "Yes" if val else "No"
        elif hasattr(val, "strftime"):
            val = val.strftime("%d %b %Y")
        else:
            val = str(val)

        field_rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className=f"fas {f.get('icon', 'fa-circle-dot')} me-2",
                                   style={"color": "#aaa", "width": "14px"}),
                            html.Span(f["label"],
                                      style={"color": "#7d8ea3", "fontSize": "11px",
                                             "fontWeight": "600", "textTransform": "uppercase",
                                             "letterSpacing": "0.4px"}),
                        ],
                        style={"marginBottom": "2px"},
                    ),
                    html.Div(val, style={"fontSize": "14px", "fontWeight": "500",
                                         "color": "#15304f", "paddingLeft": "22px"}),
                ],
                style={"marginBottom": "14px"},
            )
        )

    # ── Action buttons ────────────────────────────────────────────────────
    action_btns = []
    for act in (actions or []):
        action_btns.append(
            dbc.Button(
                [html.I(className=f"fas {act.get('icon', 'fa-bolt')} me-2"), act["label"]],
                id={"type": "profile-action", "entity": entity, "pk": str(pk_val),
                    "action": act.get("action_id", act["label"].lower().replace(" ", "_")),
                    "target": act.get("target_card", "")},
                n_clicks=0,
                color=act.get("color", "primary"),
                size="sm",
                className="me-2 mb-2",
                style={"borderRadius": "10px", "fontWeight": "600"},
            )
        )

    return html.Div(
        dbc.Card(
            [
                # ── Header ────────────────────────────────────────────
                dbc.CardHeader(
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div(
                                        html.I(className=f"fas {icon}",
                                               style={"color": "#fff", "fontSize": "16px"}),
                                        style={
                                            "width": "38px", "height": "38px",
                                            "borderRadius": "10px",
                                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                                            "display": "flex", "alignItems": "center",
                                            "justifyContent": "center", "marginRight": "12px",
                                            "flexShrink": "0",
                                        },
                                    ),
                                    html.Div(
                                        [
                                            html.Strong(title, style={"fontSize": "14px"}),
                                            html.Div(
                                                record.get("subtitle", f"ID: {pk_val}"),
                                                style={"fontSize": "11px", "color": "#999"},
                                            ),
                                        ]
                                    ),
                                ],
                                style={"display": "flex", "alignItems": "center"},
                            ),
                            # Edit / Close
                            html.Div(
                                [
                                    html.Button(
                                        html.I(className="fas fa-edit"),
                                        id={"type": "profile-edit-btn", "entity": entity,
                                            "pk": str(pk_val)},
                                        n_clicks=0,
                                        title="Edit",
                                        style=_action_btn_style(COLORS["primary"]),
                                    ),
                                ],
                                style={"display": "flex", "gap": "6px"},
                            ),
                        ],
                        style={"display": "flex", "justifyContent": "space-between",
                               "alignItems": "center"},
                    ),
                    style={"padding": "12px 16px",
                           "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
                ),

                # ── Body ──────────────────────────────────────────────
                dbc.CardBody(
                    [
                        html.Div(field_rows),
                        html.Hr(style={"margin": "8px 0", "opacity": "0.3"}) if action_btns else None,
                        html.Div(action_btns, style={"display": "flex", "flexWrap": "wrap"}),
                    ],
                    style={"padding": "16px"},
                ),
            ],
            style={
                "borderRadius": "18px",
                "border": f"1px solid {color}22",
                "boxShadow": f"0 10px 30px {color}18",
                "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
                "backdropFilter": "blur(12px)",
                "overflow": "hidden",
            },
        )
    )


# ════════════════════════════════════════════════════════════════════════════
# FORM CARD (generic)
# ════════════════════════════════════════════════════════════════════════════

def render_form_card(card_id: str, title: str, icon: str,
                     entity: str, fields: list[dict],
                     submit_label: str = "Save",
                     prefill: dict | None = None,
                     color: str = "#17976e") -> html.Div:
    """
    Generic form card with pre-fill support.

    fields = [
      {"id": "flat_number", "label": "Flat Number", "type": "text", "required": True},
      {"id": "amount",      "label": "Amount (₹)",  "type": "number"},
      {"id": "role",        "label": "Role",         "type": "select",
       "options": ["apartment", "vendor", "security"]},
    ]
    """
    prefill = prefill or {}
    form_rows = []

    for f in fields:
        fid       = f["id"]
        pre_val   = prefill.get(fid)
        ftype     = f.get("type", "text")
        required  = f.get("required", False)
        label_txt = f["label"] + (" *" if required else "")

        if ftype == "select":
            opts = [{"label": o.title(), "value": o} for o in f.get("options", [])]
            ctrl = dcc.Dropdown(
                id={"type": "form-field", "entity": entity, "field": fid},
                options=opts,
                value=pre_val,
                placeholder=f"Select {f['label']}…",
                clearable=not required,
                style={"fontSize": "13px", "borderRadius": "10px"},
            )
        elif ftype == "textarea":
            ctrl = dbc.Textarea(
                id={"type": "form-field", "entity": entity, "field": fid},
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"],
                rows=3,
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
                       "background": "#f8f9fa"},
            )
        else:
            ctrl = dbc.Input(
                id={"type": "form-field", "entity": entity, "field": fid},
                type=ftype,
                value=str(pre_val) if pre_val is not None else "",
                placeholder=f["label"],
                style={"fontSize": "13px", "borderRadius": "10px"},
            )

        form_rows.append(
            dbc.Row(
                [
                    dbc.Label(label_txt, width=4,
                               style={"fontSize": "12px", "color": "#7d8ea3",
                                      "fontWeight": "600", "paddingTop": "8px"}),
                    dbc.Col(ctrl, width=8),
                ],
                className="mb-2",
            )
        )

    return html.Div(
        dbc.Card(
            [
                dbc.CardHeader(
                    html.Div(
                        [
                            html.Div(
                                html.I(className=f"fas {icon}",
                                       style={"color": "#fff", "fontSize": "15px"}),
                                style={
                                    "width": "34px", "height": "34px",
                                    "borderRadius": "9px",
                                    "background": f"linear-gradient(135deg,{color},{color}aa)",
                                    "display": "flex", "alignItems": "center",
                                    "justifyContent": "center", "marginRight": "10px",
                                    "flexShrink": "0",
                                },
                            ),
                            html.Strong(title, style={"fontSize": "13px"}),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    style={"padding": "10px 16px",
                           "background": f"linear-gradient(135deg,{color}18,rgba(255,255,255,0.95))"},
                ),

                dbc.CardBody(
                    [
                        html.Div(form_rows),
                        html.Div(id={"type": "form-status", "entity": entity},
                                  className="mt-2"),
                        dbc.Button(
                            [html.I(className="fas fa-check me-2"), submit_label],
                            id={"type": "form-submit", "entity": entity,
                                "card_id": card_id},
                            n_clicks=0,
                            color="success" if color == COLORS["success"] else "primary",
                            className="mt-3 w-100",
                            style={"borderRadius": "12px", "fontWeight": "700",
                                   "background": f"linear-gradient(135deg,{color},{color}cc)",
                                   "border": "none"},
                        ),
                    ],
                    style={"padding": "16px", "maxHeight": "480px", "overflowY": "auto"},
                ),
            ],
            style={
                "borderRadius": "18px",
                "border": f"1px solid {color}22",
                "boxShadow": f"0 10px 30px {color}18",
                "background": "linear-gradient(180deg,rgba(255,255,255,0.92),rgba(248,251,255,0.88))",
                "backdropFilter": "blur(12px)",
                "overflow": "hidden",
            },
        )
    )


# ════════════════════════════════════════════════════════════════════════════
# HELPER STYLES
# ════════════════════════════════════════════════════════════════════════════

def _action_btn_style(color: str) -> dict:
    return {
        "background": f"{color}18",
        "border": f"1px solid {color}44",
        "color": color,
        "borderRadius": "7px",
        "padding": "4px 8px",
        "fontSize": "11px",
        "cursor": "pointer",
        "transition": "background 0.15s",
    }


def _page_btn_style() -> dict:
    return {
        "background": "rgba(29,116,216,0.1)",
        "border": "1px solid rgba(29,116,216,0.25)",
        "color": COLORS["primary"],
        "borderRadius": "8px",
        "padding": "4px 10px",
        "fontSize": "12px",
        "cursor": "pointer",
    }
