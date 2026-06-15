# app/__init__.py
"""
Flask + Dash application factory for EstateHub.
"""

import os
import logging
from pathlib import Path

from flask import Flask
from flask_login import LoginManager
from flask_cors import CORS

log = logging.getLogger(__name__)

login_manager = LoginManager()


def _ensure_asset_dirs(base: Path):
    for sub in ("default/society", "default/apartment", "default/vendor",
                "default/security", "default/concern", "default/event"):
        (base / sub).mkdir(parents=True, exist_ok=True)


# ── Flask factory ─────────────────────────────────────────────────────────────

def create_app(config_name: str | None = None) -> Flask:
    config_name = config_name or os.getenv("FLASK_CONFIG", "development")

    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
        static_url_path="/static",
    )

    # Config
    from app.config import config as config_map
    app.config.from_object(config_map[config_name])

    # Extensions
    login_manager.init_app(app)
    CORS(app)

    # Asset dirs
    assets_path = Path(__file__).parent / "assets"
    _ensure_asset_dirs(assets_path)
    from flask import send_from_directory

    @app.route("/assets/<path:filename>")
    def serve_asset(filename):
        return send_from_directory(str(assets_path), filename)

    # Flask-Login
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.get(int(user_id))

    # Blueprints
    try:
        from app.routes.auth  import auth_bp
        from app.routes.api   import api_bp
        from app.routes.web   import web_bp
        from app.routes.scan  import scan_bp
        app.register_blueprint(auth_bp, url_prefix="/auth")
        app.register_blueprint(api_bp,  url_prefix="/api")
        app.register_blueprint(web_bp)
        app.register_blueprint(scan_bp)
        log.info("Blueprints registered ✓")
    except Exception as exc:
        log.warning("Blueprint registration partial: %s", exc)

    return app


# ── Dash factory ──────────────────────────────────────────────────────────────

def create_dash_app(flask_app: Flask):
    from app.dash_apps import create_dash_app as _make_dash
    return _make_dash(flask_app)
