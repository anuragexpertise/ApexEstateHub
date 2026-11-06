# app/dash_apps/pages/team_page.py
"""
Admin portal -> "Team Logins": create and manage the logins of the society's Accountant, Supervisor, Staff and
Auditor. Admin only; the society always comes from the server session (the callbacks), never from this layout.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import team_service as ts

P = "tm"          # component id prefix

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "14px 16px", "margin": "0 0 16px", "background": "#fff",
         "border": "1px solid #e1e7ef", "borderRadius": "10px"}


def _fmt(d) -> str:
    return d.strftime("%d %b %Y, %H:%M") if hasattr(d, "strftime") else "never"


def role_badge(role: str):
    return dbc.Badge(ts.ROLE_LABEL.get(role, role), pill=True,
                     style={"background": ts.ROLE_COLOR.get(role, "#64748b"), "fontWeight": 600})


def role_guide():
    """One card per role: what that login can and cannot do. Colours match the portal themes."""
    cards = []
    for code, label, color, blurb in ts.TEAM_ROLES:
        cards.append(html.Div([
            html.Div(label, style={"fontWeight": 700, "color": "#15304f", "marginBottom": "3px"}),
            html.Div(blurb, style=_MUTED),
        ], style={"borderLeft": f"4px solid {color}", "padding": "6px 12px", "background": "#f6f8fb",
                  "borderRadius": "6px"}))
    return html.Div(cards, style={"display": "grid", "gap": "10px",
                                  "gridTemplateColumns": "repeat(auto-fit,minmax(230px,1fr))", "marginBottom": "16px"})


def team_table(society_id: int):
    rows = ts.list_team(society_id)
    if not rows:
        return html.Div("No Accountant, Supervisor, Staff or Auditor logins yet. Create the first one above.",
                        style=_MUTED)
    head = html.Thead(html.Tr([html.Th(h) for h in ("Name", "Login email", "Role", "Status", "Last sign-in")]))
    body = html.Tbody([html.Tr([
        html.Td(r.get("name") or "—", style={"fontWeight": 600}),
        html.Td(r["email"]),
        html.Td(role_badge(r["role"])),
        html.Td(dbc.Badge("Active", color="success", pill=True) if r.get("active") is not False
                else dbc.Badge("Disabled", color="secondary", pill=True)),
        html.Td(_fmt(r.get("last_login")) if r.get("last_login") else
                html.Span("not yet — must set a password" if r.get("must_change_password") else "never", style=_MUTED)),
    ]) for r in rows])
    return dbc.Table([head, body], hover=True, size="sm", responsive=True, style={"fontSize": "13px"})


def member_options(society_id: int) -> list[dict]:
    return [{"label": f"{r.get('name') or r['email']} — {ts.ROLE_LABEL[r['role']]}"
                      f"{'' if r.get('active') is not False else ' (disabled)'}", "value": r["id"]}
            for r in ts.list_team(society_id)]


def _field(label, control, hint=None):
    return html.Div([html.Label(label, style={"fontSize": "12px", "fontWeight": 600, "marginBottom": "2px"}),
                     control] + ([html.Div(hint, style=_MUTED)] if hint else []), style={"marginBottom": "10px"})


def create_form():
    return html.Div([
        html.H6("Create a login", style={"fontWeight": 700}),
        html.Div(id=f"{P}-role-hint", style={**_MUTED, "marginBottom": "10px"}),
        dbc.Row([
            dbc.Col(_field("Role", dcc.Dropdown(
                id=f"{P}-role", clearable=False, value="accountant",
                options=[{"label": label, "value": code} for code, label, _c, _b in ts.TEAM_ROLES])), md=4),
            dbc.Col(_field("Full name", dbc.Input(id=f"{P}-name", type="text", maxLength=100,
                                                  placeholder="As on their ID")), md=4),
            dbc.Col(_field("Login email", dbc.Input(id=f"{P}-email", type="email", maxLength=100,
                                                    placeholder="name@example.com"),
                           "This is what they sign in with."), md=4),
        ]),
        dbc.Row([
            dbc.Col(_field("Temporary password", dbc.Input(id=f"{P}-password", type="text", autoComplete="off",
                                                           placeholder="at least 8 characters"),
                           "They must replace it at first sign-in."), md=6),
            dbc.Col(html.Div(dbc.Button([html.I(className="fas fa-random me-2"), "Generate one"],
                                        id=f"{P}-gen", color="light", size="sm"),
                             style={"paddingTop": "22px"}), md=3),
        ]),
        dbc.Button([html.I(className="fas fa-user-plus me-2"), "Create login"], id=f"{P}-create", color="primary"),
    ], style=_CARD)


def manage_form(society_id: int):
    return html.Div([
        html.H6("Manage an existing login", style={"fontWeight": 700}),
        dbc.Row([
            dbc.Col(_field("Login", dcc.Dropdown(id=f"{P}-member", options=member_options(society_id),
                                                 placeholder="Choose a login")), md=5),
            dbc.Col(_field("New temporary password (to reset)",
                           dbc.Input(id=f"{P}-newpw", type="text", autoComplete="off",
                                     placeholder="at least 8 characters")), md=4),
        ]),
        html.Div([
            dbc.Button("Reset password", id=f"{P}-reset", color="warning", size="sm", className="me-2"),
            dbc.Button("Disable login", id=f"{P}-disable", color="secondary", size="sm", className="me-2"),
            dbc.Button("Enable login", id=f"{P}-enable", color="success", size="sm"),
        ]),
        html.Div("Disabling stops the person signing in at once; nothing they recorded is removed.",
                 style={**_MUTED, "marginTop": "8px"}),
    ], style=_CARD)


def team_tab(role: str, society_id):
    """Admin-only tab body."""
    if role != "admin":
        return html.Div("Only the society admin manages these logins.", style=_MUTED)
    if not society_id:
        return html.Div("Society not resolved.", style=_MUTED)
    return html.Div([
        html.Div(id=f"{P}-toast"),
        role_guide(),
        create_form(),
        html.Div([html.H6("Logins", style={"fontWeight": 700}), html.Div(team_table(society_id), id=f"{P}-body")],
                 style=_CARD),
        manage_form(society_id),
    ])
