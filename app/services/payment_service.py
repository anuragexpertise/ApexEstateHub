from app import db
from app.models.payment import Payment
from app.models.transaction import Transaction
from app.models.apartment import Apartment
from datetime import datetime, timedelta

def calculate_dues(apartment_id):
    """Calculate pending dues for an apartment"""
    apartment = Apartment.query.get(apartment_id)
    if not apartment:
        return {'error': 'Apartment not found'}
    
    monthly_maintenance = apartment.monthly_maintenance
    
    # Get pending payments
    pending = Payment.query.filter(
        Payment.apartment_id == apartment_id,
        Payment.status == 'pending'
    ).all()
    
    total_due = sum(float(p.amount) for p in pending)
    
    # Calculate late fees
    late_fee = 0
    for payment in pending:
        if payment.due_date and payment.due_date < datetime.now().date():
            days_overdue = (datetime.now().date() - payment.due_date).days
            late_fee += days_overdue * 10  # Rs 10 per day late fee
    
    return {
        'monthly_maintenance': monthly_maintenance,
        'pending_count': len(pending),
        'total_due': total_due,
        'late_fee': late_fee,
        'grand_total': total_due + late_fee
    }

def process_payment(user_id, society_id, amount, payment_method='online'):
    """Process a payment"""
    try:
        # Create payment record
        payment = Payment(
            society_id=society_id,
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            status='pending',
            paid_at=datetime.now()
        )
        db.session.add(payment)
        db.session.commit()
        
        # In production, integrate with payment gateway here
        # For now, auto-verify
        
        # Verify payment
        payment.verify()
        db.session.commit()
        
        return {
            'success': True,
            'payment_id': payment.id,
            'message': 'Payment processed successfully',
            'status': 'verified'
        }
        
    except Exception as e:
        db.session.rollback()
        return {
            'success': False,
            'error': str(e)
        }

def generate_monthly_maintenance(society_id):
    """Generate monthly maintenance charges for all apartments"""
    apartments = Apartment.query.filter_by(society_id=society_id, active=True).all()
    
    due_date = datetime.now().replace(day=15)  # Due on 15th of each month
    if due_date < datetime.now():
        due_date = due_date + timedelta(days=30)
    
    created = 0
    for apartment in apartments:
        amount = apartment.monthly_maintenance
        
        # Check if already generated for this month
        existing = Payment.query.filter(
            Payment.apartment_id == apartment.id,
            Payment.payment_type == 'maintenance',
            Payment.created_at >= datetime.now().replace(day=1)
        ).first()
        
        if not existing:
            payment = Payment(
                society_id=society_id,
                apartment_id=apartment.id,
                amount=amount,
                payment_type='maintenance',
                status='pending',
                due_date=due_date
            )
            db.session.add(payment)
            created += 1
    
    db.session.commit()
    return created