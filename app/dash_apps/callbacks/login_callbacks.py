# app/dash_apps/callbacks/login_callbacks.py
"""
Login Callbacks — password / PIN / pattern authentication + password reset.
"""

import dash
from dash import Input, Output, State, no_update, html
from dash.exceptions import PreventUpdate

from app.services.auth_service import authenticate_user


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    from database.db_manager import db
    return db


def _build_auth_store(user: dict) -> dict:
    return {
        "user_id":       user.get("user_id") or user.get("id"),
        "email":         user.get("email", ""),
        "role":          user.get("role", "admin"),
        "society_id":    user.get("society_id"),
        "linked_id":     user.get("linked_id"),
        # Portal-scoping fields — loaders use these to filter data
        "apartment_id":  user.get("apartment_id") or (
                             user.get("linked_id") if user.get("role") == "apartment" else None),
        "vendor_id":     user.get("vendor_id") or (
                             user.get("linked_id") if user.get("role") == "vendor" else None),
        "authenticated": True,
        "token":         user.get("token", ""),
    }


def _redirect(role: str, society_id) -> str:
    """Default landing URL for each role."""
    if role == "admin" and society_id is None:
        return "/dashboard/master"
    paths = {
        "admin":     "/dashboard/admin-portal",
        "apartment": "/dashboard/owner-portal",
        "vendor":    "/dashboard/vendor-portal",
        "security":  "/dashboard/pass-evaluation",
    }
    return paths.get(role, "/dashboard/admin-portal")


def _login_response(user: dict):
    """Tuple returned by every successful login callback."""
    role       = user.get("role", "admin")
    society_id = user.get("society_id")
    name       = user.get("email", "").split("@")[0]
    return (
        _build_auth_store(user),                                # auth-store
        _redirect(role, society_id),                            # url.pathname
        {"type": "success", "message": f"Welcome, {name}!"},   # toast-store
        False,                                                  # login-modal.is_open
    )


def _login_error(message: str):
    """Tuple returned by every failed login callback."""
    return no_update, no_update, {"type": "error", "message": message}, no_update


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

def register_login_callbacks(app):
    print("  → Registering login callbacks…")

    # ── 1. PASSWORD LOGIN ─────────────────────────────────────────────────────
    # allow_duplicate=True because shell_callbacks also writes auth-store
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
        user = authenticate_user(email.strip(), password, society_id)
        if not user:
            print(f"❌ Password login failed: {email}")
            return _login_error("Invalid email or password")
        print(f"✅ Password login success: {email}")
        return _login_response(user)

    # ── 2. PIN LOGIN ──────────────────────────────────────────────────────────
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
        # authenticate_user accepts a method kwarg so auth_service can branch
        user = authenticate_user(email.strip(), pin, society_id, method="pin")
        if not user:
            print(f"❌ PIN login failed: {email}")
            return _login_error("Invalid PIN — please try again")
        print(f"✅ PIN login success: {email}")
        return _login_response(user)

    # ── 3. PATTERN LOGIN ──────────────────────────────────────────────────────
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
        user = authenticate_user(email.strip(), pattern, society_id, method="pattern")
        if not user:
            print(f"❌ Pattern login failed: {email}")
            return _login_error("Pattern not recognised — please try again")
        print(f"✅ Pattern login success: {email}")
        return _login_response(user)

    # ── 4. MASTER ADMIN LOGIN ─────────────────────────────────────────────────
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

        # Authenticate without a society_id
        user = authenticate_user(email.strip(), password, society_id=None)
        if not user or user.get("role") != "admin":
            return _login_error("Invalid master admin credentials")

        # Confirm the is_master_admin flag in the DB
        try:
            row = _db()._execute(
                "SELECT id FROM users WHERE email = %s AND is_master_admin = TRUE",
                (email.strip(),),
                fetch_one=True,
            )
        except Exception as exc:
            print(f"❌ Master admin DB check failed: {exc}")
            return _login_error("Database error during master admin check")

        if not row:
            print(f"❌ {email} is not flagged as master admin")
            return _login_error("Not authorised as master admin")

        # Override society_id to None so routing lands on master portal
        user["society_id"] = None
        print(f"✅ Master admin login success: {email}")
        return _login_response(user)

    # ── 5. FORGOT PASSWORD — OPEN MODAL ──────────────────────────────────────
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

    # ── 6. FORGOT PASSWORD — SEND RESET / CONFIRM NEW PASSWORD ───────────────
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
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]

        if trigger == "send-reset-btn":
            if not email:
                return no_update, no_update, \
                       {"type": "error", "message": "Please enter your email address"}
            print(f"\n📧 Password reset requested for: {email}")
            society_id = (auth or {}).get("society_id")
            # Delegate to auth_service if it provides this helper,
            # otherwise handle inline
            try:
                from app.services.auth_service import request_password_reset
                ok, msg, _ = request_password_reset(email.strip(), society_id)
            except ImportError:
                # Minimal inline fallback — generate token and email
                ok, msg = _inline_request_reset(email.strip(), society_id)
            return (not ok), no_update, {"type": "success" if ok else "error", "message": msg}

        if trigger == "confirm-reset-btn":
            if not token or not new_pass:
                return no_update, no_update, \
                       {"type": "error", "message": "Please fill in all fields"}
            if new_pass != confirm_pass:
                return no_update, no_update, \
                       {"type": "error", "message": "Passwords do not match"}
            print("\n🔑 Confirming password reset")
            try:
                from app.services.auth_service import reset_password
                ok, msg = reset_password(token.strip(), new_pass)
            except ImportError:
                ok, msg = _inline_reset_password(token.strip(), new_pass)
            return no_update, (not ok), {"type": "success" if ok else "error", "message": msg}

        raise PreventUpdate

    # ── 7. PATTERN CLEAR BUTTON ───────────────────────────────────────────────
    # Simple clientside: clear the hidden pattern input when user clicks Clear
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


# ─────────────────────────────────────────────────────────────────────────────
# INLINE RESET FALLBACKS (used when auth_service lacks these helpers)
# ─────────────────────────────────────────────────────────────────────────────

def _inline_request_reset(email: str, society_id) -> tuple[bool, str]:
    """
    Minimal password-reset request: generate a token, store it in the DB,
    and log it (email delivery must be wired separately).
    """
    import secrets, hashlib
    from datetime import datetime, timedelta
    try:
        token  = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(hours=2)
        from database.db_manager import db
        q = (
            "UPDATE users SET reset_token = %s, reset_token_expires = %s "
            "WHERE email = %s"
        )
        params = (hashlib.sha256(token.encode()).hexdigest(), expiry, email)
        if society_id:
            q += " AND society_id = %s"
            params += (society_id,)
        db._execute(q, params)
        # In production: send token via email here
        print(f"🔑 Reset token generated for {email}: {token}")
        return True, "If that email exists, a reset link has been sent."
    except Exception as exc:
        print(f"❌ _inline_request_reset error: {exc}")
        return False, "Could not initiate password reset. Please try again."


def _inline_reset_password(token: str, new_password: str) -> tuple[bool, str]:
    """Minimal password reset: verify token and update hash."""
    import hashlib
    from datetime import datetime
    from werkzeug.security import generate_password_hash
    try:
        from database.db_manager import db
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        row = db._execute(
            "SELECT id, reset_token_expires FROM users "
            "WHERE reset_token = %s",
            (token_hash,),
            fetch_one=True,
        )
        if not row:
            return False, "Invalid or expired reset token."
        if row.get("reset_token_expires") and row["reset_token_expires"] < datetime.utcnow():
            return False, "Reset token has expired. Please request a new one."
        db._execute(
            "UPDATE users SET password_hash = %s, reset_token = NULL, "
            "reset_token_expires = NULL WHERE id = %s",
            (generate_password_hash(new_password), row["id"]),
        )
        return True, "Password updated successfully. You can now log in."
    except Exception as exc:
        print(f"❌ _inline_reset_password error: {exc}")
        return False, "Could not reset password. Please try again."
