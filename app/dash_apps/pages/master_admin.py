from dash import html, dcc
import dash_bootstrap_components as dbc

def layout():
    """Master Admin page"""
    
    return html.Div(
        [
            html.H2("🏢 Society Management", className="mb-4"),
            
            dbc.Card(
                [
                    dbc.CardHeader(html.H4("Create New Society")),
                    dbc.CardBody(
                        [
                            dbc.Row([
                                dbc.Col(dbc.Input(id="soc-name", placeholder="Society Name", className="mb-3"), width=6),
                                dbc.Col(dbc.Input(id="soc-email", placeholder="Email", className="mb-3"), width=6),
                            ]),
                            dbc.Row([
                                dbc.Col(dbc.Input(id="admin-email", placeholder="Admin Email", className="mb-3"), width=6),
                                dbc.Col(dbc.Input(id="admin-password", type="password", placeholder="Admin Password", className="mb-3"), width=6),
                            ]),
                            dbc.Button("Create Society", id="create-society-btn", color="primary")
                        ]
                    )
                ],
                className="mb-4"
            ),
            
            html.Div(id="society-list")
        ],
        style={"padding": "20px"}
    )