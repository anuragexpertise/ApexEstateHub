from dash import html, dcc
import dash_bootstrap_components as dbc

def owner_portal_layout(active_tab="dashboard"):
    """Owner Portal Layout"""
    
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Welcome to Owner Portal", className="mb-4"),
            
            # KPI Cards
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-rupee-sign fa-2x mb-2", style={'color': '#e74c3c'}),
                        html.H4("Pending Dues", className="card-title"),
                        html.H2("₹5,000", className="card-text", id="pending-dues"),
                        html.Small("Due by: Apr 30, 2024", className="text-muted")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-check-circle fa-2x mb-2", style={'color': '#2ecc71'}),
                        html.H4("Last Payment", className="card-title"),
                        html.H2("₹4,500", className="card-text"),
                        html.Small("Paid on: Mar 15, 2024", className="text-muted")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-ticket-alt fa-2x mb-2", style={'color': '#f39c12'}),
                        html.H4("Active Complaints", className="card-title"),
                        html.H2("2", className="card-text"),
                        html.Small("1 Resolved", className="text-muted")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-qrcode fa-2x mb-2", style={'color': '#3498db'}),
                        html.H4("My QR Code", className="card-title"),
                        html.Img(id="owner-qr-code", src="", style={"width": "80px", "marginTop": "10px"}),
                        html.Small("Scan for gate access", className="text-muted d-block mt-2")
                    ])
                ], className="glass-card text-center"), width=3),
            ], className="mb-4"),
            
            # Quick Actions
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.H5("Quick Actions", className="mb-3"),
                        dbc.Button("Pay Dues", id="pay-dues-btn", color="success", className="w-100 mb-2"),
                        dbc.Button("Raise Complaint", id="complaint-btn", color="warning", className="w-100 mb-2"),
                        dbc.Button("Gate Pass", id="gate-pass-btn", color="info", className="w-100")
                    ])
                ], className="glass-card"), width=12)
            ], className="mb-4"),
            
            # Recent Payments Table
            dbc.Card([
                dbc.CardHeader(html.H5("Recent Payments", className="mb-0")),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("Date"), html.Th("Description"), html.Th("Amount"), html.Th("Status")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td("Mar 15, 2024"), html.Td("Maintenance - March"), 
                                    html.Td("₹4,500"), html.Td(dbc.Badge("Paid", color="success"))]),
                            html.Tr([html.Td("Feb 15, 2024"), html.Td("Maintenance - February"), 
                                    html.Td("₹4,500"), html.Td(dbc.Badge("Paid", color="success"))]),
                        ])
                    ], bordered=True, hover=True, responsive=True)
                ])
            ], className="glass-card")
        ])
    
    elif active_tab == "payments":
        content = html.Div([
            html.H2("Make a Payment", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Col(dbc.Label("Amount"), width=3),
                            dbc.Col(dbc.Input(id="payment-amount", type="number", placeholder="Enter amount"), width=9)
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col(dbc.Label("Payment Method"), width=3),
                            dbc.Col(dbc.Select(
                                id="payment-method",
                                options=[
                                    {"label": "Credit Card", "value": "card"},
                                    {"label": "UPI", "value": "upi"},
                                    {"label": "Net Banking", "value": "netbanking"}
                                ],
                                value="upi"
                            ), width=9)
                        ], className="mb-3"),
                        dbc.Button("Pay Now", id="process-payment-btn", color="success", className="mt-3")
                    ])
                ])
            ], className="glass-card")
        ])
    
    elif active_tab == "charges":
        content = html.Div([
            html.H2("Maintenance Charges", className="mb-4"),
            dbc.Card([
                dbc.CardHeader(html.H5("Current Charges", className="mb-0")),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([html.Th("Description"), html.Th("Amount"), html.Th("Due Date")])),
                        html.Tbody([
                            html.Tr([html.Td("Maintenance (1500 sq ft @ ₹3/sq ft)"), 
                                    html.Td("₹4,500"), html.Td("Apr 15, 2024")]),
                            html.Tr([html.Td("Late Fee"), html.Td("₹0"), html.Td("-")]),
                            html.Tr([html.Td("Total Due"), html.Td("₹4,500"), html.Td("Apr 30, 2024")])
                        ])
                    ], bordered=True)
                ])
            ], className="glass-card")
        ])
    
    else:
        content = html.Div([
            html.H2(active_tab.replace('_', ' ').title(), className="mb-4"),
            dbc.Card([
                dbc.CardBody(html.P("Content coming soon...", className="text-muted text-center p-5"))
            ], className="glass-card")
        ])
    
    return html.Div(content, style={"padding": "20px"})