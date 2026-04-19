import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from app.models.user import User

JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key-change-this')
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour
JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))  # 30 days

def generate_tokens(user):
    """Generate access and refresh tokens for user"""
    access_payload = {
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'society_id': user.society_id,
        'type': 'access',
        'exp': datetime.utcnow() + timedelta(seconds=JWT_ACCESS_TOKEN_EXPIRES)
    }
    
    refresh_payload = {
        'user_id': user.id,
        'type': 'refresh',
        'exp': datetime.utcnow() + timedelta(seconds=JWT_REFRESH_TOKEN_EXPIRES)
    }
    
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm='HS256')
    
    return access_token, refresh_token

def verify_token(token):
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return {'error': 'Token expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}

def refresh_access_token(refresh_token):
    """Generate new access token using refresh token"""
    payload = verify_token(refresh_token)
    if payload.get('error') or payload.get('type') != 'refresh':
        return None, 'Invalid refresh token'
    
    user = User.query.get(payload.get('user_id'))
    if not user:
        return None, 'User not found'
    
    access_token, _ = generate_tokens(user)
    return access_token, None

def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        payload = verify_token(token)
        if payload.get('error'):
            return jsonify({'error': payload['error']}), 401
        
        request.user_payload = payload
        return f(*args, **kwargs)
    
    return decorated

def role_required(allowed_roles):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            user_role = request.user_payload.get('role')
            if user_role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator