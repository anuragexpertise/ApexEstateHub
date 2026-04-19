from flask import Blueprint, request, jsonify, session, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.services.auth_service import authenticate_user, authenticate_pin, authenticate_pattern
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - API endpoint for Dash"""
    if request.method == 'POST':
        data = request.get_json() or request.form
        email = data.get('email')
        password = data.get('password')
        society_id = data.get('society_id')
        method = data.get('method', 'password')
        
        # Authenticate based on method
        if method == 'password':
            user = authenticate_user(email, password, society_id)
        elif method == 'pin':
            user = authenticate_pin(email, password, society_id)
        elif method == 'pattern':
            user = authenticate_pattern(email, password, society_id)
        else:
            user = None
        
        if user:
            login_user(user, remember=data.get('remember', False))
            session['role'] = user['role'] if isinstance(user, dict) else user.role
            session['society_id'] = user['society_id'] if isinstance(user, dict) else user.society_id
            
            # Determine redirect based on role
            user_role = user['role'] if isinstance(user, dict) else user.role
            user_society_id = user['society_id'] if isinstance(user, dict) else user.society_id
            
            if user_role == 'admin' and user_society_id is None:
                redirect_url = '/dashboard/master'
            elif user_role == 'admin':
                redirect_url = '/dashboard/admin-portal'
            elif user_role == 'apartment':
                redirect_url = '/dashboard/owner-portal'
            elif user_role == 'vendor':
                redirect_url = '/dashboard/vendor-portal'
            elif user_role == 'security':
                redirect_url = '/dashboard/pass-evaluation'
            else:
                redirect_url = '/dashboard'
            
            return jsonify({
                'success': True,
                'redirect': redirect_url,
                'user': {
                    'id': user['user_id'] if isinstance(user, dict) else user.id,
                    'email': user['email'] if isinstance(user, dict) else user.email,
                    'role': user_role,
                    'society_id': user_society_id
                }
            })
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    # GET request - redirect to Dash
    return redirect('/dashboard')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect('/dashboard')


@auth_bp.route('/check-auth')
def check_auth():
    """Check if user is authenticated"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user_id': current_user.id,
            'email': current_user.email,
            'role': current_user.role,
            'society_id': current_user.society_id
        })
    return jsonify({'authenticated': False})