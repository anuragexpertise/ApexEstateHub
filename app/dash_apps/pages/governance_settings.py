import dash_bootstrap_components as dbc
from dash import html, dcc

def society_governance_kpi():
    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Span("Society Governance", style={"fontWeight": 700, "fontSize": "16px"}),
            ]),
            dbc.Row([
                dbc.Col(html.Small("KPI: Society Governance • RWA Compliance (UP) • Rules • Society By-Laws • Meetings & Resolution"), sm=12)
            ])
        ])
    ], className="mb-3 shadow-sm")

def rwa_content():
    return dbc.Card([
        dbc.CardBody([
            html.H6("RWA Compliance (UP)", className="fw-bold"),
            html.P("Informative only – cannot be edited.", className="text-muted mb-2"),
            dbc.Table([
                html.Thead(html.Tr([html.Th("Framework"), html.Th("Reference"), html.Th("Status")])),
                html.Tbody([
                    html.Tr([html.Th("Central Acts"), html.Td("Central Acts"), html.Td(html.Span("Informative", className="badge bg-secondary"))]),
                    html.Tr([html.Th("UP AOA Acts"), html.Td("UP_AOA Acts"), html.Td(html.Span("Informative", className="badge bg-secondary"))]),
                    html.Tr([html.Th("UPAOA Rules"), html.Td("UPAOA Rules"), html.Td(html.Span("Informative", className="badge bg-secondary"))]),
                    html.Tr([html.Th("UP Model By-Laws"), html.Td("UP Model By-Laws"), html.Td(html.Span("Informative", className="badge bg-secondary"))]),
                    html.Tr([html.Th("Society Policy"), html.Td("Society Policy"), html.Td(html.Span("Informative", className="badge bg-secondary"))]),
                ])
            ], bordered=True, hover=True, size="sm", striped=True)
        ])
    ], className="shadow-sm")

def rules_content():
    return dbc.Card([
        dbc.CardBody([
            html.H6("Rule Parameters", className="fw-bold"),
            html.Div(id="rules-table", className="mb-3"),
            html.H6("Scheduled changes", className="fw-bold mt-2"),
            html.Div(id="rules-scheduled", className="mb-3"),
            html.H6("Audit log (last 25)", className="fw-bold mt-2"),
            html.Div(id="rules-audit", className="mb-3"),
            html.H6("Cash-limit enforcement", className="fw-bold mt-2"),
            dbc.Row([
                dbc.Col(dcc.Dropdown(id="cash-limit-mode", options=[
                    {"label": "warn", "value": "warn"},
                    {"label": "block", "value": "block"},
                    {"label": "regime default", "value": "regime default"},
                ], clearable=False), sm=4, md=3),
                dbc.Col(dbc.Button("Save", id="cash-limit-save", color="primary", size="sm"), sm=2, md=2, className="align-self-end")
            ]),
            html.Div(id="cash-limit-msg", className="mt-2")
        ])
    ], className="shadow-sm")

def bylaws_content():
    return html.Div([
        dbc.Card([
            dbc.CardBody([
                html.H6("Society By-Laws", className="fw-bold"),
                html.Div(id="bylaws-list")
            ])
        ], className="shadow-sm mb-3"),
        dbc.Card([
            dbc.CardBody([
                html.H6("Record Policy Choice", className="fw-bold"),
                html.Small("For 'Society Policy settings'", className="text-muted"),
                dbc.Row([
                    dbc.Col(dbc.Input(id="pol-key", placeholder="Policy key (e.g. nodues_blocks_on)", size="sm"), sm=6),
                    dbc.Col(dbc.Input(id="pol-value", placeholder="Value (text)", size="sm"), sm=6)
                ], className="mt-2"),
                dbc.Row([
                    dbc.Col(dbc.Textarea(id="pol-reason", placeholder="Reason", rows=2, size="sm"), sm=12)
                ], className="mt-2"),
                dbc.Row([
                    dbc.Col(dcc.DatePickerSingle(id="pol-eff", display_format="DD-MM-YYYY", placeholder="Effective date"), sm=4),
                    dbc.Col(dbc.Button("Save Policy Choice", id="pol-save", color="primary", size="sm"), sm=4, className="align-self-end")
                ], className="mt-2"),
                html.Div(id="pol-msg", className="mt-2")
            ])
        ], className="shadow-sm")
    ])

def meetings_content():
    return dbc.Card([
        dbc.CardBody([
            dcc.Tabs([
                dcc.Tab(label="Meetings", children=html.Div([
                    dbc.Button("+ New Meeting", id="mtg-new", color="primary", size="sm", className="mb-2"),
                    html.Div(id="mtgs-list")
                ])),
                dcc.Tab(label="Resolutions", children=html.Div([
                    dbc.Button("+ New Resolution", id="res-new", color="primary", size="sm", className="mb-2"),
                    html.Div(id="ress-list")
                ])),
                dcc.Tab(label="Resolution - Enacted", children=html.Div(id="enacted-list", className="mt-2"))
            ])
        ])
    ], className="shadow-sm")

def render_tab_content(tab, rra=None, sid=None):
    if tab == "tab-rwa": return rwa_content()
    if tab == "tab-rules": return rules_content()
    if tab == "tab-bye": return bylaws_content()
    if tab == "tab-mtg": return meetings_content()
    return rwa_content()

def render_governance_tabs(role=None, sid=None, color="#1859b8"):
    tabs = dcc.Tabs(id="gov-tabs", value="tab-rwa", children=[
        dcc.Tab(label="RWA Compliance (UP)", value="tab-rwa"),
        dcc.Tab(label="Rules", value="tab-rules"),
        dcc.Tab(label="Society By-Laws", value="tab-bye"),
        dcc.Tab(label="Meetings & Resolution", value="tab-mtg"),
    ])
    gov_content = html.Div(id="gov-tab-content", className="mt-3")

    pbc_modal = dbc.Modal([
        dbc.ModalHeader("Provisional Bye-Law Choice"),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col(dbc.Label("Clause No"), width=4),
                dbc.Col(dbc.Input(id="pbc-clause-no", readOnly=True, size="sm"), width=8)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col(dbc.Label("Title"), width=4),
                dbc.Col(dbc.Input(id="pbc-title", readOnly=True, size="sm"), width=8)
            ], className="mb-2"),
            dbc.Label("Definition"),
            dbc.Textarea(id="pbc-def", readOnly=True, rows=2, size="sm", className="mb-2"),
            dbc.Label("Source Link"),
            dbc.Input(id="pbc-link", readOnly=True, size="sm", className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Layer"), dcc.Dropdown(id="pbc-layer", options=[{"label":x,"value":x} for x in ["Layer 1","Layer 2","Layer 3"]], clearable=False, value="Layer 2")], sm=6),
                dbc.Col([dbc.Label("Option"), dcc.Dropdown(id="pbc-option", options=[{"label":x,"value":x} for x in ["Adopted as-is","Adopted with variation","Not adopted"]], clearable=False, value="Adopted as-is")], sm=6)
            ], className="mb-2"),
            dbc.Label("Variation Text (if 'Adopted with variation')"),
            dbc.Textarea(id="pbc-variation", rows=2, size="sm", className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Effective Date"), dcc.DatePickerSingle(id="pbc-eff", display_format="DD-MM-YYYY")], sm=6),
            ], className="mb-2"),
            dbc.Label("Reason"),
            dbc.Textarea(id="pbc-reason", rows=2, size="sm"),
            html.Div(id="pbc-save-msg", className="mt-2")
        ]),
        dbc.ModalFooter([
            dbc.Button("Save", id="pbc-save", color="primary", size="sm"),
            dbc.Button("Close", id="pbc-close", color="secondary", size="sm")
        ])
    ], id="pbc-modal", is_open=False, size="lg")

    mtg_modal = dbc.Modal([
        dbc.ModalHeader("Record Meetings"),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([dbc.Label("Type"), dcc.Dropdown(id="mtg-type", options=[{"label":x,"value":x} for x in ["GBM","EGM","MC"]], clearable=False, value="GBM")], sm=6),
                dbc.Col([dbc.Label("Meeting No"), dbc.Input(id="mtg-no", size="sm")], sm=6)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Held On"), dcc.DatePickerSingle(id="mtg-held", display_format="DD-MM-YYYY")], sm=6),
                dbc.Col([dbc.Label("Venue"), dbc.Input(id="mtg-venue", size="sm")], sm=6)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Quorum Met"), dcc.Dropdown(id="mtg-quorum", options=[{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], clearable=False, value="yes")], sm=6),
                dbc.Col([dbc.Label("Minutes PDF (path/link)"), dbc.Input(id="mtg-minutes", size="sm")], sm=6)
            ], className="mb-2"),
            dbc.Label("Notes"),
            dbc.Textarea(id="mtg-notes", rows=2, size="sm"),
            html.Div(id="mtg-save-msg", className="mt-2")
        ]),
        dbc.ModalFooter([
            dbc.Button("Save", id="mtg-save", color="primary", size="sm"),
            dbc.Button("Close", id="mtg-close", color="secondary", size="sm")
        ])
    ], id="mtg-modal", is_open=False, size="lg")

    res_modal = dbc.Modal([
        dbc.ModalHeader("Record Resolutions"),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([dbc.Label("Meeting ID"), dbc.Input(id="res-meet", type="number", size="sm")], sm=4),
                dbc.Col([dbc.Label("Clause No"), dbc.Input(id="res-clause", size="sm")], sm=4),
                dbc.Col([dbc.Label("Subject"), dbc.Input(id="res-subj", size="sm")], sm=4)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Decision Type"), dcc.Dropdown(id="res-decision", options=[{"label":x,"value":x} for x in ["Adopt","Amend","Reject","Delegate"]], clearable=False, value="Adopt")], sm=4),
                dbc.Col([dbc.Label("Majority %"), dbc.Input(id="res-major", type="number", step="0.01", size="sm")], sm=4),
                dbc.Col([dbc.Label("Passed"), dcc.Dropdown(id="res-passed", options=[{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], clearable=False, value="yes")], sm=4)
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Passed Date"), dcc.DatePickerSingle(id="res-pdate", display_format="DD-MM-YYYY")], sm=4),
                dbc.Col([dbc.Label("Affects By-Law"), dcc.Dropdown(id="res-aff-bylaw", options=[{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], clearable=False, value="no")], sm=4),
                dbc.Col([dbc.Label("Affects Policy"), dcc.Dropdown(id="res-aff-pol", options=[{"label":"Yes","value":"yes"},{"label":"No","value":"no"}], clearable=False, value="no")], sm=4)
            ], className="mb-2"),
            dbc.Label("Policy Keys (comma separated)"),
            dbc.Input(id="res-polkeys", size="sm", className="mb-2"),
            dbc.Label("Resolution Text"),
            dbc.Textarea(id="res-text", rows=3, size="sm"),
            html.Div(id="res-save-msg", className="mt-2"),
            html.Div(id="exec-msg", className="mt-2")
        ]),
        dbc.ModalFooter([
            dbc.Button("Save", id="res-save", color="primary", size="sm"),
            dbc.Button("Close", id="res-close", color="secondary", size="sm")
        ])
    ], id="res-modal", is_open=False, size="lg")

    return html.Div([society_governance_kpi(), tabs, gov_content, pbc_modal, mtg_modal, res_modal])
