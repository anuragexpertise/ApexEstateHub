# app/dash_apps/pages/privacy_page.py
"""
DPDP screens: the privacy notice shown before anyone reaches their dashboard, and the "Privacy & data rights" panel.

Everyone: read the notice, switch the optional announcements consent on or off, raise a request (access, correction,
erasure, grievance, nominee) and see its due date and outcome.
Administrator and Secretary: the society's request register with a response form, the erasure steps (notice, then erase,
which blanks the profile and never touches the ledger), the breach register, and publishing a new notice version.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import dpdp_service as dp

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0", "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "8px"}


def notice_view(society_id: int):
    n = dp.ensure_notice(society_id)
    return html.Div([
        html.H6(n["title"]),
        html.Div(f"Version {n['version']}, effective {n['effective_from']}", style=_MUTED),
        html.Pre(n["body_text"], style={"whiteSpace": "pre-wrap", "fontFamily": "inherit", "fontSize": "13px", "maxHeight": "46vh", "overflow": "auto",
                                        "background": "#fff", "border": "1px solid #e1e7ef", "borderRadius": "8px", "padding": "10px"})])


def gate_body(society_id: int):
    return html.Div([notice_view(society_id),
                     html.Div("The first two purposes are part of running the society and are recorded as the society's legitimate use. "
                              "The third is optional: you can say no and still use everything.", style=_MUTED)])


def _mine(society_id, user_id):
    active = {c["purpose"] for c in dp.my_consents(society_id, user_id) if not c["withdrawn_at"]}
    rows = [html.Tr([html.Td(r["request_type"].title()), html.Td(str(r["subject"])[:80]), html.Td(str(r["due_date"])),
                     html.Td(r["outcome"] or "pending"), html.Td(str(r["outcome_note"] or "")[:80])]) for r in dp.list_requests(society_id, user_id)]
    return html.Div([
        html.H6("My choices"),
        dbc.Switch(id="prv-ann", label="Send me society announcements by push and email", value="announcements" in active),
        html.H6("Ask the society", className="mt-3"),
        dbc.Row([dbc.Col(dbc.Select(id="prv-type", size="sm", value="access",
                                    options=[{"label": t.title(), "value": t} for t in dp.REQUEST_TYPES]), md=3),
                 dbc.Col(dbc.Input(id="prv-subject", size="sm", placeholder="What are you asking for?", maxLength=2000), md=7),
                 dbc.Col(dbc.Button("Send", id="prv-raise", color="primary", size="sm", n_clicks=0), md=2)], className="g-2"),
        html.Div(f"The society must answer within {dp.RESPONSE_DAYS} days.", style=_MUTED),
        dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Type", "Request", "Due", "Outcome", "Note")])), html.Tbody(rows)],
                  size="sm", style={"fontSize": "12px"}) if rows else html.Div("You have not raised a request.", style=_MUTED)])


def _manager(society_id):
    reqs = dp.list_requests(society_id)
    cards = []
    for r in reqs:
        rid = r["id"]
        head = html.Div([html.Strong(f"#{rid} {r['request_type'].title()}"), html.Span(f"  from {r['requester_key']}  due {r['due_date']}", style=_MUTED),
                         dbc.Badge("OVERDUE", color="danger", className="ms-2") if r["overdue"] else None,
                         dbc.Badge(r["outcome"] or "pending", color="secondary" if r["open_request"] else "success", className="ms-2")])
        body = [head, html.Div(str(r["subject"]), style={"fontSize": "12.5px"})]
        if r["open_request"]:
            if r["request_type"] == "erasure":
                blockers = dp.erasure_blockers(society_id, rid)
                if blockers:
                    body.append(html.Ul([html.Li(b) for b in blockers], style={"fontSize": "12px", "color": "#b03a2e"}))
                body.append(html.Div([
                    dbc.Button("Give 48-hour notice", id={"type": "prv-notice", "id": rid}, size="sm", color="warning", outline=True, n_clicks=0, className="me-2",
                               disabled=bool(blockers) or bool(r["erasure_notice_at"])),
                    dbc.Button("Erase profile", id={"type": "prv-erase", "id": rid}, size="sm", color="danger", n_clicks=0,
                               disabled=bool(blockers) or not r["erasure_notice_at"]),
                    html.Span(f"  Notice given {r['erasure_notice_at']:%d %b %H:%M}" if r["erasure_notice_at"] else "  Ledger lines are never touched.", style=_MUTED)]))
            body.append(dbc.Row([
                dbc.Col(dbc.Select(id={"type": "prv-outcome", "id": rid}, size="sm", value="granted" if r["request_type"] != "erasure" else "rejected",
                                   options=[{"label": o.title(), "value": o} for o in dp.OUTCOMES]), md=3),
                dbc.Col(dbc.Input(id={"type": "prv-note", "id": rid}, size="sm", placeholder="What was done, or why not", maxLength=2000), md=7),
                dbc.Col(dbc.Button("Respond", id={"type": "prv-respond", "id": rid}, size="sm", color="primary", n_clicks=0), md=2)], className="g-2 mt-1"))
        elif r["outcome_note"]:
            body.append(html.Div(str(r["outcome_note"]), style=_MUTED))
        cards.append(html.Div(body, style=_CARD))
    breaches = [html.Tr([html.Td(str(b["discovered_at"])[:16]), html.Td(str(b["description"])[:90]), html.Td(b["affected_persons"]), html.Td(b["status"]),
                         html.Td("sent" if b["intimation_sent"] else "not sent")]) for b in dp.list_breaches(society_id)]
    n = dp.current_notice(society_id) or {}
    return html.Div([
        html.Hr(), html.H6("Society register"),
        *(cards or [html.Div("No requests have been raised.", style=_MUTED)]),
        html.H6("Breach register", className="mt-3"),
        dbc.Row([dbc.Col(dbc.Input(id="prv-b-desc", size="sm", placeholder="What happened (at least 20 characters)", maxLength=4000), md=7),
                 dbc.Col(dbc.Input(id="prv-b-n", size="sm", type="number", min=0, placeholder="People affected"), md=3),
                 dbc.Col(dbc.Button("Log breach", id="prv-b-add", color="danger", size="sm", outline=True, n_clicks=0), md=2)], className="g-2"),
        dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Found", "What", "People", "Status", "Intimation")])), html.Tbody(breaches)],
                  size="sm", style={"fontSize": "12px"}, className="mt-2") if breaches else html.Div("No breach has been logged.", style=_MUTED),
        html.H6("Privacy notice", className="mt-3"),
        dbc.Input(id="prv-n-title", size="sm", value=n.get("title") or "", className="mb-1"),
        dbc.Textarea(id="prv-n-body", value=n.get("body_text") or "", rows=7, style={"fontSize": "12px"}),
        dbc.Button("Publish as a new version", id="prv-n-pub", color="secondary", size="sm", outline=True, n_clicks=0, className="mt-1"),
        html.Div("Everyone is asked to read a new version at their next sign-in.", style=_MUTED)])


def rights_body(society_id: int, user_id: int, role: str | None):
    parts = [html.Div(id="prv-msg"), dcc.Store(id="prv-dummy"), notice_view(society_id), _mine(society_id, user_id)]
    if dp.can_manage(society_id, user_id, role):
        parts.append(_manager(society_id))
    return parts
