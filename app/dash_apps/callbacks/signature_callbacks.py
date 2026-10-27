"""Sign / Approve / Decline panel for NOC, agreements, resolutions, minutes, polls, expenses (Plan v3, 2.1/2.2/2.11/2.12).

The panel is one reusable component (signature_panel) driven by one pattern-matching callback. The signer re-enters
their OWN login password; the service (document_signing) decides whether they may sign and seals the record when the
required signatures are in. The user and the society always come from the server session, never from the browser.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, ctx, html, dcc, no_update

from app.security.audit_context import get_current_society_id, get_current_user_id
from app.security.guards import require_session
from app.services import document_signing as ds

LABEL = {"noc": "NOC", "agreement": "Agreement", "resolution": "Resolution", "minutes": "Minutes", "poll": "Poll result",
         "expense": "Expense", "fund_withdrawal": "Fund withdrawal"}


def _pid(part, kind, subject_id):
    return {"type": f"sig-{part}", "kind": kind, "id": int(subject_id)}


def status_view(kind: str, subject_id: int, message: str | None = None, ok: bool = True):
    """The 'who has signed' block."""
    try:
        st = ds.status(kind, int(subject_id))
    except ds.SigningRefused as exc:
        return dbc.Alert(str(exc), color="secondary", className="py-2 mb-0")
    rows = [html.Li(f"{x['name']} - {x['office_code'].replace('_', ' ').title()} - {str(x['signed_at'])[:16]}") for x in st["signed"]]
    rows += [html.Li(f"DECLINED: {x['name']} ({x['office_code'].replace('_', ' ').title()}) - {x['reason']}", style={"color": "#b02a37"})
             for x in st["declined"]]
    if st["sealed"]:
        head = dbc.Badge("Sealed", color="success", className="me-2")
        need = "Signed and sealed. Editing is now blocked."
    else:
        head = dbc.Badge("Awaiting signatures", color="warning", text_color="dark", className="me-2")
        miss = ", ".join(o.replace("_", " ").title() for o in st["missing_required"]) or "none"
        need = f"{st['people_signed']} of {st['min_signers']} signatures. Still required: {miss}."
    out = [html.Div([head, html.Span(need, style={"fontSize": "12px"})])]
    if rows:
        out.append(html.Ul(rows, style={"fontSize": "12px", "margin": "6px 0 0 0", "paddingLeft": "18px"}))
    if message:
        out.insert(0, dbc.Alert(message, color="success" if ok else "danger", className="py-2 mb-2"))
    return html.Div(out)


def signature_panel(kind: str, subject_id, approve_label: str = "Sign") -> html.Div:
    """Drop this into any card. Pass the saved record's id (the text that is signed is the SAVED text)."""
    if not subject_id:
        return html.Div("Save the record first; it can be signed once saved.", style={"fontSize": "12px", "color": "#999"})
    return html.Div([
        html.Div(f"Signatures - {LABEL.get(kind, kind)}", style={"fontWeight": "600", "fontSize": "12px", "marginBottom": "6px"}),
        html.Div(status_view(kind, subject_id), id=_pid("status", kind, subject_id)),
        dbc.Input(id=_pid("pw", kind, subject_id), type="password", placeholder="Your login password", autoComplete="current-password",
                  size="sm", className="mt-2", style={"maxWidth": "260px"}),
        dbc.Input(id=_pid("reason", kind, subject_id), type="text", placeholder="Reason (only if declining)", size="sm",
                  className="mt-1", style={"maxWidth": "420px"}),
        *([html.Div([
            dbc.Input(id=_pid("ref", kind, subject_id), type="text", placeholder="MC resolution reference (needed above the approval limit)",
                      size="sm", style={"maxWidth": "420px", "display": "inline-block"}),
            dbc.Button("Save ref", id=_pid("saveref", kind, subject_id), color="outline-secondary", size="sm", n_clicks=0, className="ms-2"),
        ], className="mt-1")] if kind == "expense" else []),
        html.Div([
            dbc.Button(approve_label, id=_pid("sign", kind, subject_id), color="success", size="sm", n_clicks=0),
            dbc.Button("Decline", id=_pid("decline", kind, subject_id), color="outline-danger", size="sm", n_clicks=0, className="ms-2"),
        ], className="mt-2"),
        html.Div("Your password confirms who signed. It is not a legal e-signature; keep signed paper minutes.",
                 style={"fontSize": "10px", "color": "#999", "marginTop": "6px"}),
    ], style={"borderTop": "1px solid rgba(120,148,181,0.15)", "marginTop": "12px", "paddingTop": "10px"})


def register_signature_callbacks(app):
    @app.callback(
        Output({"type": "sig-status", "kind": MATCH, "id": MATCH}, "children"),
        Output({"type": "sig-pw", "kind": MATCH, "id": MATCH}, "value"),
        Input({"type": "sig-sign", "kind": MATCH, "id": MATCH}, "n_clicks"),
        Input({"type": "sig-decline", "kind": MATCH, "id": MATCH}, "n_clicks"),
        State({"type": "sig-pw", "kind": MATCH, "id": MATCH}, "value"),
        State({"type": "sig-reason", "kind": MATCH, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _on_sign(n_sign, n_decline, password, reason):
        trig = ctx.triggered_id
        if not trig or not (n_sign or n_decline):
            return no_update, no_update
        kind, subject_id = trig["kind"], int(trig["id"])
        uid, sid = get_current_user_id(), get_current_society_id()
        if not uid or not sid or kind not in ds.KINDS:
            return no_update, no_update
        try:
            owner_sid, _ = ds.item_text(kind, subject_id)
            if owner_sid != sid:                       # another society's record: behave as if it does not exist
                return status_view(kind, subject_id, "Record not found.", ok=False), ""
            decline = trig["type"] == "sig-decline"
            ds.sign(kind, subject_id, uid, password or "", action="decline" if decline else "sign", reason=reason)
            msg = "Your decline has been recorded." if decline else "Your signature has been recorded."
            return status_view(kind, subject_id, msg), ""
        except ds.SigningRefused as exc:
            return status_view(kind, subject_id, str(exc), ok=False), ""


    @app.callback(
        Output({"type": "sig-status", "kind": MATCH, "id": MATCH}, "children", allow_duplicate=True),
        Input({"type": "sig-saveref", "kind": MATCH, "id": MATCH}, "n_clicks"),
        State({"type": "sig-ref", "kind": MATCH, "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _on_save_ref(n, ref):
        trig = ctx.triggered_id
        uid, sid = get_current_user_id(), get_current_society_id()
        if not n or not trig or trig["kind"] != "expense" or not uid or not sid:
            return no_update
        subject_id = int(trig["id"])
        try:
            owner_sid, _ = ds.item_text("expense", subject_id)
            if owner_sid != sid:
                return status_view("expense", subject_id, "Record not found.", ok=False)
            from app.services import expense_approval as ea
            ea.save_resolution_ref(subject_id, sid, uid, ref)
            return status_view("expense", subject_id, "Resolution reference saved.")
        except ds.SigningRefused as exc:
            return status_view("expense", subject_id, str(exc), ok=False)
