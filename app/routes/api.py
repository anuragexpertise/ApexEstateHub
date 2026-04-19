from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.payment import Payment
from app.models.apartment import Apartment
from app.services.qr_service import generate_qr_code, validate_qr_code
from app.services.payment_service import process_payment, calculate_dues
import csv
import io
import base64

api_bp = Blueprint('api', __name__)

@api_bp.route('/user/qr-code')
@login_required
def get_qr_code():
    """Generate QR code for current user"""
    qr_data = {
        'user_id': current_user.id,
        'email': current_user.email,
        'role': current_user.role,
        'society_id': current_user.society_id
    }
    qr_base64 = generate_qr_code(str(qr_data))
    return jsonify({'qr_code': qr_base64})

@api_bp.route('/validate-qr', methods=['POST'])
@login_required
def validate_qr():
    """Validate QR code for gate access"""
    data = request.get_json()
    qr_data = data.get('qr_data')
    
    if not qr_data:
        return jsonify({'error': 'No QR data provided'}), 400
    
    result = validate_qr_code(qr_data, current_user.society_id)
    return jsonify(result)

@api_bp.route('/payments/calculate', methods=['GET'])
@login_required
def calculate_payments():
    """Calculate pending payments for user"""
    if current_user.role == 'apartment':
        apartment = Apartment.query.filter_by(
            society_id=current_user.society_id,
            owner_name=current_user.email.split('@')[0]
        ).first()
        
        if apartment:
            dues = calculate_dues(apartment.id)
            return jsonify(dues)
    
    return jsonify({'error': 'No apartment found'}), 404

@api_bp.route('/payments/process', methods=['POST'])
@login_required
def process_payment_api():
    """Process a payment"""
    data = request.get_json()
    amount = data.get('amount')
    payment_method = data.get('payment_method')
    
    if not amount:
        return jsonify({'error': 'Amount required'}), 400
    
    result = process_payment(
        user_id=current_user.id,
        society_id=current_user.society_id,
        amount=amount,
        payment_method=payment_method
    )
    
    return jsonify(result)

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
            # Process each row
            results.append(row)
        
        return jsonify({
            'success': True,
            'rows_processed': len(results),
            'message': 'CSV uploaded successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500