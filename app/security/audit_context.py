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
authentication time and can't be edited by the client. get_current_linked_id()
extends this to apartment_id/vendor_id/security_id (users.linked_id) for
ownership checks — see its docstring below.
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


def get_current_society_id() -> int | None:
    """
    Return the authenticated user's society_id from the Flask-Login session.

    Never trust client-side auth-store for tenant scoping on a write —
    society_id there can be edited via devtools the same as role can, and
    an INSERT/UPDATE that scopes itself off that value can be redirected
    into a different tenant's data by an otherwise-legitimate admin.
    """
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return getattr(current_user, 'society_id', None)
    except Exception:
        pass
    return None


def get_current_linked_id() -> int | None:
    """
    Return the authenticated user's linked_id (apartments.id / vendors.id /
    security_staff.id — whichever applies to their role; None for
    admin/master) from the Flask-Login session.

    role and society_id alone can't answer "is this the caller's own
    record" — that's what most ownership checks actually need (an owner
    approving their own gate alert, a vendor bidding on their own concern
    invite, security clocking their own shift). Those checks were
    resolving apartment_id/vendor_id/security_id from the client-editable
    auth-store, the same trust gap as role/society_id before
    get_current_user_role()/get_current_society_id() existed — this
    closes it the same way, for the same reason: never trust client-side
    auth-store for a check that gates a write or a cross-user read.
    """
    try:
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            return getattr(current_user, 'linked_id', None)
    except Exception:
        pass
    return None
