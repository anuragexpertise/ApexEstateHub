# app/routes/auth.py
from flask import Blueprint, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from database.db_manager import db
from app.models.user import User
import jwt, os, time
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

JWT_SECRET                = os.environ.get('JWT_SECRET_KEY', 'change-me-in-production')
JWT_ACCESS_TOKEN_EXPIRES  = int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES',  3600))
JWT_REFRESH_TOKEN_EXPIRES = int(os.environ.get('JWT_REFRESH_TOKEN_EXPIRES', 2592000))


# ── Token helpers ─────────────────────────────────────────────────────────────

def generate_tokens(user_id, email, role):
    now = int(time.time())
    access_token = jwt.encode({
        'user_id': user_id, 'email': email, 'role': role,
        'exp': now + JWT_ACCESS_TOKEN_EXPIRES,
        'iat': now, 'type': 'access',
    }, JWT_SECRET, algorithm='HS256')
    refresh_token = jwt.encode({
        'user_id': user_id,
        'exp': now + JWT_REFRESH_TOKEN_EXPIRES,
        'iat': now, 'type': 'refresh',
    }, JWT_SECRET, algorithm='HS256')
    return access_token, refresh_token


def _redirect_url(role, society_id):
    if role == 'master':
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


# ── Login ─────────────────────────────────────────────────────────────────────

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

    user_obj = User(
        user_id=user_dict['user_id'],
        email=user_dict['email'],
        role=user_dict['role'],
        society_id=user_dict.get('society_id'),
    )
    login_user(user_obj, remember=data.get('remember', False))

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


# ── Token refresh ─────────────────────────────────────────────────────────────

@auth_bp.route('/refresh', methods=['POST'])
def refresh_token():
    data  = request.json or {}
    token = data.get('refresh_token')
    if not token:
        return jsonify({'success': False, 'message': 'Refresh token required'}), 400
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        if payload.get('type') != 'refresh':
            raise ValueError('Not a refresh token')
        user = User.get(payload['user_id'])
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 401
        role = user.role
        if role == 'admin' and user.society_id is None:
            role = 'master'
        access_token, _ = generate_tokens(user.id, user.email, role)
        return jsonify({'success': True, 'access_token': access_token})
    except jwt.ExpiredSignatureError:
        return jsonify({'success': False, 'message': 'Refresh token expired'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 401


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})


# ── Auth check ────────────────────────────────────────────────────────────────

@auth_bp.route('/check-auth', methods=['GET'])
def check_auth():
    if current_user.is_authenticated:
        return jsonify({'authenticated': True, 'user': current_user.to_dict()})
    return jsonify({'authenticated': False}), 401


# ── Society list (used by society_select page) ────────────────────────────────

@auth_bp.route('/societies', methods=['GET'])
def get_societies_list():
    try:
        societies = db._execute(
            'SELECT id, name, address, logo FROM societies ORDER BY name',
            fetch_all=True,
        )
        return jsonify({'societies': societies or []})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Push notification subscription ───────────────────────────────────────────
# Called by app/static/js/push.js

@auth_bp.route('/subscribe-push', methods=['POST'])
@login_required
def subscribe_push():
    try:
        subscription = request.json
        if not subscription:
            return jsonify({'success': False, 'message': 'No subscription data'}), 400
        from app.services.push_service import save_push_subscription
        ok = save_push_subscription(current_user.id, subscription)
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/unsubscribe-push', methods=['POST'])
@login_required
def unsubscribe_push():
    try:
        db._execute(
            'UPDATE users SET push_subscription = NULL WHERE id = %s',
            (current_user.id,)
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500