from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime

def vendor_portal_layout(active_tab="dashboard"):
    """Complete Vendor Portal Layout"""
    
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Vendor Dashboard", className="mb-4", style={"color": "#2c3e50"}),
            
            # KPI Cards
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-briefcase fa-2x", style={"color": "#ff9800"}),
                                html.H4("Active Services", className="card-title mt-2"),
                                html.H2(id="vendor-active-services", children="3", className="card-text"),
                                html.Small("This month", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #ff9800"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-rupee-sign fa-2x", style={"color": "#4caf50"}),
                                html.H4("Total Earnings", className="card-title mt-2"),
                                html.H2(id="vendor-total-earnings", children="₹25,000", className="card-text"),
                                html.Small("This quarter", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #4caf50"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-clock fa-2x", style={"color": "#2196f3"}),
                                html.H4("Pending Requests", className="card-title mt-2"),
                                html.H2(id="vendor-pending-requests", children="5", className="card-text"),
                                html.Small("Awaiting response", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #2196f3"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-star fa-2x", style={"color": "#ffc107"}),
                                html.H4("Rating", className="card-title mt-2"),
                                html.H2(id="vendor-rating", children="4.8", className="card-text"),
                                html.Small("Based on 45 reviews", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #ffc107"}),
                    width=3
                ),
            ], className="mb-4"),
            
            # Service Requests
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Service Requests", className="mb-0")),
                        dbc.CardBody([
                            dbc.ListGroup([
                                dbc.ListGroupItem([
                                    html.Div([
                                        html.Strong("AC Repair - Flat 304"),
                                        dbc.Badge("In Progress", color="warning", className="float-end")
                                    ]),
                                    html.Small("Requested: Mar 18, 2024", className="text-muted d-block"),
                                    html.P("AC not cooling properly", className="mt-2"),
                                    dbc.Button("Update Status", size="sm", color="primary", className="mt-2")
                                ], color="light"),
                                dbc.ListGroupItem([
                                    html.Div([
                                        html.Strong("Plumbing - Flat 102"),
                                        dbc.Badge("Pending", color="danger", className="float-end")
                                    ]),
                                    html.Small("Requested: Mar 19, 2024", className="text-muted d-block"),
                                    html.P("Water leakage in kitchen", className="mt-2"),
                                    dbc.Button("Accept Request", size="sm", color="success", className="mt-2")
                                ], color="light"),
                                dbc.ListGroupItem([
                                    html.Div([
                                        html.Strong("Electrical - Flat 201"),
                                        dbc.Badge("Completed", color="success", className="float-end")
                                    ]),
                                    html.Small("Requested: Mar 15, 2024", className="text-muted d-block"),
                                    html.P("Power socket not working", className="mt-2"),
                                    dbc.Button("View Details", size="sm", color="info", className="mt-2")
                                ], color="light"),
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=12),
            ], className="mb-4"),
            
            # Payment History
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Payment History", className="mb-0")),
                        dbc.CardBody([
                            dbc.Table([
                                html.Thead(html.Tr([
                                    html.Th("Date"), html.Th("Service"), html.Th("Amount"), html.Th("Status")
                                ])),
                                html.Tbody([
                                    html.Tr([html.Td("Mar 10, 2024"), html.Td("AC Repair - Flat 304"), 
                                            html.Td("₹1,500"), html.Td(dbc.Badge("Paid", color="success"))]),
                                    html.Tr([html.Td("Mar 5, 2024"), html.Td("Plumbing - Flat 102"), 
                                            html.Td("₹800"), html.Td(dbc.Badge("Paid", color="success"))]),
                                    html.Tr([html.Td("Feb 28, 2024"), html.Td("Electrical - Flat 201"), 
                                            html.Td("₹1,200"), html.Td(dbc.Badge("Paid", color="success"))]),
                                ])
                            ], bordered=True, hover=True, responsive=True)
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=12),
            ])
        ])
    
    elif active_tab == "vendor_cashbook":
        content = html.Div([
            html.H2("Cashbook", className="mb-4"),
            dbc.Card([
                dbc.CardHeader([
                    html.H5("Transaction Ledger", className="mb-0 d-inline-block"),
                    dbc.Button("Export CSV", color="success", size="sm", className="float-end")
                ]),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("Date"), html.Th("Particulars"), html.Th("Debit"),
                            html.Th("Credit"), html.Th("Balance")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td("Mar 10, 2024"), html.Td("AC Repair - Flat 304"), 
                                    html.Td("-"), html.Td("₹1,500"), html.Td("₹1,500")]),
                            html.Tr([html.Td("Mar 5, 2024"), html.Td("Plumbing - Flat 102"), 
                                    html.Td("-"), html.Td("₹800"), html.Td("₹2,300")]),
                            html.Tr([html.Td("Feb 28, 2024"), html.Td("Electrical - Flat 201"), 
                                    html.Td("-"), html.Td("₹1,200"), html.Td("₹3,500")]),
                        ])
                    ], bordered=True, hover=True, responsive=True)
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "vendor_payments":
        content = html.Div([
            html.H2("Payment History", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("Invoice No"), html.Th("Date"), html.Th("Service"),
                            html.Th("Amount"), html.Th("Status"), html.Th("Receipt")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td("INV-001"), html.Td("Mar 10, 2024"), html.Td("AC Repair"),
                                    html.Td("₹1,500"), html.Td(dbc.Badge("Paid", color="success")),
                                    html.Td(dbc.Button("Download", size="sm", color="info"))]),
                            html.Tr([html.Td("INV-002"), html.Td("Mar 5, 2024"), html.Td("Plumbing"),
                                    html.Td("₹800"), html.Td(dbc.Badge("Paid", color="success")),
                                    html.Td(dbc.Button("Download", size="sm", color="info"))]),
                        ])
                    ], bordered=True, hover=True, responsive=True)
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "vendor_charges":
        content = html.Div([
            html.H2("Service Charges", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Current Rates", className="mb-0")),
                        dbc.CardBody([
                            dbc.Table([
                                html.Thead(html.Tr([html.Th("Service Type"), html.Th("Rate"), html.Th("GST")])),
                                html.Tbody([
                                    html.Tr([html.Td("AC Repair"), html.Td("₹500 + Parts"), html.Td("18%")]),
                                    html.Tr([html.Td("Plumbing"), html.Td("₹400 + Materials"), html.Td("18%")]),
                                    html.Tr([html.Td("Electrical"), html.Td("₹450 + Materials"), html.Td("18%")]),
                                    html.Tr([html.Td("Carpentry"), html.Td("₹400"), html.Td("18%")]),
                                ])
                            ], bordered=True)
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Pending Payments", className="mb-0")),
                        dbc.CardBody([
                            html.Div("No pending payments", className="text-muted text-center p-4")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
            ])
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
    
    # QR Code Modal
    qr_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("My QR Code")),
        dbc.ModalBody([
            html.Div([
                html.Img(id="vendor-qr-img", src="", style={"width": "200px", "height": "200px", "display": "block", "margin": "0 auto"}),
                html.P("Scan this QR code at society gate for entry", className="text-center mt-3"),
                html.Hr(),
                html.P("Valid for: Today", className="text-center text-muted")
            ])
        ]),
        dbc.ModalFooter(dbc.Button("Close", id="close-vendor-qr-modal", className="ms-auto"))
    ], id="vendor-qr-modal", is_open=False)
    
    return html.Div([content, qr_modal], style={"padding": "20px"})