from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS
from dash import Dash, html, dcc, dependencies
import dash_bootstrap_components as dbc
import os

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'development')
    
    from app.config import config
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    
    # Configure login
    login_manager.login_view = 'auth.login'
    
    # Register blueprints
    try:
        from app.routes.auth import auth_bp
        from app.routes.api import api_bp
        from app.routes.web import web_bp
        
        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(api_bp, url_prefix='/api')
        app.register_blueprint(web_bp)
        print("✓ Blueprints registered")
    except Exception as e:
        print(f"⚠️ Blueprint error: {e}")
    
    return app


def create_dash_app(flask_app):
    """Create and configure Dash app"""
    
    dash_app = Dash(
        __name__,
        server=flask_app,
        url_base_pathname='/dashboard/',
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
        ],
        suppress_callback_exceptions=True,
    )
    
    # ============ USE FULL LAYOUT ============
    # Import the full layout from dash_apps/layout.py
    try:
        from app.dash_apps.layout import serve_layout
        dash_app.layout = serve_layout()
        print("✓ Full layout loaded from app/dash_apps/layout.py")
    except ImportError as e:
        print(f"⚠️ Could not load full layout: {e}")
        # Fallback layout
        dash_app.layout = html.Div([
            html.H1("ApexEstateHub", style={"textAlign": "center", "marginTop": "50px"}),
            html.P("Layout file not found. Please create app/dash_apps/layout.py", 
                   style={"textAlign": "center", "color": "red"})
        ])
    # =========================================
    
    # Register callbacks
    try:
        from app.dash_apps.callbacks import register_callbacks
        register_callbacks(dash_app)
        print("✓ Callbacks registered")
    except ImportError as e:
        print(f"⚠️ Could not register callbacks: {e}")
    
    return dash_app