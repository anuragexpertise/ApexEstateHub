# ── SNIPPET: fix in app/routes/auth.py ───────────────────────────────────────
#
# BUG: authenticate_user() returns a plain dict (raw SQL row).
#      login_user() requires a Flask-Login UserMixin instance.
#      Calling login_user(dict) raises:
#        AttributeError: 'dict' object has no attribute 'is_authenticated'
#
# Replace the login() route body with the version below.

from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from database.db_manager import db
from app.models.user import User
import jwt, os
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

JWT_SECRET                 = os.environ.get('JWT_SECRET_KEY', 'change-me-in-production')
JWT_ACCESS_TOKEN_EXPIRES   = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES',  3600))
JWT_REFRESH_TOKEN_EXPIRES  = int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000))


def generate_tokens(user_id, email, role):
    now = datetime.utcnow()
    access_token = jwt.encode({
        'user_id': user_id, 'email': email, 'role': role,
        'exp': now + timedelta(seconds=JWT_ACCESS_TOKEN_EXPIRES),
        'iat': now, 'type': 'access',
    }, JWT_SECRET, algorithm='HS256')
    refresh_token = jwt.encode({
        'user_id': user_id,
        'exp': now + timedelta(seconds=JWT_REFRESH_TOKEN_EXPIRES),
        'iat': now, 'type': 'refresh',
    }, JWT_SECRET, algorithm='HS256')
    return access_token, refresh_token


@auth_bp.route('/login', methods=['POST'])
def login():
    data       = request.json or {}
    email      = data.get('email')
    password   = data.get('password')
    pin        = data.get('pin')
    pattern    = data.get('pattern')
    society_id = data.get('society_id')
    method     = data.get('method', 'password')

    user_dict = None

    if method == 'password' and password:
        from app.services.auth_service import authenticate_user
        user_dict = authenticate_user(email, password, society_id)
    elif method == 'pin' and pin:
        from app.services.auth_service import authenticate_pin
        user_dict = authenticate_pin(email, pin, society_id)
    elif method == 'pattern' and pattern:
        from app.services.auth_service import authenticate_pattern
        user_dict = authenticate_pattern(email, pattern, society_id)
    else:
        return jsonify({'success': False, 'message': 'Invalid authentication method'}), 400

    if not user_dict:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    # ── FIX: build a proper UserMixin object ─────────────────────
    user_obj = User(
        user_id=user_dict['user_id'],
        email=user_dict['email'],
        role=user_dict['role'],
        society_id=user_dict.get('society_id'),
    )
    login_user(user_obj, remember=data.get('remember', False))
    # ─────────────────────────────────────────────────────────────

    access_token, refresh_token = generate_tokens(
        user_obj.id, user_obj.email, user_obj.role
    )

    return jsonify({
        'success':       True,
        'access_token':  access_token,
        'refresh_token': refresh_token,
        'user':          user_obj.to_dict(),
        'redirect':      _redirect_url(user_obj.role, user_obj.society_id),
    })


def _redirect_url(role, society_id):
    if role == 'admin' and society_id is None:
        return '/dashboard/master'
    if role == 'admin':
        return '/dashboard/admin-portal'
    if role == 'apartment':
        return '/dashboard/owner-portal'
    if role == 'vendor':
        return '/dashboard/vendor-portal'
    if role == 'security':
        return '/dashboard/pass-evaluation'
    return '/dashboard/'


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})


@auth_bp.route('/check-auth', methods=['GET'])
def check_auth():
    if current_user.is_authenticated:
        return jsonify({'authenticated': True, 'user': current_user.to_dict()})
    return jsonify({'authenticated': False}), 401


@auth_bp.route('/societies', methods=['GET'])
def get_societies_list():
    try:
        societies = db.execute_query(
            'SELECT id, name, address, logo FROM societies ORDER BY name',
            fetch_all=True,
        )
        return jsonify({'societies': societies or []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500