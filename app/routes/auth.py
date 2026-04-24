# app/routes/auth.py
from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from database.db_manager import db
from app.models.user import User
import jwt
import os
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'your-jwt-secret-key')
JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES', 3600))
JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000))


def generate_tokens(user_id, email, role):
    """Generate access and refresh tokens"""
    now = datetime.utcnow()
    
    access_token = jwt.encode({
        'user_id': user_id,
        'email': email,
        'role': role,
        'exp': now + timedelta(seconds=JWT_ACCESS_TOKEN_EXPIRES),
        'iat': now,
        'type': 'access'
    }, JWT_SECRET, algorithm='HS256')
    
    refresh_token = jwt.encode({
        'user_id': user_id,
        'exp': now + timedelta(seconds=JWT_REFRESH_TOKEN_EXPIRES),
        'iat': now,
        'type': 'refresh'
    }, JWT_SECRET, algorithm='HS256')
    
    return access_token, refresh_token


def verify_token(token):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return {'error': 'Token expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}


@auth_bp.route('/login', methods=['POST'])
def login():
    """API login endpoint - supports password, PIN, pattern"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    pin = data.get('pin')
    pattern = data.get('pattern')
    society_id = data.get('society_id')
    method = data.get('method', 'password')
    
    user = None
    
    # Authenticate based on method
    if method == 'password' and password:
        from app.services.auth_service import authenticate_user
        user_data = authenticate_user(email, password, society_id)
        
    elif method == 'pin' and pin:
        from app.services.auth_service import authenticate_pin
        user_data = authenticate_pin(email, pin, society_id)
        
    elif method == 'pattern' and pattern:
        from app.services.auth_service import authenticate_pattern
        user_data = authenticate_pattern(email, pattern, society_id)
    else:
        return jsonify({'success': False, 'message': 'Invalid authentication method'}), 400
    
    if user_data:
        # Create User object for Flask-Login
        user = User(
            user_id=user_data['user_id'],
            email=user_data['email'],
            role=user_data['role'],
            society_id=user_data.get('society_id'),
            name=user_data.get('name'),
            phone=user_data.get('phone')
        )
        login_user(user, remember=data.get('remember', False))
        
        # Generate JWT tokens for API
        access_token, refresh_token = generate_tokens(
            user.id, user.email, user.role
        )
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict(),
            'redirect': get_redirect_url(user.role, user.society_id)
        })
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401


@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """Refresh access token using refresh token"""
    data = request.json
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({'error': 'Refresh token required'}), 400
    
    payload = verify_token(refresh_token)
    
    if payload.get('error'):
        return jsonify({'error': payload['error']}), 401
    
    if payload.get('type') != 'refresh':
        return jsonify({'error': 'Invalid token type'}), 401
    
    # Generate new access token
    access_token, _ = generate_tokens(
        payload['user_id'], 
        payload.get('email', ''), 
        payload.get('role', '')
    )
    
    return jsonify({'access_token': access_token})


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Logout user"""
    logout_user()
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@auth_bp.route('/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict()
        })
    return jsonify({'authenticated': False}), 401


@auth_bp.route('/societies', methods=['GET'])
@login_required
def get_societies():
    """Get list of societies for society selection"""
    try:
        societies = db.execute_query(
            "SELECT id, name, address, logo FROM societies ORDER BY name",
            fetch_all=True
        )
        return jsonify({'societies': societies or []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_redirect_url(role, society_id):
    """Get redirect URL based on user role"""
    if role == 'admin':
        if society_id is None:
            return '/dashboard/master'
        return '/dashboard/admin-portal'
    elif role == 'apartment':
        return '/dashboard/owner-portal'
    elif role == 'vendor':
        return '/dashboard/vendor-portal'
    elif role == 'security':
        return '/dashboard/pass-evaluation'
    return '/dashboard'