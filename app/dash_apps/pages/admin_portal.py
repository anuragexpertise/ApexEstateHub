from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd
from datetime import datetime

def admin_portal_layout(active_tab="dashboard"):
    """Admin Portal Layout with glassmorphism design"""
    
    # Dashboard content
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Admin Dashboard", className="mb-4", style={'color': '#2c3e50'}),
            
            # KPI Cards
            dbc.Row([
                dbc.Col(dbc.Card(
                    dbc.CardBody([
                        html.I(className="fas fa-building fa-2x mb-2", style={'color': '#3498db'}),
                        html.H4("Total Societies", className="card-title"),
                        html.H2("0", className="card-text"),
                        html.Small("Active societies", className="text-muted")
                    ]),
                    className="glass-card text-center", style={'borderRadius': '15px', 'backdropFilter': 'blur(10px)'}
                ), width=3),
                dbc.Col(dbc.Card(
                    dbc.CardBody([
                        html.I(className="fas fa-users fa-2x mb-2", style={'color': '#2ecc71'}),
                        html.H4("Total Users", className="card-title"),
                        html.H2("0", className="card-text"),
                        html.Small("Registered users", className="text-muted")
                    ]),
                    className="glass-card text-center", style={'borderRadius': '15px', 'backdropFilter': 'blur(10px)'}
                ), width=3),
                dbc.Col(dbc.Card(
                    dbc.CardBody([
                        html.I(className="fas fa-rupee-sign fa-2x mb-2", style={'color': '#f39c12'}),
                        html.H4("Revenue", className="card-title"),
                        html.H2("₹0", className="card-text"),
                        html.Small("This month", className="text-muted")
                    ]),
                    className="glass-card text-center", style={'borderRadius': '15px', 'backdropFilter': 'blur(10px)'}
                ), width=3),
                dbc.Col(dbc.Card(
                    dbc.CardBody([
                        html.I(className="fas fa-chart-line fa-2x mb-2", style={'color': '#e74c3c'}),
                        html.H4("Growth", className="card-title"),
                        html.H2("0%", className="card-text"),
                        html.Small("Month over month", className="text-muted")
                    ]),
                    className="glass-card text-center", style={'borderRadius': '15px', 'backdropFilter': 'blur(10px)'}
                ), width=3),
            ], className="mb-4"),
            
            # Recent Activity
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5("Recent Societies", className="mb-0")),
                    dbc.CardBody(html.Div(id="recent-societies-list", children=[
                        html.P("No societies added yet", className="text-muted text-center")
                    ]))
                ], className="glass-card", style={'borderRadius': '15px'}), width=6),
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.H5("Recent Payments", className="mb-0")),
                    dbc.CardBody(html.Div(id="recent-payments-list", children=[
                        html.P("No payments processed yet", className="text-muted text-center")
                    ]))
                ], className="glass-card", style={'borderRadius': '15px'}), width=6),
            ])
        ])
    
    elif active_tab == "cashbook":
        content = html.Div([
            html.H2("Cashbook", className="mb-4"),
            dbc.Card([
                dbc.CardHeader([
                    html.H5("Transaction Ledger", className="mb-0 d-inline-block"),
                    dbc.Button("Export CSV", color="success", size="sm", className="float-end")
                ]),
                dbc.CardBody([
                    html.Div(id="cashbook-table", children=[
                        dbc.Table([
                            html.Thead(html.Tr([
                                html.Th("Date"), html.Th("Particulars"), html.Th("Debit"),
                                html.Th("Credit"), html.Th("Balance")
                            ])),
                            html.Tbody([html.Tr([html.Td("No transactions found", colSpan=5, className="text-center")])])
                        ], bordered=True, hover=True, responsive=True)
                    ])
                ])
            ], className="glass-card", style={'borderRadius': '15px'})
        ])
    
    elif active_tab == "enroll":
        content = html.Div([
            html.H2("Enroll New Member", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Col(dbc.Input(id="enroll-name", placeholder="Full Name", className="mb-3"), width=6),
                            dbc.Col(dbc.Input(id="enroll-email", type="email", placeholder="Email", className="mb-3"), width=6),
                        ]),
                        dbc.Row([
                            dbc.Col(dbc.Input(id="enroll-phone", type="tel", placeholder="Phone", className="mb-3"), width=6),
                            dbc.Col(dbc.Select(
                                id="enroll-role",
                                options=[
                                    {"label": "Apartment Owner", "value": "apartment"},
                                    {"label": "Vendor", "value": "vendor"},
                                    {"label": "Security", "value": "security"},
                                ],
                                placeholder="Select Role",
                                className="mb-3"
                            ), width=6),
                        ]),
                        dbc.Row([
                            dbc.Col(dbc.Input(id="enroll-flat", placeholder="Flat/Apartment Number", className="mb-3"), width=6),
                            dbc.Col(dbc.Input(id="enroll-size", type="number", placeholder="Area (sq ft)", className="mb-3"), width=6),
                        ]),
                        dbc.Button("Enroll Member", id="enroll-submit", color="primary", className="mt-2")
                    ])
                ])
            ], className="glass-card", style={'borderRadius': '15px'})
        ])
    
    elif active_tab == "evaluate_pass":
        content = html.Div([
            html.H2("Evaluate Pass", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        dcc.Input(id="qr-scan-input", type="text", placeholder="Scan or enter QR code", 
                                 className="form-control mb-3", style={'fontSize': '16px', 'padding': '12px'}),
                        dbc.Button("Validate", id="validate-qr-btn", color="primary", className="mb-3"),
                        html.Div(id="qr-validation-result", className="mt-3")
                    ])
                ])
            ], className="glass-card", style={'borderRadius': '15px'})
        ])
    
    else:
        content = html.Div([
            html.H2(active_tab.replace('_', ' ').title(), className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    html.P(f"This is the {active_tab.replace('_', ' ').title()} section", 
                          className="text-muted text-center p-5")
                ])
            ], className="glass-card", style={'borderRadius': '15px'})
        ])
    
    # Glassmorphism CSS
    glass_style = html.Style("""
        .glass-card {
            background: rgba(255, 255, 255, 0.25);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            transition: all 0.3s ease;
        }
        .glass-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        .sidebar {
            background: rgba(26, 26, 46, 0.95);
            backdrop-filter: blur(10px);
        }
    """)
    
    return html.Div([content, glass_style], style={'padding': '20px'})