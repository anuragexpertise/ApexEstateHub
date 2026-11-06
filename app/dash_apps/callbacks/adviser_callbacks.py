"""
Callbacks for the "Adviser Decisions" tab: create the rows, save an adviser's reference / PDF / majority / start date, and
approve as Secretary or Treasurer.

The society, the user and their role ALWAYS come from the server session, never from a browser value. What each person may
do is decided again here, from the server, on every call: the administrator or a serving Secretary / Treasurer may save;
only a serving Secretary or Treasurer may approve, with their OWN login password (the service re-checks it with the login
lockout, and the database re-checks the office).
"""
import base64

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, ctx, no_update

from app.dash_apps.pages import adviser_page as ap
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import adviser_decisions as ad

P = ap.P


def _session():
    """(society_id, user_id, role) from the server session, or None when it is not usable."""
    sid, uid = get_current_society_id(), get_current_user_id()
    if not sid or not uid:
        return None
    return int(sid), int(uid), get_current_user_role()


def _row(sid, uid, role, kind, subject_id, message=None, ok=True):
    """The refreshed row for one decision, built from the database as it stands now."""
    roles = ad.signing_roles(sid, uid)
    item = next((i for i in ad.get_state(sid)["items"] if i["kind"] == kind and i["subject_id"] == subject_id), None)
    if item is None:
        return [dbc.Alert("That decision does not belong to this society.", color="danger", className="py-2 mb-0")]
    return ap.row_children(item, ad.may_prepare(sid, uid, role), roles, message, ok)


def register_adviser_callbacks(app):

    @app.callback(Output(f"{P}-body", "children"), Input(f"{P}-init", "n_clicks"), prevent_initial_call=True)
    @require_session
    def adv_init(n):
        s = _session()
        if not n or not s:
            return no_update
        sid, uid, role = s
        if not ad.may_prepare(sid, uid, role):
            return no_update
        ad.ensure_rows(sid, uid)
        return ap.adviser_body(sid, True, ad.signing_roles(sid, uid))

    @app.callback(
        Output({"type": f"{P}-row", "kind": MATCH, "id": MATCH}, "children"),
        Input({"type": f"{P}-save", "kind": MATCH, "id": MATCH}, "n_clicks"),
        State({"type": f"{P}-adviser", "kind": MATCH, "id": MATCH}, "value"),
        State({"type": f"{P}-ref", "kind": MATCH, "id": MATCH}, "value"),
        State({"type": f"{P}-maj", "kind": MATCH, "id": MATCH}, "value"),
        State({"type": f"{P}-start", "kind": MATCH, "id": MATCH}, "value"),
        State({"type": f"{P}-pdf", "kind": MATCH, "id": MATCH}, "contents"),
        State({"type": f"{P}-pdf", "kind": MATCH, "id": MATCH}, "filename"),
        prevent_initial_call=True,
    )
    @require_session
    def adv_save(n, adviser, ref, majority, start, contents, filename):
        trig = ctx.triggered_id
        s = _session()
        if not n or not trig or not s:
            return no_update
        sid, uid, role = s
        kind, subject_id = trig["kind"], int(trig["id"])
        if not ad.may_prepare(sid, uid, role):
            return _row(sid, uid, role, kind, subject_id, "Only the administrator, the Secretary or the Treasurer can fill this in.", False)
        doc_id = None
        if contents:
            try:
                raw = base64.b64decode(contents.split(",", 1)[1])
            except Exception:                                                  # noqa: BLE001
                return _row(sid, uid, role, kind, subject_id, "That file could not be read.", False)
            ok, msg, doc_id = ad.attach_pdf(sid, uid, filename or "adviser-reference.pdf", raw)
            if not ok:
                return _row(sid, uid, role, kind, subject_id, msg, False)
        try:
            maj = float(majority) if (majority not in (None, "") and kind == "decision") else None
        except ValueError:
            return _row(sid, uid, role, kind, subject_id, "Choose one of the offered majorities.", False)
        ok, msg = ad.save(sid, kind, subject_id, on_behalf_of=adviser or None, reference_text=ref, reference_doc_id=doc_id,
                          majority_pct=maj, start_date=start or None)
        return _row(sid, uid, role, kind, subject_id, msg, ok)

    @app.callback(
        Output({"type": f"{P}-row", "kind": MATCH, "id": MATCH}, "children", allow_duplicate=True),
        Input({"type": f"{P}-sign", "kind": MATCH, "id": MATCH}, "n_clicks"),
        State({"type": f"{P}-pw", "kind": MATCH, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def adv_sign(n, password):
        trig = ctx.triggered_id
        s = _session()
        if not n or not trig or not s:
            return no_update
        sid, uid, role = s
        kind, subject_id = trig["kind"], int(trig["id"])
        mine = ad.signing_roles(sid, uid)
        item = next((i for i in ad.get_state(sid)["items"] if i["kind"] == kind and i["subject_id"] == subject_id), None)
        todo = [r for r in mine if item and r not in (item.get("signed_roles") or [])]
        if not todo:
            return _row(sid, uid, role, kind, subject_id, "Only the serving Secretary or Treasurer can approve, and only once each.", False)
        ok, msg = ad.sign(sid, kind, subject_id, uid, todo[0], password or "")
        return _row(sid, uid, role, kind, subject_id, msg, ok)
