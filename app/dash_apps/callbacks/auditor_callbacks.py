# app/dash_apps/callbacks/auditor_callbacks.py
"""
Callbacks for the Auditor portal. Read-only: they only call app.services.auditor_checks, which issues fixed
SELECTs. The society is ALWAYS the server-session society, never a browser value, and the role is read from the
Flask-Login session (not auth-store).
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

from app.dash_apps.pages.auditor_page import CHECKS, render_result
from app.security.audit_context import get_current_society_id, get_current_user_role
from app.security.guards import require_session
from app.services import auditor_checks as ac

AUDITOR_ROLE = "auditor"
_KEYS = [c[0] for c in CHECKS]


def _scope():
    """society_id for an authenticated auditor, else None."""
    if get_current_user_role() != AUDITOR_ROLE:
        return None
    sid = get_current_society_id()
    return int(sid) if sid else None


def register_auditor_callbacks(app):

    @app.callback(
        Output("aud-res", "options"),
        Input("aud-res", "id"),
    )
    @require_session
    def load_resolutions(_id):
        sid = _scope()
        if not sid:
            return []
        try:
            rows = ac.resolutions_for(sid)
        except Exception:
            return []
        return [{"label": f"#{r['id']} · {r['type']} {r['held_on']} · {r['title'] or ''}", "value": r["id"]}
                for r in rows]

    @app.callback(
        Output({"type": "aud-out", "check": ALL}, "children"),
        Output("aud-toast", "children"),
        Input({"type": "aud-run", "check": ALL}, "n_clicks"),
        Input("aud-run-all", "n_clicks"),
        State("aud-day", "date"),
        State("aud-acc", "value"),
        State("aud-res", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def run_checks(clicks, run_all, day, acc_id, res_id):
        trig = ctx.triggered_id
        if trig is None or not any(c for c in (clicks or [])) and not run_all:
            raise PreventUpdate
        sid = _scope()
        if not sid:
            return [no_update] * len(_KEYS), dbc.Alert("Auditor role required.", color="danger",
                                                      dismissable=True, style={"fontSize": "13px"})
        if trig == "aud-run-all":
            wanted = set(ac.SIMPLE_CHECKS) | {"cashbook"}
            if acc_id:
                wanted.add("receipt_chain_one")
            if res_id:
                wanted.add("resolution")
        elif isinstance(trig, dict) and trig.get("check") in _KEYS:
            wanted = {trig["check"]}
        else:
            raise PreventUpdate
        outs = []
        for key in _KEYS:
            if key in wanted:
                outs.append(render_result(ac.run(key, sid, day=day, acc_id=acc_id, resolution_id=res_id)))
            else:
                outs.append(no_update)
        return outs, None
