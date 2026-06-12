# app/dash_apps/callbacks/shell_callbacks.py
"""
Shell callbacks — owns auth-store, url, login-modal, society dropdown.
Must be registered FIRST in callbacks/__init__.py.

Dash allow_duplicate rules (definitive reference)
--------------------------------------------------
allow_duplicate=True  REQUIRES  prevent_initial_call != False
  ✓  prevent_initial_call=True             fires only on user interactions
  ✓  prevent_initial_call='initial_duplicate'  fires on load AND interactions
  ✗  prevent_initial_call=False (default)  → DuplicateCallback CRASH

Fixes in this version
---------------------
1. load_societies trigger changed from Input("login-modal","is_open") to
   Input("url","pathname") with prevent_initial_call=False.
   Reason: login-modal.is_open is written by guard_modal (allow_duplicate),
   creating a race condition. pathname fires once on initial mount,
   reliably and always, regardless of auth state.

2. guard_modal uses prevent_initial_call='initial_duplicate' so it fires
   on initial load to immediately close the modal for authenticated users.

3. All other allow_duplicate outputs use prevent_initial_call=True (user
   interactions only — buttons, logouts, etc.).
"""

import dash
from dash import Input, Output, State, html, dcc, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.dash_apps.app_shell import ROLE_CONFIG


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db():
    from database.db_manager import db
    return db


def _db_ok() -> bool:
    """Probe the DB with a trivial query. Never raises."""
    try:
        _db()._execute("SELECT 1", (), fetch_one=True)
        return True
    except Exception:
        return False


# ── Navigation helpers ────────────────────────────────────────────────────────

def _make_nav_items(role, society_id, pathname):
    """
    Build sidebar nav using dcc.Link — History API push, no page reload,
    all stores survive tab clicks, auth-store stays populated.
    """
    is_master = role == "admin" and society_id is None
    key   = "master" if is_master else (role or "admin")
    cfg   = ROLE_CONFIG.get(key, ROLE_CONFIG["admin"])
    color = cfg["color"]
    items = []
    for tab in cfg["tabs"]:
        href      = tab["href"]
        is_active = bool(pathname and href.rstrip("/") in pathname)
        items.append(
            html.Li(
                dcc.Link(
                    [
                        html.I(
                            className=f"fas {tab['icon']} me-2",
                            style={
                                "width": "18px",
                                "color": color if is_active else "rgba(255,255,255,0.55)",
                            },
                        ),
                        html.Span(
                            tab["label"],
                            style={"color": "#fff" if is_active else "rgba(255,255,255,0.8)"},
                        ),
                    ],
                    href=href,
                    refresh=False,
                    className="snav-link" + (" snav-link--active" if is_active else ""),
                    style={
                        "display": "flex", "alignItems": "center",
                        "padding": "10px 14px", "borderRadius": "10px",
                        "textDecoration": "none",
                        "background": "rgba(255,255,255,0.12)" if is_active else "transparent",
                        "transition": "background 0.15s ease",
                    },
                ),
                className="snav-item",
                style={"listStyle": "none", "marginBottom": "2px"},
            )
        )
    return items


_PATH_LABELS = {
    "admin-portal":      "Dashboard",
    "owner-portal":      "Dashboard",
    "vendor-portal":     "Dashboard",
    "master":            "Dashboard",
    "pass-evaluation":   "Pass Eval",
    "cashbook":          "Cashbook",
    "owner-cashbook":    "Cashbook",
    "vendor-cashbook":   "Cashbook",
    "receipts":          "Receipts",
    "expenses":          "Expenses",
    "enroll":            "Enroll",
    "users":             "Users",
    "events":            "Events",
    "owner-events":      "Events",
    "vendor-events":     "Events",
    "security-events":   "Events",
    "evaluate-pass":     "Evaluate Pass",
    "customize":         "Customize",
    "settings":          "Settings",
    "owner-settings":    "Settings",
    "vendor-settings":   "Settings",
    "security-settings": "Settings",
    "payments":          "Payments",
    "vendor-payments":   "Payments",
    "charges":           "Charges",
    "vendor-charges":    "Charges",
    "concerns":          "Concerns",
    "attendance":        "Attendance",
    "security-receipt":  "New Receipt",
    "security-users":    "Users",
}


def _breadcrumb(pathname):
    parts = [p for p in (pathname or "").strip("/").split("/") if p and p != "dashboard"]
    items = [
        html.Li(
            dcc.Link(
                [html.I(className="fas fa-home me-1"), "Home"],
                href="/dashboard/", refresh=False,
                style={"textDecoration": "none", "color": "#1d74d8"},
            ),
            className="bc-item",
        )
    ]
    for i, part in enumerate(parts):
        name   = _PATH_LABELS.get(part, part.replace("-", " ").title())
        active = i == len(parts) - 1
        items.append(html.Li(
            html.Span(name, style={"fontWeight": "600"}) if active
            else dcc.Link(name, href=f"/dashboard/{part}", refresh=False,
                          style={"textDecoration": "none", "color": "#1d74d8"}),
            className="bc-item" + (" bc-item--active" if active else ""),
        ))
    return items


def _portal_content(role, society_id, pathname):
    from app.dash_apps.pages.portal_pages import (
        master_portal_page, admin_portal_page, owner_portal_page,
        vendor_portal_page, security_portal_page,
    )
    is_master = role == "admin" and society_id is None
    p = pathname or ""

    if is_master:
        return master_portal_page()
    if role == "admin":
        tab = (
            "cashbook"      if "/cashbook"      in p else
            "receipts"      if "/receipts"      in p else
            "expenses"      if "/expenses"      in p else
            "enroll"        if "/enroll"        in p else
            "events"        if "/events"        in p else
            "concerns"      if "/concerns"      in p else
            "evaluate_pass" if "/evaluate-pass" in p else
            "customize"     if "/customize"     in p else
            "settings"      if "/settings"      in p else
            "dashboard"
        )
        return admin_portal_page(tab)
    if role == "apartment":
        tab = (
            "cashbook" if "/owner-cashbook" in p or "/cashbook" in p else
            "payments" if "/payments"       in p else
            "charges"  if "/charges"        in p else
            "events"   if "/owner-events"   in p or "/events"   in p else
            "concerns" if "/concerns"       in p else
            "settings" if "/owner-settings" in p or "/settings" in p else
            "dashboard"
        )
        return owner_portal_page(tab)
    if role == "vendor":
        tab = (
            "cashbook" if "/vendor-cashbook" in p or "/cashbook" in p else
            "payments" if "/vendor-payments" in p or "/payments" in p else
            "charges"  if "/vendor-charges"  in p or "/charges"  in p else
            "events"   if "/vendor-events"   in p or "/events"   in p else
            "settings" if "/vendor-settings" in p or "/settings" in p else
            "dashboard"
        )
        return vendor_portal_page(tab)
    if role == "security":
        tab = (
            "attendance"       if "/attendance"        in p else
            "security_events"  if "/security-events"   in p else
            "security_receipt" if "/security-receipt"  in p else
            "dashboard"        if "/security-users"    in p else
            "settings"         if "/security-settings" in p or "/settings" in p else
            "pass_evaluation"
        )
        return security_portal_page(tab)
    return html.Div("Page not found", className="text-muted text-center p-5 mt-5")


# ═════════════════════════════════════════════════════════════════════════════
# REGISTER
# ═════════════════════════════════════════════════════════════════════════════

def register_shell_callbacks(app):
    print("  → Registering shell callbacks…")

    # ── 0. SOCIETY DROPDOWN ───────────────────────────────────────────────────
    # Trigger: url.pathname (fires on initial mount with prevent_initial_call=False)
    # No allow_duplicate outputs → no Dash validation issue.
    # Using pathname instead of login-modal.is_open avoids a race condition
    # with guard_modal which also writes login-modal.is_open.
    @app.callback(
        Output("society-dropdown", "options"),
        Output("society-dropdown", "disabled"),
        Output("login-db-error",   "children"),
        Output("login-db-error",   "style"),
        Input("url", "pathname"),
        prevent_initial_call=False,   # fires on initial page load — no allow_duplicate here
    )
    def load_societies(pathname):
        print(f"\n🔍 load_societies — pathname={pathname}")
        _ERR = {"display": "block", "marginBottom": "15px",
                "padding": "8px", "borderRadius": "8px"}

        if not _db_ok():
            print("❌ DB unreachable")
            return (
                [], True,
                html.Div(
                    [html.I(className="fas fa-database me-2"),
                     "Cannot connect to the database."],
                    style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                ),
                {**_ERR, "background": "#f8d7da"},
            )

        try:
            rows = _db()._execute(
                "SELECT id, name FROM societies ORDER BY name",
                (), fetch_all=True,
            ) or []
        except Exception as exc:
            print(f"❌ societies query error: {exc}")
            import traceback; traceback.print_exc()
            return (
                [], True,
                html.Div(
                    [html.I(className="fas fa-database me-2"),
                     f"Database error: {str(exc)[:120]}"],
                    style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                ),
                {**_ERR, "background": "#f8d7da"},
            )

        if not rows:
            print("⚠️  societies table empty")
            return (
                [], False,
                html.Div(
                    [html.I(className="fas fa-exclamation-triangle me-2"),
                     "No societies found. Contact your administrator."],
                    style={"color": "#856404", "fontSize": "12px", "textAlign": "center"},
                ),
                {**_ERR, "background": "#fff3cd"},
            )

        options = [{"label": r["name"], "value": r["id"]} for r in rows]
        print(f"✅ {len(options)} societies loaded: {[r['name'] for r in rows]}")
        return options, False, "", {"display": "none"}

    # ── 1. LOGIN MODAL GUARD ──────────────────────────────────────────────────
    # 'initial_duplicate': fires on load AND on subsequent auth-store changes.
    # Closes modal instantly when auth-store shows authenticated=True.
    # allow_duplicate=True required because logout also writes login-modal.is_open.
    @app.callback(
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("auth-store",   "data"),
        Input("url",          "pathname"),
        prevent_initial_call="initial_duplicate",
    )
    def guard_modal(auth, pathname):
        authenticated = bool(auth and auth.get("authenticated"))
        return not authenticated  # True = open (not logged in), False = closed (logged in)

    # ── 2. STAGE 1 → STAGE 2 ─────────────────────────────────────────────────
    # allow_duplicate=True on auth-store + cookie-store.
    # prevent_initial_call=True: triggered by button click only.
    @app.callback(
        Output("login-stage-1", "style"),
        Output("login-stage-2", "style"),
        Output("auth-store",    "data",  allow_duplicate=True),
        Output("cookie-store",  "data",  allow_duplicate=True),
        Input("society-select-btn",        "n_clicks"),
        State("society-dropdown",          "value"),
        State("remember-society-checkbox", "value"),
        State("auth-store",                "data"),
        prevent_initial_call=True,
    )
    def transition_to_stage2(n, sid, remember, auth):
        if not n or not sid:
            raise PreventUpdate
        print(f"\n✅ Society selected: {sid}")
        auth = auth or {}
        auth.update({"society_id": sid, "authenticated": False})
        cookie = {"society_id": sid} if remember else no_update
        return {"display": "none"}, {"display": "block"}, auth, cookie

    # ── 3. BACK TO STAGE 1 ────────────────────────────────────────────────────
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

    # ── 4. COOKIE → AUTO-ADVANCE ──────────────────────────────────────────────
    @app.callback(
        Output("society-dropdown", "value"), 
        Output("login-stage-1",   "style",       allow_duplicate=True),
        Output("login-stage-2",   "style",       allow_duplicate=True),
        Output("auth-store",      "data",        allow_duplicate=True),
        Input("cookie-store",     "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def restore_from_cookie(cookie, options):
        if not cookie or not cookie.get("society_id"):
            return no_update, no_update, no_update, no_update
        sid = cookie["society_id"]
        if options and not any(o.get("value") == sid for o in options if isinstance(o, dict)):
            return no_update, no_update, no_update, no_update
        print(f"\n✅ Cookie restore: society_id={sid}")
        return sid, {"display": "none"}, {"display": "block"}, \
               {"society_id": sid, "authenticated": False}

    # ── 5. INJECT STAGE-2 CONTENT ─────────────────────────────────────────────
    @app.callback(
        Output("login-stage-2", "children"),
        Input("auth-store",     "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def inject_stage2(auth, options):
        if not auth or auth.get("authenticated"):
            return no_update
        sid = auth.get("society_id")
        if not sid:
            return no_update
        society_name = next(
            (o["label"] for o in (options or [])
             if isinstance(o, dict) and o["value"] == sid),
            "Society",
        )
        print(f"\n✅ Injecting login form: {society_name}")
        from app.dash_apps.pages.login_system import login_layout
        return login_layout(society_name)

    # ── 6. MASTER LOGIN TOGGLE ────────────────────────────────────────────────
    @app.callback(
        Output("master-login-collapse", "style"),
        Input("toggle-master-btn",      "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_master(n):
        if not n:
            raise PreventUpdate
        return {"display": "block"} if n % 2 == 1 else {"display": "none"}

    # ── 7. LOGOUT ─────────────────────────────────────────────────────────────
    @app.callback(
        Output("auth-store",   "data",    allow_duplicate=True),
        Output("url",          "pathname",allow_duplicate=True),
        Output("toast-store",  "data",    allow_duplicate=True),
        Output("login-modal",  "is_open", allow_duplicate=True),
        Input("sb-logout-btn",       "n_clicks"),
        Input("qr-modal-logout-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def logout(n_sb, n_qr):
        if not (n_sb or n_qr):
            raise PreventUpdate
        print("\n🚪 Logout")
        try:
            from flask_login import logout_user
            logout_user()
        except Exception:
            pass
        return None, "/dashboard/", {"type": "success", "message": "Signed out"}, True

    # ── 8. MAIN PAGE ROUTER ───────────────────────────────────────────────────
    # prevent_initial_call=False, NO allow_duplicate outputs.
    # login-modal.is_open is owned exclusively by guard_modal (above).
    @app.callback(
        Output("portal-content",   "children"),
        Output("portal-content-store", "data"),
        Output("sb-nav-list",      "children"),
        Output("breadcrumb-ol",    "children"),
        Output("hdr-portal-label", "children"),
        Output("hdr-portal-label", "style"),
        Output("sb-user-name",     "children"),
        Output("sb-user-role",     "children"),
        Output("sb-avatar",        "children"),
        Output("hdr-entity-name",  "children"),
        Output("hdr-avatar",       "children"),
        Output("hdr-society-name", "children"),
        Output("hdr-society-logo", "src"),
        Input("url",        "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def route_page(pathname, auth):
        _BLANK = (
            html.Div("Please log in", className="text-muted text-center mt-5"),
            {"rendered": False},
            [], [], "", {}, "—", "—", "?", "User", "?",
            "EstateHub", "/static/assets/EH_logo.png",
        )
        if not auth or not auth.get("authenticated"):
            return _BLANK

        role       = auth.get("role", "admin")
        society_id = auth.get("society_id")
        user_id    = auth.get("user_id")
        email      = auth.get("email", "")
        db = _db()

        try:
            u_row = db._execute(
                "SELECT name FROM users WHERE id = %s", (user_id,), fetch_one=True)
            user_name = (u_row or {}).get("name") or email.split("@")[0].title()
        except Exception:
            user_name = email.split("@")[0].title()

        society_name = "EstateHub"
        society_logo = "/static/assets/EH_logo.png"
        if society_id:
            try:
                s_row = db._execute(
                    "SELECT name, logo FROM societies WHERE id = %s",
                    (society_id,), fetch_one=True)
                if s_row:
                    society_name = s_row.get("name", society_name)
                    if s_row.get("logo"):
                        society_logo = f"/assets/{society_id}/{s_row['logo']}"
            except Exception:
                pass

        is_master = role == "admin" and society_id is None
        key = "master" if is_master else (role or "admin")
        cfg = ROLE_CONFIG.get(key, ROLE_CONFIG["admin"])
        portal_style = {
            "fontWeight": "700", "fontSize": "20px",
            "color": cfg["color"], "minWidth": "160px", "textAlign": "center",
        }
        avatar = (user_name or "?")[0].upper()

        return (
            _portal_content(role, society_id, pathname),
            {"rendered": True},
            _make_nav_items(role, society_id, pathname),
            _breadcrumb(pathname),
            cfg["label"], portal_style,
            user_name, role.title(), avatar,
            user_name, avatar,
            society_name, society_logo,
        )

    # ── 9. SIDEBAR TOGGLE ─────────────────────────────────────────────────────
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
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger   = ctx.triggered[0]["prop_id"].split(".")[0]
        collapsed = (store or {}).get("collapsed", False)
        if trigger in ("hdr-hamburger-btn", "sb-overlay"):
            nc = not collapsed
            return (
                "app-sidebar" if nc else "app-sidebar sidebar-open",
                {"display": "none"} if nc else {"display": "block"},
                {"collapsed": nc},
            )
        if trigger == "sb-collapse-btn":
            nc = not collapsed
            return (
                "app-sidebar sidebar-collapsed" if nc else "app-sidebar",
                {"display": "none"}, {"collapsed": nc},
            )
        raise PreventUpdate

    # ── 10. TOAST NOTIFICATIONS ───────────────────────────────────────────────
    @app.callback(
        Output("toast-container", "children"),
        Input("toast-store",      "data"),
        prevent_initial_call=True,
    )
    def show_toast(data):
        if not data:
            return []
        t   = data.get("type", "info")
        msg = data.get("message", "")
        icons  = {"success": "fa-check-circle", "error": "fa-exclamation-circle",
                  "warning": "fa-exclamation-triangle", "info": "fa-info-circle"}
        colors = {"success": "#10b981", "error": "#ef4444",
                  "warning": "#f59e0b", "info": "#3b82f6"}
        return dbc.Toast(
            msg,
            id="toast",
            header=html.Div([
                html.I(className=f"fas {icons.get(t,'fa-info-circle')} me-2"),
                t.title(),
            ]),
            icon=t, duration=4000, is_open=True,
            style={"borderLeft": f"4px solid {colors.get(t,'#3b82f6')}"},
        )

    print("  ✓ Shell callbacks registered")