# app/security/audit_context.py
"""
Server-side actor resolution for audit fields.

`auth-store` is a Dash dcc.Store — it lives in the browser's localStorage
and can be edited via devtools. It's fine for portal routing / UI scoping,
but it must NEVER be trusted as the source of `created_by`, `updated_by`,
`confirmed_by`, or role-based permission checks, since anyone can forge it
to impersonate another user in the audit trail or escalate privileges.

This module resolves the acting user and role from the server-side Flask-Login
session instead, which is set by `login_user()` in login_callbacks.py at
authentication time and can't be edited by the client.
"""

from __future__ import annotations


def get_current_user_id() -> int | None:
    """
    Return the authenticated user's id from the Flask-Login session for
    the current request, or None if there isn't one (not logged in, or
    the login_user()/session wiring isn't active in this environment).

    Callers should treat None as "server identity unavailable" and decide
    explicitly whether to fall back to a client-supplied value.
    """
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return int(current_user.get_id())
    except Exception:
        # No request context, flask_login not initialised, etc.
        pass
    return None


def get_current_user_role() -> str | None:
    """
    Return the authenticated user's role from the Flask-Login session.
    Never trust client-side auth-store for role-based permission checks.
    """
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return getattr(current_user, 'role', None)
    except Exception:
        pass
    return None
