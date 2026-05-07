# app/dash_apps/callbacks/login_callbacks.py
"""
Login Callbacks - Integrated with app/config.py and app/services/auth_service.py
Handles all authentication flows:
  - Password / PIN / Pattern login
  - Password reset
  - Master admin bypass
"""

import dash
from dash import Input, Output, State, callback, no_update, html
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

# Import auth service
from app.services.auth_service import (
    authenticate_user,
    authenticate_pin,
    authenticate_pattern,
    request_password_reset,
    reset_password
)

callback = dash.callback


# ── Authentication Callbacks ───────────────────────────────────────────────

@callback(
    Output("auth-store", "data"),
    Output("url", "pathname"),
    Output("toast-store", "data"),
    Output("login-modal", "is_open"),
    Input("login-btn", "n_clicks"),
    State("login-email", "value"),
    State("login-password", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def handle_password_login(n, email, password, auth):
    """Handle email/password login."""
    if not n or not email or not password:
        raise PreventUpdate
    
    society_id = (auth or {}).get("society_id")
    user = authenticate_user(email, password, society_id)
    
    if not user:
        return no_update, no_update, {
            "type": "error",
            "message": "Invalid email or password"
        }, no_update
    
    return _build_login_response(user)


@callback(
    Output("auth-store", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("toast-store", "data", allow_duplicate=True),
    Output("login-modal", "is_open", allow_duplicate=True),
    Input("login-pin-btn", "n_clicks"),
    State("login-email-pin", "value"),
    State("login-pin", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def handle_pin_login(n, email, pin, auth):
    """Handle PIN login."""
    if not n or not email or not pin:
        raise PreventUpdate
    
    society_id = (auth or {}).get("society_id")
    user = authenticate_pin(email, pin, society_id)
    
    if not user:
        return no_update, no_update, {
            "type": "error",
            "message": "Invalid PIN"
        }, no_update
    
    return _build_login_response(user)


@callback(
    Output("auth-store", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("toast-store", "data", allow_duplicate=True),
    Output("login-modal", "is_open", allow_duplicate=True),
    Input("login-pattern-btn", "n_clicks"),
    State("login-email-pattern", "value"),
    State("login-pattern", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def handle_pattern_login(n, email, pattern, auth):
    """Handle 9-dot pattern login."""
    if not n or not email or not pattern:
        raise PreventUpdate
    
    society_id = (auth or {}).get("society_id")
    user = authenticate_pattern(email, pattern, society_id)
    
    if not user:
        return no_update, no_update, {
            "type": "error",
            "message": "Invalid pattern"
        }, no_update
    
    return _build_login_response(user)


# ── Password Reset Callbacks ───────────────────────────────────────────────

@callback(
    Output("forgot-password-modal", "is_open"),
    Output("reset-email-input", "value"),
    Input("forgot-password-link", "n_clicks"),
    State("login-email", "value"),
    State("forgot-password-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_forgot_modal(n, email, is_open):
    """Toggle forgot password modal."""
    if not n:
        raise PreventUpdate
    return not is_open, email or ""


@callback(
    Output("forgot-password-modal", "is_open"),
    Output("reset-password-modal", "is_open"),
    Output("toast-store", "data"),
    Input("send-reset-btn", "n_clicks"),
    Input("confirm-reset-btn", "n_clicks"),
    State("reset-email-input", "value"),
    State("reset-token-input", "value"),
    State("new-password-input", "value"),
    State("confirm-password-input", "value"),
    State("auth-store", "data"),
    prevent_initial_call=True,
)
def handle_reset_flow(send_clicks, confirm_clicks, email, token, new_pass, confirm_pass, auth):
    """Handle complete password reset flow."""
    ctx = dash.ctx.triggered_id
    
    if ctx == "send-reset-btn":
        society_id = (auth or {}).get("society_id")
        success, message, _ = request_password_reset(email, society_id)
        return False if success else True, no_update, {
            "type": "success" if success else "error",
            "message": message
        }
    
    elif ctx == "confirm-reset-btn":
        if new_pass != confirm_pass:
            return no_update, True, {"type": "error", "message": "Passwords don't match"}
        
        success, message = reset_password(token, new_pass)
        return no_update, False if success else True, {
            "type": "success" if success else "error",
            "message": message
        }
    
    raise PreventUpdate


# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_login_response(user):
    """Build standardized login success response."""
    role = user["role"]
    
    redirect_paths = {
        "admin": "/dashboard/admin-portal",
        "apartment": "/dashboard/owner-portal",
        "vendor": "/dashboard/vendor-portal",
        "security": "/dashboard/pass-evaluation",
    }
    
    return (
        {
            "user_id": user["user_id"],
            "email": user["email"],
            "role": role,
            "society_id": user["society_id"],
            "linked_id": user.get("linked_id"),
            "authenticated": True,
            "token": user["token"],
            "push_subscription": user.get("push_subscription"),
        },
        redirect_paths.get(role, "/"),
        {"type": "success", "message": f"Welcome, {user['email'].split('@')[0]}!"},
        False  # Close login modal
    )