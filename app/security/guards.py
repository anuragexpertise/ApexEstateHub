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

from app.security.audit_context import (
    get_current_society_id,
    get_current_user_id,
    get_current_user_role,
)
from app.security.setup_guard import society_setup_incomplete

# ── Setup-completion gate (callback level) ────────────────────────────────
# The page router already refuses to render a portal for a society whose Setup
# Wizard is unfinished (shell_callbacks.py), but a request sent straight to
# /dashboard/_dash-update-component skips the router. So require_session also
# refuses to run a callback body for a signed-in, non-master user whose society
# has not finished setup — EXCEPT the callbacks the wizard itself needs, which
# must work while setup is incomplete:
#   * whole modules: the wizard, the shell/router, login, account (compulsory
#     password change) and the agreement shown right after the wizard;
#   * single functions, listed by name below (the wizard's logo/photo upload);
#   * anything marked with @allow_during_setup (either side of @require_session).
_SETUP_EXEMPT_MODULES = frozenset({
    "setup_wizard_callbacks",
    "shell_callbacks",
    "login_callbacks",
    "account_callbacks",
    "agreement_callbacks",
    "onboarding_callbacks",     # the Onboarding Hub is what a not-yet-active society uses; it authorises each action itself
    "privacy_callbacks",
})
_SETUP_EXEMPT_FUNCTIONS = frozenset({
    ("drilldown_callbacks", "handle_image_upload"),
})
_SETUP_DONE: set = set()      # a society that finished setup never goes back, so cache only "done"


def allow_during_setup(f):
    """Mark a callback as usable before the society has finished the Setup Wizard."""
    f._allow_during_setup = True
    return f


def _setup_exempt(f, wrapped) -> bool:
    if getattr(f, "_allow_during_setup", False) or getattr(wrapped, "_allow_during_setup", False):
        return True
    module = (getattr(f, "__module__", "") or "").rsplit(".", 1)[-1]
    return module in _SETUP_EXEMPT_MODULES or (module, getattr(f, "__name__", "")) in _SETUP_EXEMPT_FUNCTIONS


def _setup_blocks_callback() -> bool:
    """True when the signed-in user belongs to a society whose setup is unfinished."""
    if get_current_user_role() in (None, "master"):
        return False
    sid = get_current_society_id()
    if not sid or sid in _SETUP_DONE:
        return False
    if society_setup_incomplete(sid):      # fails closed: a database error raises and the callback does not run
        return True
    _SETUP_DONE.add(sid)
    return False


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
        if not _setup_exempt(f, wrapped) and _setup_blocks_callback():
            raise PreventUpdate
        return f(*args, **kwargs)
    return wrapped
