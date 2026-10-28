"""To-ratify register and rule-application register on the Governance tab (Plan v3, tasks 2.3 and 2.4)."""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, ctx, dcc, html, no_update

from app.security.audit_context import get_current_society_id, get_current_user_id
from app.security.guards import require_session
from app.services import ratification_service as rs


def ratification_section(society_id) -> html.Div:
    items = rs.register(society_id)
    rows = []
    for i in items:
        pending = i["status"] == "pending"
        controls = html.Div([
            dbc.Input(id={"type": "rat-res", "id": i["id"]}, type="number", placeholder="Passed resolution #", size="sm",
                      style={"width": "150px", "display": "inline-block"}),
            dbc.Input(id={"type": "rat-note", "id": i["id"]}, type="text", placeholder="Note (needed to reject)", size="sm",
                      className="ms-1", style={"width": "200px", "display": "inline-block"}),
            dbc.Button("Ratify", id={"type": "rat-ratify", "id": i["id"]}, color="success", size="sm", className="ms-1", n_clicks=0),
            dbc.Button("Reject and reverse", id={"type": "rat-reject", "id": i["id"]}, color="outline-danger", size="sm", className="ms-1", n_clicks=0),
            html.Div(id={"type": "rat-msg", "id": i["id"]}, style={"fontSize": "11px"}),
        ]) if pending else html.Span(f"Resolution #{i['resolution_id']}" if i.get("resolution_id") else (i.get("decision_note") or ""),
                                     style={"fontSize": "11px"})
        rows.append(html.Tr([html.Td(f"#{i['id']}"), html.Td(rs.KIND_LABEL.get(i["kind"], i["kind"])),
                             html.Td(i["description"], style={"maxWidth": "280px"}), html.Td(f"{i['amount']:,.2f}"),
                             html.Td(str(i["ratify_by"])), html.Td(dbc.Badge(i["status"], color={"pending": "warning", "ratified": "success"}.get(i["status"], "secondary"))),
                             html.Td(controls)]))
    table = dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("#", "Kind", "What", "Amount", "Ratify by", "Status", "Decision")])),
                       html.Tbody(rows)], size="sm", style={"fontSize": "12px"}) if rows else html.Div("Nothing to ratify.", style={"fontSize": "12px", "color": "#888"})
    return html.Div([
        html.Div("Items to ratify", style={"fontWeight": "600"}),
        html.Div("An irregular item stands for up to 90 days. If it is rejected or the date passes, its postings are reversed automatically.",
                 style={"fontSize": "11px", "color": "#888", "marginBottom": "6px"}),
        table,
        html.Div([dbc.Button("Download rule-application register (CSV)", id="rule-register-download-btn", color="outline-secondary", size="sm", n_clicks=0),
                  dcc.Download(id="rule-register-download")], className="mt-2"),
    ])


def certificate_section(society_id) -> html.Div:
    """Compliance certificate (task 2.6): generate, list, and the public verification link."""
    from app.services import compliance_certificate as cc
    from database.db_manager import db
    rows = db._execute("SELECT id, fy, overall, generated_at, status FROM compliance_certificates WHERE society_id=%s "
                       "ORDER BY id DESC LIMIT 10", (society_id,), fetch_all=True) or []
    body = [html.Tr([html.Td(r["fy"]), html.Td(r["overall"]), html.Td(str(r["generated_at"])[:16]), html.Td(r["status"]),
                     html.Td(html.A("public check page", href=f"/verify/certificate/{r['id']}", target="_blank", rel="noopener"))]) for r in rows]
    return html.Div([
        html.Div("Compliance certificate", style={"fontWeight": "600"}),
        html.Div("Each check with its result and date, plus every provisional item, signed with the society's ledger key. It is a statement of "
                 "what the system checked, not an audit opinion; your CA signs the paper copy.", style={"fontSize": "11px", "color": "#888", "marginBottom": "6px"}),
        dbc.Input(id="cert-fy", type="text", value=cc.fy_label(), size="sm", style={"width": "110px", "display": "inline-block"}),
        dbc.Button("Generate and sign", id="cert-generate", color="primary", size="sm", className="ms-2", n_clicks=0),
        dbc.Button("Download latest (text)", id="cert-download-btn", color="outline-secondary", size="sm", className="ms-2", n_clicks=0),
        dcc.Download(id="cert-download"),
        html.Div(id="cert-msg", style={"fontSize": "12px", "marginTop": "6px"}),
        dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Year", "Overall", "Generated", "Status", "Verify")])), html.Tbody(body)],
                  size="sm", style={"fontSize": "12px", "marginTop": "8px"}) if body else html.Div(),
    ])


def register_ratification_callbacks(app):
    @app.callback(
        Output("inst-msg", "children"),
        Input("inst-verify", "n_clicks"),
        State("inst-id", "value"), State("inst-notif", "value"), State("inst-url", "value"), State("inst-opinion", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _verify_instrument(n, inst_id, notif, url, opinion):
        uid, sid = get_current_user_id(), get_current_society_id()
        if not n or not uid or not sid or not inst_id:
            return no_update
        from app.services import document_signing as ds, instrument_verification as iv
        try:
            iv.verify(sid, uid, inst_id, notif, url, opinion)
            return html.Span("Marked verified.", style={"color": "#17976e"})
        except ds.SigningRefused as exc:
            return html.Span(str(exc), style={"color": "#b02a37"})

    @app.callback(
        Output("cert-msg", "children"),
        Input("cert-generate", "n_clicks"),
        State("cert-fy", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _generate_cert(n, fy):
        uid, sid = get_current_user_id(), get_current_society_id()
        if not n or not uid or not sid:
            return no_update
        from app.services import compliance_certificate as cc
        try:
            r = cc.generate(sid, uid, (fy or "").strip() or None)
            return html.Span(f"Certificate {r['fy']} signed: overall result {r['overall']}. Reload the tab to see it listed.", style={"color": "#17976e"})
        except cc.CertificateRefused as exc:
            return html.Span(str(exc), style={"color": "#b02a37"})

    @app.callback(
        Output("cert-download", "data"),
        Input("cert-download-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def _download_cert(n):
        sid = get_current_society_id()
        if not n or not sid:
            return no_update
        from app.services import compliance_certificate as cc
        from database.db_manager import db
        r = db._execute("SELECT id FROM compliance_certificates WHERE society_id=%s AND status='valid' ORDER BY id DESC LIMIT 1", (sid,), fetch_one=True)
        if not r:
            return no_update
        return dcc.send_string(cc.render_text(r["id"], sid), "compliance_certificate.txt")

    @app.callback(
        Output({"type": "rat-msg", "id": MATCH}, "children"),
        Input({"type": "rat-ratify", "id": MATCH}, "n_clicks"),
        Input({"type": "rat-reject", "id": MATCH}, "n_clicks"),
        State({"type": "rat-res", "id": MATCH}, "value"),
        State({"type": "rat-note", "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _decide(n_ok, n_no, res, note):
        trig = ctx.triggered_id
        uid, sid = get_current_user_id(), get_current_society_id()
        if not trig or not uid or not sid or not (n_ok or n_no):
            return no_update
        try:
            msg = rs.decide(sid, int(trig["id"]), trig["type"] == "rat-ratify", int(res) if res else None, uid, note)
            return html.Span(f"Done: {msg}. Reload the tab to see the new status.", style={"color": "#17976e"})
        except rs.RatificationRefused as exc:
            return html.Span(str(exc), style={"color": "#b02a37"})

    @app.callback(
        Output("rule-register-download", "data"),
        Input("rule-register-download-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def _download(n):
        sid = get_current_society_id()
        if not n or not sid:
            return no_update
        return dcc.send_string(rs.export_rule_register_csv(sid), "rule_application_register.csv")
