import qrcode
import base64
import json
from io import BytesIO
from app.models.payment import Payment
from app.models.user import User
from datetime import datetime

def generate_qr_code(data):
    """Generate QR code as base64 string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

def validate_qr_code(qr_data, society_id):
    """Validate QR code and check for pending dues"""
    try:
        # Parse QR data (assuming it's JSON string)
        user_data = json.loads(qr_data.replace("'", '"'))
        user_id = user_data.get('user_id')
        
        if not user_id:
            return {'status': 'FAIL', 'reason': 'Invalid QR code'}
        
        user = User.query.get(user_id)
        if not user or user.society_id != society_id:
            return {'status': 'FAIL', 'reason': 'User not found'}
        
        # Check for pending dues
        pending_payments = Payment.query.filter(
            Payment.user_id == user_id,
            Payment.status == 'pending',
            Payment.due_date < datetime.now().date()
        ).count()
        
        if pending_payments > 0:
            return {
                'status': 'FAIL',
                'reason': f'Pending dues: {pending_payments} payments overdue',
                'user': {
                    'name': user.email,
                    'role': user.role
                }
            }
        
        # Record gate access
        from app.models.gate_access import GateAccess
        gate_entry = GateAccess(
            society_id=society_id,
            role=user.role[0] if user.role else 'u',
            entity_id=user.id
        )
        db.session.add(gate_entry)
        db.session.commit()
        
        return {
            'status': 'PASS',
            'message': 'Access granted',
            'user': {
                'name': user.email,
                'role': user.role,
                'time_in': datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        return {'status': 'FAIL', 'reason': f'Error: {str(e)}'}