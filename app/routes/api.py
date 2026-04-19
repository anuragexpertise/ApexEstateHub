from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.auth.jwt_handler import token_required, role_required
from app.models.user import User
from app.models.payment import Payment
from app.models.apartment import Apartment
from app.services.qr_service import generate_qr_code, validate_qr_code
from app.services.payment_service import process_payment, calculate_dues
from app.services.push_service import send_push_notification
import csv
import io

api_bp = Blueprint('api', __name__)

# JWT Protected Routes (for API clients)
@api_bp.route('/user/qr-code', methods=['GET'])
@token_required
def get_qr_code_api():
    """Generate QR code for user (JWT protected)"""
    user_id = request.user_payload.get('user_id')
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    qr_data = {
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'society_id': user.society_id
    }
    qr_base64 = generate_qr_code(str(qr_data))
    return jsonify({'qr_code': qr_base64})

@api_bp.route('/validate-qr', methods=['POST'])
@token_required
def validate_qr_api():
    """Validate QR code for gate access (JWT protected)"""
    data = request.get_json()
    qr_data = data.get('qr_data')
    society_id = request.user_payload.get('society_id')
    
    if not qr_data:
        return jsonify({'error': 'No QR data provided'}), 400
    
    result = validate_qr_code(qr_data, society_id)
    
    # Send push notification on gate access
    if result.get('user'):
        user = User.query.filter_by(email=result['user']['name']).first()
        if user:
            send_push_notification(user.id, "Gate Access", f"Access {result['status']} at gate")
    
    return jsonify(result)

@api_bp.route('/payments/calculate', methods=['GET'])
@role_required(['apartment', 'admin'])
def calculate_payments_api():
    """Calculate pending payments (JWT protected with role check)"""
    user_id = request.user_payload.get('user_id')
    user = User.query.get(user_id)
    
    if user.role == 'apartment':
        apartment = Apartment.query.filter_by(
            society_id=user.society_id,
            owner_name=user.email.split('@')[0]
        ).first()
        
        if apartment:
            dues = calculate_dues(apartment.id)
            return jsonify(dues)
    
    return jsonify({'error': 'No apartment found'}), 404

@api_bp.route('/payments/process', methods=['POST'])
@role_required(['apartment', 'admin'])
def process_payment_api():
    """Process a payment (JWT protected with role check)"""
    data = request.get_json()
    amount = data.get('amount')
    payment_method = data.get('payment_method')
    user_id = request.user_payload.get('user_id')
    society_id = request.user_payload.get('society_id')
    
    if not amount:
        return jsonify({'error': 'Amount required'}), 400
    
    result = process_payment(
        user_id=user_id,
        society_id=society_id,
        amount=amount,
        payment_method=payment_method
    )
    
    if result.get('success'):
        # Send push notification on successful payment
        send_push_notification(user_id, "Payment Received", f"Payment of ₹{amount} processed successfully")
    
    return jsonify(result)

# Session-based routes (for Dash app)
@api_bp.route('/user/qr-code-session', methods=['GET'])
@login_required
def get_qr_code_session():
    """Generate QR code for current user (session-based)"""
    qr_data = {
        'user_id': current_user.id,
        'email': current_user.email,
        'role': current_user.role,
        'society_id': current_user.society_id
    }
    qr_base64 = generate_qr_code(str(qr_data))
    return jsonify({'qr_code': qr_base64})

@api_bp.route('/attendance/clock-in', methods=['POST'])
@login_required
def clock_in():
    """Record attendance clock in"""
    from app.models.gate_access import GateAccess
    
    gate_entry = GateAccess(
        society_id=current_user.society_id,
        role=current_user.role[0] if current_user.role else 's',
        entity_id=current_user.id
    )
    db.session.add(gate_entry)
    db.session.commit()
    
    send_push_notification(current_user.id, "Attendance", "Clocked in successfully")
    
    return jsonify({'success': True, 'message': 'Clocked in successfully'})

@api_bp.route('/attendance/clock-out', methods=['POST'])
@login_required
def clock_out():
    """Record attendance clock out"""
    from app.models.gate_access import GateAccess
    
    gate_entry = GateAccess.query.filter_by(
        society_id=current_user.society_id,
        entity_id=current_user.id,
        time_out=None
    ).first()
    
    if gate_entry:
        gate_entry.check_out()
        db.session.commit()
        send_push_notification(current_user.id, "Attendance", "Clocked out successfully")
        return jsonify({'success': True, 'message': 'Clocked out successfully'})
    
    return jsonify({'error': 'No active clock-in found'}), 404

@api_bp.route('/upload/csv', methods=['POST'])
@login_required
def upload_csv():
    """Upload CSV file for bulk data import"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be CSV'}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.reader(stream)
        
        results = []
        for row in csv_input:
            results.append(row)
        
        send_push_notification(current_user.id, "Upload Complete", f"CSV uploaded with {len(results)} rows")
        
        return jsonify({
            'success': True,
            'rows_processed': len(results),
            'message': 'CSV uploaded successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500