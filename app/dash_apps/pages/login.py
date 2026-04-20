from dash import html, dcc
import dash_bootstrap_components as dbc

def society_login_layout(society_name="EstateHub", prefill_email=None, default_method="password"):
    """Society-specific login page - Secondary Login"""
    
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
            
            # Centered card
            html.Div(
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "minHeight": "100vh",
                    "padding": "20px"
                },
                children=[
                    html.Div(
                        style={
                            "maxWidth": "450px",
                            "width": "100%",
                            "backgroundColor": "white",
                            "borderRadius": "20px",
                            "boxShadow": "0 20px 60px rgba(0,0,0,0.3)",
                            "overflow": "hidden",
                            "padding": "40px"
                        },
                        children=[
                            html.H2(society_name, 
                                   style={"textAlign": "center", "marginBottom": "20px", "color": "#333"}),
                            html.P("Please login to continue",
                                   style={"TextAlign": "center", "marginBottom": "30px", "color": "#666"}),
                            
                            # Tabs for login methods
                            dcc.Tabs(
                                id="login-tabs",
                                value=default_method,
                                children=[
                                    dcc.Tab(label="Password", value="password", children=[
                                        html.Div(style={"padding": "20px 0"}, children=[
                                            dcc.Input(
                                                id="login-email",
                                                type="email",
                                                placeholder="Email",
                                                value=prefill_email,
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "15px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dcc.Input(
                                                id="login-password",
                                                type="password",
                                                placeholder="Password",
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "20px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dbc.Button(
                                                "Login",
                                                id="login-btn",
                                                color="primary",
                                                style={"width": "100%"}
                                            ),
                                        ])
                                    ]),
                                    dcc.Tab(label="PIN", value="pin", children=[
                                        html.Div(style={"padding": "20px 0"}, children=[
                                            dcc.Input(
                                                id="login-email-pin",
                                                type="email",
                                                placeholder="Email",
                                                value=prefill_email,
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "15px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dcc.Input(
                                                id="login-pin",
                                                type="password",
                                                placeholder="4-Digit PIN",
                                                maxLength=4,
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "20px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd",
                                                    "textAlign": "center",
                                                    "letterSpacing": "5px"
                                                }
                                            ),
                                            dbc.Button(
                                                "Login with PIN",
                                                id="login-pin-btn",
                                                color="primary",
                                                style={"width": "100%"}
                                            ),
                                        ])
                                    ]),
                                    dcc.Tab(label="Pattern", value="pattern", children=[
                                        html.Div(style={"padding": "20px 0"}, children=[
                                            dcc.Input(
                                                id="login-email-pattern",
                                                type="email",
                                                placeholder="Email",
                                                value=prefill_email,
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "15px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dcc.Input(
                                                id="login-pattern",
                                                type="text",
                                                placeholder="9-Dot Pattern (e.g., 1-2-3-5-7)",
                                                style={
                                                    "width": "100%",
                                                    "padding": "12px",
                                                    "marginBottom": "20px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dbc.Button(
                                                "Login with Pattern",
                                                id="login-pattern-btn",
                                                color="primary",
                                                style={"width": "100%"}
                                            ),
                                        ])
                                    ]),
                                ]
                            ),
                            
                            # Remember me checkbox
                            html.Div(
                                style={"marginTop": "20px", "marginBottom": "20px"},
                                children=[
                                    dbc.Checkbox(
                                        id="remember-me-checkbox",
                                        label="Remember me on this device",
                                        style={"fontSize": "14px"}
                                    )
                                ]
                            ),
                            
                            html.Hr(),
                            
                            html.Div(
                                dcc.Link("← Change Society", href="/dashboard", 
                                        style={"color": "#667eea", "textDecoration": "none"}),
                                style={"textAlign": "center", "marginTop": "15px"}
                            )
                        ]
                    )
                ]
            )
        ]
    )
    
    return layout