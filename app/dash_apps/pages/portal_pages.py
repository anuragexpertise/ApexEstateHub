# app/dash_apps/pages/portal_pages.py
"""
ALL 5 PORTAL PAGE LAYOUTS — single source of truth.
v3 additions:
  Admin:     new tabs — Receivables, Payments, Assets
  Apartment: new tab  — Receivables (read-only own dues)
  Vendor:    new tab  — Receivables (read-only own pass/charges)
  Security:  new tab  — Payments    (read-only own salary rows)
  All portals: Verify button on Receivables/Payments is admin-only
               (enforced in renderers.py via _PORTAL_PERMS)
"""

from __future__ import annotations
from dash import html, dcc
import dash_bootstrap_components as dbc

_C = {
    "master":    "#c96a19",
    "admin":     "#1859b8",
    "apartment": "#18794e",
    "vendor":    "#b98a07",
    "security":  "#b63b3b",
}


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


def _kpi_row(*kpis, cols: str = "repeat(auto-fill,minmax(155px,1fr))") -> html.Div:
    return html.Div(
        list(kpis), id="kpi-row", className="kpi-row",
        style={"gridTemplateColumns": cols, "marginBottom": "20px"},
    )


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

def master_portal_page() -> html.Div:
    c = _C["master"]
    return html.Div([
        _page_title("fa-crown", c, "Master Admin Portal", "Manage all societies on this platform"),
        _sec_hdr("Platform Overview", "click any card to drill down", "fa-chart-bar"),
        _kpi_row(
            _kpi("kpi_societies_total",     "fa-building",    c,         "Total Societies"),
            _kpi("kpi_societies_free",       "fa-circle",      "#7d8ea3", "Free Plan"),
            _kpi("kpi_societies_9Apts",      "fa-star",        "#17976e", "9Apts Plan"),
            _kpi("kpi_societies_99Apts",     "fa-star",        "#17976e", "99Apts Plan"),
            _kpi("kpi_societies_999Apts",    "fa-star",        "#17976e", "999Apts Plan"),
            _kpi("kpi_societies_unlimited",  "fa-star",        "#17976e", "Unlimited"),
            _kpi("kpi_societies_expired",    "fa-exclamation-triangle", "#de5c52", "Expired"),
            _kpi("kpi_master_apartments_total", "fa-home",     "#1859b8", "Apartments"),
            _kpi("kpi_master_vendors_total",    "fa-truck",    "#b98a07", "Vendors"),
            _kpi("kpi_master_security_total",   "fa-user-shield", "#b63b3b", "Security"),
            cols="repeat(auto-fill,minmax(148px,1fr))",
        ),
        _divider(), _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# ADMIN PORTAL
# ════════════════════════════════════════════════════════════════════════════

def admin_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["admin"]

    # ── Dashboard ────────────────────────────────────────────────────────────
    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-user-shield", c, "Admin Dashboard"),
            _sec_hdr("Society Overview", "click any KPI to drill down"),
            _kpi_row(
                _kpi("kpi_apartments_total",     "fa-home",              "#1859b8", "Apartments"),
                _kpi("kpi_apartments_dues",       "fa-exclamation-triangle", "#de5c52", "Apts Overdue"),
                _kpi("kpi_receivables_total",     "fa-hand-holding-usd",  "#17976e", "Dues Pending"),
                _kpi("kpi_advance_credits",       "fa-hand-point-down",   "#0ea5a8", "Advance Credits"),
                _kpi("kpi_vendors_total",         "fa-truck",             "#b98a07", "Vendors"),
                _kpi("kpi_vendors_passes",        "fa-id-card",           "#b98a07", "Valid Passes"),
                _kpi("kpi_security_total",        "fa-user-shield",       "#b63b3b", "Security"),
                _kpi("kpi_security_on_duty",      "fa-shield-alt",        "#691b1b", "On Duty"),
                _kpi("kpi_events_total",          "fa-calendar-check",    "#8e44ad", "Upcoming Events"),
                _kpi("kpi_concerns_open",         "fa-hand-point-up",     "#de5c52", "Open Concerns"),
                _kpi("kpi_gate_logs",             "fa-receipt",           "#1abc9c", "Gate Logs Today"),
                _kpi("kpi_receipts_month",        "fa-receipt",           "#17976e", "Receipts (Month)"),
                _kpi("kpi_expenses_month",        "fa-wallet",            "#aa241a", "Expenses (Month)"),
                _kpi("kpi_payables_total",        "fa-clock",             "#de5c52", "Salary Pending"),
                _kpi("kpi_cash_in_hand",          "fa-wallet",            "#2c3e50", "Cash in Hand"),
                _kpi("kpi_bank_balance",          "fa-coins",             "#2c3e50", "Balance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Enroll ───────────────────────────────────────────────────────────────
    if active_tab == "enroll":
        return html.Div([
            _page_title("fa-user-plus", c, "Enroll Members", "apartments · vendors · security"),
            _kpi_row(
                _kpi("kpi_apartments_total", "fa-home",       "#1859b8", "Apartments"),
                _kpi("kpi_vendors_total",    "fa-truck",      "#b98a07", "Vendors"),
                _kpi("kpi_security_total",   "fa-user-shield","#b63b3b", "Security Staff"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Cashbook ─────────────────────────────────────────────────────────────
    if active_tab == "cashbook":
        return html.Div([
            _page_title("fa-book", c, "Cashbook", "full transaction ledger"),
            _kpi_row(
                _kpi("kpi_receipts_month",   "fa-receipt",  "#17976e",  "Receipts (Month)"),
                _kpi("kpi_expenses_month",   "fa-wallet",   "#de5c52",  "Expenses (Month)"),
                _kpi("kpi_cash_in_hand",     "fa-wallet",   "#2c3e50",  "Cash in Hand"),
                _kpi("kpi_bank_balance",     "fa-coins",    "#2c3e50",  "Balance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Receivables (NEW) ─────────────────────────────────────────────────────
    if active_tab == "receivables":
        return html.Div([
            _page_title("fa-hand-holding-usd", c, "Receivables",
                        "auto-generated maintenance dues — click Verify to post to ledger"),
            _kpi_row(
                _kpi("kpi_receivables_total",    "fa-hand-holding-usd", "#17976e", "Total Pending"),
                _kpi("kpi_receivables_overdue",  "fa-exclamation-circle","#de5c52", "Overdue"),
                _kpi("kpi_advance_credits",      "fa-hand-point-down",  "#0ea5a8", "Advance Credits"),
                _kpi("kpi_apartments_dues",      "fa-home",             "#de5c52", "Apts Overdue"),
                _kpi("kpi_apartments_no_dues",   "fa-check-circle",     "#17976e", "Apts Clear"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Receipts ──────────────────────────────────────────────────────────────
    if active_tab == "receipts":
        return html.Div([
            _page_title("fa-file-invoice-dollar", c, "Receipts", "manual income entries"),
            _kpi_row(
                _kpi("kpi_receipts_month",   "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi("kpi_receipts_total",   "fa-receipt", "#17976e", "Receipts (All)"),
                _kpi("kpi_bank_balance",     "fa-coins",   "#2c3e50", "Balance"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Expenses ──────────────────────────────────────────────────────────────
    if active_tab == "expenses":
        return html.Div([
            _page_title("fa-wallet", c, "Expenses", "manual outgoing payments"),
            _kpi_row(
                _kpi("kpi_expenses_month",         "fa-wallet",      "#de5c52", "Expenses (Month)"),
                _kpi("kpi_security_salaries_paid", "fa-check-double","#17976e", "Salary Verified"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Payments (NEW) ────────────────────────────────────────────────────────
    if active_tab == "payments":
        return html.Div([
            _page_title("fa-user-clock", c, "Salary Payments",
                        "auto-generated security payroll — click Verify to post to ledger"),
            _kpi_row(
                _kpi("kpi_payables_total",           "fa-wallet",       "#de5c52", "Total Pending"),
                _kpi("kpi_security_salaries_due",    "fa-rupee-sign",   "#b63b3b", "Salary Due"),
                _kpi("kpi_security_salaries_paid",   "fa-check-double", "#17976e", "Salary Verified"),
                _kpi("kpi_security_shifts_pending",  "fa-clock",        "#e59620", "Shifts Unpaid"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Events ────────────────────────────────────────────────────────────────
    if active_tab == "events":
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row(
                _kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Concerns ─────────────────────────────────────────────────────────────
    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "Concerns"),
            _kpi_row(
                _kpi("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns"),
                cols="1fr",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Assets (NEW) ──────────────────────────────────────────────────────────
    if active_tab == "assets":
        return html.Div([
            _page_title("fa-boxes", c, "Asset Register",
                        "buy / sell assets — creates expense or receipt automatically"),
            _kpi_row(
                _kpi("kpi_assets_count", "fa-boxes",     "#6c5ce7", "Active Assets"),
                _kpi("kpi_assets_value", "fa-coins",     "#6c5ce7", "Assets at Cost"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Settings ──────────────────────────────────────────────────────────────
    if active_tab == "settings":
        return html.Div([
            _page_title("fa-cog", c, "Settings", "accounts · charge rates"),
            _kpi_row(
                _kpi("kpi_societies_calc_start_date","fa-clock",      "#34ee45", "Calc Start Date"),
                _kpi("kpi_plan_validity",            "fa-calendar-times","#e67e22","Plan Expires"),
                _kpi("kpi_accounts_count",           "fa-book-open",  "#6c5ce7", "Accounts"),
                _kpi("kpi_apt_charges_count",        "fa-rupee-sign", "#de5c52", "Apt Charge Rules"),
                _kpi("kpi_ven_charges_count",        "fa-rupee-sign", "#de5c52", "Vendor Charge Rules"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
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

def owner_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["apartment"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-home", c, "Owner Dashboard"),
            _sec_hdr("My Account", "click any card to view details"),
            _kpi_row(
                _kpi("kpi_my_pending_dues",  "fa-rupee-sign",    "#de5c52", "Pending Dues"),
                _kpi("kpi_my_overdue_dues",  "fa-exclamation-circle","#de5c52","Overdue Dues"),
                _kpi("kpi_advance_credits",  "fa-hand-point-down","#0ea5a8", "Advance Credit"),
                _kpi("kpi_concerns_open",    "fa-hand-point-up", "#e59620", "My Concerns"),
                _kpi("kpi_events_total",     "fa-calendar-check","#8e44ad", "Upcoming Events"),
                _kpi("kpi_gate_logs",        "fa-receipt",       "#1abc9c", "Gate Logs"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Receivables tab (NEW for apartment portal) ────────────────────────
    if active_tab in ("receivables", "owner_dues"):
        return html.Div([
            _page_title("fa-hand-holding-usd", c, "My Dues", "monthly maintenance + interest"),
            _kpi_row(
                _kpi("kpi_my_pending_dues", "fa-rupee-sign",     "#de5c52", "Pending"),
                _kpi("kpi_my_overdue_dues", "fa-exclamation-circle","#de5c52","Overdue"),
                _kpi("kpi_advance_credits", "fa-hand-point-down","#0ea5a8", "Advance Credit"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "owner_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook"),
            _kpi_row(
                _kpi("kpi_my_pending_dues", "fa-rupee-sign", "#de5c52", "To Pay"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "concerns":
        return html.Div([
            _page_title("fa-hand-point-up", c, "My Concerns"),
            _kpi_row(_kpi("kpi_concerns_open", "fa-hand-point-up", "#de5c52", "Open Concerns"), cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "owner_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row(_kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Upcoming Events"), cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("charges", "owner_charges"):
        return html.Div([
            _page_title("fa-file-invoice", c, "My Charges"),
            _kpi_row(
                _kpi("kpi_maintainence_charges", "fa-file-invoice", "#e59620", "Maintenance Rules"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "owner_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Profile & Settings"),
            _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# VENDOR PORTAL
# ════════════════════════════════════════════════════════════════════════════

def vendor_portal_page(active_tab: str = "dashboard") -> html.Div:
    c = _C["vendor"]

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-briefcase", c, "Vendor Dashboard"),
            _kpi_row(
                _kpi("kpi_my_pass_expiry",  "fa-id-card",       "#b98a07", "Pass Expiry"),
                _kpi("kpi_concerns_open",   "fa-hand-point-up", "#e59620", "Jobs / Concerns"),
                _kpi("kpi_events_total",    "fa-calendar-check","#8e44ad", "Upcoming Events"),
                _kpi("kpi_gate_logs",       "fa-receipt",       "#1abc9c", "Gate Logs Today"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Receivables tab (vendor's own pass charges / fines) ──────────────
    if active_tab in ("receivables", "vendor_dues"):
        return html.Div([
            _page_title("fa-hand-holding-usd", c, "My Receivables"),
            _kpi_row(
                _kpi("kpi_my_pass_expiry", "fa-id-card", "#b98a07", "Pass Expiry"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "vendor_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "My Cashbook"),
            _kpi_row(
                _kpi("kpi_receipts_month", "fa-receipt", c, "Receipts (Month)"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("events", "vendor_events"):
        return html.Div([
            _page_title("fa-calendar-alt", c, "Events"),
            _kpi_row(_kpi("kpi_events_total", "fa-calendar-check", "#8e44ad", "Events"), cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "vendor_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row(_kpi("kpi_vendor_date", "fa-calendar-alt", "#de5c52", "Registered Since"), cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    return html.Div([
        _page_title("fa-th-large", c, active_tab.replace("_", " ").title()),
        _drill_panel(),
    ], className="portal-page")


# ════════════════════════════════════════════════════════════════════════════
# SECURITY PORTAL
# ════════════════════════════════════════════════════════════════════════════

def security_portal_page(active_tab: str = "pass_evaluation") -> html.Div:
    c = _C["security"]

    if active_tab == "pass_evaluation":
        return _evaluate_pass_page()

    if active_tab == "dashboard":
        return html.Div([
            _page_title("fa-users", c, "All Users", "registered members"),
            _kpi_row(
                _kpi("kpi_apartments_total",      "fa-home",         "#1859b8", "Apartments"),
                _kpi("kpi_vendors_total",         "fa-truck",        "#b98a07", "Vendors"),
                _kpi("kpi_security_total",        "fa-user-shield",  c,         "Security"),
                _kpi("kpi_security_shift_count",  "fa-hand-point-up","#de5c52", "Active Shifts"),
                _kpi("kpi_receipts_in_hand_total","fa-receipt",      "#17976e", "Receipts-in-hand"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    # ── Payments tab (security's own salary rows — read-only) ─────────────
    if active_tab in ("payments", "security_payments"):
        return html.Div([
            _page_title("fa-user-clock", c, "My Salary", "per-shift payroll — read only"),
            _kpi_row(
                _kpi("kpi_security_salaries_due",  "fa-rupee-sign",   "#b63b3b", "Salary Due"),
                _kpi("kpi_security_salaries_paid", "fa-check-double", "#17976e", "Salary Paid"),
                _kpi("kpi_security_shifts_pending","fa-clock",        "#e59620", "Shifts Unpaid"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("cashbook", "security_cashbook"):
        return html.Div([
            _page_title("fa-book", c, "Cashbook"),
            _kpi_row(
                _kpi("kpi_receipts_month",  "fa-receipt", "#17976e", "Receipts (Month)"),
                _kpi("kpi_expenses_month",  "fa-wallet",  "#de5c52", "Expenses (Month)"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
            ),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab == "security_receipt":
        return html.Div([
            _page_title("fa-plus-circle", c, "New Receipt", "collect cash payments at gate"),
            _kpi_row(_kpi("kpi_receipts_month", "fa-receipt", "#17976e", "Receipts (Month)"), cols="1fr"),
            _divider(), _drill_panel(),
        ], className="portal-page")

    if active_tab in ("settings", "security_settings"):
        return html.Div([
            _page_title("fa-cog", c, "My Settings"),
            _kpi_row(
                _kpi("kpi_security_date",          "fa-calendar-alt", "#de5c52", "Joined"),
                _kpi("kpi_security_salary_per_shift","fa-rupee-sign", "#b63b3b", "Salary/Shift"),
                cols="repeat(auto-fill,minmax(148px,1fr))",
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
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.I(className="fas fa-filter me-2", style={"color": c}),
                                html.Strong("Select Dashboard to Edit"),
                            ], style={"display": "flex", "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody([
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
                        ], className="mb-3 shadow-sm", style={"borderRadius": "14px", "overflow": "hidden"}),
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.I(className="fas fa-th-large me-2", style={"color": c}),
                                html.Strong("Active Dashboard"),
                                html.Small(" — drag KPIs here",
                                           style={"color": "#999", "fontSize": "11px", "marginLeft": "6px"}),
                            ], style={"display": "flex", "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody(
                                html.Div(id="dnd-active-zone",
                                         children=[html.Div(
                                             [html.I(className="fas fa-arrow-down me-2"),
                                              "Drag KPI cards here from the palette below"],
                                             style={"color": "#ccc", "fontSize": "13px",
                                                    "textAlign": "center", "padding": "30px"},
                                         )],
                                         style={"display": "grid",
                                                "gridTemplateColumns": "repeat(auto-fill,minmax(200px,1fr))",
                                                "gap": "12px", "minHeight": "120px", "padding": "10px",
                                                "border": "2px dashed #dee2e6", "borderRadius": "10px",
                                                "background": "rgba(248,251,255,0.6)"}),
                                style={"padding": "14px"},
                            ),
                        ], className="mb-3 shadow-sm", style={"borderRadius": "14px", "overflow": "hidden"}),
                        dbc.Card([
                            dbc.CardHeader(html.Div([
                                html.I(className="fas fa-grip-horizontal me-2", style={"color": "#7d8ea3"}),
                                html.Strong("KPI Palette"),
                            ], style={"display": "flex", "alignItems": "center"}),
                            style={"padding": "10px 14px"}),
                            dbc.CardBody(
                                html.Div(style={"maxHeight": "52vh", "overflowY": "auto", "padding": "4px 0"},
                                         children=[html.Div(id="dnd-palette-zone",
                                                            children=[html.Div(
                                                                "Select a portal and tab above to load KPIs",
                                                                style={"color": "#ccc", "fontSize": "13px",
                                                                       "textAlign": "center", "padding": "30px"})],
                                                            style={"display": "grid",
                                                                   "gridTemplateColumns": "repeat(auto-fill,minmax(200px,1fr))",
                                                                   "gap": "12px", "padding": "6px",
                                                                   "minHeight": "80px"})]),
                                style={"padding": "8px"},
                            ),
                        ], className="shadow-sm", style={"borderRadius": "14px", "overflow": "hidden"}),
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
