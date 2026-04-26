from dash import Dash, html

app = Dash(__name__)

app.layout = html.Div([
    html.H1("ApexEstateHub - Test Page", style={"textAlign": "center", "marginTop": "50px"}),
    html.P("If you can see this, Dash is working!", style={"textAlign": "center"}),
    html.Button("Click Me", style={"display": "block", "margin": "20px auto"})
])

if __name__ == '__main__':
    app.run(debug=True, port=8051)