# app/dash_apps/callbacks/committee_callbacks.py
"""
Callbacks for Society governance -> Managing Committee (Admin portal). Admin only; the society is ALWAYS taken from
the server-side Flask-Login session, never from a browser value, and committee_service re-checks that the actor's
society matches. Owners get a read-only tab with no callbacks at all.
"""
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html, no_update

from app.dash_apps.pages import committee_page as cp
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.authorization import Cap
from app.security.guards import require_session
from app.security.service_guard import blocks, check
from app.services import committee_service as cs

P = cp.P
_TOAST = Output(f"{P}-toast", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _ctx():
    """((society_id, user_id), None) for an authenticated admin who holds `roles.manage` in their OWN society, else
    (None, alert). Seating an office-bearer confers roles, so it needs the same capability as granting one."""
    if get_current_user_role() != "admin":
        return None, _alert("Admin role required.", "danger")
    sid = get_current_society_id()
    if not sid:
        return None, _alert("Society not resolved.", "danger")
    if blocks(check(Cap.ROLES_MANAGE, "role_assignment", target_society_id=int(sid))):
        return None, _alert("You don't have permission to do that.", "danger")
    return (int(sid), get_current_user_id()), None


def hint_for(flat: dict):
    """One line telling the admin whether this flat may hold office today."""
    if flat.get("ineligible_stand"):
        return html.Span([html.I(className="fas fa-ban me-1"),
                          f"Flat {flat['flat_number']} has arrears ({cp._money(flat.get('dues_outstanding'))}) and cannot "
                          "hold office until they are cleared (bye-law 7)."], style={"color": "#b02a37"})
    return html.Span([html.I(className="fas fa-check-circle me-1"),
                      f"Flat {flat['flat_number']} is in good standing today."], style={"color": "#1b7a3d"})


def register_committee_callbacks(app):

    @app.callback(Output(f"{P}-user", "options"), Output(f"{P}-user", "value"), Output(f"{P}-name", "value"),
                  Output(f"{P}-hint", "children"), Input(f"{P}-flat", "value"), prevent_initial_call=True)
    @require_session
    def mc_pick_flat(apartment_id):
        c, err = _ctx()
        if err or not apartment_id:
            return [], None, "", None
        flat = cs.flat_detail(c[0], apartment_id)
        if not flat:                      # not a flat of THIS society: show nothing rather than leak anything
            return [], None, "", None
        users = flat["users"]
        options = [{"label": f"{u['name']} ({u['email']})", "value": u["id"]} for u in users]
        first = users[0] if users else None
        name = (first["name"] if first else flat.get("owner_name")) or ""
        return options, (first["id"] if first else None), name, hint_for(flat)

    @app.callback(Output(f"{P}-name", "value", allow_duplicate=True), Input(f"{P}-user", "value"),
                  State(f"{P}-flat", "value"), prevent_initial_call=True)
    @require_session
    def mc_pick_user(user_id, apartment_id):
        c, err = _ctx()
        if err or not user_id or not apartment_id:
            return no_update
        flat = cs.flat_detail(c[0], apartment_id)
        for u in (flat or {}).get("users", []):
            if u["id"] == user_id:
                return u["name"]
        return no_update

    @app.callback(_TOAST, Output(f"{P}-body", "children", allow_duplicate=True),
                  Output(f"{P}-end-office", "options", allow_duplicate=True),
                  Input(f"{P}-appoint-btn", "n_clicks"),
                  State(f"{P}-office", "value"), State(f"{P}-flat", "value"), State(f"{P}-user", "value"),
                  State(f"{P}-name", "value"), State(f"{P}-start", "date"), State(f"{P}-term-end", "date"),
                  State(f"{P}-ref", "value"), prevent_initial_call=True)
    @require_session
    def mc_appoint(n, office, apartment_id, user_id, name, start, term_end, ref):
        if not n:
            return no_update, no_update, no_update
        c, err = _ctx()
        if err:
            return err, no_update, no_update
        sid, uid = c
        if not apartment_id:
            return _alert("Choose the flat the office-bearer represents.", "warning"), no_update, no_update
        try:
            ok, msg = cs.appoint(uid, "admin", sid, apartment_id, office, name, user_id, start, term_end, ref,
                                 actor_society_id=sid)
        except PermissionError as exc:
            return _alert(str(exc), "danger"), no_update, no_update
        except Exception as exc:     # never a blank page
            return _alert(f"Could not save: {exc}", "danger"), no_update, no_update
        if not ok:
            return _alert(msg, "warning"), no_update, no_update
        return _alert(msg, "success"), cp.committee_body(sid), cp.end_options(sid)

    @app.callback(_TOAST, Output(f"{P}-body", "children", allow_duplicate=True),
                  Output(f"{P}-end-office", "options", allow_duplicate=True),
                  Output(f"{P}-end-office", "value"), Output(f"{P}-end-reason", "value"),
                  Input(f"{P}-end-btn", "n_clicks"),
                  State(f"{P}-end-office", "value"), State(f"{P}-end-reason", "value"), prevent_initial_call=True)
    @require_session
    def mc_end_office(n, office_id, reason):
        if not n:
            return (no_update,) * 5
        c, err = _ctx()
        if err:
            return (err,) + (no_update,) * 4
        sid, uid = c
        try:
            ok, msg = cs.end_office(uid, "admin", sid, office_id, reason, actor_society_id=sid)
        except PermissionError as exc:
            return (_alert(str(exc), "danger"),) + (no_update,) * 4
        except Exception as exc:
            return (_alert(f"Could not save: {exc}", "danger"),) + (no_update,) * 4
        if not ok:
            return (_alert(msg, "warning"),) + (no_update,) * 4
        return _alert(msg, "success"), cp.committee_body(sid), cp.end_options(sid), None, ""
