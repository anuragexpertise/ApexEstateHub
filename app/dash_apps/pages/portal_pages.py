# app/dash_apps/pages/portal_pages.py
"""
All 5 role portal page layouts — integrated with the Drill-Down UX Engine.

Each portal page:
  1. Renders KPI row (clickable → drill into list)
  2. Renders #drill-content div (the drill-down content area)
  3. Renders #drill-breadcrumb (updated by callbacks)
  4. Has a dcc.Store for drill-down state

Pages:
  master_portal_page()
  admin_portal_page()
  owner_portal_page()
  vendor_portal_page()
  security_portal_page()
"""

from __future__ import annotations
from dash import html, dcc
import dash_bootstrap_components as dbc


# ── Colour tokens per role (must match CSS theme-* classes) ──────────────────
ROLE_THEME = {
    "master":    {"primary": "#c96a19", "light": "#fff1e0", "icon": "fa-crown"},
    "admin":     {"primary": "#1859b8", "light": "#dbeafe", "icon": "fa-user-shield"},
    "apartment": {"primary": "#18794e", "light": "#d9fbe3", "icon": "fa-home"},
    "vendor":    {"primary": "#b98a07", "light": "#fff1b8", "icon": "fa-briefcase"},
    "security":  {"primary": "#b63b3b", "light": "#ffd6d6", "icon": "fa-shield-alt"},
}


# ═══════════════════════════════════════════════════════════════════════════
# SHARED BUILDING BLOCKS
# ═══════════════════════════════════════════════════════════════════════════

def _kpi_shell(card_id: str, icon: str, color: str,
               label: str, subtitle: str = "") -> html.Div:
    """
    Placeholder KPI card whose value is filled by card_catalogue_callbacks.
    The outer div is the drill-down click target.
    Uses id={"type":"kpi-card-div","card_id":card_id} — matches drilldown_callbacks.
    """
    return html.Div(
        html.Div(
            [
                html.Div(style={                             # accent bar
                    "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                    "width": "4px", "background": color, "borderRadius": "4px 0 0 4px",
                }),
                html.Div("⠿", className="dnd-handle", style={
                    "position": "absolute", "top": "6px", "right": "8px",
                    "fontSize": "12px", "color": "#ddd", "cursor": "grab",
                    "userSelect": "none",
                }),
                html.I(className=f"fas {icon}",
                       style={"color": color, "fontSize": "20px", "marginBottom": "8px",
                              "display": "block"}),
                html.Div("—",
                         id={"type": "kpi-value", "card_id": card_id},
                         style={"fontSize": "24px", "fontWeight": "800",
                                "color": "#15304f", "lineHeight": "1"}),
                html.Div(label, style={
                    "fontSize": "11px", "fontWeight": "600", "color": "#7d8ea3",
                    "marginTop": "4px", "textTransform": "uppercase", "letterSpacing": "0.4px",
                }),
                html.Div(subtitle, style={"fontSize": "10px", "color": "#aaa", "marginTop": "2px"}) if subtitle else None,
                html.Div(html.I(className="fas fa-arrow-right",
                                style={"fontSize": "9px", "color": color}),
                         style={"position": "absolute", "bottom": "8px", "right": "12px",
                                "opacity": "0.5"}),
            ],
            id={"type": "kpi-card-div", "card_id": card_id},
            n_clicks=0,
            title=f"Click to view {label}",
            style={
                "position": "relative",
                "background": "linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,251,255,0.9))",
                "border": "1px solid rgba(255,255,255,0.68)",
                "borderRadius": "16px",
                "padding": "18px 14px 14px 18px",
                "cursor": "pointer",
                "boxShadow": "0 8px 24px rgba(15,23,42,0.07)",
                "transition": "transform 0.16s ease, box-shadow 0.16s ease",
                "minHeight": "108px",
                "backdropFilter": "blur(10px)",
                "overflow": "hidden",
            },
        ),
        className="kpi-card",
    )


def _section_header(title: str, subtitle: str = "", icon: str = "fa-layer-group") -> html.Div:
    return html.Div(
        [
            html.I(className=f"fas {icon} me-2", style={"color": "#7d8ea3", "fontSize": "14px"}),
            html.Span(title, style={"fontWeight": "700", "fontSize": "15px", "color": "#15304f"}),
            html.Small(f"  {subtitle}", style={"color": "#aaa", "fontSize": "11px"}) if subtitle else None,
        ],
        style={"marginBottom": "14px", "marginTop": "4px",
               "display": "flex", "alignItems": "center"},
    )


def _drill_area() -> html.Div:
    """
    The drill-down content panel.
    id="drill-content" is the Output target in drilldown_callbacks.py.
    id="drill-breadcrumb" shows the navigation crumb trail.
    """
    return html.Div(
        [
            # Breadcrumb trail
            html.Div(id="drill-breadcrumb"),
            # Dynamic card content (list / profile / form)
            html.Div(
                id="drill-content",
                children=html.Div(
                    [
                        html.I(className="fas fa-hand-pointer fa-2x mb-3",
                               style={"color": "rgba(29,116,216,0.2)"}),
                        html.P("Click any KPI card above to explore",
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
            "boxShadow": "0 10px 30px rgba(15,23,42,0.06)",
            "minHeight": "400px",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PORTAL  — manage all societies
# ═══════════════════════════════════════════════════════════════════════════

def master_portal_page() -> html.Div:
    color = ROLE_THEME["master"]["primary"]
    return html.Div(
        [
            # ── Page title ─────────────────────────────────────────────────
            html.Div(
                [
                    html.Div(
                        html.I(className="fas fa-crown",
                               style={"color": "#fff", "fontSize": "18px"}),
                        style={
                            "width": "44px", "height": "44px", "borderRadius": "12px",
                            "background": f"linear-gradient(135deg,{color},{color}aa)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "14px",
                        },
                    ),
                    html.Div(
                        [
                            html.H4("Master Admin Portal", className="mb-0",
                                    style={"fontWeight": "800", "color": "#15304f"}),
                            html.Small("Manage all societies on this platform",
                                       style={"color": "#aaa"}),
                        ]
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "marginBottom": "24px"},
            ),

            # ── KPI Row ────────────────────────────────────────────────────
            _section_header("Platform Overview", "click any card to drill down", "fa-chart-bar"),
            html.Div(
                [
                    _kpi_shell("kpi_societies_total", "fa-building", color, "Total Societies"),
                    _kpi_shell("kpi_societies_paid",  "fa-star",     "#17976e", "Paid Plan",   "active subscriptions"),
                    _kpi_shell("kpi_societies_free",  "fa-circle",   "#7d8ea3", "Free Plan"),
                    _kpi_shell("kpi_apartments_total","fa-home",     "#1859b8", "Apartments",  "across all societies"),
                    _kpi_shell("kpi_vendors_total",   "fa-person-digging", "#b98a07", "Vendors"),
                    _kpi_shell("kpi_security_total",  "fa-user-shield",    "#b63b3b", "Security Staff"),
                ],
                className="kpi-row",
                style={"gridTemplateColumns": "repeat(auto-fill,minmax(160px,1fr))"},
            ),

            html.Hr(style={"margin": "24px 0", "opacity": "0.15"}),

            # ── Drill-Down Panel ───────────────────────────────────────────
            _drill_area(),
        ],
        className="portal-page",
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN PORTAL  — full society management
# ═══════════════════════════════════════════════════════════════════════════

def admin_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = ROLE_THEME["admin"]["primary"]

    # ── DASHBOARD tab ──────────────────────────────────────────────────────
    if active_tab == "dashboard":
        return html.Div(
            [
                html.Div(
                    [
                        html.I(className="fas fa-user-shield me-2",
                               style={"color": c, "fontSize": "20px"}),
                        html.H4("Admin Dashboard", className="mb-0",
                                style={"fontWeight": "800", "color": "#15304f"}),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "20px"},
                ),

                _section_header("Society Overview", "click any card to drill down"),
                html.Div(
                    [
                        _kpi_shell("kpi_apartments_total",  "fa-home",          "#1859b8", "Apartments"),
                        _kpi_shell("kpi_apartments_dues",   "fa-rupee-sign",    "#de5c52", "With Dues",   "need attention"),
                        _kpi_shell("kpi_apartments_no_dues","fa-check-circle",  "#17976e", "Dues Clear",  "fully paid"),
                        _kpi_shell("kpi_vendors_total",     "fa-person-digging","#b98a07", "Vendors"),
                        _kpi_shell("kpi_security_total",    "fa-user-shield",   "#b63b3b", "Security"),
                        _kpi_shell("kpi_events_total",      "fa-calendar-check","#8e44ad", "Upcoming Events"),
                        _kpi_shell("kpi_concerns_open",     "fa-hand-point-up", "#de5c52", "Open Concerns"),
                        _kpi_shell("kpi_gate_logs_today",   "fa-road-barrier",  "#1abc9c", "Gate Logs Today"),
                        _kpi_shell("kpi_receipts_month",    "fa-receipt",       "#17976e", "Receipts (Month)"),
                        _kpi_shell("kpi_balance",           "fa-wallet",        "#2c3e50", "Balance"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(auto-fill,minmax(155px,1fr))"},
                ),
                html.Hr(style={"margin": "20px 0", "opacity": "0.15"}),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── ENROLL tab ─────────────────────────────────────────────────────────
    if active_tab == "enroll":
        return html.Div(
            [
                _section_header("Enroll Members", "apartments · vendors · security", "fa-user-plus"),
                html.Div(
                    [
                        _kpi_shell("kpi_apartments_total","fa-home",          "#1859b8", "Apartments"),
                        _kpi_shell("kpi_vendors_total",  "fa-person-digging", "#b98a07", "Vendors"),
                        _kpi_shell("kpi_security_total", "fa-user-shield",    "#b63b3b", "Security Staff"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(3,1fr)", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── CASHBOOK tab ───────────────────────────────────────────────────────
    if active_tab == "cashbook":
        return html.Div(
            [
                _section_header("Cashbook", "full transaction ledger", "fa-book"),
                html.Div(
                    [
                        _kpi_shell("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                        _kpi_shell("kpi_expenses_month", "fa-wallet",  "#de5c52", "Expenses (Month)"),
                        _kpi_shell("kpi_balance",        "fa-coins",   "#2c3e50", "Balance"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(3,1fr)", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── RECEIPTS tab ───────────────────────────────────────────────────────
    if active_tab == "receipts":
        return html.Div(
            [
                _section_header("Receipts", "all incoming payments", "fa-file-invoice-dollar"),
                html.Div(
                    [_kpi_shell("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)")],
                    className="kpi-row",
                    style={"gridTemplateColumns": "1fr", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── EXPENSES tab ───────────────────────────────────────────────────────
    if active_tab == "expenses":
        return html.Div(
            [
                _section_header("Expenses", "outgoing payments", "fa-wallet"),
                html.Div(
                    [_kpi_shell("kpi_expenses_month", "fa-wallet", "#de5c52", "Expenses (Month)")],
                    className="kpi-row",
                    style={"gridTemplateColumns": "1fr", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── EVENTS tab ─────────────────────────────────────────────────────────
    if active_tab == "events":
        return html.Div(
            [
                _section_header("Events", "upcoming society events", "fa-calendar-alt"),
                html.Div(
                    [_kpi_shell("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events")],
                    className="kpi-row",
                    style={"gridTemplateColumns": "1fr", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── CONCERNS tab ───────────────────────────────────────────────────────
    if active_tab == "concerns":
        return html.Div(
            [
                _section_header("Concerns", "maintenance & issues", "fa-hand-point-up"),
                html.Div(
                    [_kpi_shell("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns")],
                    className="kpi-row",
                    style={"gridTemplateColumns": "1fr", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # ── EVALUATE PASS tab ──────────────────────────────────────────────────
    if active_tab == "evaluate_pass":
        return _evaluate_pass_page()

    # ── SETTINGS tab ───────────────────────────────────────────────────────
    if active_tab == "settings":
        return html.Div(
            [
                _section_header("Settings", "accounts & charges", "fa-cog"),
                html.Div(
                    [
                        _kpi_shell("kpi_balance",       "fa-book-open", "#6c5ce7", "Accounts"),
                        _kpi_shell("kpi_concerns_open", "fa-rupee-sign","#de5c52", "Pending Dues"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(2,1fr)", "marginBottom": "20px"},
                ),
                _drill_area(),
            ],
            className="portal-page",
        )

    # Fallback
    return html.Div(
        html.P(f"Section: {active_tab}", className="text-muted p-4"),
        className="portal-page",
    )


# ═══════════════════════════════════════════════════════════════════════════
# OWNER (APARTMENT) PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def owner_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = ROLE_THEME["apartment"]["primary"]

    if active_tab == "dashboard":
        return html.Div(
            [
                html.Div(
                    [
                        html.I(className="fas fa-home me-2",
                               style={"color": c, "fontSize": "20px"}),
                        html.H4("Owner Dashboard", className="mb-0",
                                style={"fontWeight": "800", "color": "#15304f"}),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "20px"},
                ),

                _section_header("My Account", "click any card to view details"),
                html.Div(
                    [
                        _kpi_shell("kpi_apartments_dues",  "fa-rupee-sign",    "#de5c52", "Pending Dues",   "tap to pay"),
                        _kpi_shell("kpi_concerns_open",    "fa-hand-point-up", "#e59620", "My Concerns"),
                        _kpi_shell("kpi_events_total",     "fa-calendar-check","#8e44ad", "Upcoming Events"),
                        _kpi_shell("kpi_gate_logs_today",  "fa-road-barrier",  "#1abc9c", "My Gate Logs"),
                        _kpi_shell("kpi_receipts_month",   "fa-receipt",       "#17976e", "Paid (Month)"),
                        _kpi_shell("kpi_balance",          "fa-wallet",        "#2c3e50", "Balance"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(auto-fill,minmax(150px,1fr))"},
                ),
                html.Hr(style={"margin": "20px 0", "opacity": "0.15"}),
                _drill_area(),
            ],
            className="portal-page",
        )

    if active_tab in ("cashbook", "owner_cashbook"):
        return html.Div([
            _section_header("My Cashbook", "payments & charges", "fa-book"),
            html.Div(
                [
                    _kpi_shell("kpi_receipts_month", "fa-receipt", "#17976e", "Paid (Month)"),
                    _kpi_shell("kpi_balance",        "fa-wallet",  "#2c3e50", "Balance"),
                ],
                className="kpi-row",
                style={"gridTemplateColumns": "repeat(2,1fr)", "marginBottom": "20px"},
            ),
            _drill_area(),
        ], className="portal-page")

    if active_tab == "payments":
        return html.Div([
            _section_header("My Payments", "maintenance & other dues", "fa-credit-card"),
            html.Div([_kpi_shell("kpi_apartments_dues", "fa-rupee-sign", "#de5c52", "Pending Dues")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab == "charges":
        return html.Div([
            _section_header("My Charges", "maintenance rates & fines", "fa-file-invoice"),
            html.Div([_kpi_shell("kpi_balance", "fa-file-invoice", "#e59620", "Charges")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("events", "owner_events"):
        return html.Div([
            _section_header("Events", "upcoming society events", "fa-calendar-alt"),
            html.Div([_kpi_shell("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _section_header("My Concerns", "raise & track maintenance issues", "fa-hand-point-up"),
            html.Div([_kpi_shell("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("settings", "owner_settings"):
        return html.Div([
            _section_header("My Profile & Settings", "", "fa-cog"),
            _drill_area(),
        ], className="portal-page")

    return html.Div(html.P(f"Section: {active_tab}", className="text-muted p-4"), className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# VENDOR PORTAL
# ═══════════════════════════════════════════════════════════════════════════

def vendor_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = ROLE_THEME["vendor"]["primary"]

    if active_tab == "dashboard":
        return html.Div(
            [
                html.Div(
                    [
                        html.I(className="fas fa-briefcase me-2",
                               style={"color": c, "fontSize": "20px"}),
                        html.H4("Vendor Dashboard", className="mb-0",
                                style={"fontWeight": "800", "color": "#15304f"}),
                    ],
                    style={"display": "flex", "alignItems": "center", "marginBottom": "20px"},
                ),

                _section_header("My Overview"),
                html.Div(
                    [
                        _kpi_shell("kpi_vendors_dues",   "fa-rupee-sign",    "#de5c52", "Pending Dues"),
                        _kpi_shell("kpi_events_total",   "fa-calendar-check","#8e44ad", "Upcoming Events"),
                        _kpi_shell("kpi_concerns_open",  "fa-hand-point-up", "#e59620", "Jobs / Concerns"),
                        _kpi_shell("kpi_gate_logs_today","fa-road-barrier",  "#1abc9c", "Gate Logs Today"),
                        _kpi_shell("kpi_receipts_month", "fa-receipt",       "#17976e", "Receipts (Month)"),
                        _kpi_shell("kpi_balance",        "fa-wallet",        "#2c3e50", "Balance"),
                    ],
                    className="kpi-row",
                    style={"gridTemplateColumns": "repeat(auto-fill,minmax(150px,1fr))"},
                ),
                html.Hr(style={"margin": "20px 0", "opacity": "0.15"}),
                _drill_area(),
            ],
            className="portal-page",
        )

    if active_tab in ("cashbook", "vendor_cashbook"):
        return html.Div([
            _section_header("My Cashbook", "", "fa-book"),
            html.Div([
                _kpi_shell("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi_shell("kpi_expenses_month", "fa-wallet",  "#de5c52", "Expenses (Month)"),
                _kpi_shell("kpi_balance",        "fa-coins",   "#2c3e50", "Balance"),
            ], className="kpi-row",
               style={"gridTemplateColumns": "repeat(3,1fr)", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("payments", "vendor_payments"):
        return html.Div([
            _section_header("Payments", "", "fa-credit-card"),
            html.Div([_kpi_shell("kpi_vendors_dues", "fa-rupee-sign", "#de5c52", "Pending Dues")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("charges", "vendor_charges"):
        return html.Div([
            _section_header("My Charges", "", "fa-file-invoice"),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("events", "vendor_events"):
        return html.Div([
            _section_header("Events", "", "fa-calendar-alt"),
            html.Div([_kpi_shell("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("settings", "vendor_settings"):
        return html.Div([
            _section_header("My Settings", "", "fa-cog"),
            _drill_area(),
        ], className="portal-page")

    return html.Div(html.P(f"Section: {active_tab}", className="text-muted p-4"), className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# SECURITY PORTAL  — includes QR scanner (pass evaluation)
# ═══════════════════════════════════════════════════════════════════════════

def security_portal_page(active_tab: str = "pass_evaluation") -> html.Div:
    c = ROLE_THEME["security"]["primary"]

    if active_tab == "pass_evaluation":
        return _evaluate_pass_page()

    if active_tab == "attendance":
        return html.Div(
            [
                _section_header("Attendance", "clock in / clock out", "fa-clock"),
                dbc.Card(
                    dbc.CardBody([
                        html.Div([
                            html.I(className="fas fa-clock fa-3x mb-3",
                                   style={"color": c, "display": "block",
                                          "textAlign": "center"}),
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
                            ], className="mb-4"),
                            html.Div(id="attendance-status",
                                     className="text-center text-muted",
                                     style={"fontSize": "13px"}),
                        ]),
                    ]),
                    style={"borderRadius": "16px", "maxWidth": "480px", "margin": "0 auto"},
                ),

                html.Hr(style={"margin": "20px 0", "opacity": "0.15"}),
                _section_header("Gate Logs", "today's entries", "fa-road-barrier"),
                html.Div([_kpi_shell("kpi_gate_logs_today", "fa-road-barrier", "#1abc9c", "Gate Logs Today")],
                         className="kpi-row",
                         style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
                _drill_area(),
            ],
            className="portal-page",
        )

    if active_tab == "security_events":
        return html.Div([
            _section_header("Events", "", "fa-calendar-alt"),
            html.Div([_kpi_shell("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab == "security_receipt":
        return html.Div([
            _section_header("New Receipt", "collect cash payments", "fa-plus-circle"),
            html.Div([_kpi_shell("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)")],
                     className="kpi-row",
                     style={"gridTemplateColumns": "1fr", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab == "security_users":
        return html.Div([
            _section_header("Users", "all registered members", "fa-users"),
            html.Div([
                _kpi_shell("kpi_apartments_total", "fa-home",          "#1859b8", "Apartments"),
                _kpi_shell("kpi_vendors_total",    "fa-person-digging","#b98a07", "Vendors"),
                _kpi_shell("kpi_security_total",   "fa-user-shield",   "#b63b3b", "Security"),
            ], className="kpi-row",
               style={"gridTemplateColumns": "repeat(3,1fr)", "marginBottom": "20px"}),
            _drill_area(),
        ], className="portal-page")

    if active_tab in ("settings", "security_settings"):
        return html.Div([
            _section_header("My Settings", "", "fa-cog"),
            _drill_area(),
        ], className="portal-page")

    return html.Div(html.P(f"Section: {active_tab}", className="text-muted p-4"), className="portal-page")


# ═══════════════════════════════════════════════════════════════════════════
# QR EVALUATE PASS  — shared between Admin + Security portals
# Fixed camera: uses jsQR via requestAnimationFrame, proper permissions
# ═══════════════════════════════════════════════════════════════════════════

def _evaluate_pass_page() -> html.Div:
    return html.Div(
        [
            _section_header("Evaluate Gate Pass", "scan QR or enter code manually", "fa-qrcode"),

            html.Div(
                [
                    # ── Left: Scanner card ────────────────────────────────
                    html.Div(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            html.I(className="fas fa-qrcode me-2",
                                                   style={"color": "#1859b8"}),
                                            html.Strong("QR Scanner"),
                                            dbc.Badge("LIVE", color="success",
                                                      className="ms-2",
                                                      style={"fontSize": "9px",
                                                             "animation": "pulse 2s infinite"}),
                                        ],
                                        style={"display": "flex", "alignItems": "center"},
                                    ),
                                    style={"padding": "10px 14px"},
                                ),
                                dbc.CardBody(
                                    [
                                        # Manual entry
                                        dbc.InputGroup(
                                            [
                                                dbc.Input(
                                                    id="eval-qr-input",
                                                    placeholder="Scan QR or type code…",
                                                    debounce=False,
                                                    style={"borderRadius": "10px 0 0 10px",
                                                           "fontSize": "14px"},
                                                ),
                                                dbc.Button(
                                                    html.I(className="fas fa-check"),
                                                    id="eval-validate-btn",
                                                    color="primary",
                                                    style={"borderRadius": "0 10px 10px 0"},
                                                ),
                                            ],
                                            className="mb-3",
                                        ),

                                        # Result area
                                        html.Div(
                                            id="eval-result",
                                            style={
                                                "minHeight": "70px",
                                                "borderRadius": "10px",
                                                "padding": "10px",
                                                "transition": "all 0.3s",
                                            },
                                        ),

                                        html.Hr(style={"margin": "12px 0"}),

                                        # Camera preview
                                        html.Div(
                                            [
                                                html.Div(
                                                    style={
                                                        "position": "relative",
                                                        "borderRadius": "12px",
                                                        "overflow": "hidden",
                                                        "background": "#111",
                                                        "marginBottom": "10px",
                                                    },
                                                    children=[
                                                        html.Video(
                                                            id="eval-video",
                                                            autoPlay=True,
                                                            playsInline=True,
                                                            muted=True,
                                                            style={
                                                                "width": "100%",
                                                                "maxHeight": "220px",
                                                                "objectFit": "cover",
                                                                "display": "none",
                                                            },
                                                        ),
                                                        # Scan-line overlay
                                                        html.Div(
                                                            id="eval-scanline",
                                                            style={
                                                                "display": "none",
                                                                "position": "absolute",
                                                                "left": "0", "right": "0",
                                                                "top": "0", "height": "3px",
                                                                "background": "linear-gradient(90deg,transparent,#1859b8,transparent)",
                                                                "animation": "scanLine 2s ease-in-out infinite",
                                                            },
                                                        ),
                                                        # Corner markers
                                                        html.Div([
                                                            html.Div(style=_corner("top","left")),
                                                            html.Div(style=_corner("top","right")),
                                                            html.Div(style=_corner("bottom","left")),
                                                            html.Div(style=_corner("bottom","right")),
                                                        ], id="eval-corners", style={"display":"none"}),
                                                        html.Canvas(id="eval-canvas",
                                                                    style={"display": "none"}),
                                                    ],
                                                ),
                                                html.Small(
                                                    id="eval-scan-status",
                                                    children="Camera off — tap Start",
                                                    style={"color": "#aaa", "fontSize": "11px",
                                                           "display": "block",
                                                           "textAlign": "center",
                                                           "marginBottom": "8px"},
                                                ),
                                                html.Div(
                                                    [
                                                        dbc.Button(
                                                            [html.I(className="fas fa-camera me-1"), "Start"],
                                                            id="eval-start-btn", size="sm",
                                                            color="primary",
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="fas fa-sync-alt me-1"), "Flip"],
                                                            id="eval-switch-btn", size="sm",
                                                            color="info", outline=True,
                                                            style={"display": "none"},
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="fas fa-lightbulb me-1"), "Torch"],
                                                            id="eval-torch-btn", size="sm",
                                                            color="warning", outline=True,
                                                            style={"display": "none"},
                                                        ),
                                                        dbc.Button(
                                                            [html.I(className="fas fa-stop me-1"), "Stop"],
                                                            id="eval-stop-btn", size="sm",
                                                            color="danger", outline=True,
                                                            style={"display": "none"},
                                                        ),
                                                    ],
                                                    style={"display": "flex", "gap": "6px",
                                                           "flexWrap": "wrap",
                                                           "justifyContent": "center"},
                                                ),
                                            ]
                                        ),
                                    ],
                                    style={"padding": "14px"},
                                ),
                            ],
                            style={"borderRadius": "18px",
                                   "boxShadow": "0 10px 28px rgba(24,89,184,0.1)"},
                        ),
                        style={"flex": "1", "minWidth": "300px"},
                    ),

                    # ── Right: Recent scans ───────────────────────────────
                    html.Div(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            html.I(className="fas fa-history me-2",
                                                   style={"color": "#7d8ea3"}),
                                            html.Strong("Recent Scans"),
                                        ],
                                        style={"display": "flex", "alignItems": "center"},
                                    ),
                                    style={"padding": "10px 14px"},
                                ),
                                dbc.CardBody(
                                    dbc.ListGroup(
                                        id="eval-recent-scans",
                                        children=[
                                            dbc.ListGroupItem(
                                                "No scans yet",
                                                className="text-muted text-center",
                                                style={"fontSize": "12px", "padding": "10px"},
                                            )
                                        ],
                                        flush=True,
                                        style={"maxHeight": "400px", "overflowY": "auto"},
                                    ),
                                    style={"padding": "8px"},
                                ),
                            ],
                            style={"borderRadius": "18px",
                                   "boxShadow": "0 10px 28px rgba(0,0,0,0.06)"},
                        ),
                        style={"flex": "1", "minWidth": "260px"},
                    ),
                ],
                style={"display": "flex", "gap": "20px", "flexWrap": "wrap"},
            ),

            # CSS for animations
            html.Style("""
                @keyframes scanLine {
                    0%   { top: 2%;  opacity: 0; }
                    10%  { opacity: 1; }
                    90%  { opacity: 1; }
                    100% { top: 96%; opacity: 0; }
                }
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50%       { opacity: 0.4; }
                }
                #eval-video:not([style*="display: none"]) + div { display: block !important; }
            """),
        ],
        className="portal-page",
    )


def _corner(v: str, h: str) -> dict:
    """Helper: corner marker style for QR viewfinder."""
    s = {
        "position": "absolute", "width": "20px", "height": "20px",
        "border": "3px solid #1859b8", "borderRadius": "2px",
    }
    s[v]  = "8px"
    s[h]  = "8px"
    s["borderRight" if h == "left" else "borderLeft"] = "none"
    s["borderBottom" if v == "top" else "borderTop"]  = "none"
    return s
