# app/__init__.py
from flask import Flask, redirect
from flask_login import LoginManager
from flask_cors import CORS
import os
from dotenv import load_dotenv

load_dotenv()

# Create login manager
login_manager = LoginManager()

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_CONFIG') == 'production'
    app.config['REMEMBER_COOKIE_SECURE'] = os.environ.get('FLASK_CONFIG') == 'production'

    # Initialize extensions
    CORS(app, supports_credentials=True)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page'

    # Initialize database connection pool
    from database.db_manager import db
    db.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    # Simple home route
    @app.route('/')
    def index():
        return redirect('/dashboard/')

    print("✓ Blueprints and routes registered")

    return app


def create_dash_app(flask_app):
    """Create and configure the Dash application"""
    from dash import Dash, html
    import dash_bootstrap_components as dbc

    # Setup user loader for this app
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        if user_id:
            return User.get(int(user_id))
        return None
        print("✓ User loader registered")

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

    # Set index string to a simple HTML shell (no template file needed)
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
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    background: #f5f7fb;
                }
                .dash-loading {
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    text-align: center;
                    z-index: 9999;
                }
                .dash-loading i {
                    font-size: 48px;
                    color: #667eea;
                    animation: spin 1s linear infinite;
                }
                .dash-loading p {
                    margin-top: 15px;
                    color: #667eea;
                    font-size: 14px;
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
                html.H1("ApexEstateHub", style={"textAlign": "center", "marginTop": "50px", "color": "#2c3e50"}),
                html.P("Loading dashboard...", style={"textAlign": "center", "color": "#666"}),
            ],
            style={"minHeight": "100vh", "background": "#f5f7fb", "padding": "20px"}
        )

    # Register callbacks
    try:
        from .callbacks import register_all_callbacks
        register_all_callbacks(dash_app)
        print("✓ All callbacks registered")
    except ImportError as e:
        print(f"⚠️ Could not register callbacks: {e}")

    return dash_app
