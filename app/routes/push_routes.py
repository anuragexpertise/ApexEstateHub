from flask import Blueprint, request, jsonify, render_template
from app.services.push_service import save_push_subscription, send_push_notification
from app.auth.jwt_handler import verify_token
import logging
import os

logger = logging.getLogger(__name__)
push_bp = Blueprint('push', __name__)

VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC') or os.getenv('VAPID_PUBLIC_KEY')

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
        
        # Get user_id from JWT token in Authorization header
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401
        
        payload = verify_token(token)

        if not payload or payload.get('error'):
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = payload.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'User ID not found in token'}), 401
        
        # Save subscription using your push service
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
        # Get user_id from JWT token
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401
        
        payload = verify_token(token)

        if not payload or payload.get('error'):
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = payload.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'User ID not found in token'}), 401
        
        # Send test notification
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
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401
        
        payload = verify_token(token)

        if not payload or payload.get('error'):
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = payload.get('user_id')
        
        # Clear subscription in database
        from database.db_manager import db
        db._execute(
            "UPDATE users SET push_subscription = NULL WHERE id = :user_id",
            {"user_id": user_id}
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

        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401

        payload = verify_token(token)
        if not payload or payload.get('error'):
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = payload.get('user_id')
        from database.db_manager import db
        db._execute(
            "UPDATE users SET push_token = :token, push_enabled = TRUE WHERE id = :user_id",
            {"token": fcm_token, "user_id": user_id}
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
        auth_header = request.headers.get('Authorization', '')
        token = auth_header.replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Authorization token required'}), 401

        payload = verify_token(token)
        if not payload or payload.get('error'):
            return jsonify({'error': 'Invalid or expired token'}), 401

        user_id = payload.get('user_id')
        from database.db_manager import db
        db._execute(
            "UPDATE users SET push_token = NULL, push_enabled = FALSE WHERE id = :user_id",
            {"user_id": user_id}
        )
        logger.info(f"FCM token deleted for user {user_id}")
        return jsonify({'message': 'FCM token removed'}), 200
    except Exception as e:
        logger.error(f"Delete FCM token error: {e}")
        return jsonify({'error': str(e)}), 500
