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
    
    Payload format: user_id|role_code|society_id
    Example: 42|O|1
    """
    try:
        role_code = ROLE_CODE_MAP_REV.get(role, "A")
 
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
        if role == "admin":
            # Admin: Always pass
            user_row = db._execute(
            """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id 
               FROM users u 
               WHERE u.linked_id = 'None' AND u.society_id = %s AND u.role = 'admin'""",
            (qr_society_id),
            fetch_one=True
        )
            if not user_row:
                return {"status": "FAIL", "reason": "Admin user not found", "gate_action": "deny"}
            return {
                "status": "PASS",
                "user": {
                    "id": user_row["id"],
                    "name": user_row.get("name", "Admin"),
                    "email": user_row.get("email"),
                    "role": user_row["role"],
                    "society_id": user_row["society_id"],
                    "flat_number": "",
                },
                "message": "Admin access granted",
                "gate_action": "allow",
            }
        # ── FIX 1: %s placeholders + tuple params (was :name + dict) ──────
        
        user_row = db._execute(
            """SELECT u.id, u.name, u.email, u.role, u.society_id, u.linked_id 
               FROM users u 
               WHERE u.linked_id = %s AND u.society_id = %s""",
            (entity_id, qr_society_id),
            fetch_one=True
        )
 
        if not user_row:
            return {"status": "FAIL", "reason": "User not found", "gate_action": "deny"}
 
        if user_row["role"] != role:
            return {
                "status": "FAIL",
                "reason": f"Role mismatch: QR={role}, DB={user_row['role']}",
                "gate_action": "deny"
            }

    
       
        #           p_entity_id: for apartment this is users.linked_id
        #           (apartments.id); for vendor/security this is the
        #           QR-encoded user_id, matching what fn_evaluate_gate_pass
        #           and vendor_passes/gate_access already expect.
        # entity_id = user_row.get("linked_id") if role != "admin" else user_id
 
        result = db._execute(
            "SELECT * FROM fn_evaluate_gate_pass(%s, %s)",
            (role, entity_id),
            fetch_one=True,
        )
        if not result:
            return {"status": "FAIL", "reason": "Gate evaluation error", "gate_action": "deny"}
 
        base_user = {
            "id": user_row["id"],
            "name": user_row.get("name", role.title()),
            "email": user_row.get("email"),
            "role": user_row["role"],
            "society_id": user_row["society_id"],
            "flat_number": user_row.get("flat_number", "") if role == "apartment" else "",
        }
 
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