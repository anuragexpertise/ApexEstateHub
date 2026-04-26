from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_cors import CORS
from dash import Dash, html
import dash_bootstrap_components as dbc
import os

# ── Extensions (initialised without app, bound in create_app) ──────────────
db           = SQLAlchemy()
login_manager = LoginManager()
migrate      = Migrate()


# ══════════════════════════════════════════════════════════════════════════════
# Flask application factory
# ══════════════════════════════════════════════════════════════════════════════
def create_app(config_name=None):
    """Create and configure the Flask application."""

    if config_name is None:
        config_name = os.getenv('FLASK_CONFIG', 'development')

    from app.config import config

    app = Flask(
        __name__,
        # Flask static files (login.html, sw.js, push.js, logo.png …)
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
        static_url_path='/static',
    )
    app.config.from_object(config[config_name])

    # ── Bind extensions ────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    # ── Flask-Login config ─────────────────────────────────────────
    login_manager.login_view       = 'auth.login'
    login_manager.login_message    = 'Please log in to access this page.'
    login_manager.session_protection = 'strong'

    # ── Blueprints ─────────────────────────────────────────────────
    try:
        from app.routes.auth import auth_bp
        from app.routes.api  import api_bp
        from app.routes.web  import web_bp

        app.register_blueprint(auth_bp, url_prefix='/auth')
        app.register_blueprint(api_bp,  url_prefix='/api')
        app.register_blueprint(web_bp)
        print("✓ Blueprints registered")
    except Exception as e:
        print(f"⚠️  Blueprint error: {e}")

    return app


# ══════════════════════════════════════════════════════════════════════════════
# Dash application factory
# ══════════════════════════════════════════════════════════════════════════════
def create_dash_app(flask_app):
    """Mount the Dash SPA onto the Flask server.

    CSS / JS loading
    ----------------
    Dash automatically injects every file inside `assets_folder` into its
    pages (no manual <link> or <script> tags required).

    Correct folder  →  app/assets/          (resolved below via __file__)
    Wrong folder    →  app/static/css/      (Flask serves it, Dash ignores it)

    Keep app/static/ for Flask-only files:
        • templates/login.html  (references /static/css/style.css)
        • static/js/sw.js       (service-worker, registered at root scope)
        • static/js/push.js
        • static/assets/logo.png
    """

    # Absolute path → app/assets/  (sibling of this __init__.py)
    _here         = os.path.dirname(os.path.abspath(__file__))
    assets_folder = os.path.join(_here, 'assets')
    os.makedirs(assets_folder, exist_ok=True)   # create on first run

    dash_app = Dash(
        __name__,
        server               = flask_app,
        url_base_pathname    = '/dashboard/',
        # ↓ KEY: Dash loads style.css (and any .js) from here automatically
        assets_folder        = assets_folder,
        assets_url_path      = '/dashboard/assets',
        external_stylesheets = [
            dbc.themes.BOOTSTRAP,
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',
        ],
        suppress_callback_exceptions = True,
        # Show a loading indicator while callbacks run
        update_title         = 'Loading… | ApexEstateHub',
    )

    # Expose the server for gunicorn / ApexWeave
    # (entry point:  from app import create_dash_app; server = dash_app.server)
    dash_app.title = 'ApexEstateHub'

    # ── Layout ────────────────────────────────────────────────────
    try:
        from app.dash_apps.layout import serve_layout
        dash_app.layout = serve_layout()
        print("✓ Dash layout loaded")
    except ImportError as e:
        print(f"⚠️  Layout import error: {e}")
        dash_app.layout = _fallback_layout(str(e))

    # ── Callbacks ─────────────────────────────────────────────────
    try:
        from app.dash_apps.callbacks import register_callbacks
        register_callbacks(dash_app)
        print("✓ Callbacks registered")
    except ImportError as e:
        print(f"⚠️  Callback import error: {e}")

    return dash_app


# ── Private helpers ────────────────────────────────────────────────────────
def _fallback_layout(error_msg: str):
    """Minimal layout shown when the real layout cannot be imported."""
    return html.Div(
        [
            html.H1("ApexEstateHub",
                    style={"textAlign": "center", "marginTop": "60px", "color": "#2c3e50"}),
            html.P("⚠️  Could not load dashboard layout.",
                   style={"textAlign": "center", "color": "#e74c3c", "marginTop": "10px"}),
            html.Pre(error_msg,
                     style={"maxWidth": "700px", "margin": "20px auto",
                            "background": "#f8f9fa", "padding": "15px",
                            "borderRadius": "8px", "fontSize": "13px"}),
        ],
        style={"fontFamily": "sans-serif"}
    )