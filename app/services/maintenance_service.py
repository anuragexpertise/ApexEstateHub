from app import db
from app.models.apartment import Apartment
from app.models.payment import Payment
from datetime import datetime, timedelta

def get_current_maintenance_rate(society_id):
    """Get current maintenance rate per sq ft for a society"""
    # This would come from society settings
    # Default rate of ₹3 per sq ft
    return 3.0

def calculate_monthly_maintenance(apartment_id):
    """Calculate monthly maintenance for an apartment"""
    apartment = Apartment.query.get(apartment_id)
    if not apartment:
        return 0
    
    rate = get_current_maintenance_rate(apartment.society_id)
    return apartment.apartment_size * rate

def generate_monthly_maintenance_charges(society_id):
    """Generate monthly maintenance charges for all apartments"""
    apartments = Apartment.query.filter_by(society_id=society_id, active=True).all()
    
    due_date = datetime.now().replace(day=15)
    if due_date < datetime.now():
        due_date = due_date + timedelta(days=30)
    
    created_count = 0
    for apartment in apartments:
        amount = calculate_monthly_maintenance(apartment.id)
        
        # Check if already generated for this month
        existing = Payment.query.filter(
            Payment.apartment_id == apartment.id,
            Payment.payment_type == 'maintenance',
            Payment.created_at >= datetime.now().replace(day=1)
        ).first()
        
        if not existing:
            payment = Payment(
                society_id=apartment.society_id,
                apartment_id=apartment.id,
                amount=amount,
                payment_type='maintenance',
                status='pending',
                due_date=due_date
            )
            db.session.add(payment)
            created_count += 1
    
    db.session.commit()
    return created_count

def calculate_late_fee(payment):
    """Calculate late fee for overdue payment"""
    if not payment.due_date or payment.status != 'pending':
        return 0
    
    days_overdue = (datetime.now().date() - payment.due_date).days
    if days_overdue <= 0:
        return 0
    
    # Late fee: 2% per month (0.0667% per day)
    daily_rate = 0.000667
    late_fee = float(payment.amount) * daily_rate * days_overdue
    
    # Cap at 20% of amount
    max_fee = float(payment.amount) * 0.2
    return min(late_fee, max_fee)

def apply_daily_fine(payment):
    """Apply daily fine for overdue payment"""
    if not payment.due_date or payment.status != 'pending':
        return 0
    
    days_overdue = (datetime.now().date() - payment.due_date).days
    if days_overdue <= 0:
        return 0
    
    # Daily fine: ₹10 per day
    daily_fine = 10 * days_overdue
    return daily_fine

def process_overdue_payments(society_id):
    """Process all overdue payments and apply fines"""
    overdue_payments = Payment.query.filter(
        Payment.society_id == society_id,
        Payment.status == 'pending',
        Payment.due_date < datetime.now().date()
    ).all()
    
    processed = 0
    for payment in overdue_payments:
        late_fee = calculate_late_fee(payment)
        daily_fine = apply_daily_fine(payment)
        
        if late_fee > 0 or daily_fine > 0:
            # Create fine payment record
            fine_payment = Payment(
                society_id=society_id,
                apartment_id=payment.apartment_id,
                user_id=payment.user_id,
                amount=late_fee + daily_fine,
                payment_type='late_fee',
                status='pending',
                due_date=datetime.now().date() + timedelta(days=7)
            )
            db.session.add(fine_payment)
            processed += 1
    
    db.session.commit()
    return processed