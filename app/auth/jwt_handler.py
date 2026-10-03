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
_DEFAULT_JWT_SECRET = 'your-jwt-secret-key-change-this'


def _is_production() -> bool:
    """True on Render (it sets RENDER) or when an env flag says production."""
    return bool(os.getenv('RENDER')) or any(
        os.getenv(k, '').strip().lower() == 'production' for k in ('APP_ENV', 'FLASK_ENV', 'ENV')
    )


JWT_SECRET = os.getenv('JWT_SECRET_KEY') or _DEFAULT_JWT_SECRET
JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour
JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))  # 30 days

# FAIL CLOSED in production. A published default signing key means anyone can
# mint a valid token for any user id, so the app must refuse to boot rather
# than warn and carry on. Outside production (local dev, tests) it still warns.
if JWT_SECRET == _DEFAULT_JWT_SECRET:
    if _is_production():
        raise RuntimeError(
            "JWT_SECRET_KEY is unset (or still the built-in default) in a production "
            "environment. Set a long random JWT_SECRET_KEY before starting the app."
        )
    log.warning(
        "JWT_SECRET_KEY is not set — falling back to an insecure development key. "
        "Never deploy like this."
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
    """Verify a JWT's signature and expiry and return its payload.

    The payload is only PROOF THAT WE ISSUED THIS TOKEN. Never authorise from
    its role/society claims — they go stale (a demoted admin keeps the old
    role until expiry). Use authenticate_bearer() to get the current identity.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'], options={'require': ['exp']})
    except jwt.ExpiredSignatureError:
        return {'error': 'Token expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}


def authenticate_bearer(token, expected_type='access'):
    """Resolve a bearer token to the CURRENT user, from the database.

    Returns (user, None) on success or (None, error_message). Only the token's
    signature, expiry, type and user_id are used; role, society_id and
    linked_id are re-read from the database on every call, so a role change,
    demotion or deleted account takes effect on the next request instead of
    when the token expires. A refresh token is rejected where an access
    token is expected (it used to be accepted by every push route).
    """
    payload = verify_token(token)
    if payload.get('error'):
        return None, payload['error']
    if payload.get('type') != expected_type:
        return None, 'Invalid token type'
    user_id = payload.get('user_id')
    if not user_id:
        return None, 'Invalid token'
    user = User.get(user_id)
    if user is None:
        return None, 'User not found'
    return user, None


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

def _bearer_from_request():
    header = request.headers.get('Authorization', '')
    return header[7:] if header.startswith('Bearer ') else header


def token_required(f):
    """Require a valid access token and pass the DB-resolved user as the FIRST
    argument (`def view(current_user, ...)`). Identity is re-resolved from the
    database on every request — see authenticate_bearer()."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _bearer_from_request()
        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        user, error = authenticate_bearer(token)
        if error:
            return jsonify({'error': error}), 401

        # Same shape as before, but built from the database, not the token.
        request.user_payload = {
            'user_id': user.id, 'email': user.email, 'role': user.role,
            'society_id': user.society_id, 'linked_id': user.linked_id,
            'type': 'access',
        }
        return f(user, *args, **kwargs)

    return decorated


def role_required(allowed_roles):
    """Like token_required, but also requires the CURRENT role to be allowed."""
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(current_user, *args, **kwargs):
            if current_user.role not in allowed_roles:
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(current_user, *args, **kwargs)
        return decorated
    return decorator
