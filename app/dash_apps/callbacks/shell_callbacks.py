# app/dash_apps/callbacks/shell_callbacks.py
import json
from datetime import datetime, timedelta

import dash
from dash import Input, Output, State, html, dcc, no_update
import dash_bootstrap_components as dbc

from app.dash_apps.app_shell import ROLE_CONFIG


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db():
    from database.db_manager import db
    return db


def _sid(auth):
    return (auth or {}).get("society_id")


def _redirect_for_role(role, society_id):
    if role == "admin" and society_id is None:
        return "/dashboard/master"
    if role == "admin":
        return "/dashboard/admin-portal"
    if role == "apartment":
        return "/dashboard/owner-portal"
    if role == "vendor":
        return "/dashboard/vendor-portal"
    if role == "security":
        return "/dashboard/pass-evaluation"
    return "/dashboard/"


def _make_nav_items(role, society_id, pathname):
    is_master = role == "admin" and society_id is None
    key  = "master" if is_master else (role or "admin")
    cfg  = ROLE_CONFIG.get(key, ROLE_CONFIG["admin"])
    color = cfg["color"]
    items = []
    for tab in cfg["tabs"]:
        href      = tab["href"]
        is_active = bool(pathname and href.rstrip("/") in pathname)
        items.append(
            html.Li(
                html.A(
                    [
                        html.I(
                            className=f"fas {tab['icon']} me-2",
                            style={
                                "width": "18px",
                                "color": color if is_active else "rgba(255,255,255,0.55)",
                            },
                        ),
                        html.Span(tab["label"]),
                    ],
                    href=href,
                    className="snav-link" + (" snav-link--active" if is_active else ""),
                ),
                className="snav-item",
            )
        )
    return items


def _breadcrumb(pathname):
    path_map = {
        "admin-portal":    "Dashboard",
        "owner-portal":    "Dashboard",
        "vendor-portal":   "Dashboard",
        "master":          "Dashboard",
        "pass-evaluation": "Pass Eval",
        "cashbook":        "Cashbook",
        "owner-cashbook":  "Cashbook",
        "vendor-cashbook": "Cashbook",
        "receipts":        "Receipts",
        "expenses":        "Expenses",
        "enroll":          "Enroll",
        "users":           "Users",
        "events":          "Events",
        "owner-events":    "Events",
        "vendor-events":   "Events",
        "security-events": "Events",
        "evaluate-pass":   "Evaluate Pass",
        "customize":       "Customize",
        "settings":        "Settings",
        "owner-settings":  "Settings",
        "vendor-settings": "Settings",
        "security-settings": "Settings",
        "payments":        "Payments",
        "vendor-payments": "Payments",
        "charges":         "Charges",
        "vendor-charges":  "Charges",
        "attendance":      "Attendance",
        "security-receipt":"New Receipt",
        "security-users":  "Users",
    }
    parts = [p for p in (pathname or "").strip("/").split("/") if p and p != "dashboard"]
    items = [
        html.Li(
            html.A([html.I(className="fas fa-home me-1"), "Home"], href="/dashboard/"),
            className="bc-item",
        )
    ]
    for i, part in enumerate(parts):
        name   = path_map.get(part, part.replace("-", " ").title())
        active = i == len(parts) - 1
        items.append(
            html.Li(
                name if active else html.A(name, href=f"/dashboard/{part}"),
                className="bc-item" + (" bc-item--active" if active else ""),
            )
        )
    return items


def _portal_content(role, society_id, pathname):
    """
    Route pathname → portal page content.
    Uses portal_pages.py — the single source for all portal layouts.
    """
    from app.dash_apps.pages.portal_pages import (
        master_portal_page,
        admin_portal_page,
        owner_portal_page,
        vendor_portal_page,
        security_portal_page,
    )

    is_master = role == "admin" and society_id is None
    p = pathname or ""

    # ── Master admin ──────────────────────────────────────────────────────
    if is_master:
        return master_portal_page()

    # ── Admin portal ──────────────────────────────────────────────────────
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
        # Customize has its own layout
        if tab == "customize":
            try:
                from app.dash_apps.pages.customize_layout import customize_layout
                return customize_layout()
            except Exception as e:
                print(f"Customize error: {e}")
        return admin_portal_page(tab)

    # ── Apartment owner ───────────────────────────────────────────────────
    if role == "apartment":
        tab = (
            "cashbook"      if "/owner-cashbook" in p or ("/cashbook" in p) else
            "payments"      if "/payments"       in p else
            "charges"       if "/charges"        in p else
            "events"        if "/owner-events"   in p or ("/events" in p) else
            "concerns"      if "/concerns"       in p else
            "settings"      if "/owner-settings" in p or ("/settings" in p) else
            "dashboard"
        )
        return owner_portal_page(tab)

    # ── Vendor ────────────────────────────────────────────────────────────
    if role == "vendor":
        tab = (
            "cashbook"      if "/vendor-cashbook" in p or ("/cashbook" in p) else
            "payments"      if "/vendor-payments" in p or ("/payments" in p) else
            "charges"       if "/vendor-charges"  in p or ("/charges"  in p) else
            "events"        if "/vendor-events"   in p or ("/events"   in p) else
            "settings"      if "/vendor-settings" in p or ("/settings" in p) else
            "dashboard"
        )
        return vendor_portal_page(tab)

    # ── Security ──────────────────────────────────────────────────────────
    if role == "security":
        tab = (
            "attendance"       if "/attendance"        in p else
            "security_events"  if "/security-events"   in p else
            "security_receipt" if "/security-receipt"  in p else
            "security_users"   if "/security-users"    in p else
            "settings"         if "/security-settings" in p or ("/settings" in p) else
            "pass_evaluation"
        )
        return security_portal_page(tab)

    return html.Div("Page not found", className="text-muted text-center p-5 mt-5")


def _login_success(user, remember, email, society_id, method):
    is_dict = isinstance(user, dict)
    role    = user.get("role")       if is_dict else user.role
    sid     = user.get("society_id") if is_dict else user.society_id
    uid     = user.get("user_id")    if is_dict else user.id

    user_dict = {
        "user_id": uid, "email": email,
        "role": role, "society_id": sid,
        "authenticated": True,
    }
    redirect = _redirect_for_role(role, sid)
    cookie   = ({"email": email, "society_id": society_id, "method": method}
                if remember else no_update)
    return (
        user_dict, redirect,
        {"type": "success", "message": f"Welcome, {email.split('@')[0].title()}!"},
        False, cookie,
    )


def _check_db_and_seed():
    try:
        db = _db()
        if not db.test_connection():
            return False, "Cannot reach the database.", []
        user_count = db.execute_query("SELECT COUNT(*) AS c FROM users", fetch_one=True)
        if user_count and user_count["c"] == 0:
            from werkzeug.security import generate_password_hash
            db.execute_query(
                "INSERT INTO users(email,password_hash,role,login_method) VALUES(%s,%s,'admin','password') ON CONFLICT(email) DO NOTHING",
                ("master@estatehub.com", generate_password_hash("Master@2024")),
            )
        societies = db.execute_query(
            "SELECT id, name FROM societies ORDER BY name", fetch_all=True
        ) or []
        return True, None, societies
    except Exception as e:
        return False, str(e), []


# ── Register ──────────────────────────────────────────────────────────────────
# app/dash_apps/callbacks/shell_callbacks.py

def register_shell_callbacks(app):
    """Register all shell-level callbacks with the Dash app."""

    # ── 0. Populate society dropdown when modal opens ──────────────────────────────────────
    @app.callback(
        Output("society-dropdown", "options"),
        Output("society-dropdown", "disabled"),
        Output("login-db-error", "children"),
        Output("login-db-error", "style"),
        Input("login-modal", "is_open"),
        prevent_initial_call=False,
    )
    def load_societies(is_open):
        """Load societies from database into dropdown."""
        if not is_open:
            return no_update, no_update, no_update, no_update
            
        try:
            from database.db_manager import db
            
            # Test connection first
            if not db.test_connection():
                return (
                    [],
                    True,
                    html.Div(
                        [
                            html.I(className="fas fa-database me-2"),
                            "Cannot connect to database. Please check your connection.",
                        ],
                        style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                    ),
                    {"display": "block", "marginBottom": "15px", "padding": "8px", 
                     "background": "#f8d7da", "borderRadius": "8px"}
                )
            
            # Fetch societies
            societies = db.execute_query(
                "SELECT id, name FROM societies WHERE active = true ORDER BY name",
                fetch_all=True
            ) or []
            
            if not societies:
                return (
                    [],
                    False,
                    html.Div(
                        [
                            html.I(className="fas fa-exclamation-triangle me-2"),
                            "No societies found. Please contact the administrator.",
                        ],
                        style={"color": "#856404", "fontSize": "12px", "textAlign": "center"},
                    ),
                    {"display": "block", "marginBottom": "15px", "padding": "8px", 
                     "background": "#fff3cd", "borderRadius": "8px"}
                )
            
            options = [{"label": s["name"], "value": s["id"]} for s in societies]
            
            return (
                options,
                False,  # enabled
                "",
                {"display": "none"}
            )
            
        except Exception as e:
            print(f"Error loading societies: {e}")
            return (
                [],
                True,
                html.Div(
                    [html.I(className="fas fa-database me-2"), f"Database error: {str(e)[:100]}"],
                    style={"color": "#dc3545", "fontSize": "12px", "textAlign": "center"},
                ),
                {"display": "block", "marginBottom": "15px", "padding": "8px", 
                 "background": "#f8d7da", "borderRadius": "8px"}
            )

    # ── 1. Stage 1 → Stage 2 transition ─────────────────────────────────────────
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
    def transition_to_stage2(n_clicks, society_id, remember_society, auth_data):
        """Move from society selection to login form."""
        if not n_clicks or not society_id:
            raise PreventUpdate
        
        # Update auth-store with society_id
        auth_data = auth_data or {}
        auth_data["society_id"] = society_id
        auth_data["authenticated"] = False
        
        # Update cookie if "remember society" is checked
        cookie_update = no_update
        if remember_society:
            cookie_update = {"society_id": society_id}
        
        return (
            {"display": "none"},  # Hide stage 1
            {"display": "block"},  # Show stage 2
            auth_data,
            cookie_update
        )
    
    # ── 1b. Back button to return to stage 1 ───────────────────────────────────
    @app.callback(
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Input("back-to-stage1-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def back_to_stage1(n_clicks):
        """Return to society selection."""
        if not n_clicks:
            raise PreventUpdate
        return {"display": "block"}, {"display": "none"}

    # ── 2. Restore society from cookie (auto-advance if cookie exists) ────────────────────
    @app.callback(
        Output("society-dropdown", "value", allow_duplicate=True),
        Output("login-stage-1", "style", allow_duplicate=True),
        Output("login-stage-2", "style", allow_duplicate=True),
        Output("auth-store", "data", allow_duplicate=True),
        Input("cookie-store", "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def restore_society_from_cookie(cookie, society_options):
        """If cookie has society_id, auto-advance to stage 2."""
        if not cookie or not cookie.get("society_id"):
            return no_update, no_update, no_update, no_update
        
        society_id = cookie["society_id"]
        
        # Verify society_id exists in options
        if society_options:
            valid = any(opt["value"] == society_id for opt in society_options if isinstance(opt, dict))
            if not valid:
                return no_update, no_update, no_update, no_update
        
        auth_data = {"society_id": society_id, "authenticated": False}
        
        return (
            society_id,           # Pre-select dropdown
            {"display": "none"},  # Hide stage 1
            {"display": "block"},  # Show stage 2
            auth_data
        )
    
    # ── 3. Restore "remember me" cookie for login form ───────────────────────────────────
    @app.callback(
        Output("login-email", "value", allow_duplicate=True),
        Output("login-email-pin", "value", allow_duplicate=True),
        Output("login-email-pattern", "value", allow_duplicate=True),
        Output("login-tabs", "value", allow_duplicate=True),
        Input("cookie-store", "data"),
        State("login-stage-2", "style"),
        prevent_initial_call=True,
    )
    def restore_login_cookie(cookie, stage2_style):
        """Pre-fill email and select correct tab from cookie."""
        if not cookie or not cookie.get("remember_me"):
            return no_update, no_update, no_update, no_update
        
        email = cookie.get("email", "")
        method = cookie.get("method", "password")
        
        # Only pre-fill if stage 2 is visible
        if stage2_style and stage2_style.get("display") == "block":
            return email, email, email, method
        
        return no_update, no_update, no_update, no_update

    # ── 4. Save "remember me" cookie on successful login ─────────────────────────────────
    @app.callback(
        Output("cookie-store", "data", allow_duplicate=True),
        Input("auth-store", "data"),
        State("remember-me-checkbox", "value"),
        State("login-email", "value"),
        State("login-tabs", "value"),
        prevent_initial_call=True,
    )
    def save_login_cookie(auth_data, remember_me, email, method):
        """Save remember me cookie after successful login."""
        if not auth_data or not auth_data.get("authenticated"):
            raise PreventUpdate
        
        if not remember_me:
            return no_update
        
        return {
            "email": email,
            "method": method,
            "remember_me": True
        }

    # ── 5. Populate login stage 2 content ─────────────────────────────────────────────────
    @app.callback(
        Output("login-stage-2", "children"),
        Input("auth-store", "data"),
        State("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def inject_login_stage2(auth_data, society_options):
        """Generate the login form with society name."""
        if not auth_data or auth_data.get("authenticated"):
            return no_update

        society_id = auth_data.get("society_id")
        if not society_id:
            return no_update

        # Find society name from options
        society_name = "Society"
        if society_options:
            for opt in society_options:
                if isinstance(opt, dict) and opt.get("value") == society_id:
                    society_name = opt.get("label", "Society")
                    break

        from app.dash_apps.pages.login_system import login_layout
        return login_layout(society_name)
    
    # ── 6. Toggle master login ───────────────────────────────────────────
    @app.callback(
        Output("master-login-collapse", "style"),
        Input("toggle-master-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_master(n):
        if not n:
            raise PreventUpdate
        return {"display": "block"} if n and n % 2 == 1 else {"display": "none"}

    # ── 7. Logout ─────────────────────────────────────────────────────────
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("sb-logout-btn", "n_clicks"),
        Input("qr-modal-logout-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def logout(n2, n3):
        if not (n2 or n3):
            raise PreventUpdate
        try:
            from flask_login import logout_user
            logout_user()
        except Exception:
            pass
        return None, "/dashboard/", {"type": "success", "message": "Signed out"}, True

    # ── 8. Main Router (continued from your existing code) ─────────────────
    # ... (keep your existing router and other callbacks here) ...

    print("✓ Shell callbacks registered")