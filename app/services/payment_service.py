from database.db_manager import db
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def calculate_dues(apartment_id):
    """Calculate pending dues for an apartment"""
    try:
        # Get apartment
        apartment = db._execute(
            "SELECT id, apartment_size FROM apartments WHERE id = :id",
            {"id": apartment_id},
            fetch_one=True
        )
        if not apartment:
            return {'error': 'Apartment not found'}

        # Get maintenance rate (default ₹3 per sq ft)
        monthly_maintenance = apartment['apartment_size'] * 3.0

        # Get pending payments
        pending = db._execute("""
            SELECT id, amount, due_date, status FROM payments
            WHERE apartment_id = :apartment_id AND status = 'pending'
        """, {"apartment_id": apartment_id}, fetch_all=True)

        total_due = sum(float(p['amount']) for p in pending) if pending else 0

        # Calculate late fees
        late_fee = 0
        today = datetime.now().date()
        for payment in pending:
            if payment['due_date'] and payment['due_date'] < today:
                days_overdue = (today - payment['due_date']).days
                late_fee += days_overdue * 10  # Rs 10 per day late fee

        return {
            'monthly_maintenance': monthly_maintenance,
            'pending_count': len(pending) if pending else 0,
            'total_due': total_due,
            'late_fee': late_fee,
            'grand_total': total_due + late_fee
        }
    except Exception as e:
        logger.error(f"Error calculating dues for apartment {apartment_id}: {e}")
        return {'error': str(e)}

def process_payment(user_id, society_id, amount, payment_method='online'):
    """Process a payment"""
    try:
        # Create payment record
        result = db._execute("""
            INSERT INTO payments (society_id, user_id, amount, payment_method, status, paid_at, created_at)
            VALUES (:society_id, :user_id, :amount, :payment_method, :status, :paid_at, :created_at)
            RETURNING id
        """, {
            "society_id": society_id,
            "user_id": user_id,
            "amount": amount,
            "payment_method": payment_method,
            "status": "verified",
            "paid_at": datetime.now(),
            "created_at": datetime.now()
        }, fetch_one=True)

        if result:
            payment_id = result['id']
            return {
                'success': True,
                'payment_id': payment_id,
                'message': 'Payment processed successfully',
                'status': 'verified'
            }
        else:
            return {
                'success': False,
                'error': 'Failed to create payment record'
            }

    except Exception as e:
        logger.error(f"Error processing payment for user {user_id}: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def generate_monthly_maintenance(society_id):
    """Generate monthly maintenance charges for all apartments"""
    try:
        # Get all active apartments
        apartments = db._execute("""
            SELECT id, apartment_size FROM apartments
            WHERE society_id = :society_id AND active = TRUE
        """, {"society_id": society_id}, fetch_all=True)

        if not apartments:
            return 0

        due_date = datetime.now().replace(day=15)
        if due_date < datetime.now():
            due_date = due_date + timedelta(days=30)

        created = 0
        month_start = datetime.now().replace(day=1)

        for apartment in apartments:
            amount = apartment['apartment_size'] * 3.0  # ₹3 per sq ft

            # Check if already generated for this month
            existing = db._execute("""
                SELECT id FROM payments
                WHERE apartment_id = :apartment_id
                  AND payment_type = 'maintenance'
                  AND created_at >= :month_start
            """, {
                "apartment_id": apartment['id'],
                "month_start": month_start
            }, fetch_one=True)

            if not existing:
                db._execute("""
                    INSERT INTO payments (society_id, apartment_id, amount, payment_type, status, due_date, created_at)
                    VALUES (:society_id, :apartment_id, :amount, :payment_type, :status, :due_date, :created_at)
                """, {
                    "society_id": society_id,
                    "apartment_id": apartment['id'],
                    "amount": amount,
                    "payment_type": "maintenance",
                    "status": "pending",
                    "due_date": due_date,
                    "created_at": datetime.now()
                })
                created += 1

        return created

    except Exception as e:
        logger.error(f"Error generating monthly maintenance for society {society_id}: {e}")
        return 0
