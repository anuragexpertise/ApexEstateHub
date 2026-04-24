# app/dash_apps/__init__.py
from dash import Dash, html
import dash_bootstrap_components as dbc

def create_dash_app(flask_app):
    """Create and configure the Dash application"""

    dash_app = Dash(
        __name__,
        server=flask_app,
        url_base_pathname='/dashboard/',
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
        ],
        suppress_callback_exceptions=True,
        assets_folder='app/static/assets',
        assets_url_path='/static'
    )

    # Set index string to a simple HTML shell
    dash_app.index_string = '''
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                }
                .dash-loading {
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    text-align: center;
                }
                .dash-loading i {
                    font-size: 48px;
                    color: #667eea;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        </head>
        <body>
            <div class="dash-loading">
                <i class="fas fa-spinner fa-pulse"></i>
                <p>Loading ApexEstateHub...</p>
            </div>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    '''

    # Import layout from app_shell
    try:
        from .app_shell import shell_layout
        dash_app.layout = shell_layout()
        print("✓ Shell layout loaded from app_shell.py")
    except ImportError as e:
        print(f"⚠️ Could not load shell layout: {e}")
        # Fallback simple layout
        dash_app.layout = html.Div(
            [
                html.H1("ApexEstateHub", style={"textAlign": "center", "marginTop": "50px"}),
                html.P("Loading dashboard...", style={"textAlign": "center"}),
            ],
            style={"minHeight": "100vh", "background": "#f5f7fb"}
        )

    # Register callbacks
    try:
        from .callbacks import register_all_callbacks
        register_all_callbacks(dash_app)
        print("✓ All callbacks registered")
    except ImportError as e:
        print(f"⚠️ Could not register callbacks: {e}")

    return dash_app
