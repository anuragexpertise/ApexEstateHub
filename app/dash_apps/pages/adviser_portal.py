# app/dash_apps/pages/adviser_portal.py
"""The adviser's own screen (Auditor, CA, Advocate): the appointment, what the role may read, and the masked ledger export."""
from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.security import adviser_access as aa
from database.db_manager import db

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0", "background": "#f6f8fb", "border": "1px solid #e1e7ef", "borderRadius": "8px"}


def adviser_portal_page(user_id: int | None, society_id: int | None):
    cur = aa.in_force(user_id) if user_id else None
    if not cur:
        row = aa.appointment(user_id) if user_id else None
        why = "Your appointment has ended or was revoked." if row and (not row["active"] or row["term_end"] < date.today()) else \
              "Your appointment has not been signed by the President, Secretary and Treasurer yet."
        return html.Div([html.H5("Adviser access"), dbc.Alert(why + " Ask the society to appoint or renew you.", color="warning")], style={"padding": "16px"})
    appt = db._execute("SELECT * FROM adviser_appointments WHERE id=%s", (cur["appointment_id"],), fetch_one=True)
    left = (appt["term_end"] - date.today()).days
    caps = aa.CAPABILITIES[cur["kind"]]
    sid = cur["society_id"]
    res = db._execute("""SELECT r.id, r.body, r.status, r.legacy, r.legacy_outcome, m.held_on, m.type FROM resolutions r JOIN meetings m ON m.id=r.meeting_id
                          WHERE m.society_id=%s ORDER BY m.held_on DESC, r.id DESC LIMIT 50""", (sid,), fetch_all=True) or []
    ag = db._execute("SELECT id FROM society_agreements WHERE society_id=%s", (sid,), fetch_one=True)
    body = [
        html.H5(f"{cur['kind'].title()} access"),
        html.Div([html.Strong(appt["name"]), html.Span(f"  {appt['firm'] or ''}", style=_MUTED),
                  html.Div(f"Term {appt['term_start']:%d %b %Y} to {appt['term_end']:%d %b %Y}: {left} day(s) left. {appt['scope'] or ''}", style=_MUTED)], style=_CARD),
        html.H6("Resolutions"),
        dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Date", "Meeting", "Decision", "Status")])),
                   html.Tbody([html.Tr([html.Td(f"{r['held_on']:%d %b %Y}"), html.Td(r["type"]), html.Td((r["body"] or "")[:110]),
                                        html.Td("legacy evidence" if r["legacy"] else r["status"])]) for r in res])],
                  size="sm", style={"fontSize": "12px"}) if res else html.Div("No resolutions recorded.", style=_MUTED),
        html.H6("Agreement", className="mt-3"),
        html.A("Verify the signed Agreement", href=f"/verify/agreement/{ag['id']}", target="_blank") if ag else html.Div("None.", style=_MUTED),
        html.H6("The books", className="mt-3"),
    ]
    if "export" in caps:
        body += [html.Div("Ledger as CSV. Owner and member names are hidden and the file carries your name as a watermark. Every download is logged.", style=_MUTED),
                 dbc.Button("Download ledger", id="adv-export-btn", color="primary", size="sm", n_clicks=0, className="mt-1"),
                 dcc.Download(id="adv-export-dl"), html.Div(id="adv-export-msg", className="mt-2")]
    else:
        body += [dbc.Alert(f"An {cur['kind'].title()} reads resolutions and legal records only. The ledger is closed to this role.", color="secondary", className="py-2"),
                 dcc.Download(id="adv-export-dl"), html.Div(id="adv-export-msg"), dbc.Button(id="adv-export-btn", n_clicks=0, style={"display": "none"})]
    return html.Div(body, style={"padding": "16px", "maxWidth": "980px"})
