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
import io
import json
import time

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, MATCH, Input, Output, State, ctx, dcc, html, no_update

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


def _paper_evidence(sid, uid, contents, filename):
    """Paper counterpart: the user uploads the scan, the SERVER computes the SHA-256 (nobody types a hash)."""
    raw = _decode(contents)
    if not raw:
        raise ds.SigningRefused("Upload the signed scan (PDF, PNG or JPG).")
    try:
        return ob.store_evidence_file(sid, "paper_signature", None, filename or "", raw, uid, {"kind": "agreement"})["sha256"]
    except ob.OnboardingError as exc:
        raise ds.SigningRefused(str(exc)) from exc


def _body(sid, uid, role, view=None):
    return op.hub_body(role, sid, uid, view=view), op.marker(sid)


def _committee_view(sid):
    """Admin edits made on the committee screen should leave the admin on it (not jump into the wizard)."""
    return "committee" if ob.state_of(sid) in ("committee seated", "setup draft") else None


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
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "filename"),
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
        sig_contents, sig_filename = _val(len(fields) + 2), _val(len(fields) + 3)
        try:
            msg = ob.seat_founding_officer(uid, sid, office, flat, name, email, phone, password or "", ref,
                                           filename, _decode(contents),
                                           signature_name=sig_filename,
                                           signature_bytes=_decode(sig_contents),
                                           apartment_size=int(size) if size not in (None, "") else None)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role, view=_committee_view(sid))
        return body, _alert(msg), mk

    # ── signature thumbnail preview while choosing a signature image ──────────
    @app.callback(
        Output({"type": f"{P}-f", "office": ALL, "field": "sig-preview"}, "children", allow_duplicate=True),
        Input({"type": f"{P}-f", "office": ALL, "field": "sig"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sig_preview(contents_list, filename_list):
        trig = ctx.triggered_id
        if not trig or not isinstance(trig, dict):
            return no_update
        office = trig["office"]
        for item in (ctx.states_list[0] or []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("office") == office and iid.get("field") == "sig":
                contents = item.get("value")
                fname = ""
                for it2 in (ctx.states_list[1] or []):
                    i2 = it2.get("id")
                    if isinstance(i2, dict) and i2.get("office") == office and i2.get("field") == "sig":
                        fname = it2.get("value") or ""
                        break
                if contents:
                    return html.Div([
                        html.Img(src=contents, style={"maxWidth": "140px", "maxHeight": "70px",
                                                      "border": "1px solid #c9d2dc", "borderRadius": "4px"}),
                        html.Div(fname, style={"fontSize": "11px", "color": "#667", "marginTop": "2px"})])
                return html.Div("Signature image selected.", style={"fontSize": "11.5px", "color": "#17976e"})
        return no_update

    # ── seated officer Edit details: mobile and/or signature replace ──────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input({"type": f"{P}-f", "office": ALL, "field": "save"}, "n_clicks"),
        State({"type": f"{P}-f", "office": ALL, "field": "phone"}, "value"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "contents"),
        State({"type": f"{P}-f", "office": ALL, "field": "sig"}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_officer_update(_clicks, phones, sig_contents_list, sig_filename_list):
        trig = ctx.triggered_id
        if not trig or not isinstance(trig, dict):
            return no_update, no_update, no_update
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update, _alert("Only the society's administrator can edit an officer.", False), no_update
        sid, uid, role = s
        office = trig["office"]
        phone = None
        for item in (ctx.states_list[0] or []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("office") == office and iid.get("field") == "phone":
                phone = item.get("value")
                break
        sig_contents = sig_filename = None
        for idx, item in enumerate((ctx.states_list[1] or [])):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("office") == office and iid.get("field") == "sig":
                sig_contents = item.get("value")
                sig_filename = (sig_filename_list or [None])[idx] if sig_filename_list else None
                break
        try:
            msg = ob.update_seated_officer(uid, sid, office, phone=phone,
                                           signature_name=sig_filename,
                                           signature_bytes=_decode(sig_contents))
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role, view=_committee_view(sid))
        return body, _alert(msg), mk

    # ── Administrator step: jump back to Stage 2 to finish an officer ─────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input("onb-back-to-committee", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_back_to_committee(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        return op.hub_body(role, sid, uid, view="committee"), "committee"

    # ── committee screen → wizard (only once the grievance officer is named) ──
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-continue-setup", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_continue_setup(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        if ob.state_of(sid) != "committee seated":
            return no_update, no_update, no_update
        if not op.grievance_named(sid):
            return no_update, _alert("Name the grievance officer first.", False), no_update
        return op.hub_body(role, sid, uid, view="setup"), no_update, "setup"

    # ── wizard step stores always follow whatever the body was just re-rendered to (F3) ──
    @app.callback(
        Output("onb-setup-step", "data", allow_duplicate=True),
        Output("onb-wizard-step", "data", allow_duplicate=True),
        Input(f"{P}-body", "children"),
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sync_step_stores(_children, view):
        s = _session()
        if not s or not s[0] or s[2] != "admin":
            return no_update, no_update
        if ob.state_of(s[0]) not in ("committee seated", "setup draft"):
            return no_update, no_update
        n = op.step_from_view(view)
        if n is None:
            n = op.start_step(s[0])
        return n, n

    @app.callback(
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-g-save", "n_clicks"),
        State(f"{P}-g-name", "value"), State(f"{P}-g-email", "value"), State(f"{P}-g-phone", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_grievance(n, name, email, phone):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return _alert("Only the society's administrator can name the grievance officer.", False), no_update, no_update
        try:
            ob.set_grievance_officer(sid, name, email, phone)
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update
        view = _committee_view(sid)               # stay here so the "Continue to society setup" button is visible
        return _alert("Grievance officer saved."), op.hub_body(role, sid, uid, view=view), (view or no_update)

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
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-prepare", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_prepare(n):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can check the annexes.", False), no_update, no_update
        try:
            ob.build_annexes(sid, uid)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role, view="current")
        return body, _alert("Annexes checked. Fix anything marked red using its link, then seal."), mk, "current"

    # ── "Fix in <step>" links on a failing annex control ─────────────────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input({"type": f"{P}-fix", "annex": ALL, "ctl": ALL, "key": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_fix(clicks):
        s = _session()
        trig = ctx.triggered_id
        if not s or not s[0] or s[2] != "admin" or not isinstance(trig, dict):
            return no_update, no_update
        if not (ctx.triggered and ctx.triggered[0].get("value")):          # a re-render, not a click
            return no_update, no_update
        sid, uid, role = s
        if ob.state_of(sid) not in ("committee seated", "setup draft"):
            return no_update, no_update
        key = trig.get("key")
        view = "committee" if key == "committee" else f"setup:{key}"
        return op.hub_body(role, sid, uid, view=view), view

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-seal", "n_clicks"),
        State(f"{P}-agree", "value"), State(f"{P}-seal-pw", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_seal(n, agree, password):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        if role != "admin" or not sid:
            return no_update, _alert("Only the society's administrator can seal the annexes.", False), no_update
        try:
            ob.seal_with_confirmation(sid, uid, agree, password)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert("Annexes sealed and the Agreement issued for signing."), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-sign", "n_clicks"),
        State(f"{P}-pw", "value"), State(f"{P}-method", "value"),
        State(f"{P}-paper", "contents"), State(f"{P}-paper", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_sign(n, password, method, paper, paper_name):
        s = _session()
        if not n or not s:
            return no_update, no_update, no_update
        sid, uid, role = s
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True) if sid else None
        if not ag:
            return no_update, _alert("There is no Agreement to sign yet.", False), no_update
        try:
            from app.services import esign_adapter as es
            mode = ob.signing_mode(sid)
            if mode == "paper":
                st = ds.sign("agreement", ag["id"], uid, password or "", method="paper",
                             evidence_ref=_paper_evidence(sid, uid, paper, paper_name))
            elif es.is_required(sid):
                st = ds.sign("agreement", ag["id"], uid, password or "", method=method or "aadhaar_eSign")
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
        Output("onb-tracker", "children"),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-poll", "n_intervals"),
        State(f"{P}-marker", "data"),
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_poll(_n, last, view):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        mk = op.marker(sid)
        if mk == last:
            return no_update, no_update, no_update
        st = ob.state_of(sid)
        # §2.3 poll safety: while the setup stage is mounted (view == "setup", or the
        # society is committee-seated / in a setup draft) the poll must not replace
        # onb-body — that wipes unsaved inputs and jumps the DOM (F3). Only refresh the
        # tracker; re-render the body only on real state transitions.
        setup_mounted = (view == "setup") or st in ("committee seated", "setup draft")
        if st == "active":
            return op.tracker(sid), op.hub_body(role, sid, uid), mk
        if setup_mounted:
            return op.tracker(sid), no_update, mk
        return op.tracker(sid), op.hub_body(role, sid, uid, view=view or "current"), mk

    # ── Master queue ────────────────────────────────────────────────────────────────────────────────────────
    def _master_ok():
        s = _session()
        return s if s and s[2] == "master" else None

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-signmode", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_signmode(mode):
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        if mode == ob.signing_mode(sid):
            return no_update, no_update, no_update
        try:
            ob.set_signing_mode(sid, uid, mode)
        except Exception as exc:                                       # noqa: BLE001
            body, mk = _body(sid, uid, role)
            return body, _alert(f"The signing method could not be changed: {exc}", False), mk
        body, mk = _body(sid, uid, role)
        return body, _alert(f"Signing method is now {mode}."), mk

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
                return _alert("A paper counterpart needs no request: upload the signed scan and sign.", False)
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

    def _platform_sign_job(sid, uid, ag_id, password, method, evidence, progress=None):
        """Runs in a worker thread (a new DB connection per call). ds.sign reports steps 1-3 and activation 4-7."""
        st = ds.sign("agreement", ag_id, uid, password or "", method=method, evidence_ref=evidence, progress=progress)
        act = st.get("activation") or {}
        if st.get("sealed") and not act.get("ok"):
            raise RuntimeError("Signed and sealed, but activation is held: " + str(act.get("error")))
        return {"sealed": bool(st.get("sealed"))}

    @app.callback(
        Output({"type": f"{P}-mmsg", "sid": MATCH}, "children"),
        Input({"type": f"{P}-msign", "sid": MATCH}, "n_clicks"),
        State({"type": f"{P}-mpw", "sid": MATCH}, "value"),
        State({"type": f"{P}-mmethod", "sid": MATCH}, "value"),
        State({"type": f"{P}-mpaper", "sid": MATCH}, "contents"), State({"type": f"{P}-mpaper", "sid": MATCH}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_master_sign(n, password, method, paper, paper_name):
        s = _master_ok()
        if not n or not s or not ctx.triggered_id:
            return no_update
        sid = int(ctx.triggered_id["sid"])
        ag = ob.db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
        if not ag:
            return _alert("That society has no Agreement.", False)
        from app.services import esign_adapter as es
        from app.services import onboarding_jobs as jobs
        try:
            mode = ob.signing_mode(sid)
            if mode == "paper":
                use_method, evidence = "paper", _paper_evidence(sid, s[1], paper, paper_name)
            elif es.is_required(sid):
                use_method, evidence = method or "dsc", None
            else:
                use_method, evidence = "password", None
        except ds.SigningRefused as exc:
            return _alert(str(exc), False)
        if jobs.latest_running(sid):
            return _alert("The platform signature is already being processed.", False)
        job_id = jobs.start("platform_sign", sid, s[1], _platform_sign_job, sid=sid, uid=s[1], ag_id=ag["id"],
                            password=password, method=use_method, evidence=evidence)
        return op.job_view(sid, job_id)

    @app.callback(
        Output({"type": f"{P}-jobbar", "sid": MATCH}, "children"),
        Output({"type": f"{P}-jobpoll", "sid": MATCH}, "disabled"),
        Input({"type": f"{P}-jobpoll", "sid": MATCH}, "n_intervals"),
        State({"type": f"{P}-jobid", "sid": MATCH}, "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_job_poll(_n, job_id):
        """Authorised on every poll: a master may watch any society's job; anyone else only their own society's."""
        s = _session()
        if not s or not job_id or not ctx.triggered_id:
            return no_update, no_update
        sid = int(ctx.triggered_id["sid"])
        if s[2] != "master" and s[0] != sid:
            return no_update, True
        from app.services import onboarding_jobs as jobs
        job = jobs.get(job_id, society_id=sid)
        if not job:
            return _alert("That job was not found.", False), True
        if job["status"] == "done":
            ev = ob.db._execute("SELECT id FROM onboarding_events WHERE society_id=%s AND event='agreement_signed' ORDER BY id DESC LIMIT 1",
                                (sid,), fetch_one=True)
            name = (ob.db._execute("SELECT name FROM societies WHERE id=%s", (sid,), fetch_one=True) or {}).get("name") or "The society"
            kids = [dbc.Progress(value=100, label="100%", color="success", style={"height": "20px"}),
                    html.Div("Society is live", style={"fontWeight": "700", "marginTop": "4px"})]
            if ev:
                kids.append(dcc.Store(id={"type": "onb-celebrate", "sid": sid}, data={"key": f"onb-celebrated-{sid}-{ev['id']}", "name": name}))
            return kids, True
        if job["status"] == "failed":
            return [dbc.Alert(str(job.get("error") or "The activation failed."), color="danger", className="py-2"),
                    dbc.Button("Retry activation", id={"type": f"{P}-retry", "sid": sid}, color="warning", size="sm", n_clicks=0)], True
        pct = op.JOB_PERCENT.get(int(job.get("step") or 0), 5)
        return dbc.Progress(value=pct, striped=True, animated=True, label=f"{pct}%", style={"height": "20px"}), False

    app.clientside_callback(
        """function(data){
            if (!data || !data.length || !window.dash_clientside || !window.dash_clientside.onboarding) {
                return window.dash_clientside.no_update;
            }
            window.dash_clientside.onboarding.celebrate(data[0]);
            return window.dash_clientside.no_update;
        }""",
        Output("onb-celebrate-sink", "children"),
        Input({"type": "onb-celebrate", "sid": ALL}, "data"),
        prevent_initial_call=False,
    )

    # ── items 14/15: Stage 5-7 buttons ───────────────────────────────────────
    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-enrol-done", "n_clicks"),
        State(f"{P}-enrol-later", "value"), State(f"{P}-enrol-later-reason", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_enrol_done(n, later, reason):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.mark_enrollment_complete(sid, uid, reason if later else None)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input(f"{P}-phase-next", "n_clicks"), Input(f"{P}-phase-later", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_phase_next(n_next, n_later):
        s = _session()
        if not (n_next or n_later) or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        nxt = {"adoption": "advisers", "advisers": "complete"}.get(ob.society_phase(sid))
        if not nxt:
            return no_update, no_update, no_update
        try:
            msg = ob.advance_phase(sid, uid, nxt)
        except ob.OnboardingError as exc:
            return no_update, _alert(str(exc), False), no_update
        body, mk = _body(sid, uid, role)
        return body, _alert(msg), mk

    @app.callback(
        Output({"type": f"{P}-retry", "sid": MATCH}, "children", allow_duplicate=True),
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



    @app.callback(
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output("onb-view", "data", allow_duplicate=True),
        Input(f"{P}-back-to-setup", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_back_to_setup(n):
        s = _session()
        if not n or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        return op.hub_body(role, sid, uid, view="setup"), "setup"

    def _tds_wizard_names():
        from database.seed import tds_wizard_rows as _rows
        return [(r[0], r[1]) for r in _rows()]

    def _bf_accs(sid):
        return ob.db._execute("SELECT id AS acc_id FROM accounts WHERE society_id=%s AND has_bf=TRUE ORDER BY id", (sid,), fetch_all=True) or []

    print("  ✓ Onboarding callbacks registered")
