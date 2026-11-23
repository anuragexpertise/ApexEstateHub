# app/routes/web.py
import logging

from flask import Blueprint, jsonify, redirect

log = logging.getLogger(__name__)
web_bp = Blueprint('web', __name__)


@web_bp.route('/')
def index():
    return redirect('/dashboard/')


@web_bp.route('/health')
@web_bp.route('/healthz')
def health():
    """Liveness + DB reachability. Unauthenticated by design (Render health
    check); never returns exception text."""
    try:
        from database.db_manager import db
        if db.is_healthy():
            return jsonify({'status': 'ok', 'db': 'connected'})
        return jsonify({'status': 'error', 'db': 'disconnected'}), 503
    except Exception:  # noqa: BLE001
        log.exception("health check failed")
        return jsonify({'status': 'error', 'db': 'unavailable'}), 503
