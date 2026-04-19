from dash import html, dcc
import dash_bootstrap_components as dbc

def society_select_layout(societies_list=None, error_message=None, show_master_login=False):
    """Society selection page"""
    
    if not societies_list:
        societies_list = []
    
    options = [{"label": s.get("name", "Unknown"), "value": s.get("id")} for s in societies_list]
    
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
                            
                            dcc.Dropdown(
                                id="society-dropdown",
                                options=options,
                                placeholder="Choose your society...",
                                style={"marginBottom": "20px"}
                            ),
                            
                            dbc.Button(
                                "Continue to Login",
                                id="society-select-btn",
                                color="primary",
                                style={"width": "100%", "marginBottom": "20px"}
                            ),
                            
                            html.Hr(),
                            
                            html.P("First time? Contact your society administrator",
                                   style={"textAlign": "center", "color": "#999", "fontSize": "12px"})
                        ]
                    )
                ]
            )
        ]
    )
    
    return layout