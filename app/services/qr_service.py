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


def generate_static_qr_code(user_id: int, role: str, society_id: int):
    """
    Generate STATIC QR code (never expires - for windshield stickers).
    
    Payload format: user_id|role_code|society_id
    Example: 42|O|1
    """
    try:
        role_code = ROLE_CODE_MAP_REV.get(role, "V")
        qr_payload = f"{user_id}|{role_code}|{society_id or 0}"
        
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
        # Parse QR payload
        parts = qr_data.strip().split("|")
        
        if len(parts) < 3:
            return {"status": "FAIL", "reason": "Invalid QR format", "gate_action": "deny"}
        
        user_id = int(parts[0])
        role_code = parts[1]
        qr_society_id = int(parts[2])
        
        role = ROLE_CODE_MAP.get(role_code, "unknown")
        
        if role == "unknown":
            return {"status": "FAIL", "reason": f"Unknown role code: {role_code}", "gate_action": "deny"}
        
        # Verify society match
        if society_id and qr_society_id != society_id:
            return {"status": "FAIL", "reason": "QR not valid for this society", "gate_action": "deny"}
        
        # Load user from DB
        user_row = db._execute(
            """SELECT u.id, u.email, u.role, u.society_id, u.linked_id,
                      COALESCE(a.owner_name, u.email) AS name,
                      COALESCE(a.flat_number, '') AS flat_number
               FROM users u
               LEFT JOIN apartments a ON u.linked_id = a.id AND u.role = 'apartment'
               WHERE u.id = :user_id AND u.society_id = :society_id""",
            {"user_id": user_id, "society_id": qr_society_id},
            fetch_one=True
        )
        
        if not user_row:
            return {"status": "FAIL", "reason": "User not found", "gate_action": "deny"}
        
        # Role mismatch check
        if user_row["role"] != role:
            return {
                "status": "FAIL", 
                "reason": f"Role mismatch: QR={role}, DB={user_row['role']}", 
                "gate_action": "deny"
            }
        
        # ═══════════════════════════════════════════════════════════════
        # ROLE-SPECIFIC VALIDATION RULES
        # ═══════════════════════════════════════════════════════════════
        
        if role == "admin":
            # Admin: Always pass
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
        
        elif role == "apartment":
            # Owner: Check pending dues
            dues = db._execute(
                """SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS total
                   FROM payments
                   WHERE society_id = :society_id
                   AND apartment_id = :apartment_id
                   AND status = 'pending'""",
                {"society_id": qr_society_id, "apartment_id": user_row.get("linked_id")},
                fetch_one=True
            ) or {"c": 0, "total": 0}
            
            if int(dues.get("c", 0)) > 0:
                return {
                    "status": "FAIL",
                    "reason": f"Pending dues: ₹{float(dues.get('total', 0)):,.0f}",
                    "user": {
                        "id": user_row["id"],
                        "name": user_row.get("name", "Owner"),
                        "flat_number": user_row.get("flat_number", ""),
                    },
                    "gate_action": "deny",
                }
            
            return {
                "status": "PASS",
                "user": {
                    "id": user_row["id"],
                    "name": user_row.get("name", "Owner"),
                    "email": user_row.get("email"),
                    "role": user_row["role"],
                    "society_id": user_row["society_id"],
                    "flat_number": user_row.get("flat_number", ""),
                },
                "message": f"Flat {user_row.get('flat_number', '?')} - Dues cleared",
                "gate_action": "allow",
            }
        
        elif role == "vendor":
            # Vendor: Check active pass
            active_pass = db._execute(
                """SELECT id, valid_until
                   FROM vendor_passes
                   WHERE society_id = :society_id AND user_id = :user_id
                   AND status = 'active'
                   AND valid_until >= CURRENT_DATE
                   ORDER BY valid_until DESC LIMIT 1""",
                {"society_id": qr_society_id, "user_id": user_id},
                fetch_one=True
            )
            
            if not active_pass:
                return {
                    "status": "FAIL",
                    "reason": "No active vendor pass",
                    "user": {
                        "id": user_row["id"],
                        "name": user_row.get("name", "Vendor"),
                    },
                    "gate_action": "deny",
                }
            
            valid_until = active_pass.get("valid_until")
            return {
                "status": "PASS",
                "user": {
                    "id": user_row["id"],
                    "name": user_row.get("name", "Vendor"),
                    "email": user_row.get("email"),
                    "role": user_row["role"],
                    "society_id": user_row["society_id"],
                    "flat_number": "",
                },
                "message": f"Pass valid until {valid_until}",
                "gate_action": "allow",
            }
        
        elif role == "security":
            # Security: Check if on duty
            on_duty = db._execute(
                """SELECT id FROM gate_access
                   WHERE society_id = :society_id AND entity_id = :entity_id
                   AND role = 's' AND time_out IS NULL
                   ORDER BY time_in DESC LIMIT 1""",
                {"society_id": qr_society_id, "entity_id": user_id},
                fetch_one=True
            )
            
            if not on_duty:
                return {
                    "status": "FAIL",
                    "reason": "Not on duty",
                    "user": {
                        "id": user_row["id"],
                        "name": user_row.get("name", "Security"),
                    },
                    "gate_action": "deny",
                }
            
            return {
                "status": "PASS",
                "user": {
                    "id": user_row["id"],
                    "name": user_row.get("name", "Security"),
                    "email": user_row.get("email"),
                    "role": user_row["role"],
                    "society_id": user_row["society_id"],
                    "flat_number": "",
                },
                "message": "On duty - access granted",
                "gate_action": "allow",
            }
        
        return {"status": "FAIL", "reason": "Unknown validation error", "gate_action": "deny"}
        
    except ValueError as e:
        return {"status": "FAIL", "reason": f"Parse error: {str(e)}", "gate_action": "deny"}
    except Exception as e:
        print(f"QR validation error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "FAIL", "reason": f"System error: {str(e)[:50]}", "gate_action": "deny"}