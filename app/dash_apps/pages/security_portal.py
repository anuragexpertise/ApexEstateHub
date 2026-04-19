from dash import html, dcc
import dash_bootstrap_components as dbc

def security_portal_layout(active_tab="pass_evaluation"):
    """Security Portal Layout"""
    
    if active_tab == "pass_evaluation":
        content = html.Div([
            html.H2("QR Code Scanner", className="mb-4"),
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        dcc.Input(
                            id="security-qr-input",
                            type="text",
                            placeholder="Scan QR Code or Enter Code",
                            className="form-control mb-3",
                            style={"fontSize": "18px", "padding": "15px", "textAlign": "center"}
                        ),
                        dbc.Button("Validate", id="security-validate-btn", color="primary", size="lg", className="w-100 mb-3"),
                        html.Div(id="security-scan-result", className="text-center p-4", style={"borderRadius": "10px"})
                    ])
                ])
            ], className="glass-card")
        ])
    
    elif active_tab == "attendance":
        content = html.Div([
            html.H2("Attendance Tracking", className="mb-4"),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.H4("Today's Status", className="text-center mb-3"),
                        html.Div(id="attendance-status", className="text-center mb-3"),
                        dbc.Button("Clock In", id="clock-in-btn", color="success", className="w-100 mb-2"),
                        dbc.Button("Clock Out", id="clock-out-btn", color="danger", className="w-100")
                    ])
                ], className="glass-card"), width=6),
                
                dbc.Col(dbc.Card([
                    dbc.CardBody([
                        html.H4("Today's Activity", className="text-center mb-3"),
                        dbc.Table([
                            html.Thead(html.Tr([html.Th("Time"), html.Th("Event")])),
                            html.Tbody(id="attendance-logs")
                        ], bordered=True)
                    ])
                ], className="glass-card"), width=6),
            ])
        ])
    
    else:
        content = html.Div([
            html.H2(active_tab.replace('_', ' ').title(), className="mb-4"),
            dbc.Card([
                dbc.CardBody(html.P("Content coming soon...", className="text-muted text-center p-5"))
            ], className="glass-card")
        ])
    
    return html.Div(content, style={"padding": "20px"})