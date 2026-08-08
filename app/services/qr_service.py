# app/services/qr_service.py

import base64
from datetime import datetime
from io import BytesIO
import qrcode
from database.db_manager import db

ROLE_CODE_MAP = {
    "ADM": "admin",
    "APT": "apartment",  # Apartment / Owner
    "VND": "vendor",
    "SEC": "security",
    "VST": "visitor",
    "EVT": "event_ticket",
    "PTL": "patrol_location",
    "CON": "concern",
    "RPT": "receipt",
    "EXP": "expense",
    "AST": "asset",
    "ATD": "attendance_entry",
    # Legacy short codes for mapping compatibility
    "A": "admin",
    "O": "apartment",
    "V": "vendor",
    "S": "security",
}

ROLE_CODE_MAP_REV = {
    "admin": "ADM",
    "apartment": "APT",
    "vendor": "VND",
    "security": "SEC",
    "visitor": "VST",
    "event_ticket": "EVT",
    "patrol_location": "PTL",
    "concern": "CON",
    "receipt": "RPT",
    "expense": "EXP",
    "asset": "AST",
    "attendance_entry": "ATD",
}


def parse_qr_payload(qr_data: str) -> dict:
    """
    Parses QR string in format: <society_id>-<ROLE_CODE>-<entity_id>
    Example: 1-EVT-1001 or 1-APT-42
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
    role_code = ROLE_CODE_MAP_REV.get(role, "APT")
    return generate_qr_code(society_id, role_code, entity_id)


def validate_event_ticket_qr(ticket_item_id: int, society_id: int, security_user_id: int = None) -> dict:
    """Check event_ticket_items row, verify validity and mark as used on gate scan.

    Single-use: a scanned ticket is stamped 'used' immediately (events are
    admission-gated, no two-actor approval needed). The event's id/title/date
    are surfaced so the gate callback can pivot to the event profile.
    """
    try:
        item = db._execute("""
            SELECT eti.*, et.booking_reference, et.event_id,
                   e.title as event_title, e.event_date, e.venue
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
            "event_id": item["event_id"],
            "ticket_item_id": item["id"],
            "user": {
                "id": item["id"],
                "name": f"Event Ticket ({item['ticket_type']}) - {item['event_title']}",
                "role": "event_ticket",
                "society_id": society_id,
                "ticket_type": item["ticket_type"],
                "event_title": item["event_title"],
                "event_date": str(item["event_date"]),
                "venue": item["venue"] or "",
                "booking_reference": item["booking_reference"] or "",
            },
            "message": f"Valid {item['ticket_type']} Pass admitted for {item['event_title']}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Event ticket scan error: {str(e)}", "gate_action": "deny"}



def _visitor_user(vis, society_id: int) -> dict:
    """Build the user-profile payload embedded in visitor QR-scan results."""
    return {
        "id": vis["id"],
        "name": f"Visitor: {vis['name']} (Flat {vis.get('flat_number', 'N/A')})",
        "role": "visitor",
        "society_id": society_id,
        "visitor_id": vis["id"],
        "visitor_name": vis["name"],
        "flat_number": vis.get("flat_number") or "",
        "purpose": vis.get("purpose") or "",
        "status": vis.get("status"),
        "owner_name": vis.get("owner_name") or "",
        "owner_phone": vis.get("owner_phone") or "",
    }


def validate_visitor_qr(visitor_id: int, society_id: int, security_user_id: int = None) -> dict:
    """Validate a scanned visitor QR.

    Two-actor enforcement: a visitor is NEVER auto-admitted by the gate scan
    alone. Only a *pre-approved* pass (status='approved', approved_by set by
    an owner up-front) is admitted directly on scan. A 'pending' presumptive
    visitor resolves to PENDING_CONFIRMATION — the caller
    (qr_callbacks.validate_qr_scanned) routes it through
    alert_service.trigger_visitor_alert(), identical to the KPI-press flow,
    so an owner must confirm before status flips to 'entered'.

    Admission (status='entered') is ultimately set by the owner's response
    via alert_service.respond_to_visitor_alert() — never by the gate scan
    itself — so security cannot bypass owner consent.
    """
    try:
        vis = db._execute("""
            SELECT v.*, a.flat_number, u.name AS owner_name, u.mobile AS owner_phone
              FROM visitors v
              LEFT JOIN apartments a ON a.id = v.apartment_id
              LEFT JOIN users u ON u.linked_id = a.id AND u.role = 'apartment'
             WHERE v.id = %s AND v.society_id = %s
        """, (visitor_id, society_id), fetch_one=True)

        if not vis:
            return {"status": "FAIL", "reason": "Visitor pass not found", "gate_action": "deny"}

        if vis["status"] == "denied":
            return {"status": "FAIL", "reason": "Visitor pass was denied", "gate_action": "deny"}

        if vis["status"] == "entered":
            return {
                "status": "PASS",
                "reason": "Visitor already admitted",
                "gate_action": "allow",
                "user": _visitor_user(vis, society_id),
            }

        # Pre-approved by an owner → admit directly on scan.
        # Concurrency-safe: a conditional UPDATE (status='approved' only) with
        # a RETURNING row, so two simultaneous scans / a scan racing the
        # owner's in-app approval can't double-admit. db._execute returns the
        # matched row (or None) for RETURNING, which stands in for rowcount
        # since this driver layer exposes no cur.rowcount.
        if vis["status"] == "approved" and vis.get("approved_by"):
            won = db._execute("""
                UPDATE visitors
                   SET status = 'entered', entered_at = NOW(), security_user_id = %s
                WHERE id = %s AND status = 'approved'
                RETURNING id
            """, (security_user_id, visitor_id), fetch_one=True)

            if not won:  # race: owner / another guard already moved it
                vis = db._execute(
                    "SELECT v.*, a.flat_number FROM visitors v "
                    "LEFT JOIN apartments a ON a.id = v.apartment_id "
                    "WHERE v.id = %s", (visitor_id,), fetch_one=True
                )
                return {
                    "status": "PASS" if vis and vis["status"] == "entered" else "PENDING_CONFIRMATION",
                    "reason": "Visitor already processed" if (vis and vis["status"] == "entered")
                            else "Visitor awaiting owner confirmation",
                    "gate_action": "allow" if vis and vis["status"] == "entered" else "review",
                    "needs_owner_approval": not (vis and vis["status"] == "entered"),
                    "user": _visitor_user(vis, society_id) if vis else None,
                }

            return {
                "status": "PASS",
                "message": f"Visitor Admitted: {vis['name']}",
                "gate_action": "allow",
                "user": _visitor_user(vis, society_id),
            }

        # Pending / not-yet-approved presumptive visitor → valid QR, but entry
        # requires owner confirmation. The gate scan itself must NOT admit.
        return {
            "status": "PENDING_CONFIRMATION",
            "gate_action": "review",
            "reason": "Visitor awaiting owner confirmation",
            "needs_owner_approval": True,
            "user": _visitor_user(vis, society_id),
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


def validate_concern_qr(concern_id: int, society_id: int, security_user_id: int = None) -> dict:
    try:
        concern = db._execute(
            "SELECT id, concern_type, status FROM concerns WHERE id = %s AND society_id = %s",
            (concern_id, society_id), fetch_one=True,
        )
        if not concern:
            return {"status": "FAIL", "reason": "Concern not found", "gate_action": "deny"}
        return {
            "status": "PASS",
            "user": {
                "id": concern_id,
                "name": f"Concern: {concern.get('concern_type', 'Unknown')} ({concern.get('status', '')})",
                "role": "concern",
                "society_id": society_id,
            },
            "message": "Valid Concern",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Concern validation error: {str(e)}", "gate_action": "deny"}


def validate_receipt_qr(receipt_id: int, society_id: int, security_user_id: int = None) -> dict:
    try:
        receipt = db._execute(
            "SELECT id, particulars, amount, status FROM receipts WHERE id = %s AND society_id = %s",
            (receipt_id, society_id), fetch_one=True,
        )
        if not receipt:
            return {"status": "FAIL", "reason": "Receipt not found", "gate_action": "deny"}
        return {
            "status": "PASS",
            "user": {
                "id": receipt_id,
                "name": f"Receipt: {receipt.get('particulars', 'Unknown')}",
                "role": "receipt",
                "society_id": society_id,
                "amount": receipt.get("amount"),
                "status": receipt.get("status"),
            },
            "message": f"Valid Receipt — {receipt.get('status', '')}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Receipt validation error: {str(e)}", "gate_action": "deny"}


def validate_expense_qr(expense_id: int, society_id: int, security_user_id: int = None) -> dict:
    try:
        expense = db._execute(
            "SELECT id, particulars, amount, status FROM expenses WHERE id = %s AND society_id = %s",
            (expense_id, society_id), fetch_one=True,
        )
        if not expense:
            return {"status": "FAIL", "reason": "Expense not found", "gate_action": "deny"}
        return {
            "status": "PASS",
            "user": {
                "id": expense_id,
                "name": f"Expense: {expense.get('particulars', 'Unknown')}",
                "role": "expense",
                "society_id": society_id,
                "amount": expense.get("amount"),
                "status": expense.get("status"),
            },
            "message": f"Valid Expense — {expense.get('status', '')}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Expense validation error: {str(e)}", "gate_action": "deny"}


def validate_asset_qr(asset_id: int, society_id: int, security_user_id: int = None) -> dict:
    try:
        asset = db._execute(
            "SELECT id, asset_name, purchase_value, disposed FROM assets WHERE id = %s AND society_id = %s",
            (asset_id, society_id), fetch_one=True,
        )
        if not asset:
            return {"status": "FAIL", "reason": "Asset not found", "gate_action": "deny"}
        return {
            "status": "PASS",
            "user": {
                "id": asset_id,
                "name": f"Asset: {asset.get('asset_name', 'Unknown')}",
                "role": "asset",
                "society_id": society_id,
                "purchase_value": asset.get("purchase_value"),
                "disposed": asset.get("disposed"),
            },
            "message": f"Valid Asset — {'Disposed' if asset.get('disposed') else 'Active'}",
            "gate_action": "allow",
        }
    except Exception as e:
        return {"status": "FAIL", "reason": f"Asset validation error: {str(e)}", "gate_action": "deny"}


ATTENDANCE_QR_EXPIRY_SECONDS = 60


def generate_time_qr(society_id: int):
    """
    Generate a 1-minute time-boxed attendance QR for the Security/Admin
    Settings tab. Payload: <society_id>-ATD-<epoch_seconds>.
    Epoch (not ISO) is used deliberately — parse_qr_payload() splits on
    '-', and an ISO timestamp would break that split.
    Returns (img_src_b64, payload, issued_at_epoch, expires_at_epoch) so
    the UI can drive its own 60s auto-refresh countdown.
    """
    issued_at = int(datetime.utcnow().timestamp())
    img_src, payload = generate_qr_code(society_id, "ATD", issued_at)
    return img_src, payload, issued_at, issued_at + ATTENDANCE_QR_EXPIRY_SECONDS


def validate_attendance_qr(issued_at: int, society_id: int, security_user_id: int = None) -> dict:
    """
    Validate a time-boxed ATD QR and toggle the SCANNING guard's own duty
    status (clock in if not on duty, clock out if already on duty).
    `security_user_id` must be the scanning guard's own users.id, taken
    from their authenticated session — not an audit-only field here.
    """
    now = int(datetime.utcnow().timestamp())
    age = now - issued_at

    if age > ATTENDANCE_QR_EXPIRY_SECONDS:
        return {"status": "FAIL", "reason": "QR expired — ask for a fresh code", "gate_action": "deny"}
    if age < -5:  # small clock-skew allowance
        return {"status": "FAIL", "reason": "QR not yet valid", "gate_action": "deny"}
    if not security_user_id:
        return {"status": "FAIL", "reason": "Attendance QR must be scanned from a logged-in security account", "gate_action": "deny"}

    user_row = db._execute(
        "SELECT id, linked_id FROM users WHERE id=%s AND society_id=%s AND role='security'",
        (security_user_id, society_id), fetch_one=True,
    )
    if not user_row or not user_row.get("linked_id"):
        return {"status": "FAIL", "reason": "Attendance QR can only be scanned by security staff", "gate_action": "deny"}

    staff_id = user_row["linked_id"]  # security_staff.id — matches gate_access.entity_id

    open_row = db._execute(
        """SELECT id FROM gate_access
           WHERE society_id=%s AND entity_id=%s AND role='SEC' AND time_out IS NULL
           ORDER BY time_in DESC LIMIT 1""",
        (society_id, staff_id), fetch_one=True,
    )

    if open_row:
        db._execute("UPDATE gate_access SET time_out=NOW(), updated_by=%s WHERE id=%s",
                    (security_user_id, open_row["id"]))
        action, msg = "clock_out", "Clocked out"
    else:
        db._execute(
            """INSERT INTO gate_access (society_id, role, entity_id, time_in, created_by)
               VALUES (%s, 'SEC', %s, NOW(), %s)""",
            (society_id, staff_id, security_user_id),
        )
        action, msg = "clock_in", "Clocked in"

    return {
        "status": "PASS", "action": action,
        "user": {"id": staff_id, "role": "security", "society_id": society_id},
        "message": msg, "gate_action": "allow",
    }


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
        elif role == "attendance_entry":
            # entity_id here is the epoch issued_at, not a row id
            return validate_attendance_qr(entity_id, qr_society_id, security_user_id)

        elif role == "concern":
            return validate_concern_qr(entity_id, qr_society_id, security_user_id)
        elif role == "receipt":
            return validate_receipt_qr(entity_id, qr_society_id, security_user_id)
        elif role == "expense":
            return validate_expense_qr(entity_id, qr_society_id, security_user_id)
        elif role == "asset":
            return validate_asset_qr(entity_id, qr_society_id, security_user_id)

        if role == "apartment":
            user_row = db._execute(
                """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
                   FROM users u
                   WHERE u.linked_id = %s AND u.role = 'apartment' AND u.society_id = %s""",
                (entity_id, qr_society_id),
                fetch_one=True,
            )
        elif role == "vendor":
            user_row = db._execute(
                """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
                   FROM users u
                   WHERE u.linked_id = %s AND u.role = 'vendor' AND u.society_id = %s""",
                (entity_id, qr_society_id),
                fetch_one=True,
            )
        elif role == "security":
            user_row = db._execute(
                """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
                   FROM users u
                   WHERE u.linked_id = %s AND u.role = 'security' AND u.society_id = %s""",
                (entity_id, qr_society_id),
                fetch_one=True,
            )
        elif role in ("admin", "master"):
            user_row = db._execute(
                """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
                   FROM users u
                   WHERE u.id = %s AND u.society_id = %s""",
                (entity_id, qr_society_id),
                fetch_one=True,
            )
        else:
            user_row = None

        if not user_row:
            return {"status": "FAIL", "reason": "User not found", "gate_action": "deny"}

        base_user = {
            "id": user_row["linked_id"] or user_row["id"],
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

        gate_entity_id = user_row.get("linked_id") or user_row["id"]
        if role == "apartment":
            flat = db._execute(
                "SELECT flat_number FROM apartments WHERE id = %s",
                (gate_entity_id,), fetch_one=True,
            )
            base_user["flat_number"] = (flat or {}).get("flat_number", "")

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

