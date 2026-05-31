# app/dash_apps/callbacks/shell_callbacks.py
"""
Shell callbacks — authentication routing, society dropdown, sidebar, toasts.

Rules:
• All DB calls use named params (:name).
• This file owns: auth-store, url, login-modal outputs.
  login_callbacks.py uses allow_duplicate=True for those same outputs.
• register_shell_callbacks() must be called BEFORE register_login_callbacks().
"""

import logging
from datetime import date as dt_date

import dash
from dash import Input, Output, State, html, dcc, no_update, ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from database.db_manager import db
from app.dash_apps.app_shell import ROLE_CONFIG

log = logging.getLogger(__name__)


def register_shell_callbacks(app):
    log.info("Registering shell callbacks…")

    # ══════════════════════════════════════════════════════════════════════════
    # 1. SOCIETY DROPDOWN — fires on page load (prevent_initial_call=False)
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("society-dropdown", "options"),
        Output("society-dropdown", "disabled"),
        Output("login-db-error", "children"),
        Output("login-db-error", "style"),
        Input("login-modal", "is_open"),
        prevent_initial_call=False,
    )
    def load_societies(_is_open):
        log.info("load_societies fired")
        _err_style = {
            "display": "block", "padding": "8px",
            "borderRadius": "8px", "marginBottom": "12px",
            "fontSize": "12px",
        }
        try:
            rows = db.execute(
                """
                SELECT id, name, plan, plan_validity
                FROM societies
                WHERE plan = 'Free'
                   OR (
                       plan IN ('9Apts', '99Apts', '999Apts', 'Unlimited')
                       AND plan_validity >= CURRENT_DATE
                   )
                ORDER BY name
                """,
                fetch_all=True,
            )

            if not rows:
                log.warning("No societies returned from DB")
                return (
                    [],
                    False,
                    html.Div(
                        "No societies found. Contact the administrator.",
                        style={"color": "#856404"},
                    ),
                    {**_err_style, "background": "#fff3cd"},
                )

            today = dt_date.today()
            options = []
            for r in rows:
                plan = r.get("plan", "Free")
                validity = r.get("plan_validity")

                if plan == "Free":
                    badge = "Free"
                elif validity:
                    if isinstance(validity, str):
                        from datetime import datetime
                        validity = datetime.fromisoformat(validity).date()
                    days = (validity - today).days
                    badge = f"{plan} · {days}d left" if days > 0 else f"{plan} · expires today"
                else:
                    badge = plan

                options.append({"label": f"{r['name']}  [{badge}]", "value": r["id"]})

            log.info("Loaded %d societies", len(options))
            return options, False, "", {"display": "none"}

        except Exception as exc:
            log.exception("load_societies error")
            return (
                [],
                True,
                html.Div(f"DB error: {exc}", style={"color": "#dc3545"}),
                {**_err_style, "background": "#f8d7da"},
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 2. STAGE 1 → STAGE 2
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("login-stage-1", "style"),
        Output("login-stage-2", "style"),
        Output("auth-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("society-select-btn", "n_clicks"),
        State("society-dropdown", "value"),
        State("remember-society-checkbox", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def advance_to_stage2(n, society_id, remember, auth):
        if not n or not society_id:
            raise PreventUpdate
        auth = dict(auth or {})
        auth["society_id"] = society_id
        auth["authenticated"] = False
        cookie = {"society_id": society_id} if remember else no_update
        return {"display": "none"}, {"display": "block"}, auth, cookie

    # ══════════════════════════════════════════════════════════════════════════
    # 3. BACK TO STAGE 1
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Input("back-to-stage1-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def back_to_stage1(n):
        if not n:
            raise PreventUpdate
        return {"display": "block"}, {"display": "none"}

    # ══════════════════════════════════════════════════════════════════════════
    # 4. RESTORE SOCIETY FROM COOKIE
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("society-dropdown", "value"),
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Output("auth-store", "data", allow_duplicate=True),
        Input("cookie-store", "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def restore_from_cookie(cookie, options):
        if not cookie or not cookie.get("society_id"):
            raise PreventUpdate
        sid = cookie["society_id"]
        if options and not any(o.get("value") == sid for o in options):
            raise PreventUpdate
        auth = {"society_id": sid, "authenticated": False}
        return sid, {"display": "none"}, {"display": "block"}, auth

    # ══════════════════════════════════════════════════════════════════════════
    # 5. INJECT STAGE-2 LOGIN FORM
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("login-stage-2", "children"),
        Input("auth-store", "data"),
        State("login-stage-2", "children"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def inject_stage2(auth, current_children, options):
        if not auth or auth.get("authenticated"):
            raise PreventUpdate
        if not auth.get("society_id"):
            raise PreventUpdate
        if current_children:          # already injected
            raise PreventUpdate

        sid = auth["society_id"]
        society_name = "Society"
        if options:
            for o in options:
                if o.get("value") == sid:
                    society_name = o["label"].split("[")[0].strip()
                    break

        from app.dash_apps.pages.login_system import login_layout
        return login_layout(society_name)

    # ══════════════════════════════════════════════════════════════════════════
    # 6. MASTER ADMIN TOGGLE
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("master-login-collapse", "style"),
        Input("toggle-master-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_master(n):
        if not n:
            raise PreventUpdate
        return {"display": "block"} if n % 2 == 1 else {"display": "none"}

    # ══════════════════════════════════════════════════════════════════════════
    # 7. LOGIN MODAL STATE (close when authenticated)
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("login-modal", "is_open"),
        Input("auth-store", "data"),
        prevent_initial_call=False,
    )
    def manage_modal(auth):
        return not bool(auth and auth.get("authenticated"))

    # ══════════════════════════════════════════════════════════════════════════
    # 8. LOGOUT
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("sb-logout-btn",        "n_clicks"),
        Input("qr-modal-logout-btn",  "n_clicks"),
        prevent_initial_call=True,
    )
    def logout(n1, n2):
        if not (n1 or n2):
            raise PreventUpdate
        return None, "/dashboard/", {"type": "success", "message": "Signed out"}

    # ══════════════════════════════════════════════════════════════════════════
    # 9. MAIN ROUTER — URL → portal content + all shell outputs
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("portal-content",    "children"),
        Output("sb-nav-list",       "children"),
        Output("breadcrumb-ol",     "children"),
        Output("hdr-portal-label",  "children"),
        Output("hdr-portal-label",  "style"),
        Output("sb-user-name",      "children"),
        Output("sb-user-role",      "children"),
        Output("sb-avatar",         "children"),
        Output("hdr-entity-name",   "children"),
        Output("hdr-avatar",        "children"),
        Output("hdr-society-name",  "children"),
        Output("hdr-society-logo",  "src"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def route_page(pathname, auth):
        if not auth or not auth.get("authenticated"):
            empty = html.Div("Please log in.", className="text-muted text-center mt-5")
            return (empty, [], [], "", {}, "—", "—", "?", "User", "?",
                    "EstateHub", "/static/assets/EH_logo.png")

        role       = auth.get("role", "")
        society_id = auth.get("society_id")
        email      = auth.get("email", "")
        user_name  = email.split("@")[0].title()
        avatar     = user_name[0].upper() if user_name else "?"

        # Society branding
        soc_name = "EstateHub"
        soc_logo = "/static/assets/EH_logo.png"
        if society_id:
            try:
                soc = db.execute(
                    "SELECT name, logo FROM societies WHERE id = :sid",
                    {"sid": society_id},
                    fetch_one=True,
                )
                if soc:
                    soc_name = soc["name"]
                    if soc.get("logo"):
                        soc_logo = f"/assets/{society_id}/{soc['logo']}"
            except Exception:
                pass

        is_master = role == "admin" and society_id is None
        cfg_key   = "master" if is_master else (role or "admin")
        cfg       = ROLE_CONFIG.get(cfg_key, ROLE_CONFIG["admin"])
        color     = cfg["color"]

        portal_style = {
            "fontWeight": "700", "fontSize": "20px",
            "minWidth": "150px", "textAlign": "center",
            "color": color,
        }

        return (
            _portal_content(role, society_id, pathname),
            _nav_items(cfg, pathname, color),
            _breadcrumb(pathname),
            cfg["label"],
            portal_style,
            user_name,
            role.title(),
            avatar,
            user_name,
            avatar,
            soc_name,
            soc_logo,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # 10. SIDEBAR TOGGLE
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("app-sidebar",        "className"),
        Output("sb-overlay",         "style"),
        Output("sidebar-open-store", "data"),
        Input("hdr-hamburger-btn",   "n_clicks"),
        Input("sb-overlay",          "n_clicks"),
        Input("sb-collapse-btn",     "n_clicks"),
        State("sidebar-open-store",  "data"),
        prevent_initial_call=True,
    )
    def toggle_sidebar(ham, over, col, store):
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        collapsed = (store or {}).get("collapsed", False)

        if trigger in ("hdr-hamburger-btn", "sb-overlay"):
            new = not collapsed
            overlay = {"display": "none"} if new else {"display": "block"}
            cls = "app-sidebar" if new else "app-sidebar sidebar-open"
            return cls, overlay, {"collapsed": new}

        if trigger == "sb-collapse-btn":
            new = not collapsed
            cls = "app-sidebar sidebar-collapsed" if new else "app-sidebar"
            return cls, {"display": "none"}, {"collapsed": new}

        raise PreventUpdate

    # ══════════════════════════════════════════════════════════════════════════
    # 11. TOAST NOTIFICATIONS
    # ══════════════════════════════════════════════════════════════════════════

    @app.callback(
        Output("toast-container", "children"),
        Input("toast-store", "data"),
        prevent_initial_call=True,
    )
    def show_toast(data):
        if not data:
            return []
        t = data.get("type", "info")
        msg = data.get("message", "")
        icons = {"success": "fa-check-circle", "error": "fa-exclamation-circle",
                 "warning": "fa-exclamation-triangle", "info": "fa-info-circle"}
        colors = {"success": "#10b981", "error": "#ef4444",
                  "warning": "#f59e0b",  "info": "#3b82f6"}
        return dbc.Toast(
            msg,
            header=html.Div([html.I(className=f"fas {icons.get(t,'fa-info-circle')} me-2"),
                              t.title()]),
            icon=t,
            duration=4000,
            is_open=True,
            style={"borderLeft": f"4px solid {colors.get(t,'#3b82f6')}"},
        )

    log.info("Shell callbacks registered ✓")


# ── Private helpers ───────────────────────────────────────────────────────────

def _nav_items(cfg: dict, pathname: str, color: str) -> list:
    items = []
    for tab in cfg["tabs"]:
        href = tab["href"]
        active = bool(pathname and href.rstrip("/") in pathname)
        items.append(
            html.Li(
                dcc.Link(
                    [
                        html.I(
                            className=f"fas {tab['icon']} me-2",
                            style={"width": "16px",
                                   "color": color if active else "rgba(255,255,255,0.5)"},
                        ),
                        html.Span(tab["label"]),
                    ],
                    href=href,
                    className="snav-link" + (" snav-link--active" if active else ""),
                    refresh=False,
                )
            )
        )
    return items


_CRUMB_MAP = {
    "admin-portal": "Dashboard", "owner-portal": "Dashboard",
    "vendor-portal": "Dashboard", "master": "Dashboard",
    "pass-evaluation": "Pass Eval", "cashbook": "Cashbook",
    "owner-cashbook": "Cashbook", "vendor-cashbook": "Cashbook",
    "receipts": "Receipts", "expenses": "Expenses",
    "enroll": "Enroll", "events": "Events",
    "owner-events": "Events", "vendor-events": "Events",
    "security-events": "Events", "concerns": "Concerns",
    "evaluate-pass": "Evaluate Pass", "customize": "Customize",
    "settings": "Settings", "owner-settings": "Settings",
    "vendor-settings": "Settings", "security-settings": "Settings",
    "payments": "Payments", "vendor-payments": "Payments",
    "charges": "Charges", "vendor-charges": "Charges",
    "attendance": "Attendance", "security-receipt": "New Receipt",
    "security-users": "Users", "master-create": "Create Society",
    "master-settings": "Settings",
}


def _breadcrumb(pathname: str) -> list:
    parts = [p for p in (pathname or "").strip("/").split("/")
             if p and p != "dashboard"]
    items = [
        html.Li(
            html.Button(
                [html.I(className="fas fa-home me-1"), "Home"],
                id={"type": "breadcrumb-link", "level": -1},
                n_clicks=0,
                style={"background": "none", "border": "none",
                       "color": "#667eea", "cursor": "pointer",
                       "padding": "0", "fontSize": "12px"},
            ),
            className="bc-item",
        )
    ]
    for i, part in enumerate(parts):
        name   = _CRUMB_MAP.get(part, part.replace("-", " ").title())
        active = i == len(parts) - 1
        items.append(
            html.Li(
                html.Span(name, style={"fontWeight": "600"}) if active
                else html.Button(
                    name,
                    id={"type": "breadcrumb-link", "level": i},
                    n_clicks=0,
                    style={"background": "none", "border": "none",
                           "color": "#667eea", "cursor": "pointer",
                           "padding": "0", "fontSize": "12px"},
                ),
                className="bc-item" + (" bc-item--active" if active else ""),
            )
        )
    return items


def _portal_content(role: str, society_id, pathname: str) -> html.Div:
    from app.dash_apps.pages.portal_pages import (
        master_portal_page, admin_portal_page,
        owner_portal_page, vendor_portal_page, security_portal_page,
    )
    p = pathname or ""
    is_master = role == "admin" and society_id is None

    if is_master:
        return master_portal_page()

    if role == "admin":
        tab = (
            "cashbook"      if "/cashbook"       in p else
            "receipts"      if "/receipts"       in p else
            "expenses"      if "/expenses"       in p else
            "enroll"        if "/enroll"         in p else
            "events"        if "/events"         in p else
            "concerns"      if "/concerns"       in p else
            "evaluate_pass" if "/evaluate-pass"  in p else
            "customize"     if "/customize"      in p else
            "settings"      if "/settings"       in p else
            "dashboard"
        )
        return admin_portal_page(tab)

    if role == "apartment":
        tab = (
            "cashbook"  if "/owner-cashbook" in p or "/cashbook" in p else
            "payments"  if "/payments"       in p else
            "charges"   if "/charges"        in p else
            "events"    if "/owner-events"   in p or "/events"   in p else
            "concerns"  if "/concerns"       in p else
            "settings"  if "/owner-settings" in p or "/settings" in p else
            "dashboard"
        )
        return owner_portal_page(tab)

    if role == "vendor":
        tab = (
            "cashbook"  if "/vendor-cashbook" in p or "/cashbook" in p else
            "payments"  if "/vendor-payments" in p or "/payments" in p else
            "charges"   if "/vendor-charges"  in p or "/charges"  in p else
            "events"    if "/vendor-events"   in p or "/events"   in p else
            "settings"  if "/vendor-settings" in p or "/settings" in p else
            "dashboard"
        )
        return vendor_portal_page(tab)

    if role == "security":
        tab = (
            "attendance"       if "/attendance"       in p else
            "security_events"  if "/security-events"  in p else
            "security_receipt" if "/security-receipt" in p else
            "security_users"   if "/security-users"   in p else
            "settings"         if "/security-settings" in p or "/settings" in p else
            "pass_evaluation"
        )
        return security_portal_page(tab)

    return html.Div("Page not found.", className="text-muted text-center p-5 mt-5")
