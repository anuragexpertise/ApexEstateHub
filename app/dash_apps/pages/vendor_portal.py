from dash import html, dcc
import dash_bootstrap_components as dbc

def vendor_portal_layout(active_tab="dashboard"):
    """Vendor Portal Layout"""
    
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Vendor Dashboard", className="mb-4"),
            
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-briefcase fa-2x mb-2", style={'color': '#ff9800'}),
                        html.H4("Active Services", className="card-title"),
                        html.H2("3", className="card-text")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-rupee-sign fa-2x mb-2", style={'color': '#4caf50'}),
                        html.H4("Total Earnings", className="card-title"),
                        html.H2("₹25,000", className="card-text")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-clock fa-2x mb-2", style={'color': '#2196f3'}),
                        html.H4("Pending Requests", className="card-title"),
                        html.H2("5", className="card-text")
                    ])
                ], className="glass-card text-center"), width=3),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.I(className="fas fa-star fa-2x mb-2", style={'color': '#ffc107'}),
                        html.H4("Rating", className="card-title"),
                        html.H2("4.8", className="card-text")
                    ])
                ], className="glass-card text-center"), width=3),
            ], className="mb-4"),
            
            dbc.Card([
                dbc.CardHeader(html.H5("Service Requests", className="mb-0")),
                dbc.CardBody([
                    dbc.ListGroup([
                        dbc.ListGroupItem([
                            html.Strong("AC Repair - Flat 304"),
                            dbc.Badge("In Progress", color="warning", className="float-end"),
                            html.Br(),
                            html.Small("Requested: Mar 18, 2024", className="text-muted")
                        ]),
                        dbc.ListGroupItem([
                            html.Strong("Plumbing - Flat 102"),
                            dbc.Badge("Pending", color="danger", className="float-end"),
                            html.Br(),
                            html.Small("Requested: Mar 19, 2024", className="text-muted")
                        ])
                    ])
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