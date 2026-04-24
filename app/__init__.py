# app/__init__.py
from flask import Flask, jsonify, redirect
from flask_login import LoginManager
from flask_cors import CORS
import os
from dotenv import load_dotenv

load_dotenv()

login_manager = LoginManager()


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
    is_prod = os.environ.get('FLASK_CONFIG') == 'production'
    app.config['SESSION_COOKIE_SECURE'] = is_prod
    app.config['REMEMBER_COOKIE_SECURE'] = is_prod

    CORS(app, supports_credentials=True)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Database pool
    from database.db_manager import db
    db.init_app(app)

    # Blueprints
    from app.routes.auth import auth_bp
    from app.routes.api import api_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return redirect('/dashboard/')

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    print("✓ Flask app created")
    return app


def create_dash_app(flask_app):
    """Mount Dash onto Flask and load full shell layout + callbacks."""
    from dash import Dash, html
    import dash_bootstrap_components as dbc
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.get(int(user_id))
        except Exception:
            return None

    dash_app = Dash(
        __name__,
        server=flask_app,
        url_base_pathname='/dashboard/',
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
        ],
        suppress_callback_exceptions=True,
        prevent_initial_callbacks='initial_duplicate',   # ← fixes allow_duplicate errors
        assets_folder=os.path.join(os.path.dirname(__file__), 'static', 'assets'),
        assets_url_path='/static/assets',
        meta_tags=[{'name': 'viewport',
                    'content': 'width=device-width, initial-scale=1.0'}],
    )

    dash_app.title = 'ApexEstateHub'

    # ── Layout ──────────────────────────────────────────────────
    try:
        from app.dash_apps.app_shell import shell_layout
        dash_app.layout = shell_layout
        print("✓ Shell layout loaded")
    except Exception as e:
        import traceback; traceback.print_exc()
        dash_app.layout = html.Div([
            html.H2("Layout Error", style={'color': 'red', 'textAlign': 'center', 'marginTop': '80px'}),
            html.Pre(str(e), style={'textAlign': 'center', 'color': '#666'}),
        ])

    # ── Callbacks ────────────────────────────────────────────────
    try:
        from app.dash_apps.callbacks import register_all_callbacks
        register_all_callbacks(dash_app)
        print("✓ All callbacks registered")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"⚠ Callback registration failed: {e}")

    print("✓ Dash app ready at /dashboard/")
    return dash_app
