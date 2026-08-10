# app/dash_apps/callbacks/login_callbacks.py
"""
Login Callbacks — EstateHub.

Password / PIN / pattern authentication.
"""

import dash
from dash import Input, Output, State, no_update, html, ctx
from dash.exceptions import PreventUpdate

from app.services.auth_service import authenticate_user
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
    get_current_linked_id,   # only if the file has an ownership check (apartment/vendor/security's own record)
)


def _login_response(user: dict):
    _establish_server_session(user)
    role       = user.get("role", "admin")
    society_id = user.get("society_id")
    name       = user.get("email", "").split("@")[0]
    return (
        _build_auth_store(user),
        _redirect(role, society_id),
        {"type": "success", "message": f"Welcome, {name}!"},
        False,
    )


def _login_error(message: str):
    return no_update, no_update, {"type": "error", "message": message}, no_update


def _establish_server_session(user: dict) -> None:
    try:
        from flask_login import login_user
        from app.models.user import User

        uid = user.get("user_id") or user.get("id")
        if not uid:
            return
        login_user(User(
            user_id=uid,
            email=user.get("email", ""),
            role=user.get("role", "admin"),
            society_id=user.get("society_id"),
            linked_id=user.get("linked_id"),
        ), remember=True)
    except Exception as exc:
        print(f"⚠️  Could not establish server-side session for user_id={user.get('user_id')}: {exc}")


def _build_auth_store(user: dict) -> dict:
    return {
        "user_id":       user.get("user_id") or user.get("id"),
        "email":         user.get("email", ""),
        "role":          user.get("role", "admin"),
        "society_id":    user.get("society_id"),
        "linked_id":     user.get("linked_id"),
        "security_id":   user.get("security_id") or (
                              user.get("linked_id") if user.get("role") == "security" else None),
        "apartment_id":  user.get("apartment_id") or (
                              user.get("linked_id") if user.get("role") == "apartment" else None),
        "vendor_id":     user.get("vendor_id") or (
                              user.get("linked_id") if user.get("role") == "vendor" else None),
        "authenticated": True,
        "token":         user.get("token", ""),
    }


def _redirect(role: str, society_id) -> str:
    if role == "master":
        return "/dashboard/master"
    paths = {
        "admin":     "/dashboard/admin-portal",
        "apartment": "/dashboard/owner-portal",
        "vendor":    "/dashboard/vendor-portal",
        "security":  "/dashboard/pass-evaluation",
    }
    return paths.get(role, "/dashboard/admin-portal")


def register_login_callbacks(app):
    print("  → Registering login callbacks…")

    # ── 1. PASSWORD LOGIN ──────────────────────────────────────────
    @app.callback(
        Output("auth-store",   "data",    allow_duplicate=True),
        Output("url",          "pathname",allow_duplicate=True),
        Output("toast-store",  "data",    allow_duplicate=True),
        Output("login-modal",  "is_open", allow_duplicate=True),
        Input("login-btn",     "n_clicks"),
        State("login-email",    "value"),
        State("login-password", "value"),
        State("auth-store",     "data"),
        prevent_initial_call=True,
    )
    def handle_password_login(n, email, password, auth):
        if not n or not email or not password:
            raise PreventUpdate

        print(f"\n🔐 Password login: {email}")
        society_id = (auth or {}).get("society_id")
        try:
            user = authenticate_user(email.strip(), password, society_id)
        except Exception:
            print(f"❌ Database connection error during password login")
            return _login_error("No Database connection")
        if not user:
            print(f"❌ Password login failed: {email}")
            return _login_error("Invalid email or password")
        print(f"✅ Password login success: {email}")
        return _login_response(user)

    # ── 2. PIN LOGIN ───────────────────────────────────────────────
    @app.callback(
        Output("auth-store",   "data",    allow_duplicate=True),
        Output("url",          "pathname",allow_duplicate=True),
        Output("toast-store",  "data",    allow_duplicate=True),
        Output("login-modal",  "is_open", allow_duplicate=True),
        Input("login-pin-btn", "n_clicks"),
        State("login-email-pin", "value"),
        State("login-pin",       "value"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def handle_pin_login(n, email, pin, auth):
        if not n or not email or not pin:
            raise PreventUpdate

        print(f"\n🔢 PIN login: {email}")
        society_id = (auth or {}).get("society_id")
        from app.services.auth_service import authenticate_pin
        try:
            user = authenticate_pin(email.strip(), pin, society_id)
        except Exception:
            print(f"❌ Database connection error during PIN login")
            return _login_error("No Database connection")
        if not user:
            print(f"❌ PIN login failed: {email}")
            return _login_error("Invalid PIN — please try again")
        print(f"✅ PIN login success: {email}")
        return _login_response(user)

    # ── 3. PATTERN LOGIN ──────────────────────────────────────────
    @app.callback(
        Output("auth-store",       "data",    allow_duplicate=True),
        Output("url",              "pathname",allow_duplicate=True),
        Output("toast-store",      "data",    allow_duplicate=True),
        Output("login-modal",      "is_open", allow_duplicate=True),
        Input("login-pattern-btn", "n_clicks"),
        State("login-email-pattern","value"),
        State("login-pattern",      "value"),
        State("auth-store",         "data"),
        prevent_initial_call=True,
    )
    def handle_pattern_login(n, email, pattern, auth):
        if not n or not email or not pattern:
            raise PreventUpdate

        print(f"\n🔵 Pattern login: {email}")
        society_id = (auth or {}).get("society_id")
        from app.services.auth_service import authenticate_pattern
        try:
            user = authenticate_pattern(email.strip(), pattern, society_id)
        except Exception:
            print(f"❌ Database connection error during pattern login")
            return _login_error("No Database connection")
        if not user:
            print(f"❌ Pattern login failed: {email}")
            return _login_error("Pattern not recognised — please try again")
        print(f"✅ Pattern login success: {email}")
        return _login_response(user)

    # ── 4. MASTER ADMIN LOGIN ──────────────────────────────────────
    @app.callback(
        Output("auth-store",    "data",    allow_duplicate=True),
        Output("url",           "pathname",allow_duplicate=True),
        Output("toast-store",   "data",    allow_duplicate=True),
        Output("login-modal",   "is_open", allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        State("master-admin-email",    "value"),
        State("master-admin-password", "value"),
        prevent_initial_call=True,
    )
    def handle_master_login(n, email, password):
        if not n or not email or not password:
            raise PreventUpdate

        print(f"\n👑 Master admin login: {email}")
        try:
            user = authenticate_user(email.strip(), password, society_id=None)
        except Exception:
            print(f"❌ Database connection error during master admin login")
            return _login_error("No Database connection")
        if not user or user.get("role") != "master":
            return _login_error("Invalid master admin credentials")

        print(f"✅ Master admin login success: {email}")
        return _login_response(user)

    # ── 5. FORGOT PASSWORD — OPEN MODAL ──────────────────────────
    @app.callback(
        Output("forgot-password-modal", "is_open"),
        Output("reset-email-input",     "value"),
        Input("forgot-password-link",   "n_clicks"),
        State("login-email",            "value"),
        State("forgot-password-modal",  "is_open"),
        prevent_initial_call=True,
    )
    def toggle_forgot_modal(n, email, is_open):
        if not n:
            raise PreventUpdate
        return not is_open, email or ""

    # ── 6. FORGOT PASSWORD — SEND RESET / CONFIRM NEW PASSWORD ──
    @app.callback(
        Output("forgot-password-modal", "is_open",  allow_duplicate=True),
        Output("reset-password-modal",  "is_open"),
        Output("toast-store",           "data",     allow_duplicate=True),
        Input("send-reset-btn",    "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        State("reset-email-input",    "value"),
        State("reset-token-input",    "value"),
        State("new-password-input",   "value"),
        State("confirm-password-input","value"),
        State("auth-store",            "data"),
        prevent_initial_call=True,
    )
    def handle_reset_flow(send_n, confirm_n, email, token, new_pass, confirm_pass, auth):
        ctx_local = dash.callback_context
        if not ctx_local.triggered:
            raise PreventUpdate
        trigger = ctx_local.triggered[0]["prop_id"].split(".")[0]

        if trigger == "send-reset-btn":
            if not email:
                return no_update, no_update, \
                       {"type": "error", "message": "Please enter your email address"}

            print(f"\n📧 Password reset requested for: {email}")
            society_id = (auth or {}).get("society_id")
            from app.services.auth_service import request_password_reset
            ok, msg, _ = request_password_reset(email.strip(), society_id)
            return (not ok), no_update, {"type": "success" if ok else "error", "message": msg}

        if trigger == "confirm-reset-btn":
            if not token or not new_pass:
                return no_update, no_update, \
                       {"type": "error", "message": "Please fill in all fields"}
            if new_pass != confirm_pass:
                return no_update, no_update, \
                       {"type": "error", "message": "Passwords do not match"}

            print("\n🔑 Confirming password reset")
            from app.services.auth_service import reset_password
            ok, msg = reset_password(token.strip(), new_pass)
            return no_update, (not ok), {"type": "success" if ok else "error", "message": msg}

        raise PreventUpdate

    # ── 7. PATTERN CLEAR BUTTON ────────────────────────────────────
    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var inp = document.getElementById('login-pattern');
            if (inp) { inp.value = ''; inp.dispatchEvent(new Event('input',{bubbles:true})); }
            var prev = document.getElementById('pattern-preview');
            if (prev) prev.textContent = 'No pattern drawn';
            var dots = document.querySelectorAll('.pattern-dot');
            dots.forEach(function(d){ d.classList.remove('active'); });
            return '';
        }
        """,
        Output("login-pattern",    "value",  allow_duplicate=True),
        Input("pattern-clear-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    print("  ✓ Login callbacks registered")