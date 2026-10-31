# app/dash_apps/callbacks/privacy_callbacks.py
"""
Callbacks for the DPDP notice gate and the "Privacy & data rights" panel (pages/privacy_page.py).

The society, the user and the role come from the SERVER session. What a person may do is decided again here: anyone may
read the notice, manage their own optional consent and raise a request; only the administrator or a serving Secretary may
work the register, erase, log a breach or publish a notice (dpdp_service re-checks on every call).
"""
from dash import ALL, Input, Output, State, ctx, no_update

import dash_bootstrap_components as dbc

from app.dash_apps.pages import privacy_page as pp
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import dpdp_service as dp


def _s():
    sid, uid = get_current_society_id(), get_current_user_id()
    return (int(sid), int(uid), get_current_user_role()) if sid and uid else None


def _msg(text, ok=True):
    return dbc.Alert(text, color="success" if ok else "danger", className="py-2", style={"fontSize": "12.5px"}, dismissable=True)


def register_privacy_callbacks(app):

    # ── the gate: before the dashboard, after the compulsory password change ────────────────────────────────
    @app.callback(
        Output("privacy-notice-modal", "is_open"),
        Output("privacy-notice-body", "children"),
        Input("auth-store", "data"),
        Input("pwd-gate-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def privacy_gate(_auth, _gate):
        s = _s()
        if not s or s[2] == "master":
            return no_update, no_update
        sid, uid, _role = s
        from app.services.auth_service import must_change_password
        if must_change_password(uid):
            return no_update, no_update          # the password change comes first; pwd-gate-store fires this again
        from app.services import onboarding_service as ob
        if ob.state_of(sid) != "active" or not dp.needs_notice(sid, uid):
            return no_update, no_update
        return True, pp.gate_body(sid)

    @app.callback(
        Output("privacy-notice-modal", "is_open", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("privacy-accept-btn", "n_clicks"),
        State("privacy-opt-announcements", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def privacy_accept(n, announcements):
        s = _s()
        if not n or not s:
            return no_update, no_update
        sid, uid, _role = s
        try:
            dp.accept_notice(sid, uid, ["announcements"] if announcements else [])
        except dp.DpdpError as exc:
            return True, {"type": "error", "message": str(exc)}
        return False, {"type": "success", "message": "Thank you. Your choices are recorded; change them any time under Privacy."}

    # ── the panel ────────────────────────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("privacy-rights-modal", "is_open"),
        Output("privacy-rights-body", "children"),
        Input("open-privacy-rights-btn", "n_clicks"),
        Input("close-privacy-rights-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def privacy_open(n_open, n_close):
        s = _s()
        if ctx.triggered_id == "close-privacy-rights-btn" or not s:
            return False, no_update
        if not n_open:
            return no_update, no_update
        sid, uid, role = s
        return True, pp.rights_body(sid, uid, role)

    def _refresh(text, ok=True):
        s = _s()
        body = pp.rights_body(s[0], s[1], s[2])
        body[0] = _msg(text, ok)
        return body

    @app.callback(Output("privacy-rights-body", "children", allow_duplicate=True),
                  Input("prv-raise", "n_clicks"), State("prv-type", "value"), State("prv-subject", "value"), prevent_initial_call=True)
    @require_session
    def privacy_raise(n, kind, subject):
        s = _s()
        if not n or not s:
            return no_update
        try:
            r = dp.raise_request(s[0], s[1], kind, subject)
        except dp.DpdpError as exc:
            return _refresh(str(exc), False)
        return _refresh(f"Request #{r['id']} sent. The society must answer by {r['due_date']}.")

    @app.callback(Output("prv-dummy", "data"), Input("prv-ann", "value"), prevent_initial_call=True)
    @require_session
    def privacy_toggle(on):
        s = _s()
        if not s:
            return no_update
        try:
            dp.set_optional_consent(s[0], s[1], "announcements", bool(on))
        except dp.DpdpError:
            pass
        return no_update

    @app.callback(
        Output("privacy-rights-body", "children", allow_duplicate=True),
        Input({"type": "prv-respond", "id": ALL}, "n_clicks"),
        State({"type": "prv-outcome", "id": ALL}, "value"), State({"type": "prv-note", "id": ALL}, "value"),
        State({"type": "prv-outcome", "id": ALL}, "id"),
        prevent_initial_call=True,
    )
    @require_session
    def privacy_respond(clicks, outcomes, notes, ids):
        s, t = _s(), ctx.triggered_id
        if not s or not t or not any(clicks or []):
            return no_update
        i = [x["id"] for x in ids].index(t["id"])
        try:
            dp.respond(s[0], t["id"], s[1], s[2], outcomes[i], notes[i] or "")
        except dp.DpdpError as exc:
            return _refresh(str(exc), False)
        return _refresh(f"Request #{t['id']} answered.")

    @app.callback(
        Output("privacy-rights-body", "children", allow_duplicate=True),
        Input({"type": "prv-notice", "id": ALL}, "n_clicks"), Input({"type": "prv-erase", "id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def privacy_erasure(_n1, _n2):
        s, t = _s(), ctx.triggered_id
        if not s or not t or not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update
        try:
            if t["type"] == "prv-notice":
                dp.give_erasure_notice(s[0], t["id"], s[1], s[2])
                return _refresh("The member is on notice. Erasure can proceed 48 hours from now.")
            dp.erase(s[0], t["id"], s[1], s[2])
            return _refresh("Profile erased. Ledger lines are untouched.")
        except dp.DpdpError as exc:
            return _refresh(str(exc), False)

    @app.callback(Output("privacy-rights-body", "children", allow_duplicate=True),
                  Input("prv-b-add", "n_clicks"), State("prv-b-desc", "value"), State("prv-b-n", "value"), prevent_initial_call=True)
    @require_session
    def privacy_breach(n, desc, count):
        s = _s()
        if not n or not s:
            return no_update
        try:
            dp.log_breach(s[0], s[1], s[2], None, desc or "", int(count or 0))
        except dp.DpdpError as exc:
            return _refresh(str(exc), False)
        return _refresh("Breach logged. Tell the Board and the people affected without delay.")

    @app.callback(Output("privacy-rights-body", "children", allow_duplicate=True),
                  Input("prv-n-pub", "n_clicks"), State("prv-n-title", "value"), State("prv-n-body", "value"), prevent_initial_call=True)
    @require_session
    def privacy_publish(n, title, body):
        s = _s()
        if not n or not s:
            return no_update
        if not dp.can_manage(s[0], s[1], s[2]):
            return _refresh("Only the administrator or the Secretary can publish a notice.", False)
        try:
            v = dp.publish_notice(s[0], title or "", body or "", s[1])
        except dp.DpdpError as exc:
            return _refresh(str(exc), False)
        return _refresh(f"Notice version {v['version']} published.")

    print("  ✓ Privacy callbacks registered")
