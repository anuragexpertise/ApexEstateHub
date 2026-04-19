from flask import Blueprint, redirect, send_from_directory
from flask_login import login_required, current_user
import os

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    """Home page - redirect to dashboard"""
    return redirect('/dashboard')


@web_bp.route('/dashboard')
@web_bp.route('/dashboard/<path:path>')
def dashboard(path=None):
    """Dashboard route - redirect to Dash app"""
    # Dash app is mounted at /dashboard/
    # This just ensures the route works
    return redirect('/dashboard/')


@web_bp.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)


@web_bp.route('/static/assets/<path:filename>')
def assets_files(filename):
    """Serve assets files"""
    return send_from_directory('static/assets', filename)