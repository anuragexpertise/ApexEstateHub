# app/dash_apps/callbacks/account_callbacks.py
"""
Account Settings — self-service "Change Password" (new 2026-08).

Previously there was no way for a logged-in user of any role (master,
admin, apartment owner, vendor, security) to change their own password —
the "Settings" tab in every portal is chart-of-accounts / charge-rate
configuration, unrelated to the user's own login. The only password-
change path was the pre-login "Forgot Password" flow.

This adds an "Account Settings" entry to the sidebar (next to Logout,
visible for every role) that opens a small modal: current password + new
password + confirm. The submit callback identifies the user being changed
via app.security.audit_context.get_current_user_id() — the server-side
Flask-Login session — never from auth-store, so a client can't edit
auth-store.user_id to change someone else's password.

Requires in app_shell.py:
  - a "Account Settings" html.Button with id="account-settings-btn" in
    the sidebar (next to sb-logout-btn)
  - _account_settings_modal() included once in shell_layout()
"""
from __future__ import annotations

from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from app.security.audit_context import get_current_user_id


def register_account_callbacks(app):
    print("  → Registering account callbacks…")

    # ── 1. Open / close the modal ───────────────────────────────────
    @app.callback(
        Output("account-settings-modal", "is_open"),
        Output("current-password-input", "value"),
        Output("new-password-input-acct", "value"),
        Output("confirm-password-input-acct", "value"),
        Input("account-settings-btn", "n_clicks"),
        Input("close-account-settings-modal", "n_clicks"),
        State("account-settings-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_account_settings_modal(open_n, close_n, is_open):
        if not open_n and not close_n:
            raise PreventUpdate
        # Always clear the fields on open or close — never leave a
        # previously-typed password sitting in the DOM.
        return (not is_open), "", "", ""

    # ── 2. Submit the change ────────────────────────────────────────
    @app.callback(
        Output("account-settings-modal", "is_open", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("change-password-btn", "n_clicks"),
        State("current-password-input", "value"),
        State("new-password-input-acct", "value"),
        State("confirm-password-input-acct", "value"),
        prevent_initial_call=True,
    )
    def handle_change_password(n, current_pw, new_pw, confirm_pw):
        if not n:
            raise PreventUpdate

        # SECURITY: user_id comes from the server-side Flask-Login
        # session, not from auth-store — auth-store is client-editable
        # and must never decide *whose* password gets changed.
        user_id = get_current_user_id()
        if not user_id:
            return no_update, {"type": "error", "message": "Your session has expired — please log in again."}

        if not new_pw or new_pw != confirm_pw:
            return no_update, {"type": "error", "message": "New password and confirmation don't match."}

        from app.services.auth_service import change_password
        ok, msg = change_password(user_id, current_pw or "", new_pw)

        return (not ok), {"type": "success" if ok else "error", "message": msg}

    print("  ✓ Account callbacks registered")
