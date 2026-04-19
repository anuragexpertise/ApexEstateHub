import json
import os
from pywebpush import webpush, WebPushException
from app.models.user import User

VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
VAPID_CLAIM_EMAIL = os.getenv('VAPID_CLAIM_EMAIL', 'admin@apexestatehub.com')

def save_push_subscription(user_id, subscription_info):
    """Save push subscription for user"""
    from app import db
    user = User.query.get(user_id)
    if user:
        user.push_subscription = json.dumps(subscription_info)
        db.session.commit()
        return True
    return False

def get_push_subscription(user_id):
    """Get push subscription for user"""
    from app.models.user import User
    user = User.query.get(user_id)
    if user and user.push_subscription:
        return json.loads(user.push_subscription)
    return None

def send_push_notification(user_id, title, body, icon=None, url=None):
    """Send push notification to user"""
    subscription = get_push_subscription(user_id)
    if not subscription:
        return False, "No subscription found"
    
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps({
                'title': title,
                'body': body,
                'icon': icon or '/static/assets/logo.png',
                'url': url or '/dashboard'
            }),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={
                'sub': f'mailto:{VAPID_CLAIM_EMAIL}'
            }
        )
        return True, "Notification sent"
    except WebPushException as e:
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