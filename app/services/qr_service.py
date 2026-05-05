# app/services/qr_service.py (ENHANCED)

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

ROLE_CODE_MAP_REV = {
    "admin": "A",
    "apartment": "O",
    "vendor": "V",
    "security": "S",
}


def _calculate_validity(user_id: int, role: str, society_id: int) -> tuple:
    """
    Calculate QR validity based on role-specific rules.
    Returns: (is_valid: bool, reason: str, expiry: datetime|None)
    """
    try:
        if role == "admin":
            # Admin always valid
            return True, "Admin access", datetime.now() + timedelta(days=365)
        
        elif role == "apartment":
            # Valid if no pending dues
            dues = db.execute_query(
                """SELECT COUNT(*) AS c, COALESCE(SUM(amount), 0) AS total
                   FROM payments 
                   WHERE society_id = %s AND apartment_id = (
                       SELECT linked_id FROM users WHERE id = %s
                   ) AND status = 'pending'""",
                (society_id, user_id),
                fetch_one=True
            ) or {"c": 0, "total": 0}
            
            if int(dues.get("c", 0)) > 0:
                return False, f"Pending dues: ₹{float(dues.get('total', 0)):.0f}", None
            return True, "Dues cleared", datetime.now() + timedelta(days=30)
        
        elif role == "vendor":
            # Valid if has active vendor pass
            active_pass = db.execute_query(
                """SELECT id, valid_until 
                   FROM vendor_passes 
                   WHERE society_id = %s AND user_id = %s 
                   AND status = 'active' 
                   AND valid_until >= CURRENT_DATE
                   ORDER BY valid_until DESC LIMIT 1""",
                (society_id, user_id),
                fetch_one=True
            )
            
            if not active_pass:
                return False, "No active vendor pass", None
            
            valid_until = active_pass.get("valid_until")
            return True, f"Pass valid until {valid_until}", valid_until
        
        elif role == "security":
            # Valid if currently on duty
            on_duty = db.execute_query(
                """SELECT id FROM gate_access 
                   WHERE society_id = %s AND entity_id = %s 
                   AND role = 's' AND time_out IS NULL
                   ORDER BY time_in DESC LIMIT 1""",
                (society_id, user_id),
                fetch_one=True
            )
            
            if not on_duty:
                return False, "Not on duty", None
            return True, "On duty", datetime.now() + timedelta(hours=12)
        
        return False, "Unknown role", None
        
    except Exception as e:
        print(f"Validity check error: {e}")
        return False, f"Error: {str(e)[:50]}", None


def generate_qr_code_with_validity(user_id: int, role: str, society_id: int):
    """
    Generate QR code with embedded validity timestamp.
    
    Payload format: user_id|role_code|society_id|issued_at|valid_until
    Example: 42|O|1|2025-05-05T14:30:00|2025-06-05T14:30:00
    """
    try:
        is_valid, reason, expiry = _calculate_validity(user_id, role, society_id)
        
        if not is_valid:
            return None, f"Cannot generate QR: {reason}"
        
        role_code = ROLE_CODE_MAP_REV.get(role, "V")
        issued_at = datetime.now().isoformat()
        valid_until = expiry.isoformat() if expiry else ""
        
        qr_payload = f"{user_id}|{role_code}|{society_id or 0}|{issued_at}|{valid_until}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
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


def validate_qr_local(qr_payload: str) -> dict:
    """
    Client-side validation using embedded QR data (no DB query).
    Returns status with 'local_validation' flag.
    """
    try:
        parts = qr_payload.strip().split("|")
        
        if len(parts) < 5:
            return {"status": "FAIL", "reason": "Invalid QR format"}
        
        user_id, role_code, society_id, issued_at, valid_until = parts[:5]
        role = ROLE_CODE_MAP.get(role_code, "unknown")
        
        # Check expiry
        if valid_until:
            expiry = datetime.fromisoformat(valid_until)
            if datetime.now() > expiry:
                return {
                    "status": "FAIL",
                    "reason": f"QR expired on {expiry.strftime('%Y-%m-%d')}",
                }
        
        # Check issued time (reject if > 1 year old as safety)
        if issued_at:
            issued = datetime.fromisoformat(issued_at)
            if datetime.now() - issued > timedelta(days=365):
                return {"status": "FAIL", "reason": "QR too old, regenerate"}
        
        return {
            "status": "PASS",
            "local_validation": True,
            "user": {
                "id": int(user_id),
                "role": role,
                "society_id": int(society_id),
            },
            "valid_until": valid_until,
        }
        
    except Exception as e:
        return {"status": "FAIL", "reason": f"Parse error: {str(e)[:30]}"}


def validate_qr_code(qr_data: str, society_id: int = None) -> dict:
    """
    Full server-side validation with DB checks.
    First tries local validation, then verifies against DB.
    """
    # Try local validation first
    local_result = validate_qr_local(qr_data)
    
    if local_result.get("status") != "PASS":
        return local_result
    
    # Extract user info
    user_id = local_result["user"]["id"]
    role = local_result["user"]["role"]
    qr_society_id = local_result["user"]["society_id"]
    
    # Verify society match
    if society_id and qr_society_id != society_id:
        return {"status": "FAIL", "reason": "QR not valid for this society"}
    
    # Load full user from DB
    try:
        user_row = db.execute_query(
            """SELECT u.id, u.email, u.role, u.society_id,
                      COALESCE(a.owner_name, u.email) AS name
               FROM users u
               LEFT JOIN apartments a ON u.linked_id = a.id
               WHERE u.id = %s AND u.society_id = %s""",
            (user_id, qr_society_id),
            fetch_one=True
        )
        
        if not user_row:
            return {"status": "FAIL", "reason": "User not found in database"}
        
        # Re-check live validity
        is_valid, reason, _ = _calculate_validity(user_id, role, qr_society_id)
        
        if not is_valid:
            return {
                "status": "FAIL",
                "reason": f"Server check failed: {reason}",
                "note": "QR was valid locally but failed live verification"
            }
        
        return {
            "status": "PASS",
            "server_validation": True,
            "user": {
                "id": user_row["id"],
                "name": user_row.get("name", "User"),
                "email": user_row.get("email"),
                "role": user_row["role"],
                "society_id": user_row["society_id"],
            },
            "message": "Access granted (verified with server)",
        }
        
    except Exception as e:
        print(f"Server validation error: {e}")
        # Fall back to local validation if DB fails
        return {
            **local_result,
            "note": "Validated locally (server check failed)",
        }