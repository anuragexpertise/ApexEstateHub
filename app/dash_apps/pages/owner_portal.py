from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime

def owner_portal_layout(active_tab="dashboard"):
    """Complete Owner Portal Layout"""
    
    if active_tab == "dashboard":
        content = html.Div([
            html.H2("Owner Dashboard", className="mb-4", style={"color": "#2c3e50"}),
            
            # KPI Cards
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-rupee-sign fa-2x", style={"color": "#e74c3c"}),
                                html.H4("Pending Dues", className="card-title mt-2"),
                                html.H2(id="owner-pending-dues", children="₹0", className="card-text"),
                                html.Small("Due by: End of month", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #e74c3c"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                                html.H4("Last Payment", className="card-title mt-2"),
                                html.H2(id="owner-last-payment", children="₹0", className="card-text"),
                                html.Small("Paid on: --", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #2ecc71"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-ticket-alt fa-2x", style={"color": "#f39c12"}),
                                html.H4("Active Complaints", className="card-title mt-2"),
                                html.H2(id="owner-complaints", children="0", className="card-text"),
                                html.Small("In progress", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #f39c12"}),
                    width=3
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="fas fa-qrcode fa-2x", style={"color": "#3498db"}),
                                html.H4("My QR Code", className="card-title mt-2"),
                                html.Img(id="owner-qr-display", src="", style={"width": "60px", "marginTop": "5px"}),
                                html.Br(),
                                html.Small("Scan for gate access", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px", "borderLeft": "4px solid #3498db"}),
                    width=3
                ),
            ], className="mb-4"),
            
            # Quick Actions
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Quick Actions", className="mb-0")),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col(dbc.Button("💰 Pay Dues", id="pay-dues-btn", color="success", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("📝 Raise Complaint", id="raise-complaint-btn", color="warning", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("🎫 Gate Pass", id="gate-pass-btn", color="info", className="w-100 mb-2"), width=6),
                                dbc.Col(dbc.Button("📄 Download Receipt", id="download-receipt-btn", color="secondary", className="w-100 mb-2"), width=6),
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=12
                ),
            ], className="mb-4"),
            
            # Recent Payments and Notices
            dbc.Row([
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Payments", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="owner-payments-list", children=[
                                html.P("No payments recorded", className="text-muted text-center")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=6
                ),
                dbc.Col(
                    dbc.Card([
                        dbc.CardHeader(html.H5("Recent Notices", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="owner-notices-list", children=[
                                html.P("No notices available", className="text-muted text-center")
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"}),
                    width=6
                ),
            ]),
        ])
    
    elif active_tab == "payments":
        content = html.Div([
            html.H2("Make a Payment", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Payment Details", className="mb-0")),
                        dbc.CardBody([
                            dbc.Form([
                                dbc.Row([
                                    dbc.Col(dbc.Label("Amount Due"), width=4),
                                    dbc.Col(html.H4(id="payment-due-amount", children="₹0", className="text-danger"), width=8),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Payment Amount"), width=4),
                                    dbc.Col(dbc.Input(id="payment-amount", type="number", placeholder="Enter amount"), width=8),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("Payment Method"), width=4),
                                    dbc.Col(dcc.Dropdown(
                                        id="payment-method",
                                        options=[
                                            {"label": "Credit Card", "value": "card"},
                                            {"label": "UPI", "value": "upi"},
                                            {"label": "Net Banking", "value": "netbanking"},
                                            {"label": "Cash", "value": "cash"},
                                        ],
                                        value="upi",
                                        placeholder="Select method"
                                    ), width=8),
                                ], className="mb-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Label("UPI ID / Card Number"), width=4),
                                    dbc.Col(dbc.Input(id="payment-details", type="text", placeholder="Enter payment details"), width=8),
                                ], className="mb-3"),
                                dbc.Button("Pay Now", id="process-payment-btn", color="success", className="mt-3", style={"width": "100%"})
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Payment History", className="mb-0")),
                        dbc.CardBody([
                            html.Div(id="payment-history", children=[
                                dbc.Table([
                                    html.Thead(html.Tr([
                                        html.Th("Date"), html.Th("Description"), 
                                        html.Th("Amount"), html.Th("Status")
                                    ])),
                                    html.Tbody(id="payment-history-body", children=[
                                        html.Tr([html.Td("No payments found", colSpan=4, className="text-center")])
                                    ])
                                ], bordered=True, hover=True, responsive=True)
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=6),
            ])
        ])
    
    elif active_tab == "charges":
        content = html.Div([
            html.H2("Maintenance Charges", className="mb-4"),
            dbc.Card([
                dbc.CardHeader(html.H5("Current Charges Breakdown", className="mb-0")),
                dbc.CardBody([
                    dbc.Table([
                        html.Thead(html.Tr([
                            html.Th("Description"), html.Th("Amount"), html.Th("Due Date"), html.Th("Status")
                        ])),
                        html.Tbody([
                            html.Tr([html.Td("Maintenance (1200 sq ft @ ₹3/sq ft)"), html.Td("₹3,600"), html.Td("15th of each month"), html.Td(dbc.Badge("Pending", color="warning"))]),
                            html.Tr([html.Td("Late Fee"), html.Td("₹0"), html.Td("-"), html.Td(dbc.Badge("N/A", color="secondary"))]),
                            html.Tr([html.Td("Previous Dues"), html.Td("₹0"), html.Td("-"), html.Td(dbc.Badge("Cleared", color="success"))]),
                            html.Tr([html.Td("Total Due", className="fw-bold"), html.Td("₹3,600", className="fw-bold text-danger"), html.Td("Apr 30, 2024"), html.Td(dbc.Badge("Pending", color="warning"))])
                        ])
                    ], bordered=True, hover=True)
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"}),
            html.Br(),
            dbc.Card([
                dbc.CardHeader(html.H5("Charge Calculation", className="mb-0")),
                dbc.CardBody([
                    html.P("Maintenance is calculated as: Apartment Area × Rate per sq ft"),
                    html.P("Rate: ₹3 per sq ft", className="text-primary"),
                    html.P("Your Apartment Area: 1200 sq ft"),
                    html.H5("Monthly Maintenance: ₹3,600", className="text-success mt-3")
                ])
            ], className="shadow-sm", style={"borderRadius": "15px"})
        ])
    
    elif active_tab == "events":
        content = html.Div([
            html.H2("Society Events", className="mb-4"),
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader(html.H5("Upcoming Events", className="mb-0")),
                        dbc.CardBody([
                            dbc.ListGroup([
                                dbc.ListGroupItem([
                                    html.Strong("🎉 Ganesh Chaturthi Celebration"),
                                    html.Br(),
                                    html.Small("Date: September 19, 2024", className="text-muted"),
                                    html.P("Join us for the annual Ganesh Chaturthi celebration at the clubhouse.", className="mt-2")
                                ], color="info"),
                                dbc.ListGroupItem([
                                    html.Strong("🏏 Annual Sports Day"),
                                    html.Br(),
                                    html.Small("Date: October 15, 2024", className="text-muted"),
                                    html.P("Register your family for various sports events.", className="mt-2")
                                ], color="info"),
                                dbc.ListGroupItem([
                                    html.Strong("🎄 Christmas Celebration"),
                                    html.Br(),
                                    html.Small("Date: December 25, 2024", className="text-muted"),
                                    html.P("Christmas party for all residents.", className="mt-2")
                                ], color="info"),
                            ])
                        ])
                    ], className="shadow-sm", style={"borderRadius": "15px"})
                ], width=12)
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
    
    # Modals
    complaint_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Raise Complaint")),
        dbc.ModalBody([
            dbc.Label("Complaint Type"),
            dcc.Dropdown(
                id="complaint-type",
                options=[
                    {"label": "Plumbing", "value": "plumbing"},
                    {"label": "Electrical", "value": "electrical"},
                    {"label": "Cleaning", "value": "cleaning"},
                    {"label": "Security", "value": "security"},
                    {"label": "Others", "value": "others"},
                ],
                placeholder="Select complaint type",
                className="mb-3"
            ),
            dbc.Label("Description"),
            dbc.Textarea(id="complaint-desc", placeholder="Describe your issue in detail...", rows=4, className="mb-3"),
            dbc.Label("Preferred Time"),
            dcc.Dropdown(
                id="complaint-time",
                options=[
                    {"label": "Morning (9 AM - 12 PM)", "value": "morning"},
                    {"label": "Afternoon (12 PM - 3 PM)", "value": "afternoon"},
                    {"label": "Evening (3 PM - 6 PM)", "value": "evening"},
                ],
                placeholder="Select preferred time",
                className="mb-3"
            )
        ]),
        dbc.ModalFooter([
            dbc.Button("Submit", id="submit-complaint-btn", color="primary"),
            dbc.Button("Cancel", id="close-complaint-modal", className="ms-auto")
        ])
    ], id="complaint-modal", is_open=False)
    
    gatepass_modal = dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Generate Gate Pass")),
        dbc.ModalBody([
            dbc.Label("Visitor Name *"),
            dbc.Input(id="visitor-name", type="text", placeholder="Enter visitor name", className="mb-3"),
            dbc.Label("Visitor Phone"),
            dbc.Input(id="visitor-phone", type="tel", placeholder="Enter phone number", className="mb-3"),
            dbc.Label("Purpose of Visit"),
            dcc.Dropdown(
                id="visit-purpose",
                options=[
                    {"label": "Guest", "value": "guest"},
                    {"label": "Delivery", "value": "delivery"},
                    {"label": "Service", "value": "service"},
                    {"label": "Other", "value": "other"},
                ],
                placeholder="Select purpose",
                className="mb-3"
            ),
            dbc.Label("Valid Until"),
            dcc.DatePickerSingle(id="gatepass-validity", placeholder="Select date", className="mb-3"),
            dbc.Label("Vehicle Number (if any)"),
            dbc.Input(id="visitor-vehicle", type="text", placeholder="Vehicle number", className="mb-3")
        ]),
        dbc.ModalFooter([
            dbc.Button("Generate", id="generate-gatepass-btn", color="success"),
            dbc.Button("Cancel", id="close-gatepass-modal", className="ms-auto")
        ])
    ], id="gatepass-modal", is_open=False)
    
    return html.Div([content, complaint_modal, gatepass_modal], style={"padding": "20px"})