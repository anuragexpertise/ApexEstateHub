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

def _create_notification(user_id, title, body, society_id=None, url=None):
    """Persist a notification row so the in-app inbox can surface it."""
    try:
        from database.db_manager import db
        if society_id is None:
            row = db._execute(
                "SELECT society_id FROM users WHERE id = :user_id",
                {"user_id": user_id}, fetch_one=True
            )
            society_id = row["society_id"] if row else None
        db._execute(
            """INSERT INTO notifications (user_id, society_id, title, body, url, notification_type, read, created_at)
               VALUES (:user_id, :society_id, :title, :body, :url, 'push', FALSE, NOW())""",
            {"user_id": user_id, "society_id": society_id, "title": title, "body": body,
             "url": url or '/dashboard/'}
        )
    except Exception as e:
        logger.error(f"create_notification error: {e}")

def send_push_notification(user_id, title, body, icon=None, url=None, society_id=None):
    """Send push notification to user.

    The in-app notification (which drives the dashboard toast/inbox via
    polling) is always persisted first, independent of whether the actual
    browser push succeeds. Push delivery requires VAPID keys to be
    configured AND the user to have an active push_subscription; neither
    of those should gate the in-app notification, or users who haven't
    opted into browser push would never see anything at all.
    """
    _create_notification(user_id, title, body, society_id=society_id, url=url)

    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("Push notifications disabled: VAPID keys not configured. In-app notification still recorded.")
        return False, "VAPID keys not configured"

    subscription = get_push_subscription(user_id)
    if not subscription:
        logger.warning(f"No subscription found for user {user_id}. In-app notification still recorded.")
        return False, "No subscription found"

    try:
        notification_data = {
            'title': title,
            'body': body,
            'icon': icon or '/static/assets/EH_logo.png',
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

# ── Bulk / targeted notification helpers (NEW) ──────────────────────────────

def get_notification_targets(society_id, roles=None, exclude_user_id=None):
    """
    Return user_ids in a society matching one or more roles.

    Deliberately NOT filtered to push_subscription IS NOT NULL: these ids
    feed the in-app notification inbox/toast (via send_push_notification's
    _create_notification call) as well as actual browser push. Excluding
    non-subscribed users here would silently drop the in-app notification
    for anyone who hasn't opted into browser push, even though the dashboard
    toast has nothing to do with push delivery.
    """
    try:
        from database.db_manager import db
        query = "SELECT id FROM users WHERE society_id = :sid"
        params = {"sid": society_id}
        if roles:
            query += " AND role = ANY(:roles)"
            params["roles"] = list(roles)
        if exclude_user_id:
            query += " AND id != :exclude_id"
            params["exclude_id"] = exclude_user_id
        rows = db._execute(query, params, fetch_all=True) or []
        return [r["id"] for r in rows]
    except Exception as e:
        logger.error(f"get_notification_targets error: {e}")
        return []


def send_bulk_push(user_ids, title, body, url=None, society_id=None):
    """Send the same notification to a list of user_ids. Never raises."""
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            ok, _ = send_push_notification(uid, title, body, url=url, society_id=society_id)
            sent += 1 if ok else 0
            failed += 0 if ok else 1
        except Exception as e:
            logger.error(f"send_bulk_push error for user {uid}: {e}")
            failed += 1
    return sent, failed


def notify_poll_created(society_id, poll_title):
    """Notify all apartment owners in the society when a new poll is created."""
    targets = get_notification_targets(society_id, roles=["apartment"])
    if not targets:
        return 0, 0
    body = f"New poll: {poll_title}"
    return send_bulk_push(targets, "📊 New Poll", body, url="/dashboard/polls", society_id=society_id)


def notify_event_created(society_id, event_title, open_to="all", event_date=None):
    """
    Push a new-event alert to everyone matching open_to.
    open_to: 'apartment' | 'vendor' | 'security' | 'all'
    """
    role_map = {
        "apartment": ["apartment"],
        "vendor":    ["vendor"],
        "security":  ["security"],
        "all":       ["apartment", "vendor", "security"],
    }
    roles = role_map.get(open_to, ["apartment", "vendor", "security"])
    targets = get_notification_targets(society_id, roles=roles)
    if not targets:
        return 0, 0
    body = f"New event: {event_title}"
    if event_date:
        body += f" on {event_date}"
    return send_bulk_push(targets, "📅 New Event", body, url="/dashboard/events", society_id=society_id)


def notify_concern_created(society_id, apartment_id, concern_type):
    """Notify all admins in the society, plus the apartment owner (if the
    concern wasn't raised by the owner themself, e.g. admin raised it on
    their behalf), when a new concern is raised."""
    from database.db_manager import db
    targets = list(get_notification_targets(society_id, roles=["admin"]))
    if apartment_id:
        apt = db._execute(
            "SELECT flat_number FROM apartments WHERE id=%s AND society_id=%s",
            (apartment_id, society_id), fetch_one=True,
        )
        flat_label = f"Flat {apt['flat_number']}" if apt else "A concern"
        owner = db._execute(
            "SELECT id AS user_id FROM users WHERE linked_id=%s AND role='apartment' AND society_id=%s",
            (apartment_id, society_id), fetch_one=True,
        )
        if owner and owner.get("user_id") and owner["user_id"] not in targets:
            targets.append(owner["user_id"])
    else:
        flat_label = "A concern"
    if not targets:
        return 0, 0
    body = f"{flat_label}: {concern_type.replace('_',' ').title()}"
    return send_bulk_push(targets, "🔔 New Concern Raised", body, url="/dashboard/concerns", society_id=society_id)


def notify_concern_assigned(society_id, concern_id, concern_type, assignments):
    """
    Notify each newly-assigned admin/vendor/security entity that a concern
    has been assigned to them.

    `assignments` is a list of (role, entity_id) tuples using the
    concerns_assigns role codes: 'ADM' | 'VND' | 'SEC'. For 'ADM', entity_id
    is already users.id. For 'VND'/'SEC', entity_id is vendors.id /
    security_staff.id and must be translated to the linked users.id.
    """
    from database.db_manager import db
    sent, failed = 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    body = f"A concern ({label}) has been assigned to you"
    role_lookup = {"VND": "vendor", "SEC": "security"}
    for role, entity_id in assignments:
        user_id = None
        if role == "ADM":
            user_id = entity_id  # concerns_assigns.entity_id IS users.id for admins
        elif role in role_lookup:
            row = db._execute(
                "SELECT id FROM users WHERE linked_id=%s AND role=%s AND society_id=%s",
                (entity_id, role_lookup[role], society_id), fetch_one=True,
            )
            user_id = row["id"] if row else None
        if not user_id:
            failed += 1
            continue
        ok, _ = send_push_notification(
            user_id, "🧰 Concern Assigned", body,
            url="/dashboard/concerns", society_id=society_id,
        )
        sent += 1 if ok else 0
        failed += 0 if ok else 1
    return sent, failed


def notify_concern_status_change(user_id, concern_type, new_status):
    """Notify the resident who raised a concern when its status changes."""
    if not user_id:
        return False, "No user_id"
    status_label = new_status.replace("_", " ").title()
    title = "✅ Concern Resolved" if new_status == "resolved" else "🔧 Concern Update"
    body = f"Your concern ({concern_type.replace('_',' ').title()}) is now: {status_label}"
    return send_push_notification(user_id, title, body, url="/dashboard/owner-concerns")


def _concern_notify_targets(society_id, apartment_id):
    """Common target set for concern lifecycle events: all admins + the
    apartment owner (if apartment_id is known)."""
    from database.db_manager import db
    targets = list(get_notification_targets(society_id, roles=["admin"]))
    if apartment_id:
        owner = db._execute(
            "SELECT id AS user_id FROM users WHERE linked_id=%s AND role='apartment' AND society_id=%s",
            (apartment_id, society_id), fetch_one=True,
        )
        if owner and owner.get("user_id") and owner["user_id"] not in targets:
            targets.append(owner["user_id"])
    return targets


def notify_concern_bid_saved(society_id, apartment_id, concern_type, vendor_label=None):
    """Vendor saved/updated a bid — notify admin + the concern's creator apartment."""
    targets = _concern_notify_targets(society_id, apartment_id)
    if not targets:
        return 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    who = f" by {vendor_label}" if vendor_label else ""
    body = f"A bid was submitted{who} for: {label}"
    return send_bulk_push(targets, "💰 Concern Bid Submitted", body, url="/dashboard/concerns", society_id=society_id)


def notify_concern_resolved_by_vendor(society_id, apartment_id, concern_type):
    """Vendor marked their assignment resolved — notify admin + creator apartment."""
    targets = _concern_notify_targets(society_id, apartment_id)
    if not targets:
        return 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    body = f"A vendor marked the concern as resolved: {label}"
    return send_bulk_push(targets, "✅ Concern Resolved By Vendor", body, url="/dashboard/concerns", society_id=society_id)


def notify_concern_closed(society_id, apartment_id, concern_type, assignments=None):
    """Admin/Owner closed a concern — notify admin, the creator apartment,
    and every assignee. `assignments` is the list of rows returned by
    loaders.get_concern_assignments() (each with role/entity_id)."""
    from database.db_manager import db
    targets = _concern_notify_targets(society_id, apartment_id)
    role_lookup = {"VND": "vendor", "SEC": "security"}
    for a in (assignments or []):
        role, entity_id = a.get("role"), a.get("entity_id")
        if role == "ADM":
            user_id = entity_id
        elif role in role_lookup:
            row = db._execute(
                "SELECT id FROM users WHERE linked_id=%s AND role=%s AND society_id=%s",
                (entity_id, role_lookup[role], society_id), fetch_one=True,
            )
            user_id = row["id"] if row else None
        else:
            user_id = None
        if user_id and user_id not in targets:
            targets.append(user_id)
    if not targets:
        return 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    body = f"Concern closed: {label}"
    return send_bulk_push(targets, "🔒 Concern Closed", body, url="/dashboard/concerns", society_id=society_id)


def notify_concern_invited(society_id, concern_id, concern_type, assignments):
    """Admin/Owner invited vendors/security to bid — notify the invited entities."""
    from database.db_manager import db
    targets = []
    role_lookup = {"VND": "vendor", "SEC": "security"}
    for role, entity_id in (assignments or []):
        user_id = None
        if role in role_lookup:
            row = db._execute(
                "SELECT id FROM users WHERE linked_id=%s AND role=%s AND society_id=%s",
                (entity_id, role_lookup[role], society_id), fetch_one=True,
            )
            user_id = row["id"] if row else None
        if not user_id:
            continue
        targets.append(user_id)
    if not targets:
        return 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    body = f"You've been invited to bid on: {label}"
    return send_bulk_push(targets, "📨 Concern Invitation", body, url="/dashboard/concerns", society_id=society_id)


def notify_concern_invite_bid_saved(society_id, apartment_id, concern_type, vendor_label=None):
    """Vendor submitted a bid on an invite — notify admin + the concern's creator apartment."""
    targets = _concern_notify_targets(society_id, apartment_id)
    if not targets:
        return 0, 0
    label = concern_type.replace('_', ' ').title() if concern_type else "Concern"
    who = f" by {vendor_label}" if vendor_label else ""
    body = f"A bid was submitted{who} for: {label}"
    return send_bulk_push(targets, "💰 Concern Bid Submitted", body, url="/dashboard/concerns", society_id=society_id)


def notify_payment_received(user_id, amount, particulars=None):
    """Confirm to the payer that their payment was recorded."""
    if not user_id:
        return False, "No user_id"
    title = "💰 Payment Received"
    body = f"₹{float(amount):,.2f} received" + (f" — {particulars}" if particulars else "")
    return send_push_notification(user_id, title, body, url="/dashboard/owner-cashbook")


def notify_admin_payment_recorded(society_id, amount, particulars=None, exclude_user_id=None):
    """Let admins know a payment was recorded (e.g. by security at the gate)."""
    targets = get_notification_targets(society_id, roles=["admin"], exclude_user_id=exclude_user_id)
    if not targets:
        return 0, 0
    body = f"₹{float(amount):,.2f} recorded" + (f" — {particulars}" if particulars else "")
    return send_bulk_push(targets, "💰 Payment Recorded", body, url="/dashboard/financials", society_id=society_id)


def notify_dues_overdue(user_id, amount):
    """
    Alert a resident that their dues have crossed into overdue status.
    Call this from whatever job/cron generates monthly receivables —
    no such scheduler exists in the current codebase; this is the hook
    to call once one is added (e.g. APScheduler job or Render cron task).
    """
    if not user_id:
        return False, "No user_id"
    title = "⚠️ Dues Overdue"
    body = f"₹{float(amount):,.2f} is now overdue. Please clear it to avoid a failed gate pass."
    return send_push_notification(user_id, title, body, url="/dashboard/owner-receivables")