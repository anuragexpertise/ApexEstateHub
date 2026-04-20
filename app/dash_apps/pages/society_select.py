from dash import html, dcc
import dash_bootstrap_components as dbc

def society_select_layout(societies_list=None, error_message=None, show_master_login=False):
    """Society selection page - Primary Login with Master Admin option"""
    
    if not societies_list:
        societies_list = []
    
    options = [{"label": s.get("name", "Unknown") if isinstance(s, dict) else str(s), 
                "value": s.get("id") if isinstance(s, dict) else i} 
               for i, s in enumerate(societies_list)]
    
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
                            "maxWidth": "500px",
                            "width": "100%",
                            "backgroundColor": "white",
                            "borderRadius": "20px",
                            "boxShadow": "0 20px 60px rgba(0,0,0,0.3)",
                            "overflow": "hidden",
                            "padding": "40px"
                        },
                        children=[
                            html.H1("ApexEstateHub", 
                                   style={"textAlign": "center", "marginBottom": "20px", "color": "#333"}),
                            html.H3("Welcome Back!", 
                                   style={"textAlign": "center", "marginBottom": "10px"}),
                            html.P("Please select your society to continue",
                                   style={"textAlign": "center", "marginBottom": "30px", "color": "#666"}),
                            
                            # Error message
                            html.Div(
                                error_message,
                                style={
                                    "color": "red",
                                    "textAlign": "center",
                                    "marginBottom": "20px",
                                    "display": "block" if error_message else "none"
                                }
                            ) if error_message else None,
                            
                            # Society dropdown
                            html.Label("Select Society", 
                                      style={"display": "block", "marginBottom": "8px", "fontWeight": "500"}),
                            dcc.Dropdown(
                                id="society-dropdown",
                                options=options,
                                placeholder="Choose your society...",
                                style={"marginBottom": "20px"}
                            ),
                            
                            # Remember checkbox
                            html.Div(
                                style={"marginBottom": "20px"},
                                children=[
                                    dbc.Checkbox(
                                        id="remember-society-checkbox",
                                        label="Remember this society",
                                        style={"fontSize": "14px"}
                                    )
                                ]
                            ),
                            
                            # Continue button
                            dbc.Button(
                                "Continue to Login",
                                id="society-select-btn",
                                color="primary",
                                style={"width": "100%", "marginBottom": "20px"}
                            ),
                            
                            html.Hr(),
                            
                            # Master Admin Section (conditional - shows when no societies)
                            html.Div(
                                id="master-admin-section",
                                style={"display": "block" if show_master_login else "none"},
                                children=[
                                    html.P("No societies found. Login as Master Admin to create one.",
                                           style={"textAlign": "center", "marginBottom": "15px", "color": "#e74c3c"}),
                                    html.Div(
                                        style={"marginBottom": "15px"},
                                        children=[
                                            dcc.Input(
                                                id="master-admin-email",
                                                type="email",
                                                value="master@estatehub.com",
                                                placeholder="Email",
                                                style={
                                                    "width": "100%",
                                                    "padding": "10px",
                                                    "marginBottom": "10px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dcc.Input(
                                                id="master-admin-password",
                                                type="password",
                                                placeholder="Password",
                                                style={
                                                    "width": "100%",
                                                    "padding": "10px",
                                                    "marginBottom": "20px",
                                                    "borderRadius": "8px",
                                                    "border": "1px solid #ddd"
                                                }
                                            ),
                                            dbc.Button(
                                                "Master Admin Login",
                                                id="master-admin-login-btn",
                                                color="danger",
                                                style={"width": "100%"}
                                            )
                                        ]
                                    )
                                ]
                            ),
                            
                            html.P("Need help? Contact your society administrator",
                                   style={"textAlign": "center", "color": "#999", "fontSize": "12px", "marginTop": "20px"})
                        ]
                    )
                ]
            )
        ]
    )
    
    return layout