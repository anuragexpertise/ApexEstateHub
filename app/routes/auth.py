from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.auth.jwt_handler import generate_tokens, verify_token, refresh_access_token, token_required
from app.services.push_service import save_push_subscription, send_push_notification
from app.services.auth_service import authenticate_user, authenticate_pin, authenticate_pattern

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login - Primary + Secondary combined"""
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
            # Login with Flask-Login for session management
            login_user(user, remember=data.get('remember', False))
            
            # Generate JWT tokens
            access_token, refresh_token = generate_tokens(user)
            
            session['role'] = user.role
            session['society_id'] = user.society_id
            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            
            # Determine redirect based on role
            if user.is_master_admin():
                redirect_url = '/dashboard/master'
            elif user.role == 'admin':
                redirect_url = '/dashboard/admin-portal'
            elif user.role == 'apartment':
                redirect_url = '/dashboard/owner-portal'
            elif user.role == 'vendor':
                redirect_url = '/dashboard/vendor-portal'
            elif user.role == 'security':
                redirect_url = '/dashboard/pass-evaluation'
            else:
                redirect_url = '/dashboard'
            
            # Send push notification on login (if subscribed)
            send_push_notification(user.id, "Login Alert", f"New login from {request.remote_addr}")
            
            return jsonify({
                'success': True,
                'redirect': redirect_url,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'role': user.role,
                    'society_id': user.society_id
                }
            })
        
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@auth_bp.route('/start-auth', methods=['POST'])
def start_auth():
    """Start authentication and return JWT token (for API clients)"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    society_id = data.get('society_id')
    
    user = authenticate_user(email, password, society_id)
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    access_token, refresh_token = generate_tokens(user)
    
    return jsonify({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': {
            'id': user.id,
            'email': user.email,
            'role': user.role,
            'society_id': user.society_id
        }
    })

@auth_bp.route('/refresh', methods=['POST'])
def refresh():
    """Refresh access token"""
    data = request.get_json()
    refresh_token = data.get('refresh_token')
    
    if not refresh_token:
        return jsonify({'error': 'Refresh token required'}), 400
    
    new_access_token, error = refresh_access_token(refresh_token)
    
    if error:
        return jsonify({'error': error}), 401
    
    return jsonify({'access_token': new_access_token})

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token_route():
    """Verify JWT token"""
    token = request.json.get('token')
    payload = verify_token(token)
    
    if payload.get('error'):
        return jsonify({'valid': False, 'error': payload['error']}), 401
    
    return jsonify({'valid': True, 'user': payload})

@auth_bp.route('/subscribe-push', methods=['POST'])
@login_required
def subscribe_push():
    """Save push notification subscription"""
    subscription = request.json
    success = save_push_subscription(current_user.id, subscription)
    
    if success:
        # Send test notification
        send_push_notification(current_user.id, "Welcome!", "Push notifications enabled")
        return jsonify({'success': True, 'message': 'Subscribed successfully'})
    
    return jsonify({'success': False, 'error': 'Failed to save subscription'}), 400

@auth_bp.route('/unsubscribe-push', methods=['POST'])
@login_required
def unsubscribe_push():
    """Remove push notification subscription"""
    current_user.push_subscription = None
    db.session.commit()
    return jsonify({'success': True, 'message': 'Unsubscribed successfully'})

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('web.index'))

@auth_bp.route('/check-auth')
def check_auth():
    """Check if user is authenticated (session-based)"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user_id': current_user.id,
            'email': current_user.email,
            'role': current_user.role,
            'society_id': current_user.society_id
        })
    return jsonify({'authenticated': False})

@auth_bp.route('/check-jwt', methods=['POST'])
def check_jwt():
    """Check if JWT token is valid (API clients)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    payload = verify_token(token)
    
    if payload.get('error'):
        return jsonify({'authenticated': False, 'error': payload['error']}), 401
    
    return jsonify({
        'authenticated': True,
        'user_id': payload.get('user_id'),
        'email': payload.get('email'),
        'role': payload.get('role'),
        'society_id': payload.get('society_id')
    })