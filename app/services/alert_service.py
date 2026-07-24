# app/services/alert_service.py

from datetime import datetime, timedelta
import logging
from database.db_manager import db
from app.services.push_service import send_push_notification

logger = logging.getLogger(__name__)


def create_alert_channel(
    society_id: int,
    channel_type: str,
    name: str,
    identifier: str = None,
    apartment_id: int = None,
    is_recurring: bool = True,
):
    """
    Create a new alert channel (e.g. School Bus or Taxi).
    `is_recurring` determines if channel persists across days.
    """
    try:
        channel_type_clean = channel_type.lower().strip()
        if channel_type_clean not in ("school_bus", "taxi", "visitor"):
            return None, f"Invalid channel type: {channel_type}"

        row = db._execute("""
            INSERT INTO alert_channels (society_id, channel_type, name, identifier, apartment_id, is_recurring, active)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
        """, (society_id, channel_type_clean, name, identifier, apartment_id, is_recurring), fetch_one=True)

        channel_id = row["id"]

        # Auto-subscribe creator apartment if provided
        if apartment_id:
            subscribe_channel(channel_id, apartment_id)

        return channel_id, "Channel created successfully"
    except Exception as e:
        logger.error(f"Error creating alert channel: {e}")
        return None, str(e)


def subscribe_channel(channel_id: int, apartment_id: int):
    """Subscribe an apartment to an alert channel."""
    try:
        db._execute("""
            INSERT INTO alert_subscriptions (channel_id, apartment_id)
            VALUES (%s, %s)
            ON CONFLICT (channel_id, apartment_id) DO NOTHING
        """, (channel_id, apartment_id))
        return True, "Subscribed successfully"
    except Exception as e:
        return False, str(e)


def unsubscribe_channel(channel_id: int, apartment_id: int):
    """Unsubscribe an apartment from an alert channel."""
    try:
        db._execute("""
            DELETE FROM alert_subscriptions
             WHERE channel_id = %s AND apartment_id = %s
        """, (channel_id, apartment_id))
        return True, "Unsubscribed successfully"
    except Exception as e:
        return False, str(e)


def list_channels(society_id: int, apartment_id: int = None, is_admin: bool = False):
    """
    List alert channels.
    If is_admin=False: Only active channels are shown to apartment owners.
    If is_admin=True: Active and inactive channels are returned (inactive flagged for gray border display).
    apartment_id: the apartments.id (linked_id) of the current user — used to
                  determine is_subscribed. Pass None for admin (subscription check
                  is irrelevant; falls back to 0 so the LEFT JOIN returns FALSE cleanly).
    """
    try:
        where_clause = "ac.society_id = %s"
        if not is_admin:
            where_clause += " AND ac.active = TRUE"

        # apartment_id may be None for admin views — fall back to 0 so the
        # LEFT JOIN produces FALSE (no row) rather than a NULL comparison.
        apt_id_param = apartment_id or 0

        rows = db._execute(f"""
            SELECT ac.*,
                   a.flat_number as creator_flat,
                   (CASE WHEN sub.id IS NOT NULL THEN TRUE ELSE FALSE END) as is_subscribed,
                   (SELECT COUNT(*) FROM alert_subscriptions s WHERE s.channel_id = ac.id) as subscriber_count,
                   (CASE WHEN ac.active = FALSE THEN TRUE ELSE FALSE END) as is_inactive
              FROM alert_channels ac
              LEFT JOIN apartments a ON a.id = ac.apartment_id
              LEFT JOIN alert_subscriptions sub ON sub.channel_id = ac.id AND sub.apartment_id = %s
             WHERE {where_clause}
             ORDER BY ac.active DESC, ac.created_at DESC
        """, (apt_id_param, society_id))
        return rows or []
    except Exception as e:
        logger.error(f"Error listing alert channels: {e}")
        return []


def trigger_channel_alert(channel_id: int, triggered_by_user_id: int):
    """
    Trigger a School Bus, Taxi, or Visitor alert via Guard 'Entry IN' button.
    First press: Sets state to 'pending' (Yellow badge), sends push notification to subscribed owners.
                 Security CANNOT force PASS.
    Second press while 'pending': Triggers calling phone dialer to apartment owner for verbal confirmation.
    """
    try:
        channel = db._execute("""
            SELECT ac.*, a.flat_number, u.id as owner_user_id, u.phone as owner_phone
              FROM alert_channels ac
              LEFT JOIN apartments a ON a.id = ac.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE ac.id = %s
        """, (channel_id,), fetch_one=True)

        if not channel:
            return False, "Alert channel not found", None

        society_id = channel["society_id"]
        channel_type = channel["channel_type"]
        name = channel["name"]
        identifier = channel["identifier"] or ""

        # Check existing active alert event for this channel
        existing = db._execute("""
            SELECT * FROM alert_events
             WHERE channel_id = %s AND (expires_at IS NULL OR expires_at > NOW())
             ORDER BY triggered_at DESC LIMIT 1
        """, (channel_id,), fetch_one=True)

        if existing and existing["state"] == "pending":
            # 2nd Press on Yellow (Pending) -> Escalate to Phone Call
            db._execute("""
                UPDATE alert_events SET state = 'calling' WHERE id = %s
            """, (existing["id"],))
            return True, "Calling owner for verbal confirmation", {
                "action": "call",
                "phone": channel.get("owner_phone"),
                "state": "calling",
            }

        # First Press -> Set State = pending (Yellow badge)
        expires_at = datetime.now() + timedelta(minutes=30)
        event_row = db._execute("""
            INSERT INTO alert_events (society_id, channel_id, state, triggered_by, triggered_at, expires_at)
            VALUES (%s, %s, 'pending', %s, NOW(), %s)
            RETURNING id
        """, (society_id, channel_id, triggered_by_user_id, expires_at), fetch_one=True)

        # Dispatch Push Notifications
        if channel_type == "school_bus":
            sub_users = db._execute("""
                SELECT DISTINCT u.id
                  FROM alert_subscriptions sub
                  JOIN users u ON u.linked_id = sub.apartment_id AND u.role = 'apartment'
                 WHERE sub.channel_id = %s
            """, (channel_id,))
            title = f"🚌 School Bus Arrived: {name}"
            body = f"School Bus {name} ({identifier}) is at the gate. Please confirm entry."
            for u in (sub_users or []):
                send_push_notification(u["id"], title, body, society_id=society_id)
        else:
            if channel["owner_user_id"]:
                title = f"🚖 Channel Alert: {name}"
                body = f"{name} ({identifier}) for Flat {channel.get('flat_number', '')} is at the gate. Tap to Approve/Deny."
                send_push_notification(channel["owner_user_id"], title, body, society_id=society_id)

        return True, "Entry IN initiated: Pending owner approval (Yellow)", {"state": "pending", "event_id": event_row["id"]}
    except Exception as e:
        logger.error(f"Error triggering channel alert: {e}")
        return False, str(e), None


def respond_to_alert(alert_event_id: int, owner_user_id: int, action: str):
    """
    Owner responds to alert push notification / app prompt:
    action = 'approve' -> State set to 'resolved' (Green / PASS)
    action = 'deny'    -> State set to 'denied' (Red / Denied)
    If non-recurring channel, deactivates channel upon completion.

    Note: DB CHECK on alert_events.state allows:
      idle | pending | arrived | calling | resolved | denied
    'approved' is intentionally mapped to 'resolved' here to satisfy the constraint.
    """
    try:
        # Map 'approve' -> 'resolved' (DB CHECK does not include 'approved').
        new_state = "resolved" if action == "approve" else "denied"

        event = db._execute("""
            SELECT ae.*, ac.is_recurring, ac.id as channel_id
              FROM alert_events ae
              LEFT JOIN alert_channels ac ON ac.id = ae.channel_id
             WHERE ae.id = %s
        """, (alert_event_id,), fetch_one=True)

        if not event:
            return False, "Alert event not found"

        # Update event state (alert_events has no resolved_at/resolved_by cols)
        db._execute("""
            UPDATE alert_events
               SET state = %s
             WHERE id = %s
        """, (new_state, alert_event_id))

        # If non-recurring channel, set active = FALSE after event resolution
        if event.get("channel_id") and event.get("is_recurring") is False:
            db._execute("UPDATE alert_channels SET active = FALSE WHERE id = %s", (event["channel_id"],))

        return True, f"Alert response recorded: {new_state.upper()}"
    except Exception as e:
        logger.error(f"Error responding to alert: {e}")
        return False, str(e)


def get_active_alerts(society_id: int):
    """
    Fetch all active alerts for gate security and dashboard KPI cards.
    Color rules:
      - 'pending': Yellow (#eab308 / yellow)
      - 'approved' / 'entered' / 'resolved': Green (#22c55e / green)
      - 'denied': Red (#ef4444 / red)
      - 'calling': Orange (#f97316 / orange)
    """
    try:
        channel_alerts = db._execute("""
            SELECT ae.id as alert_event_id, ae.state, ae.triggered_at,
                   ac.id as channel_id, ac.channel_type, ac.name, ac.identifier, ac.is_recurring, ac.active as channel_active,
                   a.flat_number, u.phone as owner_phone, u.name as owner_name
              FROM alert_events ae
              JOIN alert_channels ac ON ac.id = ae.channel_id
              LEFT JOIN apartments a ON a.id = ac.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE ae.society_id = %s AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
             ORDER BY ae.triggered_at DESC
        """, (society_id,))

        formatted = []
        for ca in (channel_alerts or []):
            ctype = ca["channel_type"]
            state = ca["state"]
            color = "yellow"
            if state in ("approved", "entered", "resolved", "arrived"):
                color = "green"
            elif state == "denied":
                color = "red"
            elif state == "calling":
                color = "orange"
            elif state == "pending":
                color = "yellow"

            formatted.append({
                "type": ctype,
                "id": ca["channel_id"],
                "alert_event_id": ca["alert_event_id"],
                "title": f"{'🚌' if ctype == 'school_bus' else '🚖'} {ca['name']}",
                "identifier": ca["identifier"] or "",
                "flat_number": ca.get("flat_number") or "",
                "owner_phone": ca.get("owner_phone") or "",
                "owner_name": ca.get("owner_name") or "",
                "is_recurring": ca.get("is_recurring"),
                "channel_active": ca.get("channel_active"),
                "state": state,
                "color": color,
                "triggered_at": str(ca["triggered_at"]),
            })

        # Visitors
        visitor_alerts = db._execute("""
            SELECT v.id as visitor_id, v.name as visitor_name, v.purpose, v.status as visitor_status,
                   a.flat_number, u.phone as owner_phone, u.name as owner_name,
                   ae.id as alert_event_id, ae.state, ae.triggered_at
              FROM visitors v
              LEFT JOIN alert_events ae ON ae.visitor_id = v.id AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
              LEFT JOIN apartments a ON a.id = v.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE v.society_id = %s AND v.visit_date = CURRENT_DATE
             ORDER BY v.created_at DESC
        """, (society_id,))

        for va in (visitor_alerts or []):
            status = va["visitor_status"]
            state = va.get("state") or status
            color = "yellow"
            if status in ("entered", "approved") or state in ("approved", "resolved"):
                color = "green"
            elif status == "denied" or state == "denied":
                color = "red"
            elif state == "calling":
                color = "orange"
            elif status == "pending" or state == "pending":
                color = "yellow"

            formatted.append({
                "type": "visitor",
                "id": va["visitor_id"],
                "alert_event_id": va.get("alert_event_id"),
                "title": f"👤 Visitor: {va['visitor_name']}",
                "identifier": va.get("purpose") or "",
                "flat_number": va.get("flat_number") or "",
                "owner_phone": va.get("owner_phone") or "",
                "owner_name": va.get("owner_name") or "",
                "state": state,
                "color": color,
                "triggered_at": str(va.get("triggered_at") or ""),
            })

        return formatted
    except Exception as e:
        logger.error(f"Error fetching active alerts: {e}")
        return []


def get_channel_subscribers_with_profile(channel_id: int):
    """
    Fetch subscribers for a channel along with their user profile details and arrival status.
    Returns list of subscriber profile dicts with border_color indicating status:
      - 'approved' -> #22c55e (Green)
      - 'pending'  -> #eab308 (Yellow)
      - 'denied'   -> #ef4444 (Red)
    """
    try:
        rows = db._execute("""
            SELECT sub.id as subscription_id,
                   a.id as apartment_id, a.flat_number, a.block,
                   u.id as user_id, u.name as owner_name, u.phone, u.email,
                   COALESCE(ae.state, 'pending') as arrival_status
              FROM alert_subscriptions sub
              JOIN apartments a ON a.id = sub.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
              LEFT JOIN alert_events ae ON ae.channel_id = sub.channel_id AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
             WHERE sub.channel_id = %s
             ORDER BY a.flat_number ASC
        """, (channel_id,))

        subscribers = []
        for r in (rows or []):
            st = (r.get("arrival_status") or "pending").lower()
            if st in ("approved", "entered", "resolved", "arrived"):
                border_color = "#22c55e"  # Green
                status_label = "APPROVED / ARRIVED"
            elif st == "denied":
                border_color = "#ef4444"  # Red
                status_label = "DENIED"
            else:
                border_color = "#eab308"  # Yellow
                status_label = "PENDING"

            subscribers.append({
                "subscription_id": r["subscription_id"],
                "apartment_id": r["apartment_id"],
                "flat_number": r.get("flat_number", "N/A"),
                "block": r.get("block", ""),
                "owner_name": r.get("owner_name") or "Apartment Owner",
                "phone": r.get("phone") or "N/A",
                "email": r.get("email") or "N/A",
                "status": st,
                "status_label": status_label,
                "border_color": border_color,
            })
        return subscribers
    except Exception as e:
        logger.error(f"Error fetching channel subscribers: {e}")
        return []

