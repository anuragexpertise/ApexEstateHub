from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime

def security_portal_layout(active_tab="pass_evaluation"):
    """Complete Security Portal Layout"""
    
    if active_tab == "pass_evaluation":
        content = html.Div([
            html.H2("QR Code Scanner", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Scan QR Code", className="mb-0")),
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-qrcode fa-3x mb-3", style={"color": "#6c757d"}),
                                dcc.Input(
                                    id="security-qr-input",
                                    type="text",
                                    placeholder="Scan QR Code or Enter Code",
                                    className="form-control mb-3",
                                    style={"fontSize": "18px", "padding": "15px", "textAlign": "center"}
                                ),
                                dbc.Button("Validate", id="security-validate-btn", color="primary", size="lg", className="w-100 mb-3"),
                                html.Div(id="security-scan-result", className="text-center p-4")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Scans", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="recent-scans", children=[
                                dbc.ListGroup(id="scans-list", children=[
                                    dbc.ListGroupItem("No recent scans", className="text-muted text-center")
                                ])
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
            ])
        ])
    
    elif active_tab == "attendance":
        content = html.Div([
            html.H2("Attendance Tracking", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Today's Status", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="attendance-status", className="text-center mb-4"),
                            dbc.Row([
                                dbc.Col(dbc.Button("Clock In", id="clock-in-btn", color="success", size="lg", className="w-100"), width=6),
                                dbc.Col(dbc.Button("Clock Out", id="clock-out-btn", color="danger", size="lg", className="w-100"), width=6),
                            ]),
                            html.Hr(),
                            html.H6("Today's Hours", className="text-center"),
                            html.H3(id="today-hours", children="0 hrs", className="text-center text-primary")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Attendance History", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="attendance-history", children=[
                                dbc.Table([
                                    html.Thead(html.Tr([
                                        html.Th("Date"), html.Th("Clock In"), html.Th("Clock Out"), html.Th("Hours")
                                    ])),
                                    html.Tbody(id="attendance-history-body", children=[
                                        html.Tr([html.Td("No records found", colSpan=4, className="text-center")])
                                    ])
                                ], bordered=True, hover=True, responsive=True)
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
            ])
        ])
    
    elif active_tab == "security_events":
        content = html.Div([
            html.H2("Security Events", className="mb-4"),
            dbc.Card([
                dbc.CardHeader(html.H5("Event Log", className="mb-0")),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("Time"), html.Th("Event Type"), html.Th("Description"), html.Th("Status")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td(datetime.now().strftime("%H:%M:%S")), html.Td("Gate Access"), html.Td("Visitor entry at Main Gate"), html.Td(dbc.Badge("Normal", color="success"))]),
                            html.Tr([html.Td((datetime.now().replace(hour=10, minute=30)).strftime("%H:%M:%S")), html.Td("Vehicle Entry"), html.Td("Car KA-01-AB-1234 entered"), html.Td(dbc.Badge("Normal", color="success"))]),
                            html.Tr([html.Td((datetime.now().replace(hour=9, minute=15)).strftime("%H:%M:%S")), html.Td("Delivery"), html.Td("Amazon delivery at Block A"), html.Td(dbc.Badge("Normal", color="success"))]),
                        ])
                    ], bordered=True, hover=True, responsive=True)
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "security_receipt":
        content = html.Div([
            html.H2("New Receipt", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Col(dbc.Label("Receipt Type"), width=3),
                            dbc.Col(dcc.Dropdown(
                                id="security-receipt-type",
                                options=[
                                    {"label": "Maintenance Fee", "value": "maintenance"},
                                    {"label": "Visitor Pass Fee", "value": "visitor_pass"},
                                    {"label": "Vehicle Pass", "value": "vehicle_pass"},
                                    {"label": "Other", "value": "other"},
                                ],
                                placeholder="Select type"
                            ), width=9),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col(dbc.Label("Amount"), width=3),
                            dbc.Col(dbc.Input(id="security-receipt-amount", type="number", placeholder="Enter amount"), width=9),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col(dbc.Label("Paid By"), width=3),
                            dbc.Col(dbc.Input(id="security-receipt-paidby", type="text", placeholder="Payer name"), width=9),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col(dbc.Label("Payment Method"), width=3),
                            dbc.Col(dcc.Dropdown(
                                id="security-receipt-method",
                                options=[
                                    {"label": "Cash", "value": "cash"},
                                    {"label": "Card", "value": "card"},
                                    {"label": "UPI", "value": "upi"},
                                ],
                                placeholder="Select method"
                            ), width=9),
                        ], className="mb-3"),
                        dbc.Button("Generate Receipt", id="generate-security-receipt-btn", color="primary", className="mt-3")
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "security_users":
        content = html.Div([
            html.H2("User Management", className="mb-4"),
            dbc.Card([
                dbc.CardHeader([
                    html.H5("All Users", className="mb-0 d-inline-block"),
                    dbc.Input(id="security-user-search", type="text", placeholder="Search users...", 
                             className="float-end", style={"width": "200px"})
                ]),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("ID"), html.Th("Name"), html.Th("Apartment"),
                            html.Th("Role"), html.Th("Status"), html.Th("Actions")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td("1"), html.Td("Rajesh Sharma"), html.Td("A-101"),
                                    html.Td("Owner"), html.Td(dbc.Badge("Active", color="success")),
                                    html.Td(dbc.Button("View", size="sm", color="info"))]),
                            html.Tr([html.Td("2"), html.Td("Priya Singh"), html.Td("B-202"),
                                    html.Td("Owner"), html.Td(dbc.Badge("Active", color="success")),
                                    html.Td(dbc.Button("View", size="sm", color="info"))]),
                        ])
                    ], bordered=True, hover=True, responsive=True)
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    else:
        content = html.Div([
            html.H2(active_tab.replace('_', ' ').title(), className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    html.P(f"This is the {active_tab.replace('_', ' ').title()} section", 
                          className="text-muted text-center p-5")
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    return html.Div(content, style={"padding": "20px"})