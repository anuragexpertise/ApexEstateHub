# app/dash_apps/pages/tax_rates_page.py
"""
"TDS & GST Rates": the screen where the society's CA, Treasurer (or Secretary when no Treasurer is seated) edit the TDS
and GST figures the Admin typed in the Setup Wizard, and confirm them.

Shown in two places: the owner portal's Settings > governance tabs (so the Treasurer / Secretary, who log in as
owners, can reach it) and the Accountant portal's "TDS & GST" tab (the CA). Everyone else gets no edit controls; the
callbacks and the service re-check the right on the server, so hiding the controls is only a convenience.
The society always comes from the server session (the callbacks), never from this layout.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import tax_rate_service as trs

P = "tr"          # component id prefix

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0 14px", "background": "#f6f8fb",
         "border": "1px solid #e1e7ef", "borderRadius": "8px"}


def _fmt_dt(d) -> str:
    return d.strftime("%d %b %Y") if hasattr(d, "strftime") else (str(d) if d else "--")


def _num_text(v) -> str:
    return "" if v is None else f"{float(v):g}"


def status_banner(society_id: int):
    st = trs.status(society_id)
    if st["pending"]:
        return dbc.Alert([html.I(className="fas fa-exclamation-triangle me-2"), html.Strong("Pending CA confirmation. "),
                          "The TDS and GST figures below were entered at setup (or edited since) and are provisional "
                          "until the CA or Treasurer confirms them."], color="warning", className="py-2 mb-3",
                         style={"fontSize": "12.5px"})
    who = f" by {st['confirmed_by']}" if st.get("confirmed_by") else ""
    return dbc.Alert([html.I(className="fas fa-check-circle me-2"), f"Confirmed{who} on {_fmt_dt(st['confirmed_at'])}."],
                     color="success", className="py-2 mb-3", style={"fontSize": "12.5px"})


def _inp(kind: str, rid, value, width="92px"):
    return dbc.Input(id={"type": f"{P}-{kind}", "id": rid}, type="number", value=value, min=0, step="any",
                     size="sm", style={"width": width})


def tax_rates_body(society_id: int, can_edit: bool) -> list:
    gst = trs.gst_row(society_id) or {}
    rows = trs.tds_rows(society_id)

    # GST
    if can_edit:
        gst_block = html.Div([
            html.H6("GST rates", className="mb-2"),
            html.Div([
                html.Span("CGST %", style={"marginRight": "6px", "fontSize": "13px"}),
                dbc.Input(id=f"{P}-cgst", type="number", min=0, step="any", size="sm", value=gst.get("cgst_rate_pct"),
                          style={"width": "100px", "display": "inline-block", "marginRight": "18px"}),
                html.Span("SGST %", style={"marginRight": "6px", "fontSize": "13px"}),
                dbc.Input(id=f"{P}-sgst", type="number", min=0, step="any", size="sm", value=gst.get("sgst_rate_pct"),
                          style={"width": "100px", "display": "inline-block", "marginRight": "18px"}),
                dbc.Button("Save GST rates", id=f"{P}-gst-save", color="primary", size="sm"),
            ]),
            html.Div("Use the figures your CA advises. Saving puts the rates back to pending until confirmed.",
                     style=_MUTED),
        ], style=_CARD)
    else:
        txt = (f"CGST {_num_text(gst.get('cgst_rate_pct'))}% / SGST {_num_text(gst.get('sgst_rate_pct'))}%"
               if gst else "Not entered yet.")
        gst_block = html.Div([html.H6("GST rates", className="mb-2"), html.Div(txt, style={"fontSize": "13px"})],
                             style=_CARD)

    # TDS
    head = html.Thead(html.Tr([html.Th(h) for h in
                               ("Section", "Nature", "Rate %", "Rate without PAN %", "Single-bill limit", "Annual limit")]))
    body_rows = []
    for r in rows:
        rid = r["id"]
        label = r["section"] + (f" ({r['discriminator']})" if r.get("discriminator") else "")
        if can_edit:
            cells = [_inp("rate", rid, r.get("rate")), _inp("rate-nopan", rid, r.get("rate_no_pan")),
                     _inp("single", rid, r.get("single_bill_threshold"), "110px"),
                     _inp("annual", rid, r.get("annual_aggregate_threshold"), "110px")]
        else:
            cells = [_num_text(r.get("rate")), _num_text(r.get("rate_no_pan")),
                     _num_text(r.get("single_bill_threshold")), _num_text(r.get("annual_aggregate_threshold"))]
        body_rows.append(html.Tr([html.Td(label), html.Td(r.get("nature_of_income") or "--",
                                                          style={"fontSize": "12px", "color": "#445"})]
                                 + [html.Td(c) for c in cells]))
    if not rows:
        tds_block = html.Div([html.H6("TDS rates", className="mb-2"),
                              html.Div("No TDS rates are set. Until the CA's rates are entered, no TDS rate exists for "
                                       "this society.", style=_MUTED)], style=_CARD)
    else:
        tds_block = html.Div([
            html.H6("TDS rates", className="mb-2"),
            html.Div(dbc.Table([head, html.Tbody(body_rows)], size="sm", bordered=True, className="mb-2"),
                     style={"overflowX": "auto"}),
            (dbc.Button("Save TDS rates", id=f"{P}-tds-save", color="primary", size="sm") if can_edit else None),
            (html.Div("A blank box leaves that figure as it is.", style=_MUTED) if can_edit else None),
        ], style=_CARD)

    actions = []
    if can_edit:
        st = trs.status(society_id)
        actions = [html.Div([
            dbc.Button("Confirm TDS & GST rates", id=f"{P}-confirm", color="success", size="sm",
                       disabled=not st["pending"]),
            html.Span("  Confirms the figures as they stand now. Any later edit makes them pending again.",
                      style=_MUTED)], style={**_CARD, "background": "#f1faf4"})]
    return [status_banner(society_id), gst_block, tds_block, *actions]


def tax_rates_tab(role: str, society_id: int | None):
    """Returns the tab body, or None when this viewer has no business seeing it."""
    if not society_id:
        return None
    can_edit = trs.may_edit_tax_rates(society_id)[0]
    if not can_edit and role != "admin":
        return None
    out = [html.Div(id=f"{P}-toast"), html.Div(tax_rates_body(society_id, can_edit), id=f"{P}-body")]
    if role == "admin" and not can_edit:
        out.insert(0, html.Div("Read-only. You enter the first figures in the Setup Wizard; after setup the CA, the "
                               "Treasurer (or the Secretary when no Treasurer is seated) edit and confirm them.",
                               style={**_MUTED, "margin": "8px 0"}))
    return html.Div(out)


def tax_rates_page(role: str, society_id: int | None, color: str = "#7c3aed"):
    """Whole page for the Accountant portal tab."""
    body = tax_rates_tab(role, society_id)
    if body is None:
        body = html.Div("TDS & GST rates are not available to this login.", style=_MUTED)
    return html.Div([html.H5("TDS & GST Rates", style={"fontWeight": "700", "marginTop": "8px"}), body])
