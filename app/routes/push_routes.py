from flask import Blueprint, request, jsonify, render_template
from app.services.push_service import save_push_subscription, send_push_notification
from app.services.auth_service import verify_jwt_token
import logging

logger = logging.getLogger(__name__)
push_bp = Blueprint('push', __name__)

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
        
        payload = verify_jwt_token(token)
        
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        user_id = payload.get('sub')
        
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
        
        payload = verify_jwt_token(token)
        
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        user_id = payload.get('sub')
        
        if not user_id:
            return jsonify({'error': 'User ID not found in token'}), 401
        
        # Send test notification
        success, message = send_push_notification(
            user_id,
            title="🔔 Test Notification from ApexEstateHub",
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
        
        payload = verify_jwt_token(token)
        
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        user_id = payload.get('sub')
        
        # Clear subscription in database
        from database.db_manager import db
        db.execute_query(
            "UPDATE users SET push_subscription = NULL WHERE id = :user_id",
            {"user_id": user_id}
        )
        
        logger.info(f"Push subscription deleted for user {user_id}")
        return jsonify({'message': 'Subscription deleted successfully'}), 200
        
    except Exception as e:
        logger.error(f"Delete subscription error: {e}")
        return jsonify({'error': str(e)}), 500
