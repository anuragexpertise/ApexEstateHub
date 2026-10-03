from flask import Blueprint, request, jsonify, render_template
from app.services.push_service import save_push_subscription, remove_push_subscription, send_push_notification, get_push_subscriptions
from app.auth.jwt_handler import authenticate_bearer
import logging
import os

logger = logging.getLogger(__name__)
push_bp = Blueprint('push', __name__)

VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC') or os.getenv('VAPID_PUBLIC_KEY')


def _bearer_user_id():
    """Return (user_id, error_response). The user is re-resolved from the
    database and the token must be an ACCESS token (refresh tokens used to be
    accepted here)."""
    header = request.headers.get('Authorization', '')
    token = header[7:] if header.startswith('Bearer ') else header
    if not token:
        return None, (jsonify({'error': 'Authorization token required'}), 401)
    user, error = authenticate_bearer(token)
    if error:
        return None, (jsonify({'error': 'Invalid or expired token'}), 401)
    return user.id, None

@push_bp.route('/api/push/vapid-public-key')
def vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        return jsonify({'error': 'VAPID public key not configured'}), 500
    return jsonify({'publicKey': VAPID_PUBLIC_KEY})

@push_bp.route('/push/test')
def push_test_page():
    """Serve the push notification test page"""
    return render_template('test_push.html')

@push_bp.route('/api/push/subscribe', methods=['POST'])
def subscribe():
    """Save browser push subscription"""
    try:
        data = request.get_json()
        
        if not data or not data.get('endpoint'):
            return jsonify({'error': 'Invalid subscription data'}), 400
        
        user_id, _auth_err = _bearer_user_id()
        if _auth_err:
            return _auth_err
        
        success = save_push_subscription(user_id, data)
        
        if success:
            logger.info(f"Push subscription saved for user {user_id}")
            return jsonify({'message': 'Subscription saved successfully'}), 200
        else:
            return jsonify({'error': 'Failed to save subscription'}), 500
            
    except Exception as e:
        logger.error(f"Subscribe error: {e}")
        return jsonify({'error': str(e)}), 500

@push_bp.route('/api/push/send-test', methods=['POST'])
def send_test():
    """Send a test notification to the current user"""
    try:
        user_id, _auth_err = _bearer_user_id()
        if _auth_err:
            return _auth_err
        
        success, message = send_push_notification(
            user_id,
            title="🔔 Test Notification from EsateHub",
            body="This is a test message! Your push notifications are working correctly.",
            url="/dashboard/"
        )
        
        if success:
            logger.info(f"Test notification sent to user {user_id}")
            return jsonify({'success': True, 'message': 'Notification sent successfully'}), 200
        else:
            return jsonify({'success': False, 'message': message}), 500
            
    except Exception as e:
        logger.error(f"Send test error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@push_bp.route('/api/push/subscription', methods=['DELETE'])
def delete_subscription():
    """Delete push subscription"""
    try:
        user_id, _auth_err = _bearer_user_id()
        if _auth_err:
            return _auth_err
        data = request.get_json() or {}
        endpoint = data.get('endpoint')
        if endpoint:
            remove_push_subscription(user_id, endpoint)
        else:
            from database.db_manager import db
            db._execute(
                "DELETE FROM push_subscriptions WHERE user_id = %s",
                (user_id,),
            )
        
        logger.info(f"Push subscription deleted for user {user_id}")
        return jsonify({'message': 'Subscription deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Delete subscription error: {e}")
        return jsonify({'error': str(e)}), 500


@push_bp.route('/api/push/fcm-token', methods=['POST'])
def save_fcm_token():
    """Save FCM registration token for mobile push notifications."""
    try:
        data = request.get_json()
        fcm_token = data.get('fcm_token') if data else None
        if not fcm_token or not isinstance(fcm_token, str):
            return jsonify({'error': 'fcm_token is required'}), 400

        user_id, _auth_err = _bearer_user_id()
        if _auth_err:
            return _auth_err
        from database.db_manager import db
        db._execute(
            "UPDATE users SET push_token = %s, push_enabled = TRUE WHERE id = %s",
            (fcm_token, user_id)
        )
        logger.info(f"FCM token saved for user {user_id}")
        return jsonify({'message': 'FCM token saved'}), 200
    except Exception as e:
        logger.error(f"Save FCM token error: {e}")
        return jsonify({'error': str(e)}), 500


@push_bp.route('/api/push/fcm-token', methods=['DELETE'])
def delete_fcm_token():
    """Remove stored FCM token."""
    try:
        user_id, _auth_err = _bearer_user_id()
        if _auth_err:
            return _auth_err
        from database.db_manager import db
        db._execute(
            "UPDATE users SET push_token = NULL, push_enabled = FALSE WHERE id = %s",
            (user_id,)
        )
        logger.info(f"FCM token deleted for user {user_id}")
        return jsonify({'message': 'FCM token removed'}), 200
    except Exception as e:
        logger.error(f"Delete FCM token error: {e}")
        return jsonify({'error': str(e)}), 500
