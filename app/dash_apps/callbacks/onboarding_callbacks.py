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
from dash import ALL, MATCH, Input, Output, State, ctx, dcc, no_update

from app.dash_apps.pages import onboarding_page as op
from app.dash_apps.pages.setup_wizard import CATEGORIES
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
        State("onb-view", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_poll(_n, last, view):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        mk = op.marker(sid)
        if mk == last:
            return no_update, no_update
        if ob.state_of(sid) == "active":                      # activated while the page was open: show the dashboard
            return op.hub_body(role, sid, uid), mk
        return op.hub_body(role, sid, uid, view=view or "current"), mk

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

    # ── stage 3: society setup — inline navigation + submit ───────────────────────────────────────────
    def _step_styles(n):
        return [{"display": "block" if i == n else "none"} for i in range(len(CATEGORIES))]

    def _nav_classes(n):
        return ["onb-nav-item" + (" active" if i == n else "") for i in range(len(CATEGORIES))]

    def _nav_styles(n):
        return [{"textAlign": "center", "flex": "1", "padding": "4px 2px", "cursor": "pointer",
                 "borderBottom": "2px solid " + (_ICON_COLOR(i, n) if i == n else "#e1e7ef"),
                 "opacity": 1.0 if i <= n else 0.5} for i in range(len(CATEGORIES))]

    def _ICON_COLOR(i, n):
        return "#1d74d8" if i == n else ("#2e9e5b" if i < n else "#b8c2cf")

    @app.callback(
        Output("onb-setup-step", "data"),
        Output({"type": "onb-step", "index": ALL}, "style"),
        Output({"type": "onb-nav", "index": ALL}, "className"),
        Output({"type": "onb-nav", "index": ALL}, "style"),
        Output("onb-btn-prev", "disabled"),
        Output("onb-setup-error", "children"),
        Input("onb-btn-prev", "n_clicks"),
        Input("onb-btn-next", "n_clicks"),
        Input({"type": "onb-nav", "index": ALL}, "n_clicks"),
        State("onb-setup-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_setup_nav(n_prev, n_next, nav_clicks, step):
        s = _session()
        if not s or not ctx.triggered_id:
            return no_update, no_update, no_update, no_update, no_update, no_update
        sid, _uid, role = s
        if role != "admin" or not sid:
            return no_update, no_update, no_update, no_update, no_update, _alert("Only the administrator can navigate setup.", False)
        n = int(step or 0)
        trig = ctx.triggered_id
        if trig == "onb-btn-prev":
            n = max(0, n - 1)
        elif trig == "onb-btn-next":
            n = min(len(CATEGORIES) - 1, n + 1)
        elif isinstance(trig, dict) and trig.get("type") == f"{P}-nav":
            n = int(trig.get("index", n))
        return n, _step_styles(n), _nav_classes(n), _nav_styles(n), (n == 0), ""

    @app.callback(
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Input("onb-btn-submit", "n_clicks"),
        State("sw-society-address", "value"), State("sw-society-email", "value"), State("sw-society-phone", "value"),
        State("sw-society-state", "value"), State("sw-society-constitution", "value"),
        State("sw-society-tan", "value"), State("sw-society-gstin", "value"),
        State("sw-calc-start-date", "value"),
        State("sw-qr-secret", "value"), State("sw-qr-secret-confirm", "value"), State("sw-qr-confirm-final", "value"),
        State("sw-admin-password", "value"), State("sw-i-agree", "value"),
        State("sw-gate-logic", "value"), State("sw-duty-hrs", "value"),
        State("sw-cgst", "value"), State("sw-sgst", "value"),
        State("sw-tds-effective-date", "value"),
        State({"type": "tds-rate", "index": ALL}, "value"),
        State({"type": "tds-nature", "index": ALL}, "value"),
        State({"type": "tds-rate-no-pan", "index": ALL}, "value"),
        State({"type": "tds-single-bill", "index": ALL}, "value"),
        State({"type": "tds-agg-bill", "index": ALL}, "value"),
        State("sw-apt-cost", "value"), State("sw-apt-budget", "value"), State("sw-apt-rate", "value"),
        State("sw-apt-amt", "value"), State("sw-apt-billing-basis", "value"), State("sw-apt-due", "value"),
        State("sw-apt-interest", "value"),
        State("sw-apt-sinking", "value"), State("sw-apt-repair", "value"),
        State("sw-ven-1day", "value"), State("sw-ven-7day", "value"), State("sw-ven-1mth", "value"),
        State("sw-bf-fy", "value"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_setup_submit(n_clicks, addr, email, phone, state, constitution, tan, gstin, calc_start,
                         secret, secret_confirm, secret_confirm_final, admin_pw, i_agree,
                         gate_logic, duty_hrs, cgst, sgst, tds_eff_date,
                         tds_rate, tds_nature, tds_no_pan, tds_single, tds_agg,
                         apt_cost, apt_budget, apt_rate, apt_amt, apt_basis, apt_due, apt_interest,
                         apt_sink, apt_repair, ven_1, ven_7, ven_30, bf_fy, bf_amt, bf_remarks):
        s = _session()
        if not n_clicks or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update
        sid, uid, role = s
        tds = []
        names = _tds_wizard_names()
        for idx, name in enumerate(names):
            rate = tds_rate[idx] if idx < len(tds_rate) else None
            if rate in (None, ""):
                continue
            tds.append({"section": name[0], "discriminator": name[1], "nature_of_income": (tds_nature[idx] if idx < len(tds_nature) else None),
                        "rate": rate,
                        "rate_no_pan": (tds_no_pan[idx] if idx < len(tds_no_pan) else None),
                        "single_bill_threshold": (tds_single[idx] if idx < len(tds_single) else None),
                        "annual_aggregate_threshold": (tds_agg[idx] if idx < len(tds_agg) else None)})
        bf = []
        for idx, acc in enumerate(_bf_accs(sid)):
            amt = bf_amt[idx] if idx < len(bf_amt) else None
            if amt is None or amt == "":
                continue
            try:
                amt_f = float(amt)
            except (TypeError, ValueError):
                continue
            if amt_f <= 0:
                continue
            bf.append({"acc_id": acc["acc_id"], "bf_amount": str(amt_f), "remarks": (bf_remarks[idx] if idx < len(bf_remarks) else "")})
        data = {"address": addr, "s_email": email, "phone": phone, "s_state": state, "s_constitution": constitution,
                "tan": tan, "gstin": gstin, "calc_start": calc_start,
                "secret": secret, "secret_confirm": secret_confirm, "secret_confirm_final": secret_confirm_final,
                "admin_password": admin_pw, "i_agree": i_agree,
                "gate_logic": gate_logic, "duty_hrs": duty_hrs,
                "tds": tds, "cgst": cgst, "sgst": sgst, "tds_effective_date": tds_eff_date,
                "apt_cost": apt_cost, "apt_budget": apt_budget, "apt_rate": apt_rate, "apt_amt": apt_amt,
                "apt_billing_basis": apt_basis, "apt_due_day": apt_due, "apt_interest": apt_interest,
                "apt_sinking": apt_sink, "apt_repair": apt_repair,
                "ven_1": ven_1, "ven_7": ven_7, "ven_30": ven_30,
                "bf_fy": bf_fy, "bf_json": bf}
        try:
            msg = ob.submit_setup_draft(sid, uid, data)
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update
        body, mk = _body(sid, uid, role)
        return _alert(msg), body, mk

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

    @app.callback(
        Output(f"{P}-c-download", "data"),
        Input(f"{P}-c-template", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_c_download(n):
        if not n:
            return no_update
        s = _session()
        if not s or s[2] != "admin" or not s[0]:
            return no_update
        cols = ["account_code", "account_name", "opening_debit", "opening_credit",
                "flat_number", "arrears_amount", "overdue_days"]
        df = pd.DataFrame(columns=cols)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        return dcc.send_bytes(output.getvalue(), filename="opening_position_template.xlsx")

    @app.callback(
        Output(f"{P}-c-feedback", "children"),
        Input(f"{P}-c-upload", "contents"),
        State(f"{P}-c-upload", "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def onb_c_upload(contents, filename):
        s = _session()
        if not contents or not s or s[2] != "admin" or not s[0]:
            return no_update
        sid, _uid, _role = s
        if not str(filename or "").lower().endswith((".xlsx", ".xls")):
            return _alert("Choose an Excel .xlsx or .xls file.", False)
        try:
            raw = base64.b64decode(contents.split(",", 1)[1])
            df = pd.read_excel(io.BytesIO(raw))
        except Exception as exc:  # noqa: BLE001
            return _alert(f"Could not read the file: {exc}", False)
        required = {"account_code", "account_name", "opening_debit", "opening_credit"}
        missing = required - set(df.columns)
        if missing:
            return _alert(f"Template missing columns: {', '.join(sorted(missing))}", False)
        dr = float(pd.to_numeric(df.get("opening_debit", pd.Series([0])), errors="coerce").fillna(0).sum() or 0)
        cr = float(pd.to_numeric(df.get("opening_credit", pd.Series([0])), errors="coerce").fillna(0).sum() or 0)
        if abs(dr - cr) > 0.005:
            return _alert(f"Opening position must balance: total debit {dr:.2f} != total credit {cr:.2f}.", False)
        accts = {str(r["id"]) for r in ob.db._execute("SELECT id FROM accounts WHERE society_id=%s", (sid,), fetch_all=True) or []}
        bad = [str(v) for v in df["account_code"].dropna().astype(str) if str(v) not in accts]
        if bad:
            return _alert(f"Unknown account codes: {', '.join(bad[:5])}", False)
        arrears = []
        for _, row in df.iterrows():
            flat = str(row.get("flat_number") or "").strip()
            amt = row.get("arrears_amount")
            if flat and amt not in (None, ""):
                try:
                    arrears.append({"flat_number": flat, "amount": str(float(amt)),
                                    "overdue_days": int(row.get("overdue_days") or 0)})
                except (TypeError, ValueError):
                    pass
        d = ob.declaration(sid) or {}
        d["annex_c_inputs"] = {
            "arrears_by_flat": arrears,
            "bank_agrees": False,
            "audited_hash": None,
            "ca_review_ref": None,
            "opening_position": df.to_dict("records"),
        }
        ob.db._execute("UPDATE onboarding_declarations SET declaration_json=%s::jsonb WHERE society_id=%s",
                       (json.dumps(d), sid))
        return _alert(f"Opening position loaded: {len(df)} rows; debits {dr:.2f} = credits {cr:.2f}.")

    def _tds_wizard_names():
        from database.seed import tds_wizard_rows as _rows
        return [(r[0], r[1]) for r in _rows()]

    def _bf_accs(sid):
        return ob.db._execute("SELECT id AS acc_id FROM accounts WHERE society_id=%s AND has_bf=TRUE ORDER BY id", (sid,), fetch_all=True) or []

    print("  ✓ Onboarding callbacks registered")
