# app/dash_apps/pages/portal_pages.py
"""
ALL 5 PORTAL PAGE LAYOUTS — single source of truth.
Replaces these OLD files (now redundant):
  admin_portal.py  owner_portal.py  vendor_portal.py
  security_portal.py  master_portal.py  master_admin.py

HOW IT WORKS:
  shell_callbacks.py calls _portal_content(role, society_id, pathname)
  which imports and calls the correct function from this file.
  The result is placed into  id="portal-content"  in app_shell.py.

  The header/sidebar/breadcrumb/footer are in app_shell.py and are
  managed by shell_callbacks.py — they are NOT duplicated here.

  Each portal page contains:
    1. KPI row  (clickable shells — values filled by card_catalogue_callbacks)
    2. #drill-content  (the drill-down card area — managed by drilldown_callbacks)
    3. #drill-breadcrumb  (the sub-navigation crumb trail inside the content area)

  The top-level breadcrumb (breadcrumb-ol in the header area) is still
  managed by shell_callbacks, showing which Sidebar Tab is active.
  The drill-breadcrumb inside the content area shows the card-level
  navigation:  Dashboard → Apartments → Flat A-101 → Pay
"""

from __future__ import annotations
from dash import html, dcc
import dash_bootstrap_components as dbc
from app.dash_apps.drilldown import renderers

# ── Role colour palette ───────────────────────────────────────────────────────
_C = {
    "master":    "#c96a19",
    "admin":     "#1859b8",
    "apartment": "#18794e",
    "vendor":    "#b98a07",
    "security":  "#b63b3b",
}


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _kpi(card_id: str, icon: str, color: str,
         label: str, subtitle: str = "") -> html.Div:
    """
    Clickable KPI shell.  Value id={"type":"kpi-value","card_id":card_id}
    is populated by card_catalogue_callbacks.refresh_kpi_values().
    Click id={"type":"kpi-card-div","card_id":card_id}
    is consumed by drilldown_callbacks.route_drilldown().
    """
    return html.Div(
        html.Div(
            [
                html.Div(style={                       # left accent bar
                    "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                    "width": "4px", "background": color,
                    "borderRadius": "4px 0 0 4px",
                }),
                html.Div("⠿", className="dnd-handle", style={   # drag handle
                    "position": "absolute", "top": "6px", "right": "8px",
                    "fontSize": "12px", "color": "#ddd",
                    "cursor": "grab", "userSelect": "none",
                }),
                html.I(className=f"fas {icon}",
                       style={"color": color, "fontSize": "20px",
                              "marginBottom": "8px", "display": "block"}),
                html.Div("—",
                         id={"type": "kpi-value", "card_id": card_id},
                         style={"fontSize": "24px", "fontWeight": "800",
                                "color": "#15304f", "lineHeight": "1"}),
                html.Div(label, style={
                    "fontSize": "11px", "fontWeight": "600", "color": "#7d8ea3",
                    "marginTop": "4px", "textTransform": "uppercase",
                    "letterSpacing": "0.4px",
                }),
                html.Div(subtitle, style={
                    "fontSize": "10px", "color": "#aaa", "marginTop": "2px",
                }) if subtitle else None,
                html.Div(                              # bottom-right arrow
                    html.I(className="fas fa-arrow-right",
                           style={"fontSize": "9px", "color": color}),
                    style={"position": "absolute", "bottom": "8px",
                           "right": "12px", "opacity": "0.5"},
                ),
            ],
            id={"type": "kpi-card-div", "card_id": card_id},
            n_clicks=0,
            title=f"Click to drill into {label}",
            style={
                "position": "relative",
                "background": "linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,251,255,0.9))",
                "border": "1px solid rgba(255,255,255,0.68)",
                "borderRadius": "16px",
                "padding": "18px 14px 14px 18px",
                "cursor": "pointer",
                "boxShadow": "0 8px 24px rgba(15,23,42,0.07)",
                "transition": "transform 0.16s ease, box-shadow 0.16s ease",
                "minHeight": "106px",
                "backdropFilter": "blur(10px)",
                "overflow": "hidden",
            },
        ),
        className="kpi-card",
    )


def _page_title(icon: str, color: str, title: str, sub: str = "") -> html.Div:
    return html.Div(
        [
            html.Div(
                html.I(className=f"fas {icon}",
                       style={"color": "#fff", "fontSize": "17px"}),
                style={
                    "width": "42px", "height": "42px", "borderRadius": "12px",
                    "background": f"linear-gradient(135deg,{color},{color}99)",
                    "display": "flex", "alignItems": "center",
                    "justifyContent": "center", "marginRight": "14px",
                    "flexShrink": "0",
                },
            ),
            html.Div([
                html.H4(title, className="mb-0",
                        style={"fontWeight": "800", "color": "#15304f",
                               "fontSize": "18px"}),
                html.Small(sub, style={"color": "#aaa", "fontSize": "12px"}) if sub else None,
            ]),
        ],
        style={"display": "flex", "alignItems": "center", "marginBottom": "22px"},
    )


def _sec_hdr(title: str, sub: str = "", icon: str = "fa-layer-group") -> html.Div:
    return html.Div(
        [
            html.I(className=f"fas {icon} me-2",
                   style={"color": "#7d8ea3", "fontSize": "13px"}),
            html.Span(title, style={"fontWeight": "700", "fontSize": "14px",
                                    "color": "#15304f"}),
            html.Small(f"  — {sub}",
                       style={"color": "#bbb", "fontSize": "11px"}) if sub else None,
        ],
        style={"display": "flex", "alignItems": "center",
               "marginBottom": "14px", "marginTop": "2px"},
    )


def _kpi_row(*kpis, cols: str = "repeat(auto-fill,minmax(155px,1fr))") -> html.Div:
    return html.Div(
        list(kpis),
        id="kpi-row",
        className="kpi-row",
        style={"gridTemplateColumns": cols, "marginBottom": "20px"},
    )


def _drill_panel() -> html.Div:
    """
    The drill-down card area.
    id="drill-content"    ← Output in drilldown_callbacks.route_drilldown
    id="drill-breadcrumb" ← Output in drilldown_callbacks.route_drilldown
    """
    return html.Div(
        [
            # Sub-navigation breadcrumb (card-level, not tab-level)
            
            
            html.Div(id="drill-breadcrumb"),

            # Dynamic card: list / profile / form
            html.Div(
                
                id="drill-content",
                children=html.Div(
                    [
                        html.I(className="fas fa-hand-pointer fa-2x mb-3",
                               style={"color": "rgba(29,116,216,0.18)"}),
                        html.P("Click any KPI card above to explore →",
                               className="text-muted",
                               style={"fontSize": "13px"}),
                    ],
                    className="text-center",
                    style={"padding": "60px 20px"},
                ),
            ),
        ],
        style={
            "background": "rgba(255,255,255,0.55)",
            "backdropFilter": "blur(12px)",
            "border": "1px solid rgba(255,255,255,0.6)",
            "borderRadius": "20px",
            "padding": "20px",
            "boxShadow": "0 8px 26px rgba(15,23,42,0.06)",
            "minHeight": "380px",
        },
    )


def _divider() -> html.Hr:
    return html.Hr(style={"margin": "20px 0", "opacity": "0.12"})


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def master_portal_page() -> html.Div:
    c = _C["master"]
    return html.Div(
        [
            _page_title("fa-crown", c, "Master Admin Portal",
                        "Manage all societies on this platform"),
            _sec_hdr("Platform Overview", "click any card to drill down", "fa-chart-bar"),
            _kpi_row(
                _kpi("kpi_societies_total",  "fa-building",       c,         "Total Societies"),
                _kpi("kpi_societies_free",   "fa-circle",         "#7d8ea3", "Free Plan"),
                _kpi("kpi_societies_9Apts",   "fa-star",           "#17976e", "9Apts Plan",    "active subscriptions"),
                _kpi("kpi_societies_99Apts",   "fa-star",           "#17976e", "99Apts Plan",    "active subscriptions"),
                _kpi("kpi_societies_999Apts",   "fa-star",           "#17976e", "999Apts Plan",    "active subscriptions"),
                _kpi("kpi_societies_unlimited",   "fa-star",           "#17976e", "unlimited Plan",    "active subscriptions"),
                _kpi("kpi_master_apartments_total", "fa-home",           "#1859b8", "Apartments",   "across all societies"),
                _kpi("kpi_master_vendors_total",    "fa-truck",          "#b98a07", "Vendors"),
                _kpi("kpi_master_security_total",   "fa-user-shield",    "#b63b3b", "Security Staff"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(),
            _drill_panel(),
        ],
        className="portal-page",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN PORTAL — all tabs
# ═══════════════════════════════════════════════════════════════════════════
def _customize_page(c: str) -> html.Div:
    from dash import html, dcc
    import dash_bootstrap_components as dbc
 
    _PORTAL_OPTS = [
        {"label": "Admin",     "value": "admin"},
        {"label": "Master",    "value": "master"},
        {"label": "Apartment", "value": "apartment"},
        {"label": "Vendor",    "value": "vendor"},
        {"label": "Security",  "value": "security"},
    ]
 
    return html.Div([
 
        # ── Page title ─────────────────────────────────────────────────────
        html.Div([
            html.Div(
                html.I(className="fas fa-cog",
                       style={"color": "#fff", "fontSize": "17px"}),
                style={"width": "42px", "height": "42px", "borderRadius": "12px",
                       "background": f"linear-gradient(135deg,{c},{c}99)",
                       "display": "flex", "alignItems": "center",
                       "justifyContent": "center", "marginRight": "14px",
                       "flexShrink": "0"},
            ),
            html.Div([
                html.H4("Customize Dashboard", className="mb-0",
                        style={"fontWeight": "800", "color": "#15304f",
                               "fontSize": "18px"}),
                html.Small("Layout Editor · KPI Inspector · KPI Audit",
                           style={"color": "#aaa", "fontSize": "12px"}),
            ]),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "22px"}),
 
        # ── Sub-tabs ───────────────────────────────────────────────────────
        dbc.Tabs(
            id="customize-sub-tabs",
            active_tab="customize-layout",
            children=[
 
                # ══════════════════════════════════════════════════════════
                # TAB A — LAYOUT EDITOR
                # ══════════════════════════════════════════════════════════
                dbc.Tab(
                    tab_id="customize-layout",
                    label="Layout Editor",
                    children=[html.Div([
 
                        # ── Hidden stores / inputs ─────────────────────────
                        dcc.Store(id="dnd-layout-store", storage_type="session",
                                  data={"active": [], "available": []}),
                        dcc.Input(id="dnd-order-capture", value="",
                                  debounce=False, style={"display": "none"}),
                        html.Div(id="dnd-init-dummy", children="",
                                 style={"display": "none"}),
 
                        # ══ ROW 1: Portal + Tab selectors (top) ════════════
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.I(className="fas fa-filter me-2",
                                       style={"color": c}),
                                html.Strong("Select Dashboard to Edit"),
                            ], style={"display": "flex", "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody([
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("Portal",
                                                  style={"fontSize": "12px",
                                                         "fontWeight": "600"}),
                                        dcc.Dropdown(
                                            id="layout-portal-select",
                                            options=_PORTAL_OPTS,
                                            value="admin",
                                            clearable=False,
                                            style={"fontSize": "13px"},
                                        ),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Tab",
                                                  style={"fontSize": "12px",
                                                         "fontWeight": "600"}),
                                        dcc.Dropdown(
                                            id="layout-tab-select",
                                            options=[],
                                            value=None,
                                            placeholder="Select tab…",
                                            clearable=True,
                                            style={"fontSize": "13px"},
                                        ),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Actions",
                                                  style={"fontSize": "12px",
                                                         "fontWeight": "600"}),
                                        html.Div([
                                            dbc.Button(
                                                [html.I(className="fas fa-save me-1"),
                                                 "Save"],
                                                id="save-layout-btn",
                                                color="primary", size="sm",
                                                className="me-2",
                                                style={"borderRadius": "8px",
                                                       "fontWeight": "600"},
                                            ),
                                            dbc.Button(
                                                [html.I(className="fas fa-undo me-1"),
                                                 "Reset"],
                                                id="reset-layout-btn",
                                                color="light", size="sm",
                                                style={"borderRadius": "8px"},
                                            ),
                                        ], style={"display": "flex",
                                                  "gap": "6px",
                                                  "marginTop": "4px"}),
                                    ], width=4),
                                ]),
                                html.Div(id="layout-status-msg",
                                         className="mt-2"),
                            ], style={"padding": "12px 14px"}),
                        ], className="mb-3 shadow-sm",
                        style={"borderRadius": "14px", "overflow": "hidden"}),
 
                        # ══ ROW 2: Active Dashboard zone ═══════════════════
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.Div([
                                    html.I(className="fas fa-th-large me-2",
                                           style={"color": c}),
                                    html.Strong("Active Dashboard"),
                                    html.Small(" — drag KPIs here from the palette below",
                                               style={"color": "#999",
                                                      "fontSize": "11px",
                                                      "marginLeft": "6px"}),
                                ], style={"display": "flex", "alignItems": "center"}),
                                dbc.Badge("0 / 12 active",
                                          id="active-count-badge",
                                          style={"fontSize": "11px",
                                                 "background": "#1d74d8",
                                                 "borderRadius": "20px",
                                                 "padding": "4px 10px"}),
                            ], style={"display": "flex",
                                      "justifyContent": "space-between",
                                      "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody(
                                html.Div(
                                    id="dnd-active-zone",
                                    children=[
                                        html.Div(
                                            [html.I(className="fas fa-arrow-down me-2"),
                                             "Drag KPI cards here from the palette below"],
                                            style={"color": "#ccc",
                                                   "fontSize": "13px",
                                                   "textAlign": "center",
                                                   "padding": "30px"},
                                        )
                                    ],
                                    style={
                                        "display": "grid",
                                        "gridTemplateColumns":
                                            "repeat(auto-fill,minmax(200px,1fr))",
                                        "gap": "12px",
                                        "minHeight": "120px",
                                        "padding": "10px",
                                        "border": "2px dashed #dee2e6",
                                        "borderRadius": "10px",
                                        "transition":
                                            "border-color .2s, background .2s",
                                        "background": "rgba(248,251,255,0.6)",
                                    },
                                ),
                                style={"padding": "14px"},
                            ),
                        ], className="mb-3 shadow-sm",
                        style={"borderRadius": "14px", "overflow": "hidden"}),
 
                        # ══ ROW 3: KPI Palette ═════════════════════════════
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.I(className="fas fa-grip-horizontal me-2",
                                       style={"color": "#7d8ea3"}),
                                html.Strong("KPI Palette"),
                                html.Small(
                                    " — all KPIs for the selected portal/tab",
                                    style={"color": "#999", "fontSize": "11px",
                                           "marginLeft": "6px"}),
                            ], style={"display": "flex", "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody(
                                html.Div(
                                    style={"maxHeight": "52vh",
                                           "overflowY": "auto",
                                           "padding": "4px 0"},
                                    children=[
                                        html.Div(
                                            id="dnd-palette-zone",
                                            children=[
                                                html.Div(
                                                    "Select a portal and tab above to load KPIs",
                                                    style={"color": "#ccc",
                                                           "fontSize": "13px",
                                                           "textAlign": "center",
                                                           "padding": "30px"},
                                                )
                                            ],
                                            style={
                                                "display": "grid",
                                                "gridTemplateColumns":
                                                    "repeat(auto-fill,"
                                                    "minmax(200px,1fr))",
                                                "gap": "12px",
                                                "padding": "6px",
                                                "minHeight": "80px",
                                                "border":
                                                    "2px dashed transparent",
                                                "borderRadius": "10px",
                                                "transition":
                                                    "border-color .2s,"
                                                    "background .2s",
                                            },
                                        ),
                                    ],
                                ),
                                style={"padding": "8px"},
                            ),
                        ], className="shadow-sm",
                        style={"borderRadius": "14px", "overflow": "hidden"}),
 
                    ], style={"marginTop": "20px"})],
                ),
 
                # ══════════════════════════════════════════════════════════
                # TAB B — KPI INSPECTOR
                # ══════════════════════════════════════════════════════════
                dbc.Tab(
                    tab_id="customize-kpi",
                    label="KPI Inspector",
                    children=[html.Div([
 
                        # ── Selector row ───────────────────────────────────
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Portal",
                                          style={"fontSize": "12px",
                                                 "fontWeight": "600"}),
                                dcc.Dropdown(
                                    id="customize-portal-select",
                                    options=_PORTAL_OPTS,
                                    value="admin",
                                    clearable=False,
                                    style={"fontSize": "13px"},
                                ),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Tab",
                                          style={"fontSize": "12px",
                                                 "fontWeight": "600"}),
                                dcc.Dropdown(
                                    id="customize-tab-select",
                                    options=[],
                                    placeholder="Select tab…",
                                    clearable=True,
                                    style={"fontSize": "13px"},
                                ),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("KPI",
                                          style={"fontSize": "12px",
                                                 "fontWeight": "600"}),
                                dcc.Dropdown(
                                    id="customize-kpi-select",
                                    options=[],
                                    placeholder="Select KPI…",
                                    clearable=True,
                                    style={"fontSize": "13px"},
                                ),
                            ], width=4),
                        ], className="mb-3"),
 
                        html.Hr(style={"margin": "12px 0"}),
 
                        # ── Two-column: SQL  |  Metadata ───────────────────
                        dbc.Row([
 
                            # Left — editable SQL + action buttons
                            dbc.Col([
                                dbc.Label(
                                    [html.I(className="fas fa-code me-1"),
                                     "SQL Query  (editable)"],
                                    style={"fontSize": "12px",
                                           "fontWeight": "700",
                                           "color": "#15304f"},
                                ),
                                dbc.Textarea(
                                    id="customize-kpi-sql",
                                    placeholder="Select a KPI to load its SQL…",
                                    rows=13,
                                    # readOnly intentionally omitted → editable
                                    style={"fontSize": "11px",
                                           "fontFamily": "monospace",
                                           "backgroundColor": "#f5f7fa",
                                           "border": "1px solid #cdd5df",
                                           "borderRadius": "8px",
                                           "color": "#2c3e50",
                                           "resize": "vertical"},
                                ),
 
                                # Action buttons row
                                html.Div([
                                    dbc.Button(
                                        [html.I(className="fas fa-play me-1"),
                                         "Test SQL"],
                                        id="kpi-test-sql-btn",
                                        color="success", size="sm",
                                        style={"borderRadius": "8px",
                                               "fontWeight": "600"},
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-file-export me-1"),
                                         "Export .sql"],
                                        id="kpi-export-sql-btn",
                                        color="secondary", size="sm",
                                        style={"borderRadius": "8px"},
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-database me-1"),
                                         "Integrate to DB"],
                                        id="kpi-integrate-sql-btn",
                                        color="warning", size="sm",
                                        style={"borderRadius": "8px",
                                               "fontWeight": "600"},
                                    ),
                                    dcc.Download(id="kpi-export-download"),
                                ], style={"display": "flex", "gap": "6px",
                                          "marginTop": "8px",
                                          "flexWrap": "wrap"}),
 
                                html.Small(
                                    "Edit SQL freely. Test runs it against your DB "
                                    "with current society_id. Integrate executes it "
                                    "directly (use for CREATE/REPLACE functions).",
                                    style={"fontSize": "10px", "color": "#999",
                                           "display": "block", "marginTop": "4px"},
                                ),
 
                                # Results
                                dcc.Loading(
                                    html.Div(id="kpi-test-result",
                                             style={"marginTop": "8px"}),
                                    type="circle",
                                ),
                                html.Div(id="kpi-export-result"),
                                html.Div(id="kpi-integrate-result"),
 
                            ], width=6),
 
                            # Right — metadata card
                            dbc.Col([
                                dbc.Label(
                                    [html.I(className="fas fa-info-circle me-1"),
                                     "KPI Metadata"],
                                    style={"fontSize": "12px",
                                           "fontWeight": "700",
                                           "color": "#15304f"},
                                ),
                                dcc.Loading(
                                    html.Div(
                                        id="customize-kpi-metadata",
                                        children="Select a KPI to view metadata",
                                        style={"fontSize": "11px",
                                               "backgroundColor": "#f5f7fa",
                                               "border": "1px solid #cdd5df",
                                               "borderRadius": "8px",
                                               "padding": "12px",
                                               "minHeight": "340px",
                                               "maxHeight": "500px",
                                               "overflowY": "auto",
                                               "color": "#2c3e50"},
                                    ),
                                    type="default",
                                ),
                                # Entity reference below metadata
                                html.Div(
                                    id="customize-entity-reference",
                                    style={"marginTop": "10px"},
                                ),
                            ], width=6),
                        ], className="mb-3"),
 
                    ], style={"marginTop": "20px"})],
                ),
 
                # ══════════════════════════════════════════════════════════
                # TAB C — KPI AUDIT
                # ══════════════════════════════════════════════════════════
                dbc.Tab(
                    tab_id="customize-audit",
                    label="KPI Audit",
                    children=[html.Div([
 
                        dbc.Row([
                            dbc.Col(
                                html.H6(
                                    [html.I(className="fas fa-stethoscope me-2"),
                                     "KPI Health Check"],
                                    style={"color": "#15304f",
                                           "fontWeight": "700"},
                                ),
                                width="auto",
                            ),
                            dbc.Col([
                                dbc.Button(
                                    [html.I(className="fas fa-play me-2"),
                                     "Run Full Audit"],
                                    id="run-kpi-audit-btn",
                                    color="primary", size="sm",
                                    style={"borderRadius": "8px",
                                           "fontWeight": "600"},
                                ),
                            ], width="auto", className="ms-auto"),
                        ], align="center", className="mb-3"),
 
                        html.Div(
                            id="kpi-audit-summary",
                            children=html.Small(
                                "Click 'Run Full Audit' to test all KPI queries.",
                                className="text-muted",
                            ),
                            className="mb-3",
                        ),
 
                        html.Small([
                            html.Strong("Legend: "),
                            dbc.Badge("OK",    color="success",  className="me-1"),
                            "returned a value  · ",
                            dbc.Badge("NULL",  color="warning",  className="me-1"),
                            "returned NULL  · ",
                            dbc.Badge("ERROR", color="danger",   className="me-1"),
                            "threw an exception",
                        ], className="d-block mb-3",
                        style={"fontSize": "11px", "color": "#666"}),
 
                        dcc.Loading(
                            html.Div(
                                dbc.Table([
                                    html.Thead(html.Tr([
                                        html.Th("",           style={"width": "34px"}),
                                        html.Th("Card ID",    style={"fontSize": "11px"}),
                                        html.Th("Title",      style={"fontSize": "11px"}),
                                        html.Th("Params",     style={"fontSize": "11px",
                                                                      "textAlign": "center"}),
                                        html.Th("Format",     style={"fontSize": "11px"}),
                                        html.Th("Status",     style={"fontSize": "11px"}),
                                        html.Th("Raw value",  style={"fontSize": "11px"}),
                                        html.Th("Formatted",  style={"fontSize": "11px"}),
                                        html.Th("ms",         style={"fontSize": "11px"}),
                                    ])),
                                    html.Tbody(
                                        id="kpi-audit-table",
                                        children=[html.Tr(html.Td(
                                            "Click Run Full Audit",
                                            colSpan=9,
                                            className="text-center text-muted",
                                            style={"fontSize": "12px",
                                                   "padding": "20px"},
                                        ))],
                                    ),
                                ], bordered=True, hover=True,
                                responsive=True, size="sm",
                                style={"fontSize": "12px"}),
                                style={"overflowX": "auto",
                                       "maxHeight": "60vh",
                                       "overflowY": "auto"},
                            ),
                            type="circle",
                        ),
 
                    ], style={"marginTop": "20px"})],
                ),
            ],
            style={"marginBottom": "20px"},
        ),
 
    ], className="portal-page")

def admin_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["admin"]
    from app.dash_apps.pages.portal_pages import _page_title
    if active_tab == "dashboard":
        
        return html.Div([
            _page_title("fa-user-shield", c, "Admin Dashboard"),
            _sec_hdr("Society Overview", "click any KPI to drill down"),
            _kpi_row(
                _kpi("kpi_apartments_total",   "fa-home",          "#1859b8", "Apartments"),
                _kpi("kpi_vendors_total",      "fa-truck",         "#b98a07", "Vendors"),
                _kpi("kpi_security_total",     "fa-user-shield",   "#b63b3b", "Security Total"),
                _kpi("kpi_security_on_duty",   "fa-user-shield",   "#691b1b", "Security On Duty"),
                _kpi("kpi_events_total",       "fa-calendar-check","#8e44ad", "Upcoming Events"),
                _kpi("kpi_concerns_open",      "fa-hand-point-up", "#de5c52", "Open Concerns"),
                _kpi("kpi_gate_logs",          "fa-receipt",       "#1abc9c", "Gate Logs -24hrs"),
                _kpi("kpi_receipts_month",     "fa-receipt",       "#17976e", "Receipts (Month)"),
                _kpi("kpi_expenses_month",     "fa-exclamation-triangle",       "#aa241a", "Expenses (Month)"),
                _kpi("kpi_cash_in_hand",       "fa-wallet",        "#2c3e50", "Cash in Hand"),
                _kpi("kpi_bank_balance",            "fa-wallet",        "#2c3e50", "Bank Balance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "enroll":
        return html.Div([
            _page_title("fa-user-plus", c, "Enroll Members",
                        "apartments · vendors · security"),
            _sec_hdr("Current Counts", "click to view full list"),
            _kpi_row(
                _kpi("kpi_apartments_total", "fa-home",          "#1859b8", "Apartments"),
                _kpi("kpi_vendors_total",    "fa-truck","#b98a07", "Vendors"),
                _kpi("kpi_security_total",   "fa-user-shield",   "#b63b3b", "Security Staff"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "cashbook":
        return html.Div([
            _page_title("fa-book", c, "Cashbook", "full transaction ledger"),
            _kpi_row(
                _kpi("kpi_receivables_total", "fa-receipt", "#331797", "Receipts Due"),
                _kpi("kpi_payables_total", "fa-wallet",  "#6552de", "Expenses Due"),
                _kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi("kpi_expenses_month", "fa-wallet",  "#de5c52", "Expenses (Month)"),
                _kpi("kpi_cash_in_hand",       "fa-wallet",        "#2c3e50", "Cash in Hand"),
                _kpi("kpi_bank_balance",        "fa-coins",   "#2c3e50", "Bank Balance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
                ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "receipts":
        return html.Div([
            _page_title("fa-file-invoice-dollar", c, "Receipts", "all incoming payments"),
            
                _kpi_row(
                _kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi("kpi_receivables_total", "fa-receipt", "#17976e", "Receipts (Total))"),
                _kpi("kpi_maintenance_due", "fa-receipt", "#7674e0", "Maintainence Due"),
                _kpi("kpi_late_fees_due", "fa-wallet",  "#7674e0", "Late Fees Due"),
                _kpi("kpi_vendor_payables_due",       "fa-wallet", "#2c3e50", "Vendor Payables Due"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
                ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "expenses":
        return html.Div([
            _page_title("fa-wallet", c, "Expenses", "outgoing payments"),
            _kpi_row(
                _kpi("kpi_expenses_month", "fa-wallet", "#de5c52", "Expenses (Month)"),
                _kpi("kpi_payables_total", "fa-wallet",  "#de5c52", "Expenses Due (Total))"),
                _kpi("kpi_security_salaries_due", "fa-receipt", "#7674e0", "Securities Salaries Due"),
                _kpi("kpi_amc_due", "fa-receipt", "#7674e0", "AMC Due"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
                ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "events":
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events", "upcoming society events"),
            _kpi_row(
                _kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
                ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "Concerns", "maintenance & issues"),
            _kpi_row(_kpi("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns"),
                     cols="1fr"),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab == "evaluate_pass":
        return _evaluate_pass_page()

    if active_tab == "customize":
        
        return _customize_page(c)

    if active_tab == "settings":
        return html.Div([
            _page_title("fa-cog", c, "Settings", "accounts & charge rates"),
            _kpi_row(
                _kpi("kpi_societies_arrear_start_date", "fa-clock", "#34ee45", "Arrear Start Date"),
                _kpi("kpi_plan_validity", "fa-clock", "#34ee45", "Society Plan Validity"),

                _kpi("kpi_accounts_count",       "fa-book-open",   "#6c5ce7", "Accounts"),
                _kpi("kpi_apt_charges", "fa-rupee-sign",  "#de5c52", "Apartment Charges"),
                _kpi("kpi_ven_charges", "fa-rupee-sign",  "#de5c52", "Vendor Charges"),
                _kpi("kpi_sec_charges", "fa-rupee-sign",  "#de5c52", "Security Charges"),
                _kpi("kpi_attendance", "fa-book-open",  "#6638bd", "Attendance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    # Generic fallback
    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# OWNER (APARTMENT) PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def owner_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["apartment"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-home", c, "Owner Dashboard"),
            _sec_hdr("My Account", "click any card to view details"),
            _kpi_row(
                _kpi("kpi_apartments_dues",  "fa-rupee-sign",    "#de5c52", "Pending Dues",   "tap to pay"),
                _kpi("kpi_concerns_open",    "fa-hand-point-up", "#e59620", "My Concerns"),
                _kpi("kpi_events_total",     "fa-calendar-check","#8e44ad", "Upcoming Events"),
                _kpi("kpi_gate_logs",        "fa-receipt",  "#1abc9c", "Gate Logs"),
                _kpi("kpi_receipts_month",   "fa-receipt",       c,         "Paid (Month)"),
                _kpi("kpi_receivables_total", "fa-wallet",        "#2c3e50", "To Pay"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(),
            _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "owner_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook", "payments & charges"),
            _kpi_row(
                _kpi("kpi_receipts_month", "fa-receipt", c,         "Paid (Month)"),
                _kpi("kpi_receivables_total", "fa-wallet",        "#2c3e50", "To Pay"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "payments":
        return html.Div([
            _page_title("fa-credit-card", c, "My Payments", "maintenance & dues"),
            
            _kpi_row(
                _kpi("kpi_receivables_total", "fa-wallet",        "#2c3e50", "To Pay"),
                _kpi("kpi_apartments_dues", "fa-rupee-sign", "#de5c52", "Pending Dues"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "charges":
        return html.Div([
            _page_title("fa-file-invoice", c, "My Charges", "maintenance rates & fines"),
            _kpi_row(
                _kpi("kpi_maintainence_charges", "fa-file-invoice", "#e59620", "Maintainence Charge"),
                _kpi("kpi_apartment_fines", "fa-file-invoice", "#e59620", "Fines"),
                _kpi("kpi_apartment_other_charges", "fa-file-invoice", "#e59620", "Other Charge"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "owner_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events", "upcoming society events"),
            _kpi_row(_kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "My Concerns",
                        "raise & track maintenance issues"),
            _kpi_row(_kpi("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "owner_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Profile & Settings"),
            _kpi_row(_kpi("kpi_apartment_date", "fa-hand-point-up", "#de5c52", "Managed since"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),

        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# VENDOR PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def vendor_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["vendor"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-briefcase", c, "Vendor Dashboard"),
            _sec_hdr("My Overview"),
            _kpi_row(
                _kpi("kpi_concerns_open",   "fa-hand-point-up", "#e59620", "Jobs / Concerns"),
                _kpi("kpi_events_total",    "fa-calendar-check","#8e44ad", "Upcoming Events"),
                _kpi("kpi_receivables_total", "fa-receipt", "#331797", "Payable Due"),
                _kpi("kpi_receipts_month",  "fa-receipt",       "#17976e", "Paid (Month)"),
                _kpi("kpi_gate_logs", "fa-receipt",  "#1abc9c", "Gate Logs Today"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "vendor_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook"),
            _kpi_row(
                _kpi("kpi_receivables_total", "fa-receipt", "#331797", "Receipts Due"),
                _kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("charges", "vendor_charges"):
        return html.Div([
            _page_title("fa-file-invoice", c, "My Charges"),
            _kpi_row(
                _kpi("kpi_vendor_fines", "fa-file-invoice", "#e59620", "Fines"),
                _kpi("kpi_vendor_other_charges", "fa-file-invoice", "#e59620", "Other Charge"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "vendor_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row(_kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Events"),
                     cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "vendor_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row(_kpi("kpi_vendor_date", "fa-hand-point-up", "#de5c52", "Managed since"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def security_portal_page(active_tab: str = "pass_evaluation") -> html.Div:
    c = _C["security"]

    if active_tab == "pass_evaluation":
        return _evaluate_pass_page()

    if active_tab == "attendance":
        return html.Div([
            _page_title("fa-clock", c, "Attendance", "clock in / clock out"),
            dbc.Card(dbc.CardBody([
                html.I(className="fas fa-clock fa-3x mb-3 d-block text-center",
                       style={"color": c}),
                html.H5("Today's Status", className="text-center mb-4"),
                dbc.Row([
                    dbc.Col(dbc.Button(
                        [html.I(className="fas fa-sign-in-alt me-2"), "Clock In"],
                        id="clock-in-btn", color="success", size="lg",
                        className="w-100"), width=6),
                    dbc.Col(dbc.Button(
                        [html.I(className="fas fa-sign-out-alt me-2"), "Clock Out"],
                        id="clock-out-btn", color="danger", size="lg",
                        className="w-100"), width=6),
                ], className="mb-3"),
                html.Div(id="attendance-status",
                         className="text-center text-muted",
                         style={"fontSize": "13px"}),
            ]), style={"borderRadius": "16px", "maxWidth": "460px", "margin": "0 auto 20px"}),
            _divider(),
            _sec_hdr("Gate Logs", "today's entries", "fa-receipt"),
            _kpi_row(_kpi("kpi_gate_logs", "fa-receipt", "#1abc9c", "Gate Logs Today"),
                     cols="1fr"),
            _drill_panel(),
        ], className="portal-page")
    if active_tab in ("cashbook", "security_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook"),
            _kpi_row(
                _kpi("kpi_receivables_total", "fa-receipt", "#331797", "Receipts Due"),
                _kpi("kpi_payables_total", "fa-wallet",  "#6552de", "Expenses Due"),
                _kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi("kpi_expenses_month", "fa-wallet",  "#de5c52", "Expenses (Month)"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("charges", "security_charges"):
        return html.Div([
            _page_title("fa-file-invoice", c, "My Charges"),
            _kpi_row(
                _kpi("kpi_security_fines", "fa-file-invoice", "#e59620", "Fines"),
                _kpi("kpi_security_other_charges", "fa-file-invoice", "#e59620", "Other Charge"),
                _kpi("kpi_receipts_in_hand_total", "fa-receipt", "#17976e", "Receipts-in-hand"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("payments", "security_payments"):
        return html.Div([
            _page_title("fa-file-invoice", c, "My Payments"),
            _kpi_row(
                _kpi("kpi_security_salary_due", "fa-file-invoice", "#e59620", "Salary"),
                _kpi("kpi_security_bonus_due", "fa-file-invoice", "#e59620", ""),
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")
    if active_tab == "security_events":
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row(_kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events"),
                     cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_receipt":
        return html.Div([
            _page_title("fa-plus-circle", c, "New Receipt",
                        "collect cash payments at gate"),
            _kpi_row(_kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                     cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-users", c, "All Users", "registered members"),
            _kpi_row(
                _kpi("kpi_apartments_total", "fa-home",          "#1859b8", "Apartments"),
                _kpi("kpi_vendors_total",    "fa-truck","#b98a07", "Vendors"),
                _kpi("kpi_security_total",   "fa-user-shield",   c,         "Security"),
                _kpi("kpi_security_shift_count", "fa-hand-point-up", "#de5c52", "Shift count"),
                _kpi("kpi_receipts_in_hand_total", "fa-receipt", "#17976e", "Receipts-in-hand"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "security_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row(
                _kpi("kpi_security_date", "fa-hand-point-up", "#de5c52", "Managed since"),
                _kpi("kpi_security_salary_per_shift", "fa-hand-point-up", "#de5c52", "Managed since"),
                _kpi("kpi_security_shift", "fa-hand-point-up", "#de5c52", "Managed since"),
                
            cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# In app/dash_apps/pages/portal_pages.py
# Replace _evaluate_pass_page():

def _evaluate_pass_page() -> html.Div:
    return html.Div([
        _page_title("fa-qrcode", "#1859b8", "Gate Pass Evaluation",
                    "Entry IN / Exit OUT scanning"),
        # dcc.Store(id="qr-camera-store", data={}),
        # dcc.Store(id="qr-scan-log",     data=[]),
        # dcc.Store(id="qr-entity-store", data={}),
        # TWO-COLUMN LAYOUT
        html.Div([
            # ══════════════════════════════════════════════════════
            # LEFT COLUMN: Scanner
            # ══════════════════════════════════════════════════════
            html.Div(
                dbc.Card([
                    dbc.CardHeader(html.Div([
                        html.I(className="fas fa-camera me-2", style={"color": "#1859b8"}),
                        html.Strong("QR Scanner"),
                        dbc.Badge("LIVE", color="success", className="ms-2", 
                                 style={"fontSize": "9px"}),
                    ], style={"display": "flex", "alignItems": "center"}),
                    style={"padding": "10px 14px"}),
                    
                    dbc.CardBody([
                        # Hidden inputs
                        dcc.Input(id="qr-scan-input", style={"display": "none"}),
                        dcc.Input(id="qr-scan-mode",  style={"display": "none"}),
                        html.Button(id="qr-validate-btn", n_clicks=0, style={"display": "none"}),
                        
                        # Result display
                        html.Div(id="qr-result", style={"minHeight": "60px"}),
                        
                        html.Hr(style={"margin": "10px 0"}),
                        
                        # Camera container
                        html.Div(
                            id="qr-camera-container",
                            style={
                                "position": "relative",
                                "borderRadius": "10px",
                                "overflow": "hidden",
                                "background": "#1a1a2e",
                                "marginBottom": "10px",
                                "minHeight": "60px",
                            },
                            children=[
                                html.Video(
                                    id="qr-video",
                                    autoPlay=True, muted=True,
                                    style={
                                        "width": "100%", "maxHeight": "300px",
                                        "objectFit": "cover", "display": "none",
                                        "borderRadius": "10px",
                                    },
                                ),
                                html.Div(
                                    id="qr-scanline",
                                    style={"display": "none"},
                                ),
                                html.Div(
                                    id="qr-corners",
                                    style={"display": "none"},
                                    children=[
                                        html.Div(style={
                                            "position": "absolute", "width": "22px", "height": "22px",
                                            "border": "3px solid #1859b8",
                                            "borderRight": "none", "borderBottom": "none",
                                            "top": "10px", "left": "10px", "borderRadius": "3px 0 0 0",
                                        }),
                                        html.Div(style={
                                            "position": "absolute", "width": "22px", "height": "22px",
                                            "border": "3px solid #1859b8",
                                            "borderLeft": "none", "borderBottom": "none",
                                            "top": "10px", "right": "10px", "borderRadius": "0 3px 0 0",
                                        }),
                                        html.Div(style={
                                            "position": "absolute", "width": "22px", "height": "22px",
                                            "border": "3px solid #1859b8",
                                            "borderRight": "none", "borderTop": "none",
                                            "bottom": "10px", "left": "10px", "borderRadius": "0 0 0 3px",
                                        }),
                                        html.Div(style={
                                            "position": "absolute", "width": "22px", "height": "22px",
                                            "border": "3px solid #1859b8",
                                            "borderLeft": "none", "borderTop": "none",
                                            "bottom": "10px", "right": "10px", "borderRadius": "0 0 3px 0",
                                        }),
                                    ],
                                ),
                                html.Canvas(id="qr-canvas", style={"display": "none"}),
                            ],
                        ),
                        
                        # Status
                        html.Small(id="qr-scan-status", children="Camera off",
                                  style={"color": "#aaa", "fontSize": "11px", "display": "block",
                                         "textAlign": "center", "marginBottom": "10px"}),
                        
                        # Control buttons
                        html.Div([
                            dbc.Button(
                                [html.I(className="fas fa-sign-in-alt me-1"), "Entry IN"],
                                id="qr-entry-start-btn", color="success", size="sm",
                                style={"flex": "1"}, n_clicks=0,
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-sign-out-alt me-1"), "Exit OUT"],
                                id="qr-exit-start-btn", color="danger", size="sm",
                                style={"flex": "1"}, n_clicks=0,
                            ),
                        ], style={"display": "flex", "gap": "6px", "marginBottom": "6px"}),
                        
                        html.Div([
                            dbc.Button(
                                [html.I(className="fas fa-stop me-1"), "Stop"],
                                id="qr-entry-stop-btn", color="secondary", size="sm", outline=True,
                                style={"display": "none", "flex": "1"}, n_clicks=0,
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-stop me-1"), "Stop"],
                                id="qr-exit-stop-btn", color="secondary", size="sm", outline=True,
                                style={"display": "none", "flex": "1"}, n_clicks=0,
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-sync-alt me-1"), "Flip"],
                                id="qr-switch-btn", color="info", size="sm", outline=True,
                                style={"display": "none"}, n_clicks=0,
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-lightbulb me-1"), "Light"],
                                id="qr-torch-btn", color="warning", size="sm", outline=True,
                                style={"display": "none"}, n_clicks=0,
                            ),
                        ], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                        
                        html.Hr(style={"margin": "10px 0"}),
                        
                        # Emergency buttons
                        html.Div([
                            dbc.Button(
                                [html.I(className="fas fa-exclamation-triangle me-1"), "EMERGENCY"],
                                id="emergency-btn", color="danger", size="sm",
                                style={"flex": "1", "fontWeight": "700"}, n_clicks=0,
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-phone me-1"), "Call Admin"],
                                id="call-admin-btn", color="primary", size="sm",
                                style={"flex": "0"}, n_clicks=0,
                            ),
                        ], style={"display": "flex", "gap": "6px"}),
                        
                    ], style={"padding": "14px"}),
                ], style={"borderRadius": "18px", "boxShadow": "0 10px 28px rgba(24,89,184,0.1)"}),
                style={"flex": "1 1 320px", "minWidth": "280px"},
            ),
            
            # ══════════════════════════════════════════════════════
            # RIGHT COLUMN: Recent Scans
            # ══════════════════════════════════════════════════════
            html.Div(
                dbc.Card([
                    dbc.CardHeader(html.Div([
                        html.I(className="fas fa-history me-2", style={"color": "#7d8ea3"}),
                        html.Strong("Recent Scans"),
                    ], style={"display": "flex", "alignItems": "center"}),
                    style={"padding": "10px 14px"}),
                    
                    dbc.CardBody(
                        dbc.ListGroup(
                            id="qr-recent-scans",
                            children=[dbc.ListGroupItem(
                                "No scans yet",
                                className="text-muted text-center",
                                style={"fontSize": "11px", "padding": "10px"},
                            )],
                            flush=True,
                            style={"maxHeight": "520px", "overflowY": "auto"},
                        ),
                        style={"padding": "8px"},
                    ),
                ], style={"borderRadius": "18px", "boxShadow": "0 10px 28px rgba(0,0,0,0.06)"}),
                style={"flex": "1 1 280px", "minWidth": "240px"},
            ),
            
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
        
        # Call Admin Modal
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Contact Admin"), close_button=True),
            dbc.ModalBody(html.Div(id="admin-phone-display", className="text-center")),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-call-modal", color="secondary", n_clicks=0)
            ),
        ], id="call-admin-modal", centered=True, size="sm"),
        
        html.Div(id="kpi-row",          style={"display": "none"}),
        html.Div(id="drill-breadcrumb", style={"display": "none"}),
        html.Div(id="drill-content",    style={"display": "none"}),
    
    ], className="portal-page")

def _corner_div(v: str, h: str) -> html.Div:
    """QR viewfinder corner marker."""
    s: dict = {
        "position": "absolute", "width": "20px", "height": "20px",
        "border": "3px solid #1859b8",
        "borderRadius": "2px",
    }
    s[v] = "8px"
    s[h] = "8px"
    # Remove the inner edges so it looks like a corner bracket
    s["borderRight"  if h == "left"  else "borderLeft"]  = "none"
    s["borderBottom" if v == "top"   else "borderTop"]   = "none"
    return html.Div(style=s)
