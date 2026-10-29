"""Disputed / under-protest bills on the Governance tab (Plan v3, task 1.5).

The administrator or a serving office-bearer holds a bill (reason + the resolution it is held under) and later decides
it. All rules are in the database functions; this module is the screen and its callbacks. The section is only drawn
for people who may act, because the register names flats and owners.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import MATCH, Input, Output, State, ctx, dcc, html, no_update

from app.security.audit_context import get_current_society_id, get_current_user_id
from app.security.guards import require_session
from app.services import receivable_dispute_service as ds

_OK, _BAD = {"color": "#17976e"}, {"color": "#b02a37"}
_STATUS_COLOR = {"open": "warning", "upheld": "success", "dismissed": "secondary", "withdrawn": "secondary"}
_OUTCOME_OPTIONS = [{"label": ds.OUTCOME_LABEL[o], "value": o} for o in ds.OUTCOMES]


def _bill_option(b) -> dict:
    who = f"{b.get('flat_number') or '?'} {b.get('owner_name') or ''}".strip()
    return {"label": f"{who} | {b['description']} | due {b['due_date']} | outstanding {float(b['outstanding']):,.2f}", "value": b["id"]}


def _decision_cell(d) -> html.Div | html.Span:
    if d["status"] != "open":
        txt = f"{d['decision_reason']} ({d['decision_resolution_ref']}, {d['decided_on']})"
        return html.Span(txt, style={"fontSize": "11px"})
    i = d["id"]
    return html.Div([
        dcc.Dropdown(id={"type": "dsp-outcome", "id": i}, options=_OUTCOME_OPTIONS, placeholder="Outcome", clearable=False,
                     style={"fontSize": "12px", "width": "200px", "display": "inline-block", "verticalAlign": "middle"}),
        dbc.Input(id={"type": "dsp-dreason", "id": i}, type="text", placeholder="Why", size="sm", className="ms-1",
                  style={"width": "170px", "display": "inline-block"}),
        dbc.Input(id={"type": "dsp-dref", "id": i}, type="text", placeholder="Resolution no.", size="sm", className="ms-1",
                  style={"width": "130px", "display": "inline-block"}),
        dbc.Button("Record decision", id={"type": "dsp-decide", "id": i}, color="primary", size="sm", className="ms-1", n_clicks=0),
        html.Div(id={"type": "dsp-msg", "id": i}, style={"fontSize": "11px"}),
    ])


def dispute_section(society_id) -> html.Div | None:
    """None for anyone who may not act, so the tab shows no empty heading to them."""
    uid = get_current_user_id()
    if not society_id or not ds.may_act(society_id, uid):
        return None
    bills = ds.holdable_bills(society_id)
    register = ds.register(society_id)
    rows = [html.Tr([
        html.Td(f"#{d['id']}"), html.Td(d.get("flat_number") or "-"),
        html.Td(f"{d['bill']} (due {d['due_date']})", style={"maxWidth": "190px"}),
        html.Td(f"{float(d['amount_held']):,.2f}"), html.Td(str(d["raised_on"])),
        html.Td(f"{d['reason']} ({d['resolution_ref']})", style={"maxWidth": "230px", "fontSize": "11px"}),
        html.Td(dbc.Badge(d["status"], color=_STATUS_COLOR.get(d["status"], "secondary"))),
        html.Td(_decision_cell(d)),
    ]) for d in register]
    table = (dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("#", "Flat", "Bill", "Held", "Raised", "Reason (resolution)", "Status", "Decision")])),
                        html.Tbody(rows)], size="sm", style={"fontSize": "12px"})
             if rows else html.Div("No bill is disputed.", style={"fontSize": "12px", "color": "#888"}))
    return html.Div([
        html.Div("Disputed bills", style={"fontWeight": "600"}),
        html.Div("A held bill accrues no interest and is not counted as in default while the dispute is open; it stays outstanding in the books. "
                 "If the dispute is upheld the bill is cancelled and its entries reversed. If it is dismissed or withdrawn the bill stands and "
                 "interest for the held period is charged on the next run. A bill paid in part can be held but not upheld (that needs a refund).",
                 style={"fontSize": "11px", "color": "#888", "marginBottom": "6px"}),
        dbc.Row([
            dbc.Col(dcc.Dropdown(id="dsp-bill", options=[_bill_option(b) for b in bills], placeholder="Choose the disputed bill",
                                 style={"fontSize": "12px"}), md=6),
            dbc.Col(dbc.Input(id="dsp-reason", type="text", placeholder="Reason for the dispute", size="sm"), md=3),
            dbc.Col(dbc.Input(id="dsp-ref", type="text", placeholder="Resolution no. holding the bill", size="sm"), md=2),
            dbc.Col(dbc.Button("Hold bill", id="dsp-raise", color="warning", size="sm", n_clicks=0), md=1),
        ], className="mb-1"),
        html.Div(id="dsp-raise-msg", style={"fontSize": "12px", "marginBottom": "6px"}),
        table,
    ])


def register_dispute_callbacks(app):
    @app.callback(
        Output("dsp-raise-msg", "children"),
        Input("dsp-raise", "n_clicks"),
        State("dsp-bill", "value"), State("dsp-reason", "value"), State("dsp-ref", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _raise(n, bill, reason, ref):
        uid, sid = get_current_user_id(), get_current_society_id()
        if not n or not uid or not sid:
            return no_update
        if not bill:
            return html.Span("Choose the bill first.", style=_BAD)
        try:
            did = ds.raise_dispute(sid, int(bill), uid, reason or "", ref or "")
            return html.Span(f"Bill held (dispute #{did}). Reload the tab to see it in the register.", style=_OK)
        except ds.DisputeRefused as exc:
            return html.Span(str(exc), style=_BAD)

    @app.callback(
        Output({"type": "dsp-msg", "id": MATCH}, "children"),
        Input({"type": "dsp-decide", "id": MATCH}, "n_clicks"),
        State({"type": "dsp-outcome", "id": MATCH}, "value"),
        State({"type": "dsp-dreason", "id": MATCH}, "value"),
        State({"type": "dsp-dref", "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def _decide(n, outcome, reason, ref):
        uid, sid = get_current_user_id(), get_current_society_id()
        trig = ctx.triggered_id
        if not n or not trig or not uid or not sid:
            return no_update
        if not outcome:
            return html.Span("Choose the outcome.", style=_BAD)
        try:
            msg = ds.decide(sid, int(trig["id"]), outcome, uid, reason or "", ref or "")
            return html.Span(f"Done: {msg}. Reload the tab to see the new status.", style=_OK)
        except ds.DisputeRefused as exc:
            return html.Span(str(exc), style=_BAD)
