 
# test_minimal.py - Completely standalone Dash test
from dash import Dash, html
import dash_bootstrap_components as dbc

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div(
    [
        html.H1("Standalone Dash Test", style={"textAlign": "center", "marginTop": "50px"}),
        html.P("This is a standalone Dash app", style={"textAlign": "center"}),
        dbc.Button("Click Me", color="primary", className="d-block mx-auto mt-3"),
    ],
    style={"padding": "20px"}
)

if __name__ == '__main__':
    print("Starting standalone Dash on http://localhost:8051")
    app.run(debug=True, port=8051)
