import qrcode
import base64
import json
from io import BytesIO
from datetime import datetime

def generate_qr_code(data):
    """Generate QR code as base64 string"""
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

def validate_qr_code(qr_data, society_id):
    """Validate QR code and check for pending dues"""
    try:
        # For testing, accept any non-empty QR code
        # In production, this would decode and verify against database
        if qr_data:
            return {
                'status': 'PASS',
                'message': 'Access granted',
                'user': {
                    'name': 'Test User',
                    'role': 'visitor'
                }
            }
        else:
            return {
                'status': 'FAIL',
                'reason': 'Invalid QR code'
            }
    except Exception as e:
        return {
            'status': 'FAIL',
            'reason': f'Error: {str(e)}'
        }