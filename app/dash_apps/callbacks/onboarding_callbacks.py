# app/dash_apps/callbacks/onboarding_callbacks.py
"""
Callbacks for the Onboarding Hub (pages/onboarding_page.py).

This module is exempt from the setup gate (app/security/guards.py): the hub is the thing a society uses WHILE it is not
yet active. Because of that every callback decides for itself, from the SERVER session, who may do what:

  * seating, grievance officer, annex preparation and sealing: the society's administrator only;
  * signing the Agreement: only a login that holds the office (President / Secretary / Treasurer), with its own password;
  * the platform signature, and retrying a held activation: the master login only.
"""
import base64
import time

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, ctx, dcc, no_update

from app.dash_apps.pages import onboarding_page as op
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import document_signing as ds
from app.services import onboarding_service as ob

P = op.P


def _session():
    sid, uid, role = get_current_society_id(), get_current_user_id(), get_current_user_role()
    if not uid:
        return None
    return (int(sid) if sid else None), int(uid), role


def _alert(msg, ok=True):
    return dbc.Alert(msg, color="success" if ok else "danger", className="py-2 mt-2", style={"fontSize": "12.5px"}, dismissable=True)


def _decode(contents):
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:                                                      # noqa: BLE001
        return None


def _body(sid, uid, role):
    return op.hub_body(role, sid, uid), op.marker(sid)


def register_onboarding_callbacks(app):
    fields = ("flat", "name", "size", "email", "phone", "password", "ref")

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-seat", "office": MATCH}, "n_clicks"),
        [State({"type": f"{P}-f", "office": MATCH, "field": f}, "value") for f in fields],
        State({"type": f"{P}-f", "office": MATCH, "field": "file"}, "contents"),
        State({"type": f"{P}-f", "office": MATCH, "field": "file"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_seat(n, flat, name, size, email, phone, password, ref, contents, filename):
        s = _session()
        if not n or not s or not ctx.triggered_id:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seat the committee.", False), no_update
        try:
            msg = ob.seat_founding_officer(uid, sid, ctx.triggered_id["office"], flat, name, email, phone, password or "", ref,
                                           filename, _decode(contents), int(size) if size not in (None, "") else None)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Input(f"{P}-g-save", "n_clicks"),
        State(f"{P}-g-name", "value"), State(f"{P}-g-email", "value"), State(f"{P}-g-phone", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_grievance(n, name, email, phone):
        s = _session()
        if not n or not s:
            return no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return _alert("Only the society's administrator can name the grievance officer.", False), no_update
        try:
            ob.set_grievance_officer(sid, name, email, phone)
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update
        return _alert("Grievance officer saved."), op.hub_body(role, sid, uid)

    @app.callback(
        Output("pwd-gate-store", "data", allow_duplicate=True),
        Input(f"{P}-open-wizard", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_open_wizard(n):
        s = _session()
        if not n or not s or s[2] != "admin" or ob.state_of(s[0]) != "committee seated":
            return no_update
        return time.time()                       # trigger_setup_wizard listens on this store and now opens the wizard

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-prepare", "n_clicks"),
        State(f"{P}-in-arrears", "value"), State(f"{P}-in-bank", "value"), State(f"{P}-in-audit", "value"), State(f"{P}-in-ca", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_prepare(n, arrears, bank, audit, ca):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can prepare the annexes.", False), no_update
        try:
            ob.save_annex_inputs(sid, arrears, bool(bank), audit, ca)
            ob.build_annexes(sid, uid)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("Annexes checked. Fix anything marked red, then seal."), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-seal", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_seal(n):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seal the annexes.", False), no_update
        try:
            ob.seal_annexes(sid, uid)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("Annexes sealed and the Agreement issued for signing."), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-sign", "n_clicks"),
        State(f"{P}-pw", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sign(n, password):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag:
            return no_update, _alert("There is no Agreement to sign yet.", False), no_update
        try:
            st = ds.sign("agreement", ag["id"], uid, password or "")
        except ds.SigningRefused as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("Signed." + (" The Agreement is sealed." if st.get("sealed") else "")), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-poll", "n_intervals"),
        State(f"{P}-marker", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_poll(_n, last):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        mk = op.marker(sid)
        if mk == last:
            return no_update, no_update
        if ob.state_of(sid) == "active":                      # activated while the page was open: show the dashboard
            return op.hub_body(role, sid, uid), mk
        return op.hub_body(role, sid, uid), mk

    # ── Master queue ────────────────────────────────────────────────────────────────────────────────────────
    def _master_ok():
        s = _session()
        return s if s and s[2] == "master" else None

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children"),
        Input({"type": f"{P}-msign", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mpw", "sid": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_sign(n, password):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        sid = int(ctx.triggered_id["sid"])
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag:
            return _alert("That society has no Agreement.", False)
        try:
            st = ds.sign("agreement", ag["id"], s[1], password or "")
        except ds.SigningRefused as exc:
            return _alert(str(exc), False)
        act = st.get("activation") or {}
        if act.get("ok"):
            return _alert("Signed. The Agreement is sealed and the society is active.")
        return _alert("Signed and sealed, but activation is held: " + str(act.get("error")), False)

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children", allow_duplicate=True),
        Input({"type": f"{P}-retry", "sid": MATCH}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_retry(n):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        res = ob.try_activate(int(ctx.triggered_id["sid"]), s[1])
        return _alert("The society is active." if res["ok"] else "Still held: " + res["error"], res["ok"])

    print("  ✓ Onboarding callbacks registered")
