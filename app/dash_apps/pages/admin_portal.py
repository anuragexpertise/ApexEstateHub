from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime
from .customize_layout import customize_layout   
def admin_portal_layout(active_tab="dashboard"):
    """Complete Admin Portal Layout with all features"""
    
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Admin Dashboard", className="mb-4", style={"color": "#2c3e50"}),
            
            # KPI Cards Row
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-building fa-2x", style={"color": "#3498db"}),
                                html.H4("Total Societies", className="card-title mt-2"),
                                html.H2(id="total-societies", children="0", className="card-text"),
                                html.Small("Active societies", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #3498db"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-users fa-2x", style={"color": "#2ecc71"}),
                                html.H4("Total Users", className="card-title mt-2"),
                                html.H2(id="total-users", children="0", className="card-text"),
                                html.Small("Registered users", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #2ecc71"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-rupee-sign fa-2x", style={"color": "#f39c12"}),
                                html.H4("Total Revenue", className="card-title mt-2"),
                                html.H2(id="total-revenue", children="₹0", className="card-text"),
                                html.Small("This month", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #f39c12"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-chart-line fa-2x", style={"color": "#e74c3c"}),
                                html.H4("Pending Dues", className="card-title mt-2"),
                                html.H2(id="pending-dues", children="₹0", className="card-text"),
                                html.Small("Awaiting payment", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #e74c3c"}),
                    width=3
                ),
            ], className="mb-4"),
            
            # Quick Actions Row
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Quick Actions", className="mb-0")),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col(dbc.Button("➕ Add Society", id="add-society-btn", color="primary", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("👥 Add User", id="add-user-btn", color="success", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("🏢 Add Apartment", id="add-apartment-btn", color="info", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("📊 Generate Report", id="report-btn", color="warning", className="w-100 mb-2"), width=6),
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=12
                ),
            ], className="mb-4"),
            
            # Recent Activities Row
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Societies", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="recent-societies-list", children=[
                                html.P("No societies added yet", className="text-muted text-center")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=6
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Payments", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="recent-payments-list", children=[
                                html.P("No payments processed yet", className="text-muted text-center")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=6
                ),
            ]),
        ])
    
    elif active_tab == "cashbook":
        content = html.Div([
            html.H2("Cashbook", className="mb-4"),
            dbc.Card([
                dbc.CardHeader([
                    html.H5("Transaction Ledger", className="mb-0 d-inline-block"),
                    dbc.Button("Export CSV", id="export-csv-btn", color="success", size="sm", className="float-end")
                ]),
                dbc.CardBody([
                    html.Div(id="cashbook-table", children=[
                        dbc.Table([
                            html.Thead(html.Tr([
                                html.Th("Date"), html.Th("Particulars"), html.Th("Debit"),
                                html.Th("Credit"), html.Th("Balance")
                            ])),
                            html.Tbody(id="cashbook-tbody", children=[
                                html.Tr([html.Td("No transactions found", colSpan=5, className="text-center")])
                            ])
                        ], bordered=True, hover=True, responsive=True, className="table-sm")
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "receipts":
        content = html.Div([
            html.H2("Receipts", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Generate New Receipt", className="mb-0")),
                        dbc.CardBody([
                            dbc.Form([
                                dbc.Row([
                                    dbc.Col(dbc.Label("Receipt Type"), width=3),
                                    dbc.Col(dbc.Select(
                                        id="receipt-type",
                                        options=[
                                            {"label": "Maintenance", "value": "maintenance"},
                                            {"label": "Late Fee", "value": "late_fee"},
                                            {"label": "Fine", "value": "fine"},
                                        ],
                                        placeholder="Select type"
                                    ), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Amount"), width=3),
                                    dbc.Col(dbc.Input(id="receipt-amount", type="number", placeholder="Enter amount"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Paid By"), width=3),
                                    dbc.Col(dbc.Input(id="receipt-paid-by", type="text", placeholder="Payer name"), width=9),
                                ], className="mb-3"),
                                dbc.Button("Generate Receipt", id="generate-receipt-btn", color="primary", className="mt-2")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Receipts", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="recent-receipts", children=[
                                html.P("No receipts generated", className="text-muted text-center")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
            ])
        ])
    
    elif active_tab == "expenses":
        content = html.Div([
            html.H2("Expenses", className="mb-4"),
            dbc.Card([
                dbc.CardHeader(html.H5("Add Expense", className="mb-0")),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Expense Category"),
                            dcc.Dropdown(
                                id="expense-category",
                                options=[
                                    {"label": "Maintenance", "value": "maintenance"},
                                    {"label": "Salaries", "value": "salaries"},
                                    {"label": "Utilities", "value": "utilities"},
                                    {"label": "Repairs", "value": "repairs"},
                                ],
                                placeholder="Select category"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Amount"),
                            dbc.Input(id="expense-amount", type="number", placeholder="Enter amount")
                        ], width=6),
                    ], className="mb-3"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Date"),
                            dcc.DatePickerSingle(id="expense-date", placeholder="Select date")
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Payment Method"),
                            dcc.Dropdown(
                                id="expense-method",
                                options=[
                                    {"label": "Cash", "value": "cash"},
                                    {"label": "Bank Transfer", "value": "bank"},
                                    {"label": "Cheque", "value": "cheque"},
                                ],
                                placeholder="Select method"
                            )
                        ], width=6),
                    ], className="mb-3"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Description"),
                            dbc.Textarea(id="expense-description", placeholder="Enter description")
                        ], width=12),
                    ], className="mb-3"),
                    dbc.Button("Add Expense", id="add-expense-btn", color="danger", className="mt-2")
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"}),
            html.Br(),
            dbc.Card([
                dbc.CardHeader(html.H5("Expense History", className="mb-0")),
                dbc.CardBody([
                    html.Div(id="expense-history", children=[
                        dbc.Table([
                            html.Thead(html.Tr([
                                html.Th("Date"), html.Th("Category"), html.Th("Description"),
                                html.Th("Amount"), html.Th("Status")
                            ])),
                            html.Tbody(id="expense-tbody", children=[
                                html.Tr([html.Td("No expenses recorded", colSpan=5, className="text-center")])
                            ])
                        ], bordered=True, hover=True, responsive=True)
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "enroll":
        content = html.Div([
            html.H2("Enroll New Member", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    dbc.Form([
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Full Name *"),
                                dbc.Input(id="enroll-name", type="text", placeholder="Enter full name")
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Email *"),
                                dbc.Input(id="enroll-email", type="email", placeholder="Enter email")
                            ], width=6),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Phone"),
                                dbc.Input(id="enroll-phone", type="tel", placeholder="Enter phone number")
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Role *"),
                                dcc.Dropdown(
                                    id="enroll-role",
                                    options=[
                                        {"label": "Apartment Owner", "value": "apartment"},
                                        {"label": "Vendor", "value": "vendor"},
                                        {"label": "Security Staff", "value": "security"},
                                    ],
                                    placeholder="Select role"
                                )
                            ], width=6),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Flat/Apartment No"),
                                dbc.Input(id="enroll-flat", type="text", placeholder="Enter flat number")
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Area (sq ft)"),
                                dbc.Input(id="enroll-area", type="number", placeholder="Enter area in sq ft")
                            ], width=6),
                        ], className="mb-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Password"),
                                dbc.Input(id="enroll-password", type="password", placeholder="Enter password")
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Confirm Password"),
                                dbc.Input(id="enroll-confirm", type="password", placeholder="Confirm password")
                            ], width=6),
                        ], className="mb-3"),
                        dbc.Button("Enroll Member", id="enroll-submit-btn", color="primary", className="mt-2")
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"}),
            html.Br(),
            dbc.Card([
                dbc.CardHeader(html.H5("Recent Enrollments", className="mb-0")),
                dbc.CardBody([
                    html.Div(id="recent-enrollments", children=[
                        html.P("No enrollments yet", className="text-muted text-center")
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "users":
        content = html.Div([
            html.H2("User Management", className="mb-4"),
            dbc.Card([
                dbc.CardHeader([
                    html.H5("All Users", className="mb-0 d-inline-block"),
                    dbc.Input(id="user-search", type="text", placeholder="Search users...", 
                             className="float-end", style={"width": "200px"})
                ]),
                dbc.CardBody([
                    html.Div(id="users-table", children=[
                        dbc.Table([
                            html.Thead(html.Tr([
                                html.Th("ID"), html.Th("Name"), html.Th("Email"),
                                html.Th("Role"), html.Th("Status"), html.Th("Actions")
                            ])),
                            html.Tbody(id="users-tbody", children=[
                                html.Tr([html.Td("No users found", colSpan=6, className="text-center")])
                            ])
                        ], bordered=True, hover=True, responsive=True)
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "evaluate_pass":
        content = html.Div([
            html.H2("Evaluate Pass", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        dcc.Input(
                            id="qr-scan-input", 
                            type="text", 
                            placeholder="Scan or enter QR code", 
                            className="form-control mb-3",
                            style={"fontSize": "16px", "padding": "12px"}
                        ),
                        dbc.Button("Validate QR", id="validate-qr-btn", color="primary", className="mb-3", style={"width": "100%"}),
                        html.Div(id="qr-validation-result", className="mt-3")
                    ])
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "settings":
        content = html.Div([
            html.H2("Society Settings", className="mb-4"),
            dbc.Tabs([
                dbc.Tab(label="General", children=[
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Form([
                                dbc.Row([
                                    dbc.Col(dbc.Label("Society Name"), width=3),
                                    dbc.Col(dbc.Input(id="settings-soc-name", type="text", placeholder="Society name"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Email"), width=3),
                                    dbc.Col(dbc.Input(id="settings-soc-email", type="email", placeholder="Email"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Phone"), width=3),
                                    dbc.Col(dbc.Input(id="settings-soc-phone", type="tel", placeholder="Phone"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Address"), width=3),
                                    dbc.Col(dbc.Textarea(id="settings-soc-address", placeholder="Address"), width=9),
                                ], className="mb-3"),
                                dbc.Button("Save Settings", id="save-settings-btn", color="primary")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ]),
                dbc.Tab(label="Maintenance Rates", children=[
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Form([
                                dbc.Row([
                                    dbc.Col(dbc.Label("Rate per sq ft (₹)"), width=3),
                                    dbc.Col(dbc.Input(id="maintenance-rate", type="number", placeholder="Rate per sq ft"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Due Day of Month"), width=3),
                                    dbc.Col(dbc.Input(id="due-day", type="number", placeholder="Day of month (1-31)"), width=9),
                                ], className="mb-3"),
                                dbc.Button("Update Rates", id="update-rates-btn", color="primary")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ]),
                dbc.Tab(label="Late Fees", children=[
                    dbc.Card([
                        dbc.CardBody([
                            dbc.Form([
                                dbc.Row([
                                    dbc.Col(dbc.Label("Daily Late Fee (₹)"), width=3),
                                    dbc.Col(dbc.Input(id="late-fee-daily", type="number", placeholder="Daily late fee"), width=9),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Max Late Fee (%)"), width=3),
                                    dbc.Col(dbc.Input(id="late-fee-max", type="number", placeholder="Maximum percentage"), width=9),
                                ], className="mb-3"),
                                dbc.Button("Update Late Fees", id="update-late-fees-btn", color="primary")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ]),
            ])
        ])
    
    elif active_tab == "customize":
        # content = html.Div([
        #     html.H2("Customize Society", className="mb-4"),
        #     dbc.Card([
        #         dbc.CardBody([
        #             html.P("Drag and drop layout customization coming soon...", 
        #                 className="text-muted text-center p-5")
        #         ])
        #     ], className="shadow-sm", style={"borderRadius": "15px"})
        # ])
        content = customize_layout()
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
    
    # Return content without the html.Style (use className for styling)
    return html.Div(content, style={"padding": "20px"})