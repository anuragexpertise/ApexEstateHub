from database.db_manager import db
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_current_maintenance_rate(society_id):
    """Get current maintenance rate per sq ft for a society"""
    # This would come from society settings
    # Default rate of ₹3 per sq ft
    return 3.0

def calculate_monthly_maintenance(apartment_id):
    """Calculate monthly maintenance for an apartment"""
    try:
        apartment = db._execute(
            "SELECT apartment_size FROM apartments WHERE id = :id",
            {"id": apartment_id},
            fetch_one=True
        )
        if not apartment:
            return 0

        rate = get_current_maintenance_rate(None)  # Default rate
        return apartment['apartment_size'] * rate
    except Exception as e:
        logger.error(f"Error calculating maintenance for apartment {apartment_id}: {e}")
        return 0

def generate_monthly_maintenance_charges(society_id):
    """Generate monthly maintenance charges for all apartments"""
    try:
        apartments = db._execute("""
            SELECT id, apartment_size FROM apartments
            WHERE society_id = :society_id AND active = TRUE
        """, {"society_id": society_id}, fetch_all=True)

        if not apartments:
            return 0

        due_date = datetime.now().replace(day=15)
        if due_date < datetime.now():
            due_date = due_date + timedelta(days=30)

        created_count = 0
        month_start = datetime.now().replace(day=1)

        for apartment in apartments:
            amount = apartment['apartment_size'] * get_current_maintenance_rate(society_id)

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
                created_count += 1

        return created_count
    except Exception as e:
        logger.error(f"Error generating monthly maintenance charges for society {society_id}: {e}")
        return 0

def calculate_late_fee(payment_dict):
    """Calculate late fee for overdue payment"""
    try:
        due_date = payment_dict.get('due_date')
        status = payment_dict.get('status')
        amount = payment_dict.get('amount')

        if not due_date or status != 'pending':
            return 0

        days_overdue = (datetime.now().date() - due_date).days
        if days_overdue <= 0:
            return 0

        # Late fee: 2% per month (0.0667% per day)
        daily_rate = 0.000667
        late_fee = float(amount) * daily_rate * days_overdue

        # Cap at 20% of amount
        max_fee = float(amount) * 0.2
        return min(late_fee, max_fee)
    except Exception as e:
        logger.error(f"Error calculating late fee: {e}")
        return 0

def apply_daily_fine(payment_dict):
    """Apply daily fine for overdue payment"""
    try:
        due_date = payment_dict.get('due_date')
        status = payment_dict.get('status')

        if not due_date or status != 'pending':
            return 0

        days_overdue = (datetime.now().date() - due_date).days
        if days_overdue <= 0:
            return 0

        # Daily fine: ₹10 per day
        daily_fine = 10 * days_overdue
        return daily_fine
    except Exception as e:
        logger.error(f"Error applying daily fine: {e}")
        return 0

def process_overdue_payments(society_id):
    """Process all overdue payments and apply fines"""
    try:
        overdue_payments = db._execute("""
            SELECT id, apartment_id, user_id, amount, due_date, status FROM payments
            WHERE society_id = :society_id
              AND status = 'pending'
              AND due_date < :today
        """, {
            "society_id": society_id,
            "today": datetime.now().date()
        }, fetch_all=True)

        if not overdue_payments:
            return 0

        processed = 0
        for payment in overdue_payments:
            late_fee = calculate_late_fee(payment)
            daily_fine = apply_daily_fine(payment)

            if late_fee > 0 or daily_fine > 0:
                # Create fine payment record
                db._execute("""
                    INSERT INTO payments (society_id, apartment_id, user_id, amount, payment_type, status, due_date, created_at)
                    VALUES (:society_id, :apartment_id, :user_id, :amount, :payment_type, :status, :due_date, :created_at)
                """, {
                    "society_id": society_id,
                    "apartment_id": payment['apartment_id'],
                    "user_id": payment['user_id'],
                    "amount": late_fee + daily_fine,
                    "payment_type": "late_fee",
                    "status": "pending",
                    "due_date": datetime.now().date() + timedelta(days=7),
                    "created_at": datetime.now()
                })
                processed += 1

        return processed
    except Exception as e:
        logger.error(f"Error processing overdue payments for society {society_id}: {e}")
        return 0
