# app/__init__.py
"""
Flask + Dash application factory for EstateHub.
"""

import os
import logging
from pathlib import Path

from flask import Flask, jsonify, request
from flask_login import LoginManager
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)

login_manager = LoginManager()


def _wants_json() -> bool:
    """True for API/auth calls and XHR/fetch requests, false for a browser
    navigating directly to a page."""
    if request.path.startswith(("/api/", "/auth/")):
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and \
        request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


_ERROR_PAGE = """<!DOCTYPE html>
<html><head><title>{title}</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f7fb;
     display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{background:#fff;border-radius:12px;padding:40px;max-width:420px;text-align:center;
      box-shadow:0 4px 20px rgba(0,0,0,.08)}}
.card h1{{font-size:22px;margin:0 0 10px}}
.card p{{color:#666;margin:0 0 20px}}
.card a{{color:#667eea;text-decoration:none;font-weight:600}}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p>
<a href="/">Back to EstateHub</a></div></div></body></html>"""


def _register_error_handlers(app: Flask) -> None:
    """
    A previously-uncaught exception anywhere in a Flask view (most often a
    DB/network failure — see database/db_manager.py) returned Flask's bare
    default error page with no JSON body. Any fetch()-based caller (login.html,
    push.js, Dash's own client) that then does response.json() throws a second,
    unrelated error, and the user sees either nothing or a generic "network
    error" that isn't actually accurate. These handlers guarantee every error
    response is JSON for API/fetch callers and a small branded page otherwise,
    and never leaks a stack trace or raw exception text to the user.
    """

    @app.errorhandler(404)
    def _not_found(exc):
        if _wants_json():
            return jsonify({"success": False, "message": "Not found"}), 404
        return _ERROR_PAGE.format(
            title="Page not found",
            message="That page doesn't exist or may have moved.",
        ), 404

    @app.errorhandler(500)
    def _server_error(exc):
        log.exception("Unhandled server error on %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({
                "success": False,
                "message": "Something went wrong on our end. Please try again shortly.",
            }), 500
        return _ERROR_PAGE.format(
            title="Something went wrong",
            message="We hit an unexpected error. Please try again in a moment.",
        ), 500

    @app.errorhandler(Exception)
    def _unhandled(exc):
        # Any exception not already a recognised HTTP error (e.g. a raw
        # psycopg2.OperationalError bubbling up from a route with no local
        # try/except) lands here instead of crashing the worker with a
        # blank response.
        if isinstance(exc, HTTPException):
            return exc
        log.exception("Unhandled exception on %s %s", request.method, request.path)
        if _wants_json():
            return jsonify({
                "success": False,
                "message": "Something went wrong on our end. Please try again shortly.",
            }), 500
        return _ERROR_PAGE.format(
            title="Something went wrong",
            message="We hit an unexpected error. Please try again in a moment.",
        ), 500


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
    _register_error_handlers(app)

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
        from app.routes.push_routes import push_bp
        from app.routes.sse   import sse_bp
        from app.routes.presumed_visitor import presumed_bp
        app.register_blueprint(auth_bp, url_prefix="/auth")
        app.register_blueprint(api_bp,  url_prefix="/api")
        app.register_blueprint(web_bp)
        app.register_blueprint(scan_bp)
        app.register_blueprint(push_bp)
        app.register_blueprint(sse_bp)
        app.register_blueprint(presumed_bp)
        log.info("Blueprints registered ✓")
    except Exception as exc:
        log.warning("Blueprint registration partial: %s", exc)

    return app


# ── Dash factory ──────────────────────────────────────────────────────────────

def create_dash_app(flask_app: Flask):
    from app.dash_apps import create_dash_app as _make_dash
    return _make_dash(flask_app)
