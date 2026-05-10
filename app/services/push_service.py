import json
import os
from pywebpush import webpush, WebPushException
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get VAPID keys from environment (matching your .env)
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE') or os.getenv('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC') or os.getenv('VAPID_PUBLIC_KEY')
VAPID_CLAIM_EMAIL = os.getenv('VAPID_EMAIL') or os.getenv('VAPID_CLAIM_EMAIL', 'master@estatehub.com')

def save_push_subscription(user_id, subscription_info):
    """Save push subscription to database"""
    try:
        from database.db_manager import db
        db._execute(
            """UPDATE users SET push_subscription = :subscription WHERE id = :user_id""",
            {"subscription": json.dumps(subscription_info), "user_id": user_id}
        )
        logger.info(f"Push subscription saved for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Push save error: {e}")
        return False

def get_push_subscription(user_id):
    """Get push subscription from database"""
    try:
        from database.db_manager import db
        row = db._execute(
            "SELECT push_subscription FROM users WHERE id = :user_id",
            {"user_id": user_id}, 
            fetch_one=True
        )
        if row and row.get('push_subscription'):
            return json.loads(row['push_subscription'])
    except Exception as e:
        logger.error(f"Push get error: {e}")
    return None

def send_push_notification(user_id, title, body, icon=None, url=None):
    """Send push notification to user."""
    # Guard clause - check VAPID keys
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("Push notifications disabled: VAPID keys not configured.")
        return False, "VAPID keys not configured"
    
    subscription = get_push_subscription(user_id)
    if not subscription:
        logger.warning(f"No subscription found for user {user_id}")
        return False, "No subscription found"
    
    try:
        notification_data = {
            'title': title,
            'body': body,
            'icon': icon or '/static/assets/logo.png',
            'url': url or '/dashboard/',
        }
        
        webpush(
            subscription_info=subscription,
            data=json.dumps(notification_data),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': f'mailto:{VAPID_CLAIM_EMAIL}'},
        )
        logger.info(f"Push notification sent to user {user_id}: {title}")
        return True, "Notification sent"
    except WebPushException as e:
        logger.error(f"WebPush error: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response: {e.response.read()}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Push notification error: {e}")
        return False, str(e)

def send_payment_reminder(user_id, amount, due_date):
    """Send payment reminder notification"""
    title = "💰 Payment Reminder"
    body = f"Your payment of ₹{amount} is due by {due_date}"
    return send_push_notification(user_id, title, body)

def send_gate_access_notification(user_id, status, location="Main Gate"):
    """Send gate access notification"""
    title = "🚪 Gate Access Alert"
    body = f"Access {status} at {location}"
    return send_push_notification(user_id, title, body)

def send_maintenance_update(user_id, apartment, status):
    """Send maintenance update notification"""
    title = "🔧 Maintenance Update"
    body = f"Maintenance request for {apartment} is {status}"
    return send_push_notification(user_id, title, body)
