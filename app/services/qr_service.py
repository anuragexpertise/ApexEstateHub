# app/services/qr_service.py (STATIC QR - NO EXPIRY)

import base64
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

ROLE_CODE_MAP_REV = {
    "admin": "A",
    "apartment": "O",
    "vendor": "V",
    "security": "S",
}


def generate_static_qr_code(entity_id: int, role: str, society_id: int):
    """
    Generate STATIC QR code (never expires - for windshield stickers).

    Payload format: entity_id|role_code|society_id
    Example: 42|O|1

    IMPORTANT: entity_id here MUST be users.id, not a linked_id (apartments.id
    / vendors.id / security_staff.id). validate_qr_code() below looks the
    user up by u.id — see the apartment note there for the one caller that
    currently violates this.
    """
    try:
        if role not in ROLE_CODE_MAP_REV:
            # Do NOT default an unrecognized role to admin ("A") — that's a
            # privilege-escalation bug waiting to happen if role is ever
            # missing/None. Fail loudly instead.
            return None, f"Unknown role for QR generation: {role!r}"

        role_code = ROLE_CODE_MAP_REV[role]
        qr_payload = f"{entity_id}|{role_code}|{society_id or 0}"

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for outdoor use
            box_size=12,  # Larger for distance scanning
            border=6,
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


def validate_qr_code(qr_data: str, society_id: int = None) -> dict:
    """
    Server-side validation with live DB checks.

    entity_id in the QR payload is always users.id (see generate_static_qr_code
    docstring). fn_evaluate_gate_pass, however, needs a different id per role:
      apartment -> apartments.id  (== the user row's linked_id)
      vendor    -> users.id       (vendor_passes.user_id is users.id)
      security  -> users.id       (gate_access.entity_id is stamped with
                                    users.id at entry/exit — see qr_callbacks.py)
    So we always look the user up by u.id, then derive the gate-pass id
    per role from that row — never from the raw QR value directly.

    Returns:
        {
            "status": "PASS" | "FAIL",
            "reason": str,
            "user": {...},
            "gate_action": "allow" | "deny",
        }
    """
    try:
        parts = qr_data.strip().split("|")

        if len(parts) < 3:
            return {"status": "FAIL", "reason": "Invalid QR format", "gate_action": "deny"}

        entity_id = int(parts[0])
        role_code = parts[1]
        qr_society_id = int(parts[2])

        role = ROLE_CODE_MAP.get(role_code, "unknown")

        if role == "unknown":
            return {"status": "FAIL", "reason": f"Unknown role code: {role_code}", "gate_action": "deny"}

        if society_id and qr_society_id != society_id:
            return {"status": "FAIL", "reason": "QR not valid for this society", "gate_action": "deny"}

        # Single lookup for every role, including admin — entity_id is
        # always users.id, so there's no separate admin branch needed.
        user_row = db._execute(
            """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id
               FROM users u
               WHERE u.id = %s AND u.society_id = %s""",
            (entity_id, qr_society_id),
            fetch_one=True,
        )

        if not user_row:
            return {"status": "FAIL", "reason": "User not found", "gate_action": "deny"}

        if user_row["role"] != role:
            return {
                "status": "FAIL",
                "reason": f"Role mismatch: QR={role}, DB={user_row['role']}",
                "gate_action": "deny",
            }

        base_user = {
            "id": user_row["id"],
            "name": user_row.get("name", role.title()),
            "email": user_row.get("email"),
            "role": user_row["role"],
            "society_id": user_row["society_id"],
            "flat_number": "",
        }

        if role in ("admin", "master"):
            # Admin: always passes, no gate-pass evaluation needed.
            return {
                "status": "PASS",
                "user": base_user,
                "message": "Admin access granted",
                "gate_action": "allow",
            }

        # Derive the id fn_evaluate_gate_pass actually expects for this role.
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
            # vendor / security both key off users.id directly
            gate_entity_id = user_row["id"]

        # Delegate to loaders.evaluate_gate_pass() — the existing wrapper
        # around fn_evaluate_gate_pass() — instead of duplicating the
        # db._execute() call here. Keeps a single call site for the
        # authoritative gate-pass logic (overdue-only for apartments,
        # active-pass for vendors, on-duty for security).
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
