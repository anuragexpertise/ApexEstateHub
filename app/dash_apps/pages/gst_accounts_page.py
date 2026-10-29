# app/dash_apps/pages/gst_accounts_page.py
"""
"GST Accounts": the screen where the society's CA (or the Treasurer, or the Secretary when no Treasurer is seated: the same
people who edit the TDS and GST rates) classifies each income and fund account for the GST aggregate-turnover worksheet.

An account is a taxable supply, an exempt supply, not a supply, or GST payable. The software never guesses a contested head
(interest, rent, tickets, fines, the sinking, repair and corpus funds): it stays UNCLASSIFIED until classified here, and while
the threshold falls between the classified and the unclassified amounts GST is not charged to members. Everyone else gets no
edit controls; the callback and the service re-check the right on the server. The society always comes from the server session.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app.services import gst_classification as gc
from app.services import tax_rate_service as trs

P = "gsa"          # component id prefix

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0 12px", "background": "#f6f8fb",
         "border": "1px solid #e1e7ef", "borderRadius": "8px"}
_STATE = {"above": ("Above the threshold: GST is charged", "danger"),
          "below": ("Below the threshold even counting every unclassified amount: GST is not charged", "success"),
          "indeterminate": ("The threshold falls between the classified and the unclassified amounts: GST is NOT being charged "
                            "until the open accounts are classified", "warning")}


def pid(part: str, acc_id) -> dict:
    return {"type": f"{P}-{part}", "id": int(acc_id)}


def _money(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def gate_banner(society_id: int, fy: int):
    g = gc.gate(society_id, fy)
    if not g:
        return None
    text, color = _STATE.get(g["state"], (g["state"], "secondary"))
    detail = (f"FY {fy}-{str(fy + 1)[2:]}: classified supplies Rs {_money(g['lower_bound'])}, unclassified Rs {_money(g['unclassified'])}, "
              f"threshold Rs {_money(g['threshold'])}. This is a worksheet on your own books, not a determination; the classification is the CA's.")
    return dbc.Alert([html.Strong(text), html.Div(detail, style={"fontSize": "12px", "marginTop": "4px"})], color=color,
                     className="py-2 mb-2", style={"fontSize": "12.5px"})


def row_cells(a: dict, can_edit: bool, message: str | None = None, ok: bool = True) -> list:
    cls = a.get("supply_class")
    label = gc.LABEL.get(cls, "Unclassified").split(" (")[0]
    src = a.get("class_source")
    badge = dbc.Badge(f"{label}" + (f" ({src})" if src not in (None, "society") else ""), color="warning" if cls is None else "light",
                      text_color="dark", className="ms-2")
    out = [html.Div([html.Strong(a["name"]), html.Span(f"  {a['tab_name'] or ''}", style=_MUTED), badge,
                     html.Span(f"   Rs {_money(a['amount'])} this year", style=_MUTED)])]
    if a.get("ref"):
        out.append(html.Div(f"Advice reference: {a['ref']}", style=_MUTED))
    if can_edit:
        out.append(html.Div([
            dbc.Select(id=pid("class", a["id"]), size="sm", value=a.get("own_class") or "",
                       options=[{"label": "Use the default / unclassified", "value": ""}] + [{"label": l, "value": v} for v, l in gc.CLASSES],
                       style={"width": "290px", "display": "inline-block", "marginRight": "8px"}),
            dbc.Input(id=pid("ref", a["id"]), size="sm", placeholder="Reference to the CA's / advocate's advice", value=a.get("ref") or "",
                      style={"width": "300px", "display": "inline-block", "marginRight": "8px"}),
            dbc.Button("Save", id=pid("save", a["id"]), color="primary", size="sm", n_clicks=0),
        ], style={"marginTop": "6px"}))
    if message:
        out.append(dbc.Alert(message, color="success" if ok else "danger", className="py-2 mt-2 mb-0", style={"fontSize": "12.5px"}))
    return out


def gst_accounts_body(society_id: int, can_edit: bool) -> list:
    fy = gc.current_fy()
    rows = gc.accounts(society_id, fy)
    out = [x for x in [gate_banner(society_id, fy)] if x is not None]
    if not rows:
        return out + [html.Div("This society has no credit-natured accounts.", style=_MUTED)]
    open_n = sum(1 for r in rows if r["supply_class"] is None)
    out.append(html.Div(f"{open_n} account(s) are unclassified; those that moved money this year are listed first." if open_n
                        else "Every account is classified.", style=_MUTED))
    for a in rows:
        out.append(html.Div(row_cells(a, can_edit), id=pid("row", a["id"]), style=_CARD))
    return out


def gst_accounts_tab(role: str, society_id: int | None):
    """The tab body, or None when this viewer has no business seeing it (the same rule as the TDS & GST Rates tab)."""
    if not society_id:
        return None
    can_edit = trs.may_edit_tax_rates(society_id)[0]
    if not can_edit and role != "admin":
        return None
    try:
        out = [html.Div(id=f"{P}-toast"), html.Div(gst_accounts_body(society_id, can_edit), id=f"{P}-body")]
        if not can_edit:
            out.insert(0, html.Div("Read-only. The CA, the Treasurer (or the Secretary when no Treasurer is seated) classify the accounts.",
                                   style={**_MUTED, "margin": "8px 0"}))
        return html.Div(out)
    except Exception:                      # one tab failing to load must not take the governance page down with it
        return html.Div("GST accounts could not be loaded just now. Please try again shortly.", style=_MUTED)
