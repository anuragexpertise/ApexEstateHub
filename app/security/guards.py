# app/security/guards.py
"""
Server-session guard for Dash callbacks.

Context: every @app.callback in this app is multiplexed through Dash's own
endpoint (/dashboard/_dash-update-component). Nothing at the Flask level
gates that endpoint, so a request sent directly to it — no browser, no
session cookie — reaches the callback body exactly like a normal click
would. Callbacks that resolve role/society_id/user_id from the
client-editable `auth-store` dcc.Store (a plain localStorage value) trust
whatever that request body says, session or no session.

`app/security/audit_context.py` already resolves identity from the real,
signed Flask-Login session instead of auth-store — but that only protects
a call site that remembers to *use* get_current_user_role() /
get_current_user_id() / get_current_society_id() / get_current_linked_id()
in the first place, and only for the specific value it checks. It's easy
to migrate the role check in a callback and forget the society_id filter
three lines down, or migrate a callback and leave the next one as-is.

@require_session is a coarser, cheaper backstop: it runs first, before any
of that per-field logic, and refuses to run the callback body at all if
there's no valid server session — regardless of what auth-store claims.
It does NOT replace the get_current_*() checks inside the callback (those
still decide *what* the authenticated user is allowed to do); it just
makes sure there IS an authenticated user before any of that runs.

Usage — apply directly under @app.callback, above the function body:

    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("channel-create-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def create_channel(n_clicks, auth):
        ...

Every @app.callback in the codebase should carry this EXCEPT the small,
explicit set of callbacks that must legitimately run before a session
exists — see PUBLIC_CALLBACKS in scripts/check_callback_guards.py, which
enforces that every other callback has it.
"""

from __future__ import annotations

from functools import wraps

from dash.exceptions import PreventUpdate

from app.security.audit_context import get_current_user_id


def require_session(f):
    """
    Wrap a Dash callback body. Raises PreventUpdate — a silent no-op, no
    Output is written — if there is no valid Flask-Login session on the
    current request.

    PreventUpdate (rather than returning an error toast) is deliberate:
    a request with no session shouldn't get a distinguishable response
    that confirms "the endpoint exists and understood you", it should
    behave like the callback was never wired at all.
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        if get_current_user_id() is None:
            raise PreventUpdate
        return f(*args, **kwargs)
    return wrapped
