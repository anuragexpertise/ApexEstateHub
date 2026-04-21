import json
from dash import html, dcc
import dash_bootstrap_components as dbc

# ================================================================
# Card catalogue — all 8 available KPI cards
# ================================================================
CARD_DEFINITIONS = {
    "monthly_revenue": {
        "title": "Monthly Revenue",
        "icon": "fa-rupee-sign",
        "color": "#f39c12",
        "border": "#f39c12",
        "subtitle": "This month",
        "format": "currency",
        "query": (
            "SELECT COALESCE(SUM(amount),0) AS v FROM transactions "
            "WHERE society_id = %s "
            "  AND trx_date >= date_trunc('month', CURRENT_DATE) "
            "  AND status = 'paid'"
        ),
    },
    "pending_dues": {
        "title": "Pending Dues",
        "icon": "fa-clock",
        "color": "#e74c3c",
        "border": "#e74c3c",
        "subtitle": "Awaiting payment",
        "format": "currency",
        "query": (
            "SELECT COALESCE(SUM(amount),0) AS v FROM payments "
            "WHERE society_id = %s AND status = 'pending'"
        ),
    },
    "total_users": {
        "title": "Total Users",
        "icon": "fa-users",
        "color": "#2ecc71",
        "border": "#2ecc71",
        "subtitle": "Registered members",
        "format": "count",
        "query": "SELECT COUNT(*) AS v FROM users WHERE society_id = %s",
    },
    "total_apartments": {
        "title": "Total Apartments",
        "icon": "fa-building",
        "color": "#3498db",
        "border": "#3498db",
        "subtitle": "Active units",
        "format": "count",
        "query": (
            "SELECT COUNT(*) AS v FROM apartments "
            "WHERE society_id = %s AND active = TRUE"
        ),
    },
    "active_vendors": {
        "title": "Active Vendors",
        "icon": "fa-briefcase",
        "color": "#9b59b6",
        "border": "#9b59b6",
        "subtitle": "Service providers",
        "format": "count",
        "query": (
            "SELECT COUNT(*) AS v FROM users "
            "WHERE society_id = %s AND role = 'vendor'"
        ),
    },
    "security_staff": {
        "title": "Security Staff",
        "icon": "fa-shield-alt",
        "color": "#e67e22",
        "border": "#e67e22",
        "subtitle": "On roster",
        "format": "count",
        "query": (
            "SELECT COUNT(*) AS v FROM users "
            "WHERE society_id = %s AND role = 'security'"
        ),
    },
    "gate_entries": {
        "title": "Gate Entries Today",
        "icon": "fa-door-open",
        "color": "#1abc9c",
        "border": "#1abc9c",
        "subtitle": "Today",
        "format": "count",
        "query": (
            "SELECT COUNT(*) AS v FROM gate_access "
            "WHERE society_id = %s AND DATE(time_in) = CURRENT_DATE"
        ),
    },
    "occupancy_rate": {
        "title": "Occupancy Rate",
        "icon": "fa-chart-pie",
        "color": "#34495e",
        "border": "#34495e",
        "subtitle": "Occupied units",
        "format": "percent",
        "query": (
            "SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE active = TRUE) "
            "             / NULLIF(COUNT(*), 0)) AS v "
            "FROM apartments WHERE society_id = %s"
        ),
    },
}

DEFAULT_ACTIVE = ["monthly_revenue", "pending_dues", "total_users", "total_apartments"]


# ================================================================
# Card renderer
# ================================================================
def make_card(card_id: str, value: str = "—") -> html.Div:
    cfg = CARD_DEFINITIONS[card_id]
    return html.Div(
        [
            # ── drag handle ──────────────────────────────────────
            html.Div(
                "⠿",
                className="dnd-handle",
                style={
                    "position": "absolute",
                    "top": "8px",
                    "left": "10px",
                    "fontSize": "18px",
                    "color": "#ccc",
                    "cursor": "grab",
                    "lineHeight": "1",
                    "letterSpacing": "3px",
                    "userSelect": "none",
                },
            ),
            # ── card body ────────────────────────────────────────
            html.Div(
                [
                    html.I(
                        className=f"fas {cfg['icon']} fa-lg",
                        style={"color": cfg["color"]},
                    ),
                    html.Div(
                        cfg["title"],
                        style={
                            "fontSize": "12px",
                            "fontWeight": "500",
                            "color": "#888",
                            "marginTop": "6px",
                            "lineHeight": "1.3",
                        },
                    ),
                    html.Div(
                        value,
                        **{"data-kpi-value": card_id},
                        style={
                            "fontSize": "22px",
                            "fontWeight": "700",
                            "color": "#2c3e50",
                            "lineHeight": "1.2",
                            "margin": "2px 0",
                        },
                    ),
                    html.Div(
                        cfg["subtitle"],
                        style={"fontSize": "11px", "color": "#aaa"},
                    ),
                ],
                style={"textAlign": "center"},
            ),
        ],
        id=f"dnd-card-{card_id}",
        **{"data-card-id": card_id},
        className="dnd-card",
        style={
            "position": "relative",
            "background": "white",
            "borderRadius": "12px",
            "padding": "18px 12px 14px",
            "borderLeft": f"4px solid {cfg['border']}",
            "boxShadow": "0 2px 8px rgba(0,0,0,0.07)",
            "cursor": "default",
            "userSelect": "none",
        },
    )


# ================================================================
# Page layout
# ================================================================
def customize_layout() -> html.Div:
    all_ids = list(CARD_DEFINITIONS.keys())
    available_ids = [c for c in all_ids if c not in DEFAULT_ACTIVE]

    return html.Div(
        [
            # ── Stores / hidden inputs ────────────────────────────
            dcc.Store(
                id="dnd-layout-store",
                storage_type="session",
                data={"active": DEFAULT_ACTIVE[:], "available": available_ids},
            ),
            # JS → server bridge: SortableJS writes here via React setter trick
            dcc.Input(
                id="dnd-order-capture",
                value="",
                debounce=False,
                style={"display": "none"},
            ),
            # Dummy target for clientside init callback
            html.Div(id="dnd-init-dummy", style={"display": "none"}),

            # ── Toolbar ───────────────────────────────────────────
            dbc.Row(
                [
                    dbc.Col(
                        html.H4(
                            [
                                html.I(className="fas fa-sliders-h me-2"),
                                "Customize Dashboard",
                            ],
                            className="mb-0",
                            style={"color": "#2c3e50"},
                        ),
                        width="auto",
                    ),
                    dbc.Col(
                        [
                            dbc.Button(
                                [html.I(className="fas fa-save me-1"), "Save Layout"],
                                id="save-layout-btn",
                                color="primary",
                                size="sm",
                                className="me-2",
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-undo me-1"), "Reset Default"],
                                id="reset-layout-btn",
                                color="light",
                                size="sm",
                            ),
                        ],
                        width="auto",
                        className="ms-auto",
                    ),
                ],
                align="center",
                className="mb-3",
            ),

            # Status alert area
            html.Div(id="layout-status-msg", className="mb-3"),

            # ── Dashboard (active) zone ───────────────────────────
            dbc.Card(
                [
                    dbc.CardHeader(
                        [
                            html.I(className="fas fa-th-large me-2"),
                            html.Strong("Dashboard Cards"),
                            dbc.Badge(
                                "drag to reorder  •  max 4",
                                color="secondary",
                                className="ms-2",
                                style={"fontSize": "10px", "fontWeight": "400"},
                            ),
                            dbc.Badge(
                                f"{len(DEFAULT_ACTIVE)} / 4",
                                id="active-count-badge",
                                color="primary",
                                className="float-end",
                                style={"fontSize": "11px"},
                            ),
                        ]
                    ),
                    dbc.CardBody(
                        [
                            html.Div(
                                id="dnd-active-zone",
                                **{"data-zone": "active"},
                                children=[make_card(c) for c in DEFAULT_ACTIVE],
                                style={
                                    "display": "grid",
                                    "gridTemplateColumns": "repeat(4, 1fr)",
                                    "gap": "12px",
                                    "minHeight": "130px",
                                    "padding": "8px",
                                    "border": "2px dashed #dee2e6",
                                    "borderRadius": "10px",
                                    "transition": "border-color 0.2s, background 0.2s",
                                },
                            ),
                            html.Small(
                                "Drag cards here from the palette below, or reorder within",
                                className="text-muted mt-2 d-block text-center",
                                style={"fontSize": "11px"},
                            ),
                        ]
                    ),
                ],
                className="mb-3 shadow-sm",
                style={"borderRadius": "15px"},
            ),

            # ── Palette (available) zone ──────────────────────────
            dbc.Card(
                [
                    dbc.CardHeader(
                        [
                            html.I(className="fas fa-grip-horizontal me-2"),
                            html.Strong("Card Palette"),
                            dbc.Badge(
                                "drag to dashboard above",
                                color="light",
                                text_color="dark",
                                className="ms-2",
                                style={"fontSize": "10px", "fontWeight": "400"},
                            ),
                        ]
                    ),
                    dbc.CardBody(
                        html.Div(
                            id="dnd-available-zone",
                            **{"data-zone": "available"},
                            children=[make_card(c) for c in available_ids],
                            style={
                                "display": "grid",
                                "gridTemplateColumns": "repeat(4, 1fr)",
                                "gap": "12px",
                                "minHeight": "80px",
                                "padding": "8px",
                                "border": "2px dashed #dee2e6",
                                "borderRadius": "10px",
                                "background": "#f8f9fa",
                                "transition": "border-color 0.2s, background 0.2s",
                            },
                        )
                    ),
                ],
                className="shadow-sm",
                style={"borderRadius": "15px"},
            ),

            # ── Scoped CSS ────────────────────────────────────────
            html.Style(
                """
                .dnd-card{transition:box-shadow .15s,transform .15s}
                .dnd-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.13)!important}
                .dnd-ghost{opacity:.3;border:2px dashed #667eea!important}
                .dnd-chosen{box-shadow:0 8px 28px rgba(0,0,0,.18)!important;transform:scale(1.03)!important;z-index:999}
                .dnd-drag{opacity:0}
                #dnd-active-zone.dnd-over{border-color:#667eea!important;background:#f0f3ff!important}
                #dnd-available-zone.dnd-over{border-color:#999!important;background:#f0f0f0!important}
                .dnd-handle:active{cursor:grabbing}
                .dnd-handle:hover{color:#667eea!important}
                """
            ),
        ],
        style={"padding": "20px"},
    )
