import json
import os
from pywebpush import webpush, WebPushException
from app.models.user import User

VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_CLAIM_EMAIL = os.getenv('VAPID_CLAIM_EMAIL', 'admin@estatehub.com')


def save_push_subscription(user_id, subscription_info):
    try:
        from database.db_manager import db
        db.execute_query(
            """UPDATE users SET push_subscription = %s WHERE id = %s""",
            (json.dumps(subscription_info), user_id)
        )
        return True
    except Exception as e:
        print(f"Push save error: {e}")
        return False

def get_push_subscription(user_id):
    try:
        from database.db_manager import db
        row = db.execute_query(
            "SELECT push_subscription FROM users WHERE id = %s",
            (user_id,), fetch_one=True
        )
        if row and row.get('push_subscription'):
            return json.loads(row['push_subscription'])
    except Exception as e:
        print(f"Push get error: {e}")
    return None

def send_push_notification(user_id, title, body, icon=None, url=None):
    """Send push notification to user."""
    # ── GUARD ──────────────────────────────────────────────────
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print("⚠  Push notifications disabled: VAPID keys not set in environment.")
        return False, "VAPID keys not configured"
    # ───────────────────────────────────────────────────────────
 
    subscription = get_push_subscription(user_id)
    if not subscription:
        return False, "No subscription found"
 
    try:
        webpush(
            subscription_info=subscription,
            data=__import__('json').dumps({
                'title': title,
                'body':  body,
                'icon':  icon or '/static/assets/logo.png',
                'url':   url  or '/dashboard/',
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': f'mailto:{VAPID_CLAIM_EMAIL}'},
        )
        return True, "Notification sent"
    except Exception as e:
        return False, str(e)
def send_payment_reminder(user_id, amount, due_date):
    """Send payment reminder notification"""
    title = "Payment Reminder"
    body = f"Your payment of ₹{amount} is due by {due_date}"
    return send_push_notification(user_id, title, body)

def send_gate_access_notification(user_id, status, location="Main Gate"):
    """Send gate access notification"""
    title = "Gate Access Alert"
    body = f"Access {status} at {location}"
    return send_push_notification(user_id, title, body)

def send_maintenance_update(user_id, apartment, status):
    """Send maintenance update notification"""
    title = "Maintenance Update"
    body = f"Maintenance request for {apartment} is {status}"
    return send_push_notification(user_id, title, body)