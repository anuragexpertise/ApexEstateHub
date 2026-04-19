from dash import html
import dash_bootstrap_components as dbc
from datetime import datetime

def create_footer():
    """Create footer component with glassmorphism design"""
    
    current_year = datetime.now().year
    
    footer = html.Footer(
        dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                html.P(
                                    [
                                        html.I(className="fas fa-copyright me-1"),
                                        f" {current_year} ApexEstateHub. All rights reserved."
                                    ],
                                    className="mb-0"
                                )
                            ],
                            width="auto",
                            className="text-center text-md-start"
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.A(
                                            html.I(className="fab fa-github me-2"),
                                            href="#",
                                            target="_blank",
                                            className="text-muted me-3"
                                        ),
                                        html.A(
                                            html.I(className="fab fa-twitter me-2"),
                                            href="#",
                                            target="_blank",
                                            className="text-muted me-3"
                                        ),
                                        html.A(
                                            html.I(className="fas fa-envelope"),
                                            href="mailto:support@apexestatehub.com",
                                            className="text-muted"
                                        ),
                                    ],
                                    className="text-center text-md-end"
                                )
                            ],
                            width="auto",
                            className="ms-auto"
                        )
                    ],
                    align="center",
                    justify="between",
                    className="w-100"
                ),
                dbc.Row(
                    dbc.Col(
                        html.Small(
                            "Version 1.0.0 | Built with Flask, Dash, and NeonDB",
                            className="text-muted"
                        ),
                        width=12,
                        className="text-center mt-2"
                    )
                )
            ],
            fluid=True,
            style={"padding": "0 20px"}
        ),
        className="glass-footer",
        style={
            "position": "fixed",
            "bottom": "0",
            "right": "0",
            "left": "250px",
            "zIndex": "1000",
            "background": "rgba(255, 255, 255, 0.95)",
            "backdropFilter": "blur(10px)",
            "boxShadow": "0 -2px 15px rgba(0,0,0,0.05)",
            "padding": "12px 0",
            "transition": "all 0.3s ease"
        }
    )
    
    return footer