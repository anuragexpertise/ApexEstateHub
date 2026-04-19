from dash import html, dcc
import dash_bootstrap_components as dbc

def society_login_layout(society_name="EstateHub", prefill_email=None, default_method="password"):
    """Society login page"""
    
    layout = html.Div(
        [
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
                                   style={"textAlign": "center", "marginBottom": "30px", "color": "#666"}),
                            
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
                                style={"width": "100%", "marginBottom": "20px"}
                            ),
                            
                            html.Div(
                                dcc.Link("← Change Society", href="/dashboard/", 
                                        style={"color": "#667eea", "textDecoration": "none"}),
                                style={"textAlign": "center"}
                            )
                        ]
                    )
                ]
            )
        ]
    )
    
    return layout