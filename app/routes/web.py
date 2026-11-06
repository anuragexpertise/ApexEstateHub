# app/routes/web.py — NEW FILE
from flask import Blueprint, redirect, jsonify

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return redirect('/dashboard/')

@web_bp.route('/health')
def health():
    try:
        from database.db_manager import db
        if db.is_healthy():
            return jsonify({'status': 'ok', 'db': 'connected'})
        else:
            return jsonify({'status': 'error', 'db': 'disconnected'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'db': str(e)}), 500