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
    Create a new alert channel (School Bus, Taxi, or Visitor).
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
    If is_admin=True: Active and inactive channels are returned.
    """
    try:
        where_clause = "ac.society_id = %s"
        if not is_admin:
            where_clause += " AND ac.active = TRUE"

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
    Trigger a School Bus, Taxi, or Visitor alert.

    Flow per channel_type:
      school_bus:
        - Push notification sent to ALL subscribed owners.
        - State immediately set to 'resolved' (auto-PASS). No owner confirmation needed.
      taxi:
        - Push notification sent to the channel owner.
        - State set to 'pending' (Yellow).
        - Second press while pending escalates to 'calling' (phone dialer).
        - ONLY the owner can approve/deny. Security CANNOT PASS.
      visitor:
        - Push notification sent to the visitor's apartment owner.
        - State set to 'pending' (Yellow).
        - Second press while pending escalates to 'calling'.
        - ONLY the owner can approve/deny. Security CANNOT PASS.
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
                "alert_event_id": existing["id"],
            }

        # --- School Bus: push to all subscribers + auto-resolve ---
        if channel_type == "school_bus":
            sub_users = db._execute("""
                SELECT DISTINCT u.id
                  FROM alert_subscriptions sub
                  JOIN users u ON u.linked_id = sub.apartment_id AND u.role = 'apartment'
                 WHERE sub.channel_id = %s
            """, (channel_id,))
            title = f"🚌 School Bus Arrived: {name}"
            body = f"School Bus {name} ({identifier}) is at the gate."
            for u in (sub_users or []):
                send_push_notification(u["id"], title, body, society_id=society_id)

            event_row = db._execute("""
                INSERT INTO alert_events (society_id, channel_id, state, triggered_by, triggered_at, expires_at)
                VALUES (%s, %s, 'resolved', %s, NOW(), %s)
                RETURNING id
            """, (society_id, channel_id, triggered_by_user_id,
                  datetime.now() + timedelta(minutes=30)), fetch_one=True)

            return True, "School Bus notified: subscribers alerted (auto-PASS)", {
                "state": "resolved",
                "event_id": event_row["id"],
            }

        # --- Taxi / Visitor: push to owner + pending ---
        if channel.get("owner_user_id"):
            title = f"🚖 {name} at Gate" if channel_type == "taxi" else f"👤 Visitor: {name}"
            body = (
                f"{name} ({identifier}) for Flat {channel.get('flat_number', '')} is at the gate. "
                "Tap to Approve or Deny."
            )
            send_push_notification(channel["owner_user_id"], title, body, society_id=society_id)

        expires_at = datetime.now() + timedelta(minutes=30)
        event_row = db._execute("""
            INSERT INTO alert_events (society_id, channel_id, state, triggered_by, triggered_at, expires_at)
            VALUES (%s, %s, 'pending', %s, NOW(), %s)
            RETURNING id
        """, (society_id, channel_id, triggered_by_user_id, expires_at), fetch_one=True)

        return True, "Entry IN initiated: Pending owner approval (Yellow)", {
            "state": "pending",
            "event_id": event_row["id"],
        }
    except Exception as e:
        logger.error(f"Error triggering channel alert: {e}")
        return False, str(e), None


def respond_to_alert(alert_event_id: int, owner_user_id: int, action: str):
    """
    Owner responds to a Taxi or Visitor alert:
      action = 'approve' -> State set to 'resolved' (Green / PASS)
      action = 'deny'    -> State set to 'denied' (Red / Denied)

    SECURITY: Security staff CANNOT call this function to PASS or DENY.
    This function is restricted to apartment-owner users only.
    """
    try:
        new_state = "resolved" if action == "approve" else "denied"

        event = db._execute("""
            SELECT ae.*, ac.is_recurring, ac.id as channel_id
              FROM alert_events ae
              LEFT JOIN alert_channels ac ON ac.id = ae.channel_id
             WHERE ae.id = %s
        """, (alert_event_id,), fetch_one=True)

        if not event:
            return False, "Alert event not found"

        # Verify caller is the owner of this channel's apartment
        channel = db._execute("""
            SELECT ac.apartment_id, u.id as owner_user_id
              FROM alert_channels ac
              LEFT JOIN users u ON u.linked_id = ac.apartment_id AND u.role = 'apartment'
             WHERE ac.id = %s
        """, (event["channel_id"],), fetch_one=True)

        if channel and channel.get("owner_user_id") != owner_user_id:
            return False, "Only the apartment owner can respond to this alert"

        db._execute("""
            UPDATE alert_events
               SET state = %s
             WHERE id = %s
        """, (new_state, alert_event_id))

        if event.get("channel_id") and event.get("is_recurring") is False:
            db._execute("UPDATE alert_channels SET active = FALSE WHERE id = %s", (event["channel_id"],))

        return True, f"Alert response recorded: {new_state.upper()}"
    except Exception as e:
        logger.error(f"Error responding to alert: {e}")
        return False, str(e)


def create_walk_in_visitor(society_id: int, name: str, mobile: str, purpose: str,
                           apartment_id: int = None, vehicle_number: str = None,
                           photo: str = None, security_user_id: int = None):
    """
    Create a walk-in visitor record from the security portal.
    Security fills visitor details, then triggers notification to owner.
    """
    try:
        row = db._execute("""
            INSERT INTO visitors (society_id, apartment_id, name, mobile, purpose,
                                  vehicle_number, visit_date, status, security_user_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE, 'pending', %s, NOW())
            RETURNING id
        """, (society_id, apartment_id, name, mobile, purpose, vehicle_number, security_user_id),
           fetch_one=True)

        visitor_id = row["id"]
        return visitor_id, "Walk-in visitor created"
    except Exception as e:
        logger.error(f"Error creating walk-in visitor: {e}")
        return None, str(e)


def trigger_visitor_alert(visitor_id: int, triggered_by_user_id: int, channel_id: int = None):
    """
    Trigger a visitor alert (for both presumed and walk-in visitors).
    Sends push to owner, sets state to 'pending'.
    Second press escalates to 'calling'.
    """
    try:
        visitor = db._execute("""
            SELECT v.*, a.flat_number, u.id as owner_user_id, u.phone as owner_phone
              FROM visitors v
              LEFT JOIN apartments a ON a.id = v.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE v.id = %s
        """, (visitor_id,), fetch_one=True)

        if not visitor:
            return False, "Visitor not found", None

        society_id = visitor["society_id"]
        name = visitor["name"]

        # Check existing active alert event for this visitor
        existing = db._execute("""
            SELECT * FROM alert_events
             WHERE visitor_id = %s AND (expires_at IS NULL OR expires_at > NOW())
             ORDER BY triggered_at DESC LIMIT 1
        """, (visitor_id,), fetch_one=True)

        if existing and existing["state"] == "pending":
            db._execute("""
                UPDATE alert_events SET state = 'calling' WHERE id = %s
            """, (existing["id"],))
            return True, "Calling owner for verbal confirmation", {
                "action": "call",
                "phone": visitor.get("owner_phone"),
                "state": "calling",
                "alert_event_id": existing["id"],
            }

        # First press: pending
        expires_at = datetime.now() + timedelta(minutes=30)
        event_row = db._execute("""
            INSERT INTO alert_events (society_id, channel_id, visitor_id, state, triggered_by, triggered_at, expires_at)
            VALUES (%s, %s, %s, 'pending', %s, NOW(), %s)
            RETURNING id
        """, (society_id, channel_id, visitor_id, triggered_by_user_id, expires_at), fetch_one=True)

        if visitor.get("owner_user_id"):
            title = f"👤 Visitor Arrived: {name}"
            body = f"Visitor {name} is at the gate for Flat {visitor.get('flat_number', '')}. Tap to Approve or Deny."
            send_push_notification(visitor["owner_user_id"], title, body, society_id=society_id)

        return True, "Visitor alert sent: Pending owner approval (Yellow)", {
            "state": "pending",
            "event_id": event_row["id"],
        }
    except Exception as e:
        logger.error(f"Error triggering visitor alert: {e}")
        return False, str(e), None


def respond_to_visitor_alert(visitor_id: int, owner_user_id: int, action: str):
    """
    Owner responds to a visitor alert:
      action = 'approve' -> visitor.status = 'entered', alert state = 'resolved'
      action = 'deny'    -> visitor.status = 'denied', alert state = 'denied'

    SECURITY: Security staff CANNOT call this function.
    """
    try:
        new_state = "resolved" if action == "approve" else "denied"
        visitor_status = "entered" if action == "approve" else "denied"

        visitor = db._execute("""
            SELECT v.*, a.id as apartment_id
              FROM visitors v
              LEFT JOIN apartments a ON a.id = v.apartment_id
             WHERE v.id = %s
        """, (visitor_id,), fetch_one=True)

        if not visitor:
            return False, "Visitor not found"

        # Verify caller is the owner of this visitor's apartment
        owner_check = db._execute("""
            SELECT u.id as owner_user_id
              FROM users u
             WHERE u.linked_id = %s AND u.role = 'apartment'
        """, (visitor["apartment_id"],), fetch_one=True)

        if owner_check and owner_check.get("owner_user_id") != owner_user_id:
            return False, "Only the apartment owner can respond to this visitor alert"

        # Update visitor status
        db._execute("""
            UPDATE visitors SET status = %s, approved_by = %s, entered_at = NOW()
             WHERE id = %s
        """, (visitor_status, owner_user_id, visitor_id))

        # Update alert event state
        db._execute("""
            UPDATE alert_events SET state = %s WHERE visitor_id = %s AND (expires_at IS NULL OR expires_at > NOW())
        """, (new_state, visitor_id))

        return True, f"Visitor alert response recorded: {new_state.upper()}"
    except Exception as e:
        logger.error(f"Error responding to visitor alert: {e}")
        return False, str(e)


def get_active_alerts(society_id: int):
    """
    Fetch all active alerts for gate security and dashboard KPI cards.
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


def get_presumed_visitors(society_id: int):
    """
    Fetch presumed visitors (status='pending') for the current day.
    These are visitors from the visitors table that have not yet been processed.
    """
    try:
        rows = db._execute("""
            SELECT v.id as visitor_id, v.name, v.mobile, v.purpose, v.vehicle_number,
                   v.visit_date, v.visit_time_from, v.visit_time_to, v.status,
                   a.flat_number, u.phone as owner_phone, u.name as owner_name
              FROM visitors v
              LEFT JOIN apartments a ON a.id = v.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE v.society_id = %s
               AND v.visit_date = CURRENT_DATE
               AND v.status = 'pending'
             ORDER BY v.created_at DESC
        """, (society_id,))
        return rows or []
    except Exception as e:
        logger.error(f"Error fetching presumed visitors: {e}")
        return []


def get_pending_owner_alerts(society_id: int, apartment_id: int):
    """
    Fetch pending alerts for a specific apartment owner.
    Returns channel alerts + visitor alerts that need owner action.
    """
    try:
        alerts = db._execute("""
            SELECT ae.id as alert_event_id, ae.state, ae.triggered_at,
                   ac.id as channel_id, ac.channel_type, ac.name, ac.identifier,
                   a.flat_number
              FROM alert_events ae
              JOIN alert_channels ac ON ac.id = ae.channel_id
              LEFT JOIN apartments a ON a.id = ac.apartment_id
             WHERE ae.society_id = %s
               AND a.id = %s
               AND ae.state IN ('pending', 'calling')
               AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
             ORDER BY ae.triggered_at DESC
        """, (society_id, apartment_id))

        visitor_alerts = db._execute("""
            SELECT v.id as visitor_id, v.name as visitor_name, v.purpose,
                   ae.id as alert_event_id, ae.state, ae.triggered_at
              FROM visitors v
              LEFT JOIN alert_events ae ON ae.visitor_id = v.id AND (ae.expires_at IS NULL OR ae.expires_at > NOW())
             WHERE v.society_id = %s
               AND v.apartment_id = %s
               AND v.status = 'pending'
               AND v.visit_date = CURRENT_DATE
             ORDER BY v.created_at DESC
        """, (society_id, apartment_id))

        return {
            "channel_alerts": alerts or [],
            "visitor_alerts": visitor_alerts or [],
        }
    except Exception as e:
        logger.error(f"Error fetching pending owner alerts: {e}")
        return {"channel_alerts": [], "visitor_alerts": []}


def get_channel_subscribers_with_profile(channel_id: int):
    """
    Fetch subscribers for a channel along with their user profile details and arrival status.
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
                border_color = "#22c55e"
                status_label = "APPROVED / ARRIVED"
            elif st == "denied":
                border_color = "#ef4444"
                status_label = "DENIED"
            else:
                border_color = "#eab308"
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


def get_channel_subscribers(channel_id: int, society_id: int = None):
    """
    Alias wrapper around get_channel_subscribers_with_profile.
    """
    try:
        ch = db._execute(
            "SELECT name FROM alert_channels WHERE id = %s",
            (channel_id,), fetch_one=True
        )
        channel_name = ch["name"] if ch else "Channel"
        subs = get_channel_subscribers_with_profile(channel_id)
        return {"channel_name": channel_name, "subscribers": subs}
    except Exception as e:
        logger.error(f"get_channel_subscribers error: {e}")
        return {"channel_name": "Channel", "subscribers": []}
