# app/services/settings_service.py
"""
Settings & Financial Management Service
========================================
Manages the new 4-table financial system:
- receivables (auto Cr - charges to collect)
- receipts (manual Cr - income entries)
- payments (auto Dr - payables)
- expenses (manual Dr - expense entries)
"""

from database.db_manager import db
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# RECEIVABLES - Auto-calculated Credits (Charges to Collect)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_apartment_receivables(society_id: int, apartment_id: int) -> dict:
    """
    Calculate pending receivables for an apartment based on apt_charges_fines.
    
    Returns:
        {
            'maintenance': float,
            'fine': float,
            'late_fee': float,
            'total': float,
            'charges_config': dict
        }
    """
    try:
        # Get apartment details
        apt = db._execute(
            "SELECT id, apartment_size FROM apartments WHERE id=%s AND society_id=%s",
            (apartment_id, society_id),
            fetch_one=True
        )
        if not apt:
            return {'error': 'Apartment not found'}
        
        # Get active charge configuration
        charges = db._execute(
            """
            SELECT * FROM apt_charges_fines 
            WHERE society_id=%s AND apt_id=%s AND apt_status=TRUE
            AND (end_date IS NULL OR end_date >= CURRENT_DATE)
            ORDER BY start_date DESC LIMIT 1
            """,
            (society_id, apartment_id),
            fetch_one=True
        )
        
        if not charges:
            return {
                'maintenance': 0,
                'fine': 0,
                'late_fee': 0,
                'total': 0,
                'charges_config': None
            }
        
        # Calculate maintenance
        maintenance = float(apt['apartment_size']) * float(charges.get('apt_maintenance_rate', 0))
        
        # Get static fine
        fine = float(charges.get('apt_fine', 0))
        
        # Calculate late fee
        due_day = charges.get('apt_due_day', 15)
        today = date.today()
        due_date = date(today.year, today.month, due_day)
        
        late_fee = 0
        if today > due_date:
            days_late = (today - due_date).days
            late_fee = days_late * float(charges.get('apt_delay_fine', 0))
        
        total = maintenance + fine + late_fee
        
        return {
            'maintenance': maintenance,
            'fine': fine,
            'late_fee': late_fee,
            'total': total,
            'charges_config': charges
        }
    
    except Exception as e:
        logger.error(f"Error calculating apartment receivables: {e}")
        return {'error': str(e)}


def generate_monthly_receivables(society_id: int) -> int:
    """
    Generate monthly maintenance receivables for all apartments.
    Creates records in receivables table with status='pending'.
    
    Returns:
        Number of receivables created
    """
    try:
        # Get all active apartments
        apartments = db._execute(
            "SELECT id, apartment_size FROM apartments WHERE society_id=%s AND active=TRUE",
            (society_id,),
            fetch_all=True
        ) or []
        
        created_count = 0
        current_month = date.today().replace(day=1)
        
        for apt in apartments:
            # Check if receivable already exists for this month
            existing = db._execute(
                """
                SELECT id FROM receivables 
                WHERE society_id=%s AND entity_id=%s AND entity_type='apartment'
                AND charge_type='maintenance' AND created_at >= %s
                """,
                (society_id, apt['id'], current_month),
                fetch_one=True
            )
            
            if existing:
                continue
            
            # Calculate receivable
            calc = calculate_apartment_receivables(society_id, apt['id'])
            if calc.get('error') or calc['total'] == 0:
                continue
            
            charges = calc['charges_config']
            due_day = charges.get('apt_due_day', 15)
            due_date = date.today().replace(day=due_day)
            
            # Create receivable
            db._execute(
                """
                INSERT INTO receivables (
                    society_id, entity_id, entity_type, charge_type,
                    description, amount, due_date, status,
                    source_table, source_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    society_id, apt['id'], 'apartment', 'maintenance',
                    'Monthly maintenance charge',
                    calc['maintenance'], due_date, 'pending',
                    'apt_charges_fines', charges['id']
                )
            )
            created_count += 1
        
        return created_count
    
    except Exception as e:
        logger.error(f"Error generating monthly receivables: {e}")
        return 0


def confirm_receivable(receivable_id: int, confirmed_by_user_id: int, society_id: int) -> tuple:
    """
    Confirm a receivable and add it to transactions table.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Get receivable
        rec = db._execute(
            "SELECT * FROM receivables WHERE id=%s AND society_id=%s",
            (receivable_id, society_id),
            fetch_one=True
        )
        
        if not rec:
            return False, "Receivable not found"
        
        if rec['status'] != 'pending':
            return False, f"Receivable already {rec['status']}"
        
        # Update receivable status
        db._execute(
            """
            UPDATE receivables 
            SET status='confirmed', confirmed_by=%s, confirmed_at=NOW()
            WHERE id=%s
            """,
            (confirmed_by_user_id, receivable_id)
        )
        
        # Add to transactions table
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id,
                acc_particulars, amount, mode, status, created_by
            ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, 'system', 'paid', %s)
            """,
            (
                society_id,
                _get_account_id_for_charge_type(society_id, rec['charge_type']),
                rec['entity_id'],
                f"{rec['charge_type']} - {rec['description']}",
                rec['amount'],
                confirmed_by_user_id
            )
        )
        
        return True, f"Receivable of ₹{rec['amount']:,.2f} confirmed"
    
    except Exception as e:
        logger.error(f"Error confirming receivable: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# RECEIPTS - Manual Credit Entries
# ══════════════════════════════════════════════════════════════════════════════

def create_receipt(data: dict, created_by_user_id: int, society_id: int) -> tuple:
    """
    Create a manual receipt entry (status='pending', needs admin confirmation).
    
    Args:
        data: {
            'receipt_date': date,
            'acc_id': int,
            'particulars': str,
            'amount': float,
            'mode': str,
            'entity_id': int (optional),
            'entity_type': str (optional),
            'cheque_no': str (optional),
        }
    
    Returns:
        (success: bool, message: str, receipt_id: int)
    """
    try:
        result = db._execute(
            """
            INSERT INTO receipts (
                society_id, user_id, entity_id, entity_type,
                receipt_date, acc_id, particulars, amount,
                mode, cheque_no, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
            RETURNING id
            """,
            (
                society_id, created_by_user_id,
                data.get('entity_id'), data.get('entity_type'),
                data.get('receipt_date', date.today()),
                data['acc_id'], data['particulars'], data['amount'],
                data.get('mode', 'cash'), data.get('cheque_no')
            ),
            fetch_one=True
        )
        
        return True, "Receipt created (pending admin confirmation)", result['id']
    
    except Exception as e:
        logger.error(f"Error creating receipt: {e}")
        return False, str(e), 0


def confirm_receipt(receipt_id: int, confirmed_by_user_id: int, society_id: int) -> tuple:
    """
    Confirm a receipt (admin only) and add to transactions.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Verify confirmer is admin
        user = db._execute(
            "SELECT role FROM users WHERE id=%s AND society_id=%s",
            (confirmed_by_user_id, society_id),
            fetch_one=True
        )
        
        if not user or user['role'] != 'admin':
            return False, "Only admin can confirm receipts"
        
        # Get receipt
        receipt = db._execute(
            "SELECT * FROM receipts WHERE id=%s AND society_id=%s",
            (receipt_id, society_id),
            fetch_one=True
        )
        
        if not receipt:
            return False, "Receipt not found"
        
        if receipt['status'] != 'pending':
            return False, f"Receipt already {receipt['status']}"
        
        # Update receipt status
        db._execute(
            """
            UPDATE receipts 
            SET status='confirmed', confirmed_by=%s, confirmed_at=NOW()
            WHERE id=%s
            """,
            (confirmed_by_user_id, receipt_id)
        )
        
        # Add to transactions
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id,
                acc_particulars, amount, mode, status, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'paid', %s)
            """,
            (
                society_id, receipt['receipt_date'], receipt['acc_id'],
                receipt['entity_id'], receipt['particulars'],
                receipt['amount'], receipt['mode'], confirmed_by_user_id
            )
        )
        
        return True, f"Receipt of ₹{receipt['amount']:,.2f} confirmed"
    
    except Exception as e:
        logger.error(f"Error confirming receipt: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS - Auto-calculated Debits (Payables)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_security_payment(society_id: int, security_id: int) -> tuple:
    """
    Calculate pending payment for security staff based on attendance.
    
    Returns:
        (amount: float, days_worked: int, charge_config: dict)
    """
    try:
        # Get security staff details
        staff = db._execute(
            "SELECT * FROM security_staff WHERE id=%s AND society_id=%s",
            (security_id, society_id),
            fetch_one=True
        )
        
        if not staff:
            return 0, 0, None
        
        # Get current month attendance
        current_month = date.today().replace(day=1)
        
        attendance = db._execute(
            """
            SELECT COUNT(*) as days_worked FROM attendance
            WHERE society_id=%s AND security_id=%s AND time_in >= %s
            """,
            (society_id, security_id, current_month),
            fetch_one=True
        )
        
        days_worked = attendance.get('days_worked', 0) if attendance else 0
        salary_per_shift = float(staff.get('salary_per_shift', 0))
        amount = days_worked * salary_per_shift
        
        # Get active charge config
        charges = db._execute(
            """
            SELECT * FROM security_charges_fines
            WHERE society_id=%s AND sec_id=%s AND sec_status=TRUE
            ORDER BY start_date DESC LIMIT 1
            """,
            (society_id, security_id),
            fetch_one=True
        )
        
        # Subtract fines if any
        if charges:
            fine = float(charges.get('security_fine', 0))
            amount -= fine
        
        return amount, days_worked, charges
    
    except Exception as e:
        logger.error(f"Error calculating security payment: {e}")
        return 0, 0, None


def generate_monthly_payments(society_id: int) -> int:
    """
    Generate monthly salary payments for all security staff.
    
    Returns:
        Number of payments created
    """
    try:
        # Get all active security staff
        staff_list = db._execute(
            "SELECT id FROM security_staff WHERE society_id=%s AND active=TRUE",
            (society_id,),
            fetch_all=True
        ) or []
        
        created_count = 0
        current_month = date.today().replace(day=1)
        
        for staff in staff_list:
            # Check if payment already exists
            existing = db._execute(
                """
                SELECT id FROM payments 
                WHERE society_id=%s AND entity_id=%s AND entity_type='security'
                AND payment_type='salary' AND created_at >= %s
                """,
                (society_id, staff['id'], current_month),
                fetch_one=True
            )
            
            if existing:
                continue
            
            # Calculate payment
            amount, days, charges = calculate_security_payment(society_id, staff['id'])
            if amount <= 0:
                continue
            
            # Create payment
            db._execute(
                """
                INSERT INTO payments (
                    society_id, entity_id, entity_type, amount,
                    payment_type, status, due_date,
                    source_table, source_id, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    society_id, staff['id'], 'security', amount,
                    'salary', 'pending', date.today().replace(day=25),
                    'security_charges_fines', charges['id'] if charges else None
                )
            )
            created_count += 1
        
        return created_count
    
    except Exception as e:
        logger.error(f"Error generating monthly payments: {e}")
        return 0


def confirm_payment(payment_id: int, confirmed_by_user_id: int, society_id: int) -> tuple:
    """
    Confirm a payment and add to transactions.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Get payment
        payment = db._execute(
            "SELECT * FROM payments WHERE id=%s AND society_id=%s",
            (payment_id, society_id),
            fetch_one=True
        )
        
        if not payment:
            return False, "Payment not found"
        
        if payment['status'] not in ('pending', 'verified'):
            return False, f"Payment already {payment['status']}"
        
        # Update payment status
        db._execute(
            """
            UPDATE payments 
            SET status='confirmed', confirmed_by=%s, confirmed_at=NOW()
            WHERE id=%s
            """,
            (confirmed_by_user_id, payment_id)
        )
        
        # Add to transactions (debit)
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id,
                acc_particulars, amount, mode, status, created_by
            ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, 'bank', 'paid', %s)
            """,
            (
                society_id,
                _get_account_id_for_charge_type(society_id, payment.get('payment_type', 'salary')),
                payment['entity_id'],
                f"{payment.get('payment_type', 'payment')} payment",
                payment['amount'],
                confirmed_by_user_id
            )
        )
        
        return True, f"Payment of ₹{payment['amount']:,.2f} confirmed"
    
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSES - Manual Debit Entries
# ══════════════════════════════════════════════════════════════════════════════

def create_expense(data: dict, created_by_user_id: int, society_id: int) -> tuple:
    """
    Create a manual expense entry (status='pending', needs admin confirmation).
    
    Returns:
        (success: bool, message: str, expense_id: int)
    """
    try:
        result = db._execute(
            """
            INSERT INTO expenses (
                society_id, user_id, entity_id, entity_type,
                expense_date, acc_id, particulars, amount,
                mode, cheque_no, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
            RETURNING id
            """,
            (
                society_id, created_by_user_id,
                data.get('entity_id'), data.get('entity_type'),
                data.get('expense_date', date.today()),
                data['acc_id'], data['particulars'], data['amount'],
                data.get('mode', 'cash'), data.get('cheque_no')
            ),
            fetch_one=True
        )
        
        return True, "Expense created (pending admin confirmation)", result['id']
    
    except Exception as e:
        logger.error(f"Error creating expense: {e}")
        return False, str(e), 0


def confirm_expense(expense_id: int, confirmed_by_user_id: int, society_id: int) -> tuple:
    """
    Confirm an expense (admin only) and add to transactions.
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Verify confirmer is admin
        user = db._execute(
            "SELECT role FROM users WHERE id=%s AND society_id=%s",
            (confirmed_by_user_id, society_id),
            fetch_one=True
        )
        
        if not user or user['role'] != 'admin':
            return False, "Only admin can confirm expenses"
        
        # Get expense
        expense = db._execute(
            "SELECT * FROM expenses WHERE id=%s AND society_id=%s",
            (expense_id, society_id),
            fetch_one=True
        )
        
        if not expense:
            return False, "Expense not found"
        
        if expense['status'] != 'pending':
            return False, f"Expense already {expense['status']}"
        
        # Update expense status
        db._execute(
            """
            UPDATE expenses 
            SET status='confirmed', confirmed_by=%s, confirmed_at=NOW()
            WHERE id=%s
            """,
            (confirmed_by_user_id, expense_id)
        )
        
        # Add to transactions
        db._execute(
            """
            INSERT INTO transactions (
                society_id, trx_date, acc_id, entity_id,
                acc_particulars, amount, mode, status, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'paid', %s)
            """,
            (
                society_id, expense['expense_date'], expense['acc_id'],
                expense['entity_id'], expense['particulars'],
                expense['amount'], expense['mode'], confirmed_by_user_id
            )
        )
        
        return True, f"Expense of ₹{expense['amount']:,.2f} confirmed"
    
    except Exception as e:
        logger.error(f"Error confirming expense: {e}")
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def _get_account_id_for_charge_type(society_id: int, charge_type: str) -> int:
    """Get the appropriate account ID for a charge type."""
    account_map = {
        'maintenance': 'Maintenance',
        'fine': 'Fine',
        'late_fee': 'Late Fee',
        'salary': 'Salary',
        'pass_fee': 'Pass Fees',
    }
    
    account_name = account_map.get(charge_type, 'Miscellaneous')
    
    account = db._execute(
        "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE %s LIMIT 1",
        (society_id, f"%{account_name}%"),
        fetch_one=True
    )
    
    return account['id'] if account else 1  # Fallback to root account
