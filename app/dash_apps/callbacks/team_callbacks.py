# app/dash_apps/callbacks/team_callbacks.py
"""
Callbacks for Admin portal -> Team Logins (create / disable / enable / reset the Accountant, Supervisor, Staff and
Auditor logins). Admin only; the society is ALWAYS the server-side Flask-Login session's, never a browser value, and
team_service re-checks that the actor's society matches. Creating a login confers powers, so the caller must also
hold `roles.manage`.
"""
import secrets

import dash_bootstrap_components as dbc
from dash import Input, Output, State, ctx, no_update

from app.dash_apps.pages import team_page as tp
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.authorization import Cap
from app.security.guards import require_session
from app.security.service_guard import blocks, check
from app.services import team_service as ts

P = tp.P
_TOAST = Output(f"{P}-toast", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _ctx():
    """((society_id, user_id), None) for an authenticated admin holding `roles.manage` in their OWN society."""
    if get_current_user_role() != "admin":
        return None, _alert("Admin role required.", "danger")
    sid = get_current_society_id()
    if not sid:
        return None, _alert("Society not resolved.", "danger")
    if blocks(check(Cap.ROLES_MANAGE, "role_assignment", target_society_id=int(sid))):
        return None, _alert("You don't have permission to do that.", "danger")
    return (int(sid), get_current_user_id()), None


def _temp_password() -> str:
    """12 url-safe characters, always long enough for the password policy."""
    return secrets.token_urlsafe(9)


def register_team_callbacks(app):

    @app.callback(Output(f"{P}-role-hint", "children"), Input(f"{P}-role", "value"))
    @require_session
    def tm_role_hint(role):
        return ts.ROLE_BLURB.get(role, "")

    @app.callback(Output(f"{P}-password", "value"), Input(f"{P}-gen", "n_clicks"), prevent_initial_call=True)
    @require_session
    def tm_generate(n):
        return _temp_password() if n else no_update

    @app.callback(_TOAST, Output(f"{P}-body", "children", allow_duplicate=True),
                  Output(f"{P}-member", "options", allow_duplicate=True),
                  Output(f"{P}-name", "value"), Output(f"{P}-email", "value"), Output(f"{P}-password", "value", allow_duplicate=True),
                  Input(f"{P}-create", "n_clicks"),
                  State(f"{P}-role", "value"), State(f"{P}-name", "value"), State(f"{P}-email", "value"),
                  State(f"{P}-password", "value"), prevent_initial_call=True)
    @require_session
    def tm_create(n, role, name, email, password):
        if not n:
            return (no_update,) * 6
        c, err = _ctx()
        if err:
            return (err,) + (no_update,) * 5
        sid, uid = c
        try:
            ok, msg = ts.create_login(uid, "admin", sid, role, name, email, password, actor_society_id=sid)
        except PermissionError as exc:
            return (_alert(str(exc), "danger"),) + (no_update,) * 5
        except Exception as exc:         # never a blank page
            return (_alert(f"Could not save: {exc}", "danger"),) + (no_update,) * 5
        if not ok:
            return (_alert(msg, "warning"),) + (no_update,) * 5
        # success: refresh the list and clear the form (the temporary password is not kept on screen)
        return _alert(msg, "success"), tp.team_table(sid), tp.member_options(sid), "", "", ""

    @app.callback(_TOAST, Output(f"{P}-body", "children", allow_duplicate=True),
                  Output(f"{P}-member", "options", allow_duplicate=True), Output(f"{P}-newpw", "value"),
                  Input(f"{P}-reset", "n_clicks"), Input(f"{P}-disable", "n_clicks"), Input(f"{P}-enable", "n_clicks"),
                  State(f"{P}-member", "value"), State(f"{P}-newpw", "value"), prevent_initial_call=True)
    @require_session
    def tm_manage(n_reset, n_disable, n_enable, member, new_pw):
        trig = ctx.triggered_id
        if trig not in (f"{P}-reset", f"{P}-disable", f"{P}-enable") or not (n_reset or n_disable or n_enable):
            return (no_update,) * 4
        c, err = _ctx()
        if err:
            return (err,) + (no_update,) * 3
        sid, uid = c
        if not member:
            return (_alert("Choose a login first.", "warning"),) + (no_update,) * 3
        if trig == f"{P}-disable" and member == uid:
            return (_alert("You cannot disable your own login.", "warning"),) + (no_update,) * 3
        try:
            if trig == f"{P}-reset":
                ok, msg = ts.reset_password(uid, "admin", sid, member, new_pw, actor_society_id=sid)
            else:
                ok, msg = ts.set_active(uid, "admin", sid, member, trig == f"{P}-enable", actor_society_id=sid)
        except PermissionError as exc:
            return (_alert(str(exc), "danger"),) + (no_update,) * 3
        except Exception as exc:
            return (_alert(f"Could not save: {exc}", "danger"),) + (no_update,) * 3
        if not ok:
            return (_alert(msg, "warning"),) + (no_update,) * 3
        return _alert(msg, "success"), tp.team_table(sid), tp.member_options(sid), ""
