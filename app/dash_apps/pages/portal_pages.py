# app/dash_apps/pages/portal_pages.py
"""
ALL 5 PORTAL PAGE LAYOUTS — single source of truth.
v3 additions:
  Admin:     new tabs — Receivables, payables, Assets
  Apartment: new tab  — Receivables (read-only own dues)
  Vendor:    new tab  — Receivables (read-only own pass/charges)
  Security:  new tab  — payables    (read-only own salary rows)
  All portals: Verify button on Receivables/payables is admin-only
               (enforced in renderers.py via _PORTAL_PERMS)
"""

from __future__ import annotations
import json
from dash import html, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import DEFAULT_LAYOUTS

_C = {
    "master":    "#c96a19",
    "admin":     "#1859b8",
    "apartment": "#18794e",
    "vendor":    "#b98a07",
    "security":  "#b63b3b",
}

# Single source of truth for KPI card sizing. `auto-fit` + a CAPPED max track
# width keeps every card the same width whether a tab shows 1 KPI or 8 — a lone
# KPI no longer stretches to full width, and a crowded tab no longer shrinks
# cards below the floor. Paired with the fixed `.kpi-card` height in style.css
# so every KPI tile is identical across all tabs / all portals.
KPI_GRID_COLS = "repeat(auto-fit, minmax(190px, 215px))"


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _kpi(card_id: str, icon: str, color: str, label: str, subtitle: str = "") -> html.Div:
    return html.Div(
        html.Div(
            [
                html.Div(style={
                    "position": "absolute", "left": 0, "top": 0, "bottom": 0,
                    "width": "4px", "background": color, "borderRadius": "4px 0 0 4px",
                }),
                html.Div("⠿", className="dnd-handle", style={
                    "position": "absolute", "top": "6px", "right": "8px",
                    "fontSize": "12px", "color": "#ddd", "cursor": "grab", "userSelect": "none",
                }),
                html.I(className=f"fas {icon}", style={
                    "color": color, "fontSize": "20px", "marginBottom": "8px", "display": "block",
                }),
                html.Div("—", id={"type": "kpi-value", "card_id": card_id}, style={
                    "fontSize": "24px", "fontWeight": "800", "color": "#15304f", "lineHeight": "1",
                }),
                html.Div(label, style={
                    "fontSize": "11px", "fontWeight": "600", "color": "#7d8ea3",
                    "marginTop": "4px", "textTransform": "uppercase", "letterSpacing": "0.4px",
                }),
                html.Div(subtitle, style={"fontSize": "10px", "color": "#aaa", "marginTop": "2px"})
                    if subtitle else None,
                html.Div(
                    html.I(className="fas fa-arrow-right", style={"fontSize": "9px", "color": color}),
                    style={"position": "absolute", "bottom": "8px", "right": "12px", "opacity": "0.5"},
                ),
            ],
            id={"type": "kpi-card-div", "card_id": card_id},
            n_clicks=0,
            title=f"Click to drill into {label}",
            style={
                "position": "relative",
                "background": "linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,251,255,0.9))",
                "border": "1px solid rgba(255,255,255,0.68)", "borderRadius": "16px",
                "padding": "18px 14px 14px 18px", "cursor": "pointer",
                "boxShadow": "0 8px 24px rgba(15,23,42,0.07)",
                "transition": "transform 0.16s ease, box-shadow 0.16s ease",
                "minHeight": "106px", "backdropFilter": "blur(10px)", "overflow": "hidden",
            },
        ),
        className="kpi-card",
    )


def _page_title(icon: str, color: str, title: str, sub: str = "") -> html.Div:
    return html.Div([
        html.Div(
            html.I(className=f"fas {icon}", style={"color": "#fff", "fontSize": "17px"}),
            style={
                "width": "42px", "height": "42px", "borderRadius": "12px",
                "background": f"linear-gradient(135deg,{color},{color}99)",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
                "marginRight": "14px", "flexShrink": "0",
            },
        ),
        html.Div([
            html.H4(title, className="mb-0", style={"fontWeight": "800", "color": "#15304f", "fontSize": "18px"}),
            html.Small(sub, style={"color": "#aaa", "fontSize": "12px"}) if sub else None,
        ]),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "22px"})


def _sec_hdr(title: str, sub: str = "", icon: str = "fa-layer-group") -> html.Div:
    return html.Div([
        html.I(className=f"fas {icon} me-2", style={"color": "#7d8ea3", "fontSize": "13px"}),
        html.Span(title, style={"fontWeight": "700", "fontSize": "14px", "color": "#15304f"}),
        html.Small(f"  — {sub}", style={"color": "#bbb", "fontSize": "11px"}) if sub else None,
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "14px", "marginTop": "2px"})


def _kpi_row(*kpis, cols: str = KPI_GRID_COLS) -> html.Div:
    return html.Div(
        list(kpis), id="kpi-row", className="kpi-row",
        style={"gridTemplateColumns": cols, "marginBottom": "20px"},
    )


def _kpi_from_id(card_id: str) -> html.Div:
    """
    Render a single _kpi() card purely from a card_id, pulling icon/color/
    title/group straight from KPI_CARDS metadata (card_catalogue.py) instead
    of needing them hardcoded at each call site. This is what makes
    _kpi_row_dynamic() below possible — any saved Customize layout is just
    a list of card_ids, so we need to be able to render an arbitrary one
    without the caller having supplied its display metadata inline.
    """
    from app.dash_apps.pages.card_catalogue import KPI_CARDS
    cfg = KPI_CARDS.get(card_id, {})
    return _kpi(
        card_id,
        cfg.get("icon", "fa-chart-bar"),
        cfg.get("color", "#3498db"),
        cfg.get("title", card_id),
        cfg.get("group", ""),
    )


def _kpi_row_dynamic(portal: str, tab: str, sid, *default_kpi_ids: str,
                      cols: str = KPI_GRID_COLS) -> html.Div:
    """
    THE FIX for "customization isn't working": the Customize tab's Save
    button (customize_callbacks.py's save_layout()) has always correctly
    written {"active": [...], "available": [...]} to
    Dashboard_settings[key=f"dashboard_layout_{portal}_{tab}"] — but nothing
    anywhere ever read it back. Every real dashboard tab rendered a
    hardcoded, static list of _kpi(...) calls regardless of what was saved,
    so Customize was a fully-functional dead end.

    This helper is the read side: given the portal+tab this row belongs to,
    it looks up the saved layout for the current society and renders THAT
    ordered card_id list if one exists, falling back to DEFAULT_LAYOUTS
    (the single source of truth in card_catalogue.py) for this portal+tab
    otherwise. No KPI ids are hardcoded at the call site — every tab reads
    its default set straight from DEFAULT_LAYOUTS[portal][tab].

    Usage:
        _kpi_row_dynamic("admin", "dashboard", sid, cols=...)
    (the KPI card_ids come from DEFAULT_LAYOUTS automatically via
    _kpi_from_id; icon/color/title/group are pulled from KPI_CARDS).
    """
    if not default_kpi_ids:
        default_kpi_ids = tuple(DEFAULT_LAYOUTS.get(portal, {}).get(tab, []))
    ids = list(default_kpi_ids)
    if sid:
        try:
            from database.db_manager import db
            row = db._execute(
                "SELECT value FROM Dashboard_settings WHERE society_id=%s AND key=%s",
                (sid, f"dashboard_layout_{portal}_{tab}"),
                fetch_one=True,
            )
            if row and row.get("value"):
                from app.dash_apps.pages.card_catalogue import KPI_CARDS
                parsed = json.loads(row["value"])
                saved = [c for c in parsed.get("active", []) if c in KPI_CARDS]
                if saved:
                    ids = saved
        except Exception as e:
            print(f"_kpi_row_dynamic layout load error ({portal}/{tab}): {e}")
    return _kpi_row(*[_kpi_from_id(cid) for cid in ids], cols=cols)


def _drill_panel() -> html.Div:
    return html.Div(
        [
            html.Div(id="drill-breadcrumb"),
            html.Div(
                id="drill-content",
                children=html.Div([
                    html.I(className="fas fa-hand-pointer fa-2x mb-3",
                           style={"color": "rgba(29,116,216,0.18)"}),
                    html.P("Click any KPI card above to explore →",
                           className="text-muted", style={"fontSize": "13px"}),
                ], className="text-center", style={"padding": "60px 20px"}),
            ),
        ],
        style={
            "background": "rgba(255,255,255,0.55)", "backdropFilter": "blur(12px)",
            "border": "1px solid rgba(255,255,255,0.6)", "borderRadius": "20px",
            "padding": "20px", "boxShadow": "0 8px 26px rgba(15,23,42,0.06)",
            "minHeight": "380px",
        },
    )


def _divider() -> html.Hr:
    return html.Hr(style={"margin": "20px 0", "opacity": "0.12"})


# ════════════════════════════════════════════════════════════════════════════
# MASTER PORTAL
# ════════════════════════════════════════════════════════════════════════════

def master_portal_page(active_tab="dashboard", sid=None) -> html.Div:
    c = _C["master"]
    if active_tab == "master-create":
        return html.Div([
            _page_title("fa-crown", c, "Create Society"),
            _sec_hdr("New Society Registration", "register a new society on the platform", "fa-building"),
            dbc.Form([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Society Name", html_for="new-society-name"),
                        dbc.Input(id="new-society-name", type="text", placeholder="Enter society name"),
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Label("Admin Email", html_for="new-society-email"),
                        dbc.Input(id="new-society-email", type="email", placeholder="admin@society.com"),
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Label("Admin Password", html_for="new-society-password"),
                        dbc.Input(id="new-society-password", type="password", placeholder="Min 8 characters"),
                    ], width=12, className="mb-3"),
                    dbc.Col([
                        dbc.Button([html.I(className="fas fa-plus me-2"), "Create Society"], id="master-create-society-btn", color="primary", className="me-2"),
                        dbc.Button("Clear", id="master-clear-btn", color="secondary", outline=True),
                    ], width=12),
                ]),
                html.Div(id="master-create-result", className="mt-3"),
            ], className="p-4"),
            html.Hr(style={"margin": "20px 0", "opacity": "0.12"}),
            _drill_panel(),
        ], className="portal-page")
    if active_tab == "master-settings":
        return html.Div([
            _page_title("fa-crown", c, "Master Settings"),
            _sec_hdr("Platform Configuration", "global settings for all societies", "fa-cog"),
            _kpi_row_dynamic(
                "master", "master-settings", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")
    return html.Div([
        _page_title("fa-crown", c, "Master Admin Portal", "Manage all societies on this platform"),
        _sec_hdr("Platform Overview", "click any card to drill down", "fa-chart-bar"),
        _kpi_row_dynamic(
            "master", "dashboard", sid,
            cols=KPI_GRID_COLS,
        ),
        _divider(), _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# ADMIN PORTAL
# ════════════════════════════════════════════════════════════════════════════

def admin_portal_page(active_tab: str = "dashboard", sid=None) -> html.Div:
    c = _C["admin"]

    # ── Dashboard ────────────────────────────────────────────────────────────
    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-user-shield", c, "Admin Dashboard"),
            _sec_hdr("Society Overview", "click any KPI to drill down"),
            _kpi_row_dynamic(
                "admin", "dashboard", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Enroll ───────────────────────────────────────────────────────────────
    if active_tab == "enroll":
        return html.Div([
            _page_title("fa-user-plus", c, "Enroll Members", "apartments · vendors · security"),
            _kpi_row_dynamic(
                "admin", "enroll", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Financials (NEW) ────────────────────────────────────────────────────────
    if active_tab == "financials":
        return html.Div([
            _page_title("fa-book", c, "Financials", "All financial transactions and accounts"),
            _kpi_row_dynamic(
                "admin", "financials", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Events ────────────────────────────────────────────────────────────────
    if active_tab == "events":
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row_dynamic(
                "admin", "events", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Concerns ─────────────────────────────────────────────────────────────
    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "Concerns"),
            _kpi_row_dynamic(
                "admin", "concerns", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Assets (NEW) ──────────────────────────────────────────────────────────
    if active_tab == "assets":
        return html.Div([
            _page_title("fa-boxes", c, "Asset Register",
                        "buy / sell assets — creates expense or receipt automatically"),
            _kpi_row_dynamic(
                "admin", "assets", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Settings ──────────────────────────────────────────────────────────────
    if active_tab == "settings":
        return html.Div([
            _page_title("fa-cog", c, "Settings", "accounts · charge rates"),
            _kpi_row_dynamic(
                "admin", "settings", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "evaluate_pass":
        return _evaluate_pass_page()

    if active_tab == "customize":
        from app.dash_apps.pages.portal_pages import _customize_page
        return _customize_page(c)

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# OWNER (APARTMENT) PORTAL
# ════════════════════════════════════════════════════════════════════════════

def owner_portal_page(active_tab: str = "dashboard", sid=None) -> html.Div:
    c = _C["apartment"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-home", c, "Owner Dashboard"),
            _sec_hdr("My Account", "click any card to view details"),
            _kpi_row_dynamic(
                "owner", "dashboard", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Financials ────────────────────────────────────────────────────────
    if active_tab == "financials":
        return html.Div([
            _page_title("fa-book", c, "Financials", "Cashbook, bills, and charges"),
            _kpi_row_dynamic(
                "owner", "financials", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Receivables tab (apartment dues) ──────────────────────────────────
    if active_tab in ("receivables", "owner_dues"):
        return html.Div([
            _page_title("fa-hand-holding-usd", c, "Bills Due", "monthly maintenance + interest"),
            _kpi_row_dynamic(
                "owner", "receivables", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "owner_receipts":
        return html.Div([
            _page_title("fa-file-invoice-dollar", c, "Bills Paid", "payments received / verified"),
            _kpi_row_dynamic(
                "owner", "receipts", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "owner_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "Cashbook"),
            _kpi_row_dynamic(
                "owner", "cashbook", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("charges", "owner_charges"):
        return html.Div([
            _page_title("fa-file-invoice", c, "Charges"),
            _kpi_row_dynamic(
                "owner", "charges", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "owner_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row_dynamic("owner", "events", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "Concerns"),
            _kpi_row_dynamic("owner", "concerns", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "owner_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Profile & Settings"),
            _kpi_row_dynamic(
                "owner", "settings", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# VENDOR PORTAL
# ════════════════════════════════════════════════════════════════════════════

def vendor_portal_page(active_tab: str = "dashboard", sid=None) -> html.Div:
    c = _C["vendor"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-briefcase", c, "Vendor Dashboard"),
            _kpi_row_dynamic(
                "vendor", "dashboard", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "financials":
        return html.Div([
            _page_title("fa-book", c, "Financials", "Cashbook, payments, and charges"),
            _kpi_row_dynamic(
                "vendor", "financials", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "vendor_passes":
        return html.Div([
            _page_title("fa-id-card", c, "My Passes", "active and expired passes"),
            _kpi_row_dynamic(
                "vendor", "vendor_passes", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "vendor_receipts":
        return html.Div([
            _page_title("fa-file-invoice-dollar", c, "Bills Paid", "payments received / verified"),
            _kpi_row_dynamic(
                "vendor", "receipts", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "vendor_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook"),
            _kpi_row_dynamic(
                "vendor", "cashbook", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "My Concerns"),
            _kpi_row_dynamic("vendor", "concerns", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("charges", "vendor_charges"):
        return html.Div([
            _page_title("fa-file-invoice", c, "My Charges"),
            _kpi_row_dynamic(
                "vendor", "charges", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "vendor_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row_dynamic("vendor", "events", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "vendor_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row_dynamic("vendor", "settings", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# SECURITY PORTAL
# ════════════════════════════════════════════════════════════════════════════

def security_portal_page(active_tab: str = "pass_evaluation", sid=None) -> html.Div:
    c = _C["security"]

    if active_tab == "pass_evaluation":
        return _evaluate_pass_page()

    if active_tab == "attendance":
        return html.Div([
            _page_title("fa-clock", c, "Attendance", "clock in/out for your shift"),
            dbc.Card(
                dbc.CardBody([
                    html.Div(id="attendance-status", children=[
                        html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#95a5a6"}),
                        html.H5("Not clocked in"),
                    ], style={"textAlign": "center", "marginBottom": "16px"}),
                    html.Div([
                        dbc.Button("Clock In", id="clock-in-btn", n_clicks=0,
                                    color="success", className="me-2"),
                        dbc.Button("Clock Out", id="clock-out-btn", n_clicks=0,
                                    color="danger"),
                    ], style={"textAlign": "center"}),
                ]),
                style={"maxWidth": "360px", "margin": "0 auto"},
            ),
        ], className="portal-page")

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-users", c, "All Users", "registered members"),
            _kpi_row_dynamic(
                "security", "dashboard", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── payables tab (security's own salary rows — read-only) ─────────────
    if active_tab in ("payables", "security_payables"):
        return html.Div([
            _page_title("fa-user-clock", c, "My Salary", "per-shift payroll — read only"),
            _kpi_row_dynamic(
                "security", "payables", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "security_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "Cashbook"),
            _kpi_row_dynamic(
                "security", "cashbook", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_receipt":
        return html.Div([
            _page_title("fa-plus-circle", c, "New Receipt", "collect cash at gate"),
            _kpi_row_dynamic("security", "security_receipt", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_receipts":
        return html.Div([
            _page_title("fa-receipt", c, "My Receipts", "your collected receipts"),
            _kpi_row_dynamic("security", "security_receipts", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_events":
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row_dynamic("security", "events", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "My Concerns"),
            _kpi_row_dynamic("security", "concerns", sid, cols=KPI_GRID_COLS),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "security_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row_dynamic(
                "security", "settings", sid,
                cols=KPI_GRID_COLS,
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# GATE PASS EVALUATION PAGE  (security portal, unchanged structure)
# ════════════════════════════════════════════════════════════════════════════

def _evaluate_pass_page() -> html.Div:
    return html.Div([
        _page_title("fa-qrcode", "#1859b8", "Gate Pass Evaluation",
                    "Entry IN / Exit OUT — fn_evaluate_gate_pass drives pass/fail reason"),
        html.Div([
            # ── Left: Scanner ──────────────────────────────────────────────
            html.Div(
                dbc.Card([
                    dbc.CardHeader(html.Div([
                        html.I(className="fas fa-camera me-2", style={"color": "#1859b8"}),
                        html.Strong("QR Scanner"),
                        dbc.Badge("LIVE", color="success", className="ms-2", style={"fontSize": "9px"}),
                    ], style={"display": "flex", "alignItems": "center"}),
                    style={"padding": "10px 14px"}),
                    dbc.CardBody([
                        dcc.Input(id="qr-scan-input", style={"display": "none"}),
                        dcc.Input(id="qr-scan-mode",  style={"display": "none"}),
                        html.Button(id="qr-validate-btn", n_clicks=0, style={"display": "none"}),
                        html.Div(id="qr-result", style={"minHeight": "60px"}),
                        html.Hr(style={"margin": "10px 0"}),
                        html.Div(
                            id="qr-camera-container",
                            style={"position": "relative", "borderRadius": "10px",
                                   "overflow": "hidden", "background": "#1a1a2e",
                                   "marginBottom": "10px", "minHeight": "60px"},
                            children=[
                                html.Video(id="qr-video", autoPlay=True, muted=True, style={
                                    "width": "100%", "maxHeight": "300px",
                                    "objectFit": "cover", "display": "none",
                                    "borderRadius": "10px",
                                }),
                                html.Canvas(id="qr-canvas", style={"display": "none"}),
                                html.Div(id="qr-scanline", style={"display": "none"}),
                                html.Div(id="qr-corners", style={"display": "none"}),
                            ],
                        ),
                        html.Small(id="qr-scan-status", children="Camera off",
                                   style={"color": "#aaa", "fontSize": "11px",
                                          "display": "block", "textAlign": "center",
                                          "marginBottom": "10px"}),
                        html.Div([
                            dbc.Button([html.I(className="fas fa-sign-in-alt me-1"), "Entry IN"],
                                       id="qr-entry-start-btn", color="success", size="sm",
                                       style={"flex": "1"}, n_clicks=0),
                            dbc.Button([html.I(className="fas fa-sign-out-alt me-1"), "Exit OUT"],
                                       id="qr-exit-start-btn", color="danger", size="sm",
                                       style={"flex": "1"}, n_clicks=0),
                        ], style={"display": "flex", "gap": "6px", "marginBottom": "6px"}),
                        html.Div([
                            dbc.Button([html.I(className="fas fa-stop me-1"), "Stop"],
                                       id="qr-entry-stop-btn", color="secondary", size="sm",
                                       outline=True, style={"display": "none", "flex": "1"},
                                       n_clicks=0),
                            dbc.Button([html.I(className="fas fa-stop me-1"), "Stop"],
                                       id="qr-exit-stop-btn", color="secondary", size="sm",
                                       outline=True, style={"display": "none", "flex": "1"},
                                       n_clicks=0),
                            dbc.Button([html.I(className="fas fa-sync-alt me-1"), "Flip"],
                                       id="qr-switch-btn", color="info", size="sm", outline=True,
                                       style={"display": "none"}, n_clicks=0),
                            dbc.Button([html.I(className="fas fa-lightbulb me-1"), "Light"],
                                       id="qr-torch-btn", color="warning", size="sm", outline=True,
                                       style={"display": "none"}, n_clicks=0),
                        ], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                        html.Hr(style={"margin": "10px 0"}),
                        html.Div([
                            dbc.Button([html.I(className="fas fa-exclamation-triangle me-1"), "EMERGENCY"],
                                       id="emergency-btn", color="danger", size="sm",
                                       style={"flex": "1", "fontWeight": "700"}, n_clicks=0),
                            dbc.Button([html.I(className="fas fa-phone me-1"), "Call Admin"],
                                       id="call-admin-btn", color="primary", size="sm",
                                       style={"flex": "0"}, n_clicks=0),
                        ], style={"display": "flex", "gap": "6px"}),
                    ], style={"padding": "14px"}),
                ], style={"borderRadius": "18px", "boxShadow": "0 10px 28px rgba(24,89,184,0.1)"}),
                style={"flex": "1 1 320px", "minWidth": "280px"},
            ),
            # ── Right: Recent Scans ────────────────────────────────────────
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
                                "No scans yet", className="text-muted text-center",
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

        # ── Manual QR Entry — paste/type a QR payload without the camera ──────
        # ids (manual-qr-input / validate-qr-btn / qr-validation-result) are
        # deliberately distinct from the camera pipeline's hidden
        # qr-scan-input / qr-scan-mode / qr-validate-btn above — this page is
        # shared by both the admin and security portals, so reusing those ids
        # for a second, visible field would be a duplicate-component-ID error.
        # Wired to admin_callbacks.py's validate_qr_code_admin.
        dbc.Card([
            dbc.CardHeader(html.Div([
                html.I(className="fas fa-keyboard me-2", style={"color": "#1859b8"}),
                html.Strong("Manual QR Entry"),
                html.Small("  — paste a QR payload if the camera isn't available",
                           style={"color": "#999", "fontSize": "11px", "marginLeft": "6px"}),
            ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "10px 14px"}),
            dbc.CardBody([
                html.Div([
                    dbc.Input(
                        id="manual-qr-input",
                        type="text",
                        placeholder="e.g. 42|O|1",
                        style={"fontSize": "13px", "fontFamily": "monospace"},
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-check me-1"), "Validate"],
                        id="validate-qr-btn", n_clicks=0, color="primary", size="sm",
                        style={"flexShrink": "0"},
                    ),
                ], style={"display": "flex", "gap": "8px"}),
                dcc.Loading(
                    html.Div(id="qr-validation-result", style={"marginTop": "10px"}),
                    type="circle",
                ),
            ], style={"padding": "14px"}),
        ], style={"borderRadius": "18px", "boxShadow": "0 10px 28px rgba(24,89,184,0.1)",
                  "marginTop": "16px"}),

        # Call admin modal
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


# ════════════════════════════════════════════════════════════════════════════
# CUSTOMIZE TAB  (admin only — unchanged structure, minor icon update)
# ════════════════════════════════════════════════════════════════════════════

def _customize_page(c: str) -> html.Div:
    _PORTAL_OPTS = [
        {"label": "Admin",     "value": "admin"},
        {"label": "Master",    "value": "master"},
        {"label": "Apartment", "value": "apartment"},
        {"label": "Vendor",    "value": "vendor"},
        {"label": "Security",  "value": "security"},
    ]
    return html.Div([
        html.Div([
            html.Div(html.I(className="fas fa-cog", style={"color": "#fff", "fontSize": "17px"}),
                     style={"width": "42px", "height": "42px", "borderRadius": "12px",
                            "background": f"linear-gradient(135deg,{c},{c}99)",
                            "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "14px", "flexShrink": "0"}),
            html.Div([
                html.H4("Customize Dashboard", className="mb-0",
                        style={"fontWeight": "800", "color": "#15304f", "fontSize": "18px"}),
                html.Small("Layout Editor · KPI Inspector · KPI Audit",
                           style={"color": "#aaa", "fontSize": "12px"}),
            ]),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "22px"}),
        dbc.Tabs(
            id="customize-sub-tabs",
            active_tab="customize-layout",
            children=[
                dbc.Tab(tab_id="customize-layout", label="Layout Editor", children=[
                    html.Div([
                        dcc.Store(id="dnd-layout-store", storage_type="session",
                                  data={"active": [], "available": []}),
                        dcc.Input(id="dnd-order-capture", value="", debounce=False,
                                  style={"display": "none"}),
                        html.Div(id="dnd-init-dummy", children="", style={"display": "none"}),
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-filter me-2", style={"color": c}),
                                html.Strong("Select Dashboard to Edit"),
                            ], style={"display": "flex", "alignItems": "center",
                                      "padding": "10px 14px",
                                      "background": f"linear-gradient(135deg,{c}15,{c}08)"}),
                            html.Div([
                                dbc.Row([
                                    dbc.Col([
                                        dbc.Label("Portal", style={"fontSize": "12px", "fontWeight": "600"}),
                                        dcc.Dropdown(id="layout-portal-select", options=_PORTAL_OPTS,
                                                     value="admin", clearable=False, style={"fontSize": "13px"}),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Tab", style={"fontSize": "12px", "fontWeight": "600"}),
                                        dcc.Dropdown(id="layout-tab-select", options=[], value=None,
                                                     placeholder="Select tab…", clearable=True,
                                                     style={"fontSize": "13px"}),
                                    ], width=4),
                                    dbc.Col([
                                        dbc.Label("Actions", style={"fontSize": "12px", "fontWeight": "600"}),
                                        html.Div([
                                            dbc.Button([html.I(className="fas fa-save me-1"), "Save"],
                                                       id="save-layout-btn", color="primary", size="sm",
                                                       className="me-2", style={"borderRadius": "8px", "fontWeight": "600"}),
                                            dbc.Button([html.I(className="fas fa-undo me-1"), "Reset"],
                                                       id="reset-layout-btn", color="light", size="sm",
                                                       style={"borderRadius": "8px"}),
                                        ], style={"display": "flex", "gap": "6px", "marginTop": "4px"}),
                                    ], width=4),
                                ]),
                                html.Div(id="layout-status-msg", className="mt-2"),
                            ], style={"padding": "12px 14px"}),
                        ], className="mb-3"),
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-th-large me-2", style={"color": c}),
                                html.Strong("Active Dashboard"),
                                html.Small(" — drag KPIs here",
                                           style={"color": "#999", "fontSize": "11px", "marginLeft": "6px"}),
                            ], style={"display": "flex", "alignItems": "center",
                                      "padding": "10px 14px",
                                      "background": f"linear-gradient(135deg,{c}15,{c}08)"}),
                            html.Div(
                                html.Div(id="dnd-active-zone",
                                         children=[html.Div(
                                             [html.I(className="fas fa-arrow-down me-2"),
                                              "Drag KPI cards here from the palette below"],
                                             style={"color": "#ccc", "fontSize": "13px",
                                                    "textAlign": "center", "padding": "30px"},
                                         )],
                                         style={"display": "grid",
                                                 "gridTemplateColumns": KPI_GRID_COLS,
                                                "gap": "12px", "minHeight": "120px", "padding": "10px",
                                                 "border": "2px dashed #dee2e6", "borderRadius": "10px",
                                                "background": "rgba(248,251,255,0.6)"}),
                                style={"padding": "14px"},
                            ),
                        ], className="mb-3"),
                        html.Div([
                            html.Div([
                                html.I(className="fas fa-grip-horizontal me-2", style={"color": "#7d8ea3"}),
                                html.Strong("KPI Palette"),
                            ], style={"display": "flex", "alignItems": "center",
                                      "padding": "10px 14px",
                                      "background": "linear-gradient(135deg,#7d8ea312,#7d8ea308)"}),
                            html.Div(
                                html.Div(style={"maxHeight": "52vh", "overflowY": "auto", "padding": "4px 0"},
                                         children=[html.Div(id="dnd-palette-zone",
                                                            children=[html.Div(
                                                                "Select a portal and tab above to load KPIs",
                                                                style={"color": "#ccc", "fontSize": "13px",
                                                                       "textAlign": "center", "padding": "30px"})],
                                                            style={"display": "grid",
                                                                   "gridTemplateColumns": KPI_GRID_COLS,
                                                                   "gap": "12px", "padding": "6px",
                                                                   "minHeight": "80px"})]),
                                style={"padding": "8px"},
                            ),
                        ], className="mb-3"),
                    ], style={"marginTop": "20px"}),
                ]),
                dbc.Tab(tab_id="customize-kpi", label="KPI Inspector", children=[
                    html.Div([
                        dbc.Row([
                            dbc.Col([dbc.Label("Portal", style={"fontSize":"12px","fontWeight":"600"}),
                                     dcc.Dropdown(id="customize-portal-select", options=_PORTAL_OPTS,
                                                  value="admin", clearable=False, style={"fontSize":"13px"})], width=4),
                            dbc.Col([dbc.Label("Tab", style={"fontSize":"12px","fontWeight":"600"}),
                                     dcc.Dropdown(id="customize-tab-select", options=[], placeholder="Select tab…",
                                                  clearable=True, style={"fontSize":"13px"})], width=4),
                            dbc.Col([dbc.Label("KPI", style={"fontSize":"12px","fontWeight":"600"}),
                                     dcc.Dropdown(id="customize-kpi-select", options=[], placeholder="Select KPI…",
                                                  clearable=True, style={"fontSize":"13px"})], width=4),
                        ], className="mb-3"),
                        html.Hr(style={"margin": "12px 0"}),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label([html.I(className="fas fa-code me-1"), "SQL Query (editable)"],
                                          style={"fontSize":"12px","fontWeight":"700","color":"#15304f"}),
                                dbc.Textarea(id="customize-kpi-sql", placeholder="Select a KPI to load its SQL…",
                                             rows=13,
                                             style={"fontSize":"11px","fontFamily":"monospace","backgroundColor":"#f5f7fa",
                                                    "border":"1px solid #cdd5df","borderRadius":"8px","color":"#2c3e50","resize":"vertical"}),
                                html.Div([
                                    dbc.Button([html.I(className="fas fa-play me-1"), "Test SQL"],
                                               id="kpi-test-sql-btn", color="success", size="sm",
                                               style={"borderRadius":"8px","fontWeight":"600"}),
                                    dbc.Button([html.I(className="fas fa-file-export me-1"), "Export .sql"],
                                               id="kpi-export-sql-btn", color="secondary", size="sm",
                                               style={"borderRadius":"8px"}),
                                    dbc.Button([html.I(className="fas fa-database me-1"), "Integrate to DB"],
                                               id="kpi-integrate-sql-btn", color="warning", size="sm",
                                               style={"borderRadius":"8px","fontWeight":"600"}),
                                    dcc.Download(id="kpi-export-download"),
                                ], style={"display":"flex","gap":"6px","marginTop":"8px","flexWrap":"wrap"}),
                                dcc.Loading(html.Div(id="kpi-test-result", style={"marginTop":"8px"}), type="circle"),
                                html.Div(id="kpi-export-result"),
                                html.Div(id="kpi-integrate-result"),
                            ], width=6),
                            dbc.Col([
                                dbc.Label([html.I(className="fas fa-info-circle me-1"), "KPI Metadata"],
                                          style={"fontSize":"12px","fontWeight":"700","color":"#15304f"}),
                                dcc.Loading(
                                    html.Div(id="customize-kpi-metadata",
                                             children="Select a KPI to view metadata",
                                             style={"fontSize":"11px","backgroundColor":"#f5f7fa","border":"1px solid #cdd5df",
                                                    "borderRadius":"8px","padding":"12px","minHeight":"340px",
                                                    "maxHeight":"500px","overflowY":"auto","color":"#2c3e50"}),
                                    type="default",
                                ),
                                html.Div(id="customize-entity-reference", style={"marginTop":"10px"}),
                            ], width=6),
                        ], className="mb-3"),
                    ], style={"marginTop": "20px"}),
                ]),
                dbc.Tab(tab_id="customize-audit", label="KPI Audit", children=[
                    html.Div([
                        dbc.Row([
                            dbc.Col(html.H6([html.I(className="fas fa-stethoscope me-2"), "KPI Health Check"],
                                           style={"color":"#15304f","fontWeight":"700"}), width="auto"),
                            dbc.Col([dbc.Button([html.I(className="fas fa-play me-2"), "Run Full Audit"],
                                               id="run-kpi-audit-btn", color="primary", size="sm",
                                               style={"borderRadius":"8px","fontWeight":"600"})],
                                    width="auto", className="ms-auto"),
                        ], align="center", className="mb-3"),
                        html.Div(id="kpi-audit-summary",
                                 children=html.Small("Click 'Run Full Audit' to test all KPI queries.",
                                                     className="text-muted"),
                                 className="mb-3"),
                        dcc.Loading(
                            html.Div(dbc.Table([
                                html.Thead(html.Tr([
                                    html.Th("", style={"width":"34px"}),
                                    html.Th("Card ID",   style={"fontSize":"11px"}),
                                    html.Th("Title",     style={"fontSize":"11px"}),
                                    html.Th("Params",    style={"fontSize":"11px","textAlign":"center"}),
                                    html.Th("Format",    style={"fontSize":"11px"}),
                                    html.Th("Status",    style={"fontSize":"11px"}),
                                    html.Th("Raw value", style={"fontSize":"11px"}),
                                    html.Th("Formatted", style={"fontSize":"11px"}),
                                    html.Th("ms",        style={"fontSize":"11px"}),
                                ])),
                                html.Tbody(id="kpi-audit-table",
                                           children=[html.Tr(html.Td("Click Run Full Audit", colSpan=9,
                                                                     className="text-center text-muted",
                                                                     style={"fontSize":"12px","padding":"20px"}))]),
                            ], bordered=True, hover=True, responsive=True, size="sm",
                               style={"fontSize":"12px"}),
                            style={"overflowX":"auto","maxHeight":"60vh","overflowY":"auto"}),
                            type="circle",
                        ),
                    ], style={"marginTop": "20px"}),
                ]),
            ],
            style={"marginBottom": "20px"},
        ),
    ], className="portal-page")
