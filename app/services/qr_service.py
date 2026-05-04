import base64
import json
from datetime import datetime, timedelta
from io import BytesIO

import qrcode

from database.db_manager import db


ROLE_CODE_MAP = {
    "A": "admin",
    "O": "apartment",  # Owner
    "V": "vendor",
    "S": "security",
}


def generate_qr_code(data):
    """Generate QR code as base64 string."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(str(data))
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"QR generation error: {e}")
        return ""


def _fail(reason):
    return {"status": "FAIL", "reason": reason}


def _parse_qr_payload(qr_data):
    """Parse QR payload in format: user_id|role_code|society_id"""
    if not qr_data:
        raise ValueError("Empty QR code")

    qr_text = str(qr_data).strip()

    # Parse pipe-delimited format: user_id|role_code|society_id
    parts = [part.strip() for part in qr_text.split("|")]
    if len(parts) >= 3:
        return {
            "user_id": parts[0],
            "role": parts[1],  # Single letter code (A, O, V, S)
            "society_id": parts[2],
        }

    # Fallback: if only digits, treat as user_id
    if qr_text.isdigit():
        return {"user_id": qr_text}

    raise ValueError("Unsupported QR format - expected: user_id|role|society_id")


def _normalize_role(role_value):
    """Normalize role code to full role name"""
    if role_value is None:
        return None

    role = str(role_value).strip().upper()  # Convert to uppercase for code matching
    if not role:
        return None
    
    # If it's a single letter code, map it
    if len(role) == 1:
        return ROLE_CODE_MAP.get(role, role.lower())
    
    # Otherwise return as lowercase
    return role.lower()


def _parse_issued_at(raw_value):
    if not raw_value:
        return None

    issued_at_str = str(raw_value).strip()
    if issued_at_str.endswith("Z"):
        issued_at_str = issued_at_str[:-1] + "+00:00"

    return datetime.fromisoformat(issued_at_str)


def _load_user(user_id, email, role, society_id):
    query = """
        SELECT id, email, role, society_id
        FROM users
        WHERE 1 = 1
    """
    params = []

    if user_id is not None:
        query += " AND id = %s"
        params.append(user_id)
    if email:
        query += " AND email = %s"
        params.append(email)
    if role:
        query += " AND role = %s"
        params.append(role)
    if society_id:
        query += " AND society_id = %s"
        params.append(society_id)

    if not params:
        return None

    return db.execute_query(query, tuple(params), fetch_one=True)


def _resolve_apartment_for_user(user_id, society_id):
    return db.execute_query(
        """
        SELECT id, flat_number, owner_name
        FROM apartments
        WHERE society_id = %s
          AND (
                LOWER(TRIM(owner_name)) = LOWER(TRIM(
                    COALESCE((SELECT name FROM users WHERE id = %s), '')
                ))
             OR mobile = (SELECT phone FROM users WHERE id = %s)
          )
        ORDER BY id
        LIMIT 1
        """,
        (society_id, user_id, user_id),
        fetch_one=True,
    )


def _has_pending_dues(user_row):
    role = _normalize_role(user_row.get("role"))
    society_id = user_row.get("society_id")
    user_id = user_row.get("id")

    if role == "vendor":
        pending = db.execute_query(
            """
            SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE society_id = %s AND user_id = %s AND status = 'pending'
            """,
            (society_id, user_id),
            fetch_one=True,
        ) or {"c": 0, "total": 0}
        return int(pending.get("c", 0)) > 0, pending, None

    if role == "apartment":
        apartment = _resolve_apartment_for_user(user_id, society_id)
        if not apartment:
            return False, {"c": 0, "total": 0}, None

        pending = db.execute_query(
            """
            SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS total
            FROM payments
            WHERE society_id = %s AND apartment_id = %s AND status = 'pending'
            """,
            (society_id, apartment["id"]),
            fetch_one=True,
        ) or {"c": 0, "total": 0}
        return int(pending.get("c", 0)) > 0, pending, apartment

    return False, {"c": 0, "total": 0}, None


def _has_open_gate_entry(user_row):
    role = _normalize_role(user_row.get("role"))
    role_code = role[:1] if role else None
    if not role_code:
        return False

    open_entry = db.execute_query(
        """
        SELECT id
        FROM gate_access
        WHERE society_id = %s
          AND entity_id = %s
          AND role = %s
          AND time_out IS NULL
        ORDER BY time_in DESC
        LIMIT 1
        """,
        (user_row.get("society_id"), user_row.get("id"), role_code),
        fetch_one=True,
    )
    return bool(open_entry)


def validate_qr_code(qr_data, society_id):
    """Validate QR code against database state for gate access."""
    try:
        payload = _parse_qr_payload(qr_data)

        user_id = payload.get("user_id")
        email = payload.get("email")
        role = _normalize_role(payload.get("role"))

        if user_id is not None:
            user_id = int(user_id)

        issued_at = _parse_issued_at(payload.get("issued_at"))
        if issued_at and datetime.now(issued_at.tzinfo) - issued_at > timedelta(days=7):
            return _fail("QR code expired")

        user_row = _load_user(user_id, email, role, society_id)
        if not user_row:
            return _fail("QR code does not match any registered user")

        if society_id and user_row.get("society_id") != society_id:
            return _fail("QR code is not valid for this society")

        has_dues, pending_info, apartment = _has_pending_dues(user_row)
        if has_dues:
            if apartment:
                return _fail(
                    f"Pending dues found for flat {apartment.get('flat_number', '-')}"
                )
            return _fail(
                f"Pending dues found: Rs {float(pending_info.get('total', 0)):.2f}"
            )

        if _has_open_gate_entry(user_row):
            return _fail("Open gate entry already exists for this pass")

        name = (
            user_row.get("name")
            or user_row.get("email", "").split("@")[0].title()
            or "User"
        )

        return {
            "status": "PASS",
            "message": "Access granted",
            "user": {
                "id": user_row.get("id"),
                "name": name,
                "email": user_row.get("email"),
                "role": user_row.get("role"),
                "society_id": user_row.get("society_id"),
            },
        }
    except ValueError as e:
        return _fail(str(e))
    except Exception as e:
        print(f"QR validation error: {e}")
        return _fail(f"Error: {str(e)}")
