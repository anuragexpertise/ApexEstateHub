import jwt
import os
import time
import logging
from functools import wraps
from flask import request, jsonify, current_app
from app.models.user import User

log = logging.getLogger(__name__)

# ── SECURITY (fixed 2026-08): this is now the ONLY place JWT_SECRET is
# read from the environment. Previously app/routes/auth.py defined its
# own independent copy of JWT_SECRET with a DIFFERENT fallback string
# ('change-me-in-production' vs this module's 'your-jwt-secret-key-
# change-this'). Both read the same JWT_SECRET_KEY env var, so this only
# mattered if that var was ever unset in some environment — but if it
# was, tokens minted by /auth/login (routes/auth.py's fallback) would
# silently fail verification in @token_required (this module's
# fallback), and vice versa, since jwt.decode() requires an exact key
# match. app/routes/auth.py now imports JWT_SECRET and
# generate_tokens_for() from here instead of redefining them.
JWT_SECRET = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key-change-this')
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour
JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))  # 30 days

if os.getenv('JWT_SECRET_KEY') is None:
    log.warning(
        "JWT_SECRET_KEY is not set — falling back to an insecure default "
        "signing key. Set JWT_SECRET_KEY in the environment before "
        "deploying to production."
    )


def generate_tokens_for(user_id, email, role, society_id=None):
    """
    Core token generator — everything else (generate_tokens(user) below,
    and app/routes/auth.py's login/refresh routes) wraps this so there is
    exactly one place that builds JWT payloads and signs them.
    """
    now = int(time.time())
    access_payload = {
        'user_id': user_id,
        'email': email,
        'role': role,
        'society_id': society_id,
        'type': 'access',
        'iat': now,
        'exp': now + JWT_ACCESS_TOKEN_EXPIRES
    }

    refresh_payload = {
        'user_id': user_id,
        'type': 'refresh',
        'iat': now,
        'exp': now + JWT_REFRESH_TOKEN_EXPIRES
    }

    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm='HS256')

    return access_token, refresh_token


def generate_tokens(user):
    """Generate access and refresh tokens for a User model instance."""
    return generate_tokens_for(user.id, user.email, user.role, user.society_id)

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

    user = User.get(payload.get('user_id'))
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
            role = request.user_payload.get('role')
            if role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator