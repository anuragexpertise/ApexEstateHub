# app/dash_apps/callbacks/login_callbacks.py
"""
Login callbacks — all authentication flows.

Must be registered AFTER shell_callbacks (which owns primary outputs).
Uses allow_duplicate=True on shared outputs (auth-store, url, toast-store).
All passwords verified via werkzeug.security through auth_service.
"""

import logging

import dash
from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from app.services.auth_service import (
    authenticate_user,
    authenticate_pin,
    authenticate_pattern,
    request_password_reset,
    reset_password,
)
from database.db_manager import db

log = logging.getLogger(__name__)

# Role → default redirect path
_REDIRECTS = {
    "admin":     "/dashboard/admin-portal",
    "apartment": "/dashboard/owner-portal",
    "vendor":    "/dashboard/vendor-portal",
    "security":  "/dashboard/pass-evaluation",
}


def _login_response(user: dict) -> tuple:
    """Build the 3-tuple returned by all login callbacks."""
    role      = user["role"]
    is_master = role == "admin" and user.get("society_id") is None
    redirect  = "/dashboard/master" if is_master else _REDIRECTS.get(role, "/dashboard/")
    name      = user["email"].split("@")[0]

    auth_data = {
        "user_id":           user["user_id"],
        "email":             user["email"],
        "role":              role,
        "society_id":        user.get("society_id"),
        "linked_id":         user.get("linked_id"),
        "authenticated":     True,
        "token":             user["token"],
        "push_subscription": user.get("push_subscription"),
    }
    return auth_data, redirect, {"type": "success", "message": f"Welcome, {name}!"}


def register_login_callbacks(app):
    log.info("Registering login callbacks…")

    # ── Password ──────────────────────────────────────────────────────────────

    @app.callback(
        Output("auth-store",    "data",     allow_duplicate=True),
        Output("url",           "pathname", allow_duplicate=True),
        Output("toast-store",   "data",     allow_duplicate=True),
        Input("login-btn",      "n_clicks"),
        State("login-email",    "value"),
        State("login-password", "value"),
        State("auth-store",     "data"),
        prevent_initial_call=True,
    )
    def handle_password_login(n, email, password, auth):
        if not n or not email or not password:
            raise PreventUpdate
        user = authenticate_user(email.strip(), password,
                                 (auth or {}).get("society_id"))
        if not user:
            return no_update, no_update, {
                "type": "error", "message": "Invalid email or password."
            }
        return _login_response(user)

    # ── PIN ───────────────────────────────────────────────────────────────────

    @app.callback(
        Output("auth-store",      "data",     allow_duplicate=True),
        Output("url",             "pathname", allow_duplicate=True),
        Output("toast-store",     "data",     allow_duplicate=True),
        Input("login-pin-btn",    "n_clicks"),
        State("login-email-pin",  "value"),
        State("login-pin",        "value"),
        State("auth-store",       "data"),
        prevent_initial_call=True,
    )
    def handle_pin_login(n, email, pin, auth):
        if not n or not email or not pin:
            raise PreventUpdate
        user = authenticate_pin(email.strip(), pin,
                                (auth or {}).get("society_id"))
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid PIN."}
        return _login_response(user)

    # ── Pattern ───────────────────────────────────────────────────────────────

    @app.callback(
        Output("auth-store",         "data",     allow_duplicate=True),
        Output("url",                "pathname", allow_duplicate=True),
        Output("toast-store",        "data",     allow_duplicate=True),
        Input("login-pattern-btn",   "n_clicks"),
        State("login-email-pattern", "value"),
        State("login-pattern",       "value"),
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def handle_pattern_login(n, email, pattern, auth):
        if not n or not email or not pattern:
            raise PreventUpdate
        user = authenticate_pattern(email.strip(), pattern,
                                    (auth or {}).get("society_id"))
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid pattern."}
        return _login_response(user)

    # ── Master admin ──────────────────────────────────────────────────────────

    @app.callback(
        Output("auth-store",            "data",     allow_duplicate=True),
        Output("url",                   "pathname", allow_duplicate=True),
        Output("toast-store",           "data",     allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        State("master-admin-email",     "value"),
        State("master-admin-password",  "value"),
        prevent_initial_call=True,
    )
    def handle_master_login(n, email, password):
        if not n or not email or not password:
            raise PreventUpdate
        # Verify the is_master_admin flag exists first (cheap guard)
        try:
            row = db._execute(
                "SELECT id FROM users WHERE email = :e AND is_master_admin = TRUE",
                {"e": email.strip()},
                fetch_one=True,
            )
        except Exception as exc:
            log.error("master DB check: %s", exc)
            return no_update, no_update, {"type": "error", "message": "Database error."}

        if not row:
            return no_update, no_update, {
                "type": "error", "message": "Not a master admin account."
            }

        user = authenticate_user(email.strip(), password, society_id=None)
        if not user:
            return no_update, no_update, {
                "type": "error", "message": "Invalid master admin credentials."
            }
        return _login_response(user)

    # ── Forgot password modal toggle ──────────────────────────────────────────

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

    # ── Password reset flow ───────────────────────────────────────────────────

    @app.callback(
        Output("forgot-password-modal", "is_open",  allow_duplicate=True),
        Output("reset-password-modal",  "is_open"),
        Output("toast-store",           "data",     allow_duplicate=True),
        Input("send-reset-btn",         "n_clicks"),
        Input("confirm-reset-btn",      "n_clicks"),
        Input("close-forgot-modal",     "n_clicks"),
        Input("close-reset-modal",      "n_clicks"),
        State("reset-email-input",      "value"),
        State("reset-token-input",      "value"),
        State("new-password-input",     "value"),
        State("confirm-password-input", "value"),
        State("auth-store",             "data"),
        prevent_initial_call=True,
    )
    def handle_reset_flow(send_n, confirm_n, close_f, close_r,
                          email, token, new_pass, confirm_pass, auth):
        triggered = dash.callback_context.triggered
        if not triggered or not triggered[0]["value"]:
            raise PreventUpdate
        trigger = triggered[0]["prop_id"].split(".")[0]

        if trigger == "close-forgot-modal":
            return False, no_update, no_update
        if trigger == "close-reset-modal":
            return no_update, False, no_update

        if trigger == "send-reset-btn":
            if not email:
                return True, no_update, {"type": "error", "message": "Enter your email."}
            sid = (auth or {}).get("society_id")
            ok, msg, _ = request_password_reset(email.strip(), sid)
            return (False if ok else True), no_update, {
                "type": "success" if ok else "error", "message": msg
            }

        if trigger == "confirm-reset-btn":
            if not token:
                return no_update, True, {"type": "error", "message": "Enter the reset token."}
            if not new_pass or not confirm_pass:
                return no_update, True, {"type": "error", "message": "Fill both password fields."}
            if new_pass != confirm_pass:
                return no_update, True, {"type": "error", "message": "Passwords don't match."}
            ok, msg = reset_password(token.strip(), new_pass)
            return no_update, (False if ok else True), {
                "type": "success" if ok else "error", "message": msg
            }

        raise PreventUpdate

    # ── Pattern clear ─────────────────────────────────────────────────────────

    @app.callback(
        Output("login-pattern",    "value"),
        Input("pattern-clear-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def clear_pattern(n):
        if not n:
            raise PreventUpdate
        return ""

    log.info("Login callbacks registered ✓")
