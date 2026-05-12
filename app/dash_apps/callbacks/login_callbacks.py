# app/dash_apps/callbacks/login_callbacks.py
"""
Login Callbacks - Integrated with app/config.py and app/services/auth_service.py
Handles all authentication flows:
  - Password / PIN / Pattern login
  - Password reset
  - Master admin bypass

IMPORTANT: This file does NOT own the society dropdown callback.
That's in shell_callbacks.py which must be registered first.
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


def register_login_callbacks(app):
    """Register all login-related callbacks with the Dash app."""
    
    print("  → Registering login callbacks...")
    
    # ── Authentication Callbacks ───────────────────────────────────────────────
    
    @app.callback(
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
        
        print(f"\n🔐 Password login attempt for: {email}")
        
        society_id = (auth or {}).get("society_id")
        user = authenticate_user(email, password, society_id)
        
        if not user:
            print(f"❌ Login failed for: {email}")
            return no_update, no_update, {
                "type": "error",
                "message": "Invalid email or password"
            }, no_update
        
        print(f"✅ Login successful for: {email}")
        return _build_login_response(user)
    
    @app.callback(
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
        
        print(f"\n🔢 PIN login attempt for: {email}")
        
        society_id = (auth or {}).get("society_id")
        user = authenticate_pin(email, pin, society_id)
        
        if not user:
            print(f"❌ PIN login failed for: {email}")
            return no_update, no_update, {
                "type": "error",
                "message": "Invalid PIN"
            }, no_update
        
        print(f"✅ PIN login successful for: {email}")
        return _build_login_response(user)
    
    @app.callback(
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
        
        print(f"\n🔐 Pattern login attempt for: {email}")
        
        society_id = (auth or {}).get("society_id")
        user = authenticate_pattern(email, pattern, society_id)
        
        if not user:
            print(f"❌ Pattern login failed for: {email}")
            return no_update, no_update, {
                "type": "error",
                "message": "Invalid pattern"
            }, no_update
        
        print(f"✅ Pattern login successful for: {email}")
        return _build_login_response(user)
    
    # ── Password Reset Callbacks ───────────────────────────────────────────────
    
    @app.callback(
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
    
    @app.callback(
        Output("forgot-password-modal", "is_open", allow_duplicate=True),
        Output("reset-password-modal", "is_open"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("send-reset-btn",    "n_clicks"),
        Input("confirm-reset-btn", "n_clicks"),
        Input("close-forgot-modal","n_clicks"),
        Input("close-reset-modal", "n_clicks"),
        State("reset-email-input",     "value"),
        State("reset-token-input",     "value"),
        State("new-password-input",    "value"),
        State("confirm-password-input","value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def handle_reset_flow(send_clicks, confirm_clicks,
                          close_forgot, close_reset,
                          email, token, new_pass, confirm_pass, auth):
        """Handle complete password reset flow."""
        ctx = dash.callback_context

        if not ctx.triggered:
            raise PreventUpdate

        # Guard: Dash fires dynamically-added inputs with n_clicks=0 on injection.
        # A value of 0 means no real click has happened yet — ignore it.
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        # ── Cancel buttons ────────────────────────────────────────────────────
        if trigger_id == "close-forgot-modal":
            return False, no_update, no_update

        if trigger_id == "close-reset-modal":
            return no_update, False, no_update

        # ── Send reset link ───────────────────────────────────────────────────
        if trigger_id == "send-reset-btn":
            if not email:
                return True, no_update, {
                    "type": "error",
                    "message": "Please enter your email address"
                }
            print(f"\n📧 Password reset requested for: {email}")
            society_id = (auth or {}).get("society_id")
            success, message, _ = request_password_reset(email, society_id)
            return False if success else True, no_update, {
                "type": "success" if success else "error",
                "message": message
            }

        # ── Confirm new password ──────────────────────────────────────────────
        if trigger_id == "confirm-reset-btn":
            print(f"\n🔑 Confirming password reset with token")
            if not token:
                return no_update, True, {"type": "error", "message": "Please enter the reset token"}
            if not new_pass or not confirm_pass:
                return no_update, True, {"type": "error", "message": "Please fill in both password fields"}
            if new_pass != confirm_pass:
                return no_update, True, {"type": "error", "message": "Passwords don't match"}

            success, message = reset_password(token, new_pass)
            return no_update, False if success else True, {
                "type": "success" if success else "error",
                "message": message
            }

        raise PreventUpdate

    # ── Pattern Drawing Clientside Callbacks ───────────────────────────────────
    
    # Clientside callback to handle pattern drawing and store result
    app.clientside_callback(
        """
        function(patternValue, n_clicks) {
            // This is triggered when pattern is drawn via JS
            // The actual pattern drawing is handled by pattern.js
            // This just passes through the value
            return window.dash_clientside?.pattern?.getValue ? 
                   window.dash_clientside.pattern.getValue() : 
                   (patternValue || '');
        }
        """,
        Output("login-pattern", "value"),
        Input("login-pattern", "value"),
        prevent_initial_call=True,
    )
    
    # Clear pattern when clear button is clicked
    app.clientside_callback(
        """
        function(n_clicks, current_value) {
            if (!n_clicks) return dash_clientside.no_update;
            // Clear the pattern in the hidden input
            return '';
        }
        """,
        Output("login-pattern", "value", allow_duplicate=True),
        Input("pattern-clear-btn", "n_clicks"),
        State("login-pattern", "value"),
        prevent_initial_call=True,
    )
    
    # ── Master Admin Login ─────────────────────────────────────────────────────
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        State("master-admin-email", "value"),
        State("master-admin-password", "value"),
        prevent_initial_call=True,
    )
    def handle_master_admin_login(n_clicks, email, password):
        """Handle master admin login (bypasses society selection)."""
        if not n_clicks or not email or not password:
            raise PreventUpdate
        
        print(f"\n👑 Master admin login attempt for: {email}")
        
        # Check if this is a master admin
        from app.services.auth_service import authenticate_user
        from database.db_manager import db

        # Verify master admin flag FIRST (fast, no password check)
        result = db._execute(
            "SELECT id FROM users WHERE email = :email AND is_master_admin = true",
            {"email": email},
            fetch_one=True,
        )
        if not result:
            print(f"❌ User {email} is not a master admin")
            return no_update, no_update, {
                "type": "error",
                "message": "Invalid master admin credentials"
            }, no_update

        # Authenticate credentials (society_id=None → queries users with NULL society)
        user = authenticate_user(email, password, society_id=None)

        if not user:
            print(f"❌ Master admin login failed for: {email}")
            return no_update, no_update, {
                "type": "error",
                "message": "Invalid master admin credentials"
            }, no_update
        
        print(f"✅ Master admin login successful for: {email}")
        return _build_login_response(user)

    print("  ✓ Login callbacks registered successfully")


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
    
    # Handle master admin (no society_id)
    if role == "admin" and user.get("society_id") is None:
        redirect_paths["admin"] = "/dashboard/master"
    
    return (
        {
            "user_id": user["user_id"],
            "email": user["email"],
            "role": role,
            "society_id": user.get("society_id"),
            "linked_id": user.get("linked_id"),
            "authenticated": True,
            "token": user["token"],
            "push_subscription": user.get("push_subscription"),
        },
        redirect_paths.get(role, "/"),
        {"type": "success", "message": f"Welcome, {user['email'].split('@')[0]}!"},
        False  # Close login modal
    )
