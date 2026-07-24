# app/services/qr_service.py

import base64
from datetime import datetime
from io import BytesIO
import qrcode
from database.db_manager import db

ROLE_CODE_MAP = {
    "ADM": "admin",
    "OWN": "apartment",  # Owner
    "VND": "vendor",
    "SEC": "security",
    "VST": "visitor",
    "EVT": "event_ticket",
    "PTL": "patrol_location",
    # Legacy short codes for mapping compatibility
    "A": "admin",
    "O": "apartment",
    "V": "vendor",
    "S": "security",
}

ROLE_CODE_MAP_REV = {
    "admin": "ADM",
    "apartment": "OWN",
    "vendor": "VND",
    "security": "SEC",
    "visitor": "VST",
    "event_ticket": "EVT",
    "patrol_location": "PTL",
}


def parse_qr_payload(qr_data: str) -> dict:
    """
    Parses QR string in format: <society_id>-<ROLE_CODE>-<entity_id>
    Example: 1-EVT-1001 or 1-OWN-42
    """
    try:
        raw = qr_data.strip()
        parts = [p.strip() for p in raw.split("-") if p.strip()]

        if len(parts) < 3:
            return {"error": "Invalid format. Expected: society_id-ROLE_CODE-entity_id"}

        society_id = int(parts[0])
        role_code = parts[1].upper()
        entity_id = int(parts[2])

        role = ROLE_CODE_MAP.get(role_code, "unknown")
        if role == "unknown":
            return {"error": f"Unknown role code: {role_code}"}

        return {
            "society_id": society_id,
            "role_code": role_code,
            "role": role,
            "entity_id": entity_id,
        }
    except Exception as e:
        return {"error": f"Parse failure: {str(e)}"}


def generate_qr_code(society_id: int, role_code: str, entity_id: int):
    """
    Generate QR code image (Base64) and payload.
    Payload format: <society_id>-<ROLE_CODE>-<entity_id>
    """
    try:
        role_code_clean = role_code.upper().strip()
        qr_payload = f"{society_id or 0}-{role_code_clean}-{entity_id}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_payload)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return f"data:image/png;base64,{img_str}", qr_payload
    except Exception as e:
        print(f"QR generation error: {e}")
        return None, str(e)


def generate_static_qr_code(entity_id: int, role: str, society_id: int):
    """
    Wrapper for user/apartment static QR generation using updated format.
    """
    role_code = ROLE_CODE_MAP_REV.get(role, "OWN")
    return generate_qr_code(society_id, role_code, entity_id)


def validate_event_ticket_qr(ticket_item_id: int, society_id: int, security_user_id: int = None) -> dict:
    """Check event_ticket_items row, verify validity and mark as used on gate scan."""
    try:
        item = db._execute("""
            SELECT eti.*, et.booking_reference, e.title as event_title, e.event_date, e.venue
              FROM event_ticket_items eti
              JOIN event_tickets et ON et.id = eti.event_ticket_id
              JOIN events e ON e.id = et.event_id
             WHERE eti.id = %s AND eti.society_id = %s
        """, (ticket_item_id, society_id), fetch_one=True)

        if not item:
            return {"status": "FAIL", "reason": "Ticket not found for this society", "gate_action": "deny"}

        if item["status"] == "used":
            return {
                "status": "FAIL",
                "reason": f"Ticket already used on {item['scanned_at']}",
                "gate_action": "deny",
            }
        if item["status"] == "cancelled":
            return {"status": "FAIL", "reason": "Ticket has been cancelled", "gate_action": "deny"}

        # Mark ticket item as USED
        db._execute("""
            UPDATE event_ticket_items
               SET status = 'used', scanned_at = NOW(), scanned_by = %s
             WHERE id = %s
        """, (security_user_id, ticket_item_id))

        return {
            "status": "PASS",
            "user": {
                "id": item["id"],
                "name": f"Event Ticket ({item['ticket_type']}) - {item['event_title']}",
                "role": "event_ticket",
                "society_id": society_id,
            },
            "message": f"Valid {item['ticket_type']} Pass for {item['event_title']}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Event ticket scan error: {str(e)}", "gate_action": "deny"}


def validate_visitor_qr(visitor_id: int, society_id: int, security_user_id: int = None) -> dict:
    """Check visitor pass and mark entered."""
    try:
        vis = db._execute("""
            SELECT v.*, a.flat_number
              FROM visitors v
              LEFT JOIN apartments a ON a.id = v.apartment_id
             WHERE v.id = %s AND v.society_id = %s
        """, (visitor_id, society_id), fetch_one=True)

        if not vis:
            return {"status": "FAIL", "reason": "Visitor pass not found", "gate_action": "deny"}

        if vis["status"] == "denied":
            return {"status": "FAIL", "reason": "Visitor pass was denied", "gate_action": "deny"}

        if vis["status"] == "entered":
            return {"status": "PASS", "reason": "Visitor already admitted", "gate_action": "allow"}

        # Update visitor status to entered
        db._execute("""
            UPDATE visitors
               SET status = 'entered', entered_at = NOW(), security_user_id = %s
             WHERE id = %s
        """, (security_user_id, visitor_id))

        return {
            "status": "PASS",
            "user": {
                "id": vis["id"],
                "name": f"Visitor: {vis['name']} (Flat {vis.get('flat_number', 'N/A')})",
                "role": "visitor",
                "society_id": society_id,
            },
            "message": f"Visitor Admitted: {vis['name']}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Visitor validation error: {str(e)}", "gate_action": "deny"}


def validate_patrol_qr(location_id: int, society_id: int, security_user_id: int = None) -> dict:
    """Log security patrol point scan."""
    try:
        loc = db._execute("""
            SELECT * FROM patrol_locations WHERE id = %s AND society_id = %s AND active = TRUE
        """, (location_id, society_id), fetch_one=True)

        if not loc:
            return {"status": "FAIL", "reason": "Patrol location not found or inactive", "gate_action": "deny"}

        db._execute("""
            INSERT INTO patrol_scans (society_id, location_id, security_user_id, scanned_at)
            VALUES (%s, %s, %s, NOW())
        """, (society_id, location_id, security_user_id))

        return {
            "status": "PASS",
            "user": {
                "id": loc["id"],
                "name": f"Patrol Point: {loc['location_name']}",
                "role": "patrol_location",
                "society_id": society_id,
            },
            "message": f"Patrol Scan Logged: {loc['location_name']}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Patrol scan error: {str(e)}", "gate_action": "deny"}


def validate_qr_code(qr_data: str, society_id: int = None, security_user_id: int = None) -> dict:
    """
    Server-side validation with standard hyphenated format (<society_id>-<ROLE_CODE>-<entity_id>).
    Dispatches to role-specific validators.
    """
    try:
        parsed = parse_qr_payload(qr_data)
        if "error" in parsed:
            return {"status": "FAIL", "reason": parsed["error"], "gate_action": "deny"}

        qr_society_id = parsed["society_id"]
        role = parsed["role"]
        entity_id = parsed["entity_id"]

        if society_id and qr_society_id != society_id:
            return {"status": "FAIL", "reason": "QR not valid for this society", "gate_action": "deny"}

        # Dispatch specialized roles
        if role == "event_ticket":
            return validate_event_ticket_qr(entity_id, qr_society_id, security_user_id)
        elif role == "visitor":
            return validate_visitor_qr(entity_id, qr_society_id, security_user_id)
        elif role == "patrol_location":
            return validate_patrol_qr(entity_id, qr_society_id, security_user_id)

        # Standard User lookup (admin, apartment, vendor, security)
        user_row = db._execute(
            """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
               FROM users u
               WHERE u.id = %s AND u.society_id = %s""",
            (entity_id, qr_society_id),
            fetch_one=True,
        )

        if not user_row:
            return {"status": "FAIL", "reason": "User not found", "gate_action": "deny"}

        base_user = {
            "id": user_row["id"],
            "name": user_row.get("name", role.title()),
            "email": user_row.get("email"),
            "role": user_row["role"],
            "society_id": user_row["society_id"],
            "flat_number": "",
        }

        if role in ("admin", "master"):
            return {
                "status": "PASS",
                "user": base_user,
                "message": "Admin access granted",
                "gate_action": "allow",
            }

        if role == "apartment":
            gate_entity_id = user_row.get("linked_id")
            if not gate_entity_id:
                return {"status": "FAIL", "reason": "No linked apartment for this user",
                         "user": base_user, "gate_action": "deny"}
            flat = db._execute(
                "SELECT flat_number FROM apartments WHERE id = %s",
                (gate_entity_id,), fetch_one=True,
            )
            base_user["flat_number"] = (flat or {}).get("flat_number", "")
        else:
            gate_entity_id = user_row["id"]

        from app.dash_apps.drilldown.loaders import evaluate_gate_pass

        result = evaluate_gate_pass(role, gate_entity_id)
        if not result:
            return {"status": "FAIL", "reason": "Gate evaluation error",
                     "user": base_user, "gate_action": "deny"}

        if result.get("passed"):
            return {
                "status": "PASS",
                "user": base_user,
                "message": result.get("reason", "Access granted"),
                "gate_action": "allow",
            }
        else:
            return {
                "status": "FAIL",
                "reason": result.get("reason", "Access denied"),
                "user": base_user,
                "gate_action": "deny",
            }

    except ValueError as e:
        return {"status": "FAIL", "reason": f"Parse error: {str(e)}", "gate_action": "deny"}
    except Exception as e:
        print(f"QR validation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "FAIL", "reason": f"System error: {str(e)[:50]}", "gate_action": "deny"}

