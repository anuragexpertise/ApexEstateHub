# app/dash_apps/pages/governance_guide.py
"""
Information tables shown on the Master, Admin and Owner portals (on 'RWA Compliance (UP)'):

    1. The layers - how the Act, the Model Bye-Laws, society policy and board decisions stack up.
    2. Who edits what - what Master, Admin and Owner can each do.

Purely informational and database-free. WHO_EDITS must match what the portals really offer;
test/test_governance_settings.py checks every "Edit" against a form that exists.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

EDIT, VIEW, NONE = "edit", "view", "none"

# (layer, name, what it is, decided by, where it is managed)
LAYERS = [
    ("0", "Act & Rules",
     "Figures and rules laid down by the UP Apartment Act 2010, its Rules 2011 and the Model Bye-Laws (marked "
     "Statute), plus platform settings (marked Policy). They apply to every society.",
     "The law. Master records changes.",
     "Master: AOA Rule Editor. Everyone sees it under Rules."),
    ("1", "Model Bye-Law adoption",
     "Each of the 58 Model Bye-Law 2011 clauses is adopted as-is, adopted with a variation, or - for non-statutory "
     "clauses only - not adopted. Clauses 7, 39, 49 and 55 are enforced by the engine and cannot be dropped "
     "unless the society's policy allows it.",
     "General Body (GBM / EGM) resolution",
     "Admin: Society By-laws (choice), Meetings & Resolutions (resolution)."),
    ("2", "Society policy",
     "A society tightens an adopted clause, for example which overdue bills bar a vote. It can never loosen the "
     "Model Bye-Law.",
     "General Body (GBM / EGM) resolution",
     "Admin: Society By-laws (choice), Meetings & Resolutions (resolution)."),
    ("3", "Board decision",
     "An operating limit set within the bounds of the adopted clause and the society policy.",
     "Managing Committee (MC) resolution",
     "Admin: Society By-laws (choice), Meetings & Resolutions (resolution)."),
]
LAYERS_NOTE = ("A society's choice at layers 1 to 3 stays provisional until a matching passed resolution is recorded; "
               "recording it activates the choice automatically. A lower layer can never loosen a higher one.")

# (key, what, master, admin, owner, note)
WHO_EDITS = [
    ("catalog", "Legal instrument catalog (RWA Compliance (UP))", EDIT, VIEW, VIEW,
     "Master edits status, provisions, source link and verified date."),
    ("rules", "Statute & Policy rule values (Rules)", EDIT, VIEW, VIEW,
     "Master uses Change a rule; each change is dated and audited."),
    ("audit", "Scheduled changes & audit log", VIEW, VIEW, VIEW,
     "Master sees all societies; admin and owner see their own society."),
    ("cash", "Cash-limit enforcement", NONE, EDIT, VIEW, "Specific to each society."),
    ("bye", "Society Bye-Laws register (adopt / vary / not adopt)", NONE, EDIT, VIEW,
     "Saved as provisional until the resolution is recorded."),
    ("policy", "Society policy settings", NONE, EDIT, VIEW, "Saved as provisional until the resolution is recorded."),
    ("meetings", "Meetings (GBM / EGM / MC) and Resolutions", NONE, EDIT, VIEW,
     "Recording a passed resolution activates the matching choice."),
    ("enact", "Resolution enactment", NONE, EDIT, VIEW,
     "Regime-wide changes are made by Master through Change a rule."),
]


def _cell(kind: str):
    if kind == EDIT:
        return html.Td(dbc.Badge("Edit", color="success", pill=True), style={"textAlign": "center"})
    if kind == VIEW:
        return html.Td(dbc.Badge("View", color="secondary", pill=True), style={"textAlign": "center"})
    return html.Td("—", style={"textAlign": "center", "color": "#999"})


def render_governance_guide() -> html.Div:
    th = {"fontSize": "11px"}
    layers = dbc.Table([
        html.Thead(html.Tr([html.Th(h, style=th) for h in ("Layer", "What it is", "Decided by", "Managed in")])),
        html.Tbody([html.Tr([
            html.Td(html.Strong(f"{n} · {name}", style={"fontSize": "12px"}), style={"whiteSpace": "nowrap"}),
            html.Td(html.Small(what)), html.Td(html.Small(by)), html.Td(html.Small(where, className="text-muted")),
        ]) for n, name, what, by, where in LAYERS]),
    ], bordered=True, responsive=True, size="sm", style={"fontSize": "12px"})

    matrix = dbc.Table([
        html.Thead(html.Tr([html.Th("What", style=th)] +
                           [html.Th(h, style={**th, "textAlign": "center"}) for h in ("Master", "Admin", "Owner")] +
                           [html.Th("Note", style=th)])),
        html.Tbody([html.Tr([html.Td(html.Strong(what, style={"fontSize": "12px"})),
                             _cell(m), _cell(a), _cell(o), html.Td(html.Small(note, className="text-muted"))])
                    for _k, what, m, a, o, note in WHO_EDITS]),
    ], bordered=True, responsive=True, size="sm", style={"fontSize": "12px"})

    return html.Div([
        html.H6("The layers", style={"marginTop": "22px", "fontWeight": "700", "color": "#15304f"}),
        html.Small("How the law and your society's own decisions stack up, from the top down.", className="text-muted d-block mb-2"),
        layers,
        html.Small(LAYERS_NOTE, className="text-muted d-block mb-3"),
        html.H6("Who edits what", style={"marginTop": "18px", "fontWeight": "700", "color": "#15304f"}),
        html.Small([dbc.Badge("Edit", color="success", pill=True, className="me-1"), "can change   ",
                    dbc.Badge("View", color="secondary", pill=True, className="me-1"), "read-only   ",
                    "— not offered in that portal"], className="text-muted d-block mb-2"),
        matrix,
    ], id="governance-guide")
