# app/__init__.py
from flask import Flask, jsonify, redirect
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

    # Add test route for debugging
    @app.route('/test')
    def test():
        return jsonify({
            "status": "ok",
            "message": "Flask server is running",
            "routes": [str(rule) for rule in app.url_map.iter_rules()][:10]
        })

    # Home route
    @app.route('/')
    def index():
        return redirect('/dashboard/')

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

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

    # Simple test layout
    dash_app.layout = html.Div(
        [
            html.H1("ApexEstateHub - Dashboard",
                   style={"textAlign": "center", "color": "#2c3e50", "paddingTop": "50px"}),
            html.P("If you see this, Dash is working!",
                   style={"textAlign": "center", "fontSize": "18px", "color": "#666"}),
            html.Div(
                dbc.Button("Test Button", color="primary", size="lg"),
                style={"textAlign": "center", "marginTop": "30px"}
            ),
        ],
        style={"minHeight": "100vh", "background": "#f5f7fb"}
    )

    print("✓ Dash app created with test layout")

    return dash_app
