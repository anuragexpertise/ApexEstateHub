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
from dash import ALL, MATCH, Input, Output, State, ctx, dcc, no_update

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

    # Outputs are the single hub body/toast/marker, so the inputs cannot use MATCH (Dash rejects a MATCH
    # key that the Outputs do not carry). ALL + ctx.triggered_id / ctx.states_list picks out the office clicked.
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-seat", "office": ALL}, "n_clicks"),
        [State({"type": f"{P}-f", "office": ALL, "field": f}, "value") for f in fields],
        State({"type": f"{P}-f", "office": ALL, "field": "file"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "file"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_seat(_clicks, *_states):
        s = _session()
        trig = ctx.triggered_id
        if not s or not isinstance(trig, dict) or not (ctx.triggered and ctx.triggered[0].get("value")):
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seat the committee.", False), no_update
        office = trig["office"]

        def _val(i):
            for item in (ctx.states_list[i] or []):
                if isinstance(item.get("id"), dict) and item["id"].get("office") == office:
                    return item.get("value")
            return None

        flat, name, size, email, phone, password, ref = (_val(i) for i in range(len(fields)))
        contents, filename = _val(len(fields)), _val(len(fields) + 1)
        try:
            msg = ob.seat_founding_officer(uid, sid, office, flat, name, email, phone, password or "", ref,
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
        State(f"{P}-pw", "value"), State(f"{P}-method", "value"), State(f"{P}-paper", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sign(n, password, method, paper):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag:
            return no_update, _alert("There is no Agreement to sign yet.", False), no_update
        try:
            from app.services import esign_adapter as es
            if es.is_required(sid):
                st = ds.sign("agreement", ag["id"], uid, password or "", method=method or "aadhaar_eSign", evidence_ref=(paper or None))
            else:
                st = ds.sign("agreement", ag["id"], uid, password or "")
        except ds.SigningRefused as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("Signed." + (" The Agreement is sealed." if st.get("sealed") else "")), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-esign-start", "n_clicks"), Input(f"{P}-esign-demo", "n_clicks"),
        State(f"{P}-method", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_esign_start(n_start, n_demo, method):
        s = _session()
        if not s or not (n_start or n_demo):
            return no_update, no_update, no_update
        sid, uid, role = s
        from app.services import esign_adapter as es
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag or not es.is_required(sid):
            return no_update, no_update, no_update
        try:
            _s_id, text = ds.item_text("agreement", ag["id"])
            u = ob.db._execute("SELECT name, email FROM users WHERE id=%s", (uid,), fetch_one=True) or {}
            if ctx.triggered_id == f"{P}-esign-demo":
                req = es.latest_for(sid, "agreement", ag["id"], uid)
                if not req:
                    return no_update, _alert("Start an eSign request first.", False), no_update
                es.simulate_completion(req["id"])
                msg = "The demo vendor completed your eSign."
            else:
                if method == "paper":
                    return no_update, _alert("A paper counterpart needs no request: paste the scan's SHA-256 and confirm with your password.", False), no_update
                es.create_request(sid, "agreement", ag["id"], u.get("name") or "Signer", u.get("email"), None,
                                  method or "aadhaar_eSign", ds.sha256(text), uid, signer_user_id=uid)
                msg = "eSign request started. Finish it with the vendor."
        except (es.EsignError, ds.SigningRefused) as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

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
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-esign", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_esign_toggle(required):
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            ob.set_esign_required(sid, uid, bool(required))
        except Exception as exc:                                       # noqa: BLE001
            return no_update, _alert(f"eSign toggle could not be saved: {exc}", False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("eSign required is now " + ("ON" if required else "OFF") + "."), mk

    # ── stage 7: adviser appointment / signing ──────────────────────────────
    ADV_FIELDS = ("kind", "name", "firm", "mno", "scope", "ts", "te", "res", "email", "pw")

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-adv", "field": "appoint"}, "n_clicks"),
        [State({"type": f"{P}-adv", "field": f}, "value") for f in ADV_FIELDS],
        prevent_initial_call=True,
    )
    @require_session
    def onb_adviser_appoint(n, kind, name, firm, mno, scope, ts, te, res, email, pw):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.appoint_adviser(uid, sid, kind, name, firm, mno, scope, ts, te,
                                     int(res) if res not in (None, "") else None, email, pw)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children", allow_duplicate=True),
        Input({"type": f"{P}-mstart", "sid": MATCH}, "n_clicks"), Input({"type": f"{P}-mdemo", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mmethod", "sid": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_esign(n_start, n_demo, method):
        s = _master_ok()
        if not s or not ctx.triggered_id or not (n_start or n_demo):
            return no_update
        sid = int(ctx.triggered_id["sid"])
        from app.services import esign_adapter as es
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag or not es.is_required(sid):
            return no_update
        try:
            if ctx.triggered_id["type"] == f"{P}-mdemo":
                req = es.latest_for(sid, "agreement", ag["id"], s[1])
                if not req:
                    return _alert("Start an eSign request first.", False)
                es.simulate_completion(req["id"])
                return _alert("The demo vendor completed the platform's eSign. Now confirm with your password.")
            if method == "paper":
                return _alert("A paper counterpart needs no request: paste the scan's SHA-256 and sign.", False)
            _x, text = ds.item_text("agreement", ag["id"])
            u = ob.db._execute("SELECT name, email FROM users WHERE id=%s", (s[1],), fetch_one=True) or {}
            es.create_request(sid, "agreement", ag["id"], u.get("name") or "Platform signatory", u.get("email"), None,
                              method or "dsc", ds.sha256(text), s[1], signer_user_id=s[1])
        except (es.EsignError, ds.SigningRefused) as exc:
            return _alert(str(exc), False)
        return _alert("eSign request started. Finish it with the vendor, then confirm with your password.")

    @app.callback(
        Output({"type": f"{P}-advmsg", "id": MATCH}, "children"),
        Input({"type": f"{P}-adv-sign", "id": MATCH}, "n_clicks"),
        State({"type": f"{P}-adv-pw", "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_adviser_sign(n, password):
        s = _session()
        if not n or not s or not ctx.triggered_id:
            return no_update
        _sid, uid, _role = s
        appt_id = int(ctx.triggered_id["id"])
        try:
            st = ds.sign("adviser_appointment", appt_id, uid, password or "")
        except ds.SigningRefused as exc:
            return _alert(str(exc), False)
        return _alert("Adviser appointment signed." + (" Sealed." if st.get("sealed") else ""))

    # ── stage: legacy resolution import (V5.8) ──────────────────────────────
    LEG_FIELDS = ("held", "mtype", "dtype", "outcome", "mfile", "mhash", "body")

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-leg", "field": "import"}, "n_clicks"),
        [State({"type": f"{P}-leg", "field": f}, "value") for f in LEG_FIELDS],
        prevent_initial_call=True,
    )
    @require_session
    def onb_legacy_import(n, held, mtype, dtype, outcome, mfile, mhash, body):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.import_legacy_resolution(sid, uid, held, mtype or "GBM", int(dtype) if dtype not in (None, "") else None,
                                              body, mfile, mhash, outcome or "unknown")
        except (ob.OnboardingError, ValueError, TypeError) as exc:
            return no_update, _alert(str(exc), False), no_update
        body_html, mk = _body(sid, uid, role)
        return body_html, _alert(msg), mk

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children"),
        Input({"type": f"{P}-msign", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mpw", "sid": MATCH}, "value"),
        State({"type": f"{P}-mmethod", "sid": MATCH}, "value"), State({"type": f"{P}-mpaper", "sid": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_sign(n, password, method, paper):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        sid = int(ctx.triggered_id["sid"])
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag:
            return _alert("That society has no Agreement.", False)
        try:
            from app.services import esign_adapter as es
            if es.is_required(sid):
                st = ds.sign("agreement", ag["id"], s[1], password or "", method=method or "dsc", evidence_ref=(paper or None))
            else:
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
