from dash import html, dcc
import dash_bootstrap_components as dbc

def society_login_layout(society_name="EstateHub", prefill_email=None, default_method="password"):
    """Society-specific login page with push notification prompt"""
    
    layout = html.Div(
        [
            # Background
            html.Div(
                style={
                    "position": "fixed",
                    "top": "0",
                    "left": "0",
                    "width": "100%",
                    "height": "100%",
                    "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                    "zIndex": "-1"
                }
            ),
            
            # Push notification prompt
            html.Div(
                id="push-prompt",
                style={
                    "position": "fixed",
                    "bottom": "20px",
                    "right": "20px",
                    "zIndex": "1000",
                    "display": "none"
                },
                children=dbc.Alert(
                    [
                        html.I(className="fas fa-bell me-2"),
                        "Enable notifications for important updates?",
                        dbc.Button("Enable", id="enable-push-btn", size="sm", color="primary", className="ms-2"),
                        dbc.Button("Later", id="later-push-btn", size="sm", color="secondary", className="ms-2")
                    ],
                    color="info",
                    dismissable=True
                )
            ),
            
            # Main container
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "minHeight": "100vh",
                    "padding": "20px"
                },
                children=[
                    # Login Card
                    html.Div(
                        style={
                            "maxWidth": "550px",
                            "width": "100%",
                            "backgroundColor": "white",
                            "borderRadius": "20px",
                            "boxShadow": "0 20px 60px rgba(0,0,0,0.3)",
                            "overflow": "hidden"
                        },
                        children=[
                            # Header
                            html.Div(
                                style={
                                    "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                                    "padding": "40px 30px",
                                    "textAlign": "center",
                                    "color": "white"
                                },
                                children=[
                                    html.H2(society_name, style={"fontSize": "28px", "fontWeight": "bold"}),
                                    html.P("Please login to continue", style={"fontSize": "14px", "opacity": "0.9"})
                                ]
                            ),
                            
                            # Body
                            html.Div(
                                style={"padding": "40px 35px"},
                                children=[
                                    # Tabs for login methods
                                    dcc.Tabs(
                                        id="login-tabs",
                                        value=default_method,
                                        children=[
                                            dcc.Tab(label="Password", value="password", children=[
                                                html.Div(style={"padding": "20px 0"}, children=[
                                                    dcc.Input(id="login-email", type="email", placeholder="Email", 
                                                             value=prefill_email, className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px"}),
                                                    dcc.Input(id="login-password", type="password", placeholder="Password", 
                                                             className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px"}),
                                                    dbc.Button("Login", id="login-btn", color="primary", 
                                                              style={"width": "100%", "padding": "12px"})
                                                ])
                                            ]),
                                            dcc.Tab(label="PIN", value="pin", children=[
                                                html.Div(style={"padding": "20px 0"}, children=[
                                                    dcc.Input(id="login-email-pin", type="email", placeholder="Email",
                                                             value=prefill_email, className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px"}),
                                                    dcc.Input(id="login-pin", type="password", placeholder="4-Digit PIN",
                                                             maxLength=4, className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px",
                                                                   "textAlign": "center", "letterSpacing": "5px"}),
                                                    dbc.Button("Login with PIN", id="login-pin-btn", color="primary",
                                                              style={"width": "100%", "padding": "12px"})
                                                ])
                                            ]),
                                            dcc.Tab(label="Pattern", value="pattern", children=[
                                                html.Div(style={"padding": "20px 0"}, children=[
                                                    dcc.Input(id="login-email-pattern", type="email", placeholder="Email",
                                                             value=prefill_email, className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px"}),
                                                    dcc.Input(id="login-pattern", type="text", 
                                                             placeholder="9-Dot Pattern (e.g., 1-2-3-5-7)",
                                                             className="mb-3",
                                                             style={"width": "100%", "padding": "12px", "borderRadius": "8px"}),
                                                    dbc.Button("Login with Pattern", id="login-pattern-btn", color="primary",
                                                              style={"width": "100%", "padding": "12px"})
                                                ])
                                            ])
                                        ]
                                    ),
                                    
                                    dbc.Checkbox(id="remember-me-checkbox", label="Remember me on this device", 
                                                className="mb-3"),
                                    
                                    html.Div(style={"textAlign": "center"}, children=[
                                        dcc.Link("← Change Society", href="/", style={"color": "#667eea"})
                                    ])
                                ]
                            )
                        ]
                    )
                ]
            ),
            
            # JavaScript for push notifications
            html.Script(src="/static/js/push.js")
        ]
    )
    
    return layout