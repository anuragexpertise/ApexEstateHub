# app/dash_apps/pages/committee_page.py
"""
Society governance -> "Managing Committee" tab.

Everyone in the society can see who serves on the committee. Only the society admin sees the forms to appoint and
end an office-bearer. The society always comes from the server session (the callbacks), never from this layout.

An office belongs to a FLAT (committee_offices.apartment_id), so the form is flat-first: pick the flat, and the owner's
name and the logins that may hold the office follow from it. Eligibility (bye-law 7: a flat in arrears cannot hold
office) is shown up front and enforced by the database.
"""
from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import committee_service as cs

P = "mc"          # component id prefix

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0 14px", "background": "#f6f8fb",
         "border": "1px solid #e1e7ef", "borderRadius": "8px"}


def _money(v) -> str:
    try:
        return f"₹{float(v):,.0f}"
    except (TypeError, ValueError):
        return "₹0"


def _fmt(d) -> str:
    return d.strftime("%d %b %Y") if hasattr(d, "strftime") else (str(d) if d else "—")


def standing_badge(row: dict):
    """Good standing, or arrears that bar the flat from holding office (bye-law 7)."""
    if row.get("ineligible_stand"):
        return dbc.Badge(f"Arrears {_money(row.get('dues_outstanding'))}", color="danger", pill=True)
    return dbc.Badge("Good standing", color="success", pill=True)


def vacancy_strip(society_id: int):
    s = cs.summary(society_id)
    items = [html.Span([html.Strong(str(s["seated"])), " seated"], style={"marginRight": "22px"})]
    if s["vacant_core"]:
        items.append(html.Span([html.I(className="fas fa-exclamation-triangle me-1"),
                                "Vacant: " + ", ".join(s["vacant_core"])],
                               style={"color": "#b26a00", "fontWeight": "600", "marginRight": "22px"}))
    else:
        items.append(html.Span("President, Secretary and Treasurer are seated",
                               style={"color": "#1b7a3d", "marginRight": "22px"}))
    if s["in_arrears"]:
        items.append(html.Span(f"{s['in_arrears']} office-bearer flat(s) in arrears",
                               style={"color": "#b02a37", "fontWeight": "600"}))
    return html.Div(items, style={**_CARD, "fontSize": "13px"})


def committee_table(society_id: int):
    rows = cs.current_committee(society_id)
    if not rows:
        return html.Div("No office-bearers are recorded yet.", style=_MUTED)
    head = html.Thead(html.Tr([html.Th(h) for h in ("Office", "Holder", "Flat", "Term from", "Standing", "Login")]))
    body = html.Tbody([html.Tr([
        html.Td(r["office_label"], style={"fontWeight": "600"}),
        html.Td(r["holder_name"]),
        html.Td(r["flat_number"]),
        html.Td(_fmt(r["term_start"])),
        html.Td(standing_badge(r)),
        html.Td(dbc.Badge("Can sign", color="primary", pill=True) if r.get("can_sign")
                else html.Span("none" if r.get("user_id") is None else "member", style=_MUTED)),
    ]) for r in rows])
    return dbc.Table([head, body], bordered=False, hover=True, size="sm", responsive=True,
                     style={"fontSize": "13px"})


def history_table(society_id: int):
    rows = cs.committee_history(society_id)
    if not rows:
        return None
    head = html.Thead(html.Tr([html.Th(h) for h in ("Office", "Holder", "Flat", "From", "To", "Reason")]))
    body = html.Tbody([html.Tr([html.Td(r["office_label"]), html.Td(r["holder_name"]), html.Td(r["flat_number"]),
                                html.Td(_fmt(r["term_start"])), html.Td(_fmt(r["term_end"])),
                                html.Td(r.get("ended_reason") or "—")]) for r in rows])
    return html.Div([html.H6("Past office-bearers", style={"marginTop": "16px"}),
                     dbc.Table([head, body], size="sm", responsive=True, style={"fontSize": "12.5px"})])


def committee_body(society_id: int):
    """The refreshable part: vacancy strip, current committee, history."""
    return [vacancy_strip(society_id), committee_table(society_id), history_table(society_id) or html.Div()]


def end_options(society_id: int) -> list[dict]:
    return [{"label": f"{r['office_label']} — {r['holder_name']} ({r['flat_number']})", "value": r["office_id"]}
            for r in cs.current_committee(society_id)]


def flat_options(society_id: int) -> list[dict]:
    out = []
    for f in cs.flat_choices(society_id):
        tag = "  ⚠ arrears" if f.get("ineligible_stand") else ""
        out.append({"label": f"{f['flat_number']} — {f.get('owner_name') or 'owner not recorded'}{tag}",
                    "value": f["id"]})
    return out


def _field(label, control, hint=None):
    return html.Div([html.Label(label, style={"fontSize": "12px", "fontWeight": "600", "marginBottom": "2px"}),
                     control] + ([html.Div(hint, style=_MUTED)] if hint else []), style={"marginBottom": "10px"})


def appoint_form(society_id: int):
    return html.Div([
        html.H6("Appoint an office-bearer"),
        html.Div("The office belongs to a flat. Pick the flat first; the owner and the logins that can hold the office "
                 "follow. A flat in arrears cannot hold office (bye-law 7).", style=_MUTED),
        dbc.Row([
            dbc.Col(_field("Office", dcc.Dropdown(
                id=f"{P}-office", clearable=False, value="president",
                options=[{"label": label + ("" if single else " (several allowed)"), "value": code}
                         for code, label, single, _r in cs.OFFICES])), md=4),
            dbc.Col(_field("Flat", dcc.Dropdown(id=f"{P}-flat", options=flat_options(society_id),
                                                placeholder="Select the flat…")), md=4),
            dbc.Col(_field("Login (flat owner)", dcc.Dropdown(id=f"{P}-user", options=[], placeholder="Pick a flat first"),
                           "A login lets the office-bearer sign and approve. Leave empty to record the office by name only."),
                    md=4),
        ]),
        html.Div(id=f"{P}-hint", style={"marginBottom": "8px", "fontSize": "13px"}),
        dbc.Row([
            dbc.Col(_field("Name of office-bearer", dbc.Input(id=f"{P}-name", type="text", maxLength=100)), md=4),
            dbc.Col(_field("Term starts", dcc.DatePickerSingle(id=f"{P}-start", date=date.today(),
                                                               display_format="DD MMM YYYY")), md=3),
            dbc.Col(_field("Term ends (optional)", dcc.DatePickerSingle(id=f"{P}-term-end", date=None,
                                                                        display_format="DD MMM YYYY")), md=3),
            dbc.Col(_field("Resolution / minutes ref.", dbc.Input(id=f"{P}-ref", type="text", maxLength=255,
                                                                  placeholder="e.g. GBM/2026-27/01")), md=2),
        ]),
        dbc.Button([html.I(className="fas fa-user-plus me-2"), "Appoint"], id=f"{P}-appoint-btn", color="primary",
                   size="sm"),
    ], style=_CARD)


def end_form(society_id: int):
    return html.Div([
        html.H6("End an office"),
        html.Div("Use this when an office-bearer resigns or their term is over. They keep their flat and login; "
                 "only the powers the office gave them are withdrawn.", style=_MUTED),
        dbc.Row([
            dbc.Col(_field("Office to end", dcc.Dropdown(id=f"{P}-end-office", options=end_options(society_id),
                                                         placeholder="Select…")), md=6),
            dbc.Col(_field("Reason", dbc.Input(id=f"{P}-end-reason", type="text", maxLength=200,
                                               placeholder="e.g. Resigned on 12 Oct 2026")), md=6),
        ]),
        dbc.Button([html.I(className="fas fa-user-minus me-2"), "End office"], id=f"{P}-end-btn", color="warning",
                   size="sm", outline=True),
    ], style=_CARD)


def committee_tab(role: str, society_id):
    """Tab content: the committee for everyone; the forms for the society admin."""
    if not society_id:
        return [html.Div("Society not resolved.", style=_MUTED)]
    is_admin = role == "admin"
    try:
        out = [html.Div(id=f"{P}-toast"),
               html.Div(committee_body(society_id), id=f"{P}-body")]
        if is_admin:
            out += [appoint_form(society_id), end_form(society_id),
                    html.Div("The administrator's interim secretary / treasurer authority is not changed by these "
                             "appointments.", style=_MUTED)]
        else:
            out.append(html.Div("Read-only view. The society admin records appointments.", style=_MUTED))
        return out
    except Exception:       # one tab failing to load must not take the whole governance page down with it
        return [html.Div("The committee could not be loaded just now. Please try again shortly.", style=_MUTED)]
