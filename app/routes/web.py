from flask import Blueprint, render_template, send_from_directory, current_app
from flask_login import login_required, current_user
import os

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    """Home page - redirects to dashboard or login"""
    if current_user.is_authenticated:
        if current_user.is_master_admin():
            return render_template('index.html', dash_url='/dashboard/master')
        elif current_user.role == 'admin':
            return render_template('index.html', dash_url='/dashboard/admin-portal')
        elif current_user.role == 'apartment':
            return render_template('index.html', dash_url='/dashboard/owner-portal')
        elif current_user.role == 'vendor':
            return render_template('index.html', dash_url='/dashboard/vendor-portal')
        elif current_user.role == 'security':
            return render_template('index.html', dash_url='/dashboard/pass-evaluation')
    
    return render_template('index.html', dash_url='/dashboard')

@web_bp.route('/dashboard')
@web_bp.route('/dashboard/<path:path>')
@login_required
def dashboard(path=None):
    """Dashboard route - serves the Dash app"""
    return render_template('dashboard.html')

@web_bp.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@web_bp.route('/assets/<path:filename>')
def assets_files(filename):
    """Serve assets files"""
    return send_from_directory('static/assets', filename)