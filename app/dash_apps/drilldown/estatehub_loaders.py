# app/loaders/thin_loaders.py
"""
Thin Loader Layer
Calls SQL functions and maps results to Python models
Replaces old loaders.py with direct SQL function calls
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, date
from decimal import Decimal

# ═════════════════════════════════════════════════════════════════════════════
# APARTMENTS LOADER
# ═════════════════════════════════════════════════════════════════════════════

class ApartmentLoader:
    """Load apartment data from SQL functions"""
    
    @staticmethod
    def list_apartments(db, society_id: int, search: str = None, 
                       has_dues: bool = None, page: int = 1, 
                       page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load apartment list with pagination
        Uses: fn_apartments_list(society_id, search, has_dues)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_apartments_list(%s, %s, %s)""",
            (society_id, search, has_dues), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_apartments_list(%s, %s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, has_dues, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def get_apartment_profile(db, apartment_id: int) -> Optional[Dict]:
        """Get apartment profile with full maintenance breakdown"""
        return db._execute(
            """SELECT * FROM apartments WHERE id=%s""",
            (apartment_id,), fetch_one=True
        )
    
    @staticmethod
    def create_apartment(db, society_id: int, flat_number: str, 
                        owner_name: str = None, mobile: str = None,
                        apartment_size: int = 0) -> Optional[int]:
        """Create new apartment"""
        result = db._execute(
            """INSERT INTO apartments 
               (society_id, flat_number, owner_name, mobile, apartment_size)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (society_id, flat_number, owner_name, mobile, apartment_size),
            fetch_one=True
        )
        return result['id'] if result else None
    
    @staticmethod
    def update_apartment(db, apartment_id: int, **kwargs) -> bool:
        """Update apartment"""
        fields = []
        values = []
        for key, val in kwargs.items():
            if key in ['flat_number', 'owner_name', 'mobile', 'apartment_size', 'active']:
                fields.append(f"{key}=%s")
                values.append(val)
        
        if not fields:
            return False
        
        values.append(apartment_id)
        db._execute(
            f"UPDATE apartments SET {', '.join(fields)} WHERE id=%s",
            tuple(values)
        )
        return True
    
    @staticmethod
    def delete_apartment(db, apartment_id: int) -> bool:
        """Delete apartment"""
        db._execute("DELETE FROM apartments WHERE id=%s", (apartment_id,))
        return True

# ═════════════════════════════════════════════════════════════════════════════
# VENDORS LOADER
# ═════════════════════════════════════════════════════════════════════════════

class VendorLoader:
    """Load vendor data from SQL functions"""
    
    @staticmethod
    def list_vendors(db, society_id: int, search: str = None, 
                    page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load vendor list with pagination
        Uses: fn_vendors_list(society_id, search)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_vendors_list(%s, %s)""",
            (society_id, search), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_vendors_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def get_vendor_profile(db, vendor_id: int) -> Optional[Dict]:
        """Get vendor profile"""
        return db._execute(
            """SELECT u.*, v.name, v.service_type, v.service_description,
                      v.mobile, v.active
               FROM users u
               LEFT JOIN vendors v ON v.id = u.linked_id
               WHERE u.id=%s""",
            (vendor_id,), fetch_one=True
        )
    
    @staticmethod
    def create_vendor(db, society_id: int, name: str, service_type: str = None,
                     mobile: str = None) -> Optional[int]:
        """Create new vendor"""
        result = db._execute(
            """INSERT INTO vendors (society_id, name, service_type, mobile)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (society_id, name, service_type, mobile), fetch_one=True
        )
        return result['id'] if result else None
    
    @staticmethod
    def update_vendor(db, vendor_id: int, **kwargs) -> bool:
        """Update vendor"""
        fields = []
        values = []
        for key, val in kwargs.items():
            if key in ['name', 'service_type', 'mobile', 'active']:
                fields.append(f"{key}=%s")
                values.append(val)
        
        if not fields:
            return False
        
        values.append(vendor_id)
        db._execute(
            f"UPDATE vendors SET {', '.join(fields)} WHERE id=%s",
            tuple(values)
        )
        return True

# ═════════════════════════════════════════════════════════════════════════════
# SECURITY LOADER
# ═════════════════════════════════════════════════════════════════════════════

class SecurityLoader:
    """Load security data from SQL functions"""
    
    @staticmethod
    def list_security(db, society_id: int, search: str = None,
                     page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load security list with pagination
        Uses: fn_security_list(society_id, search)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_security_list(%s, %s)""",
            (society_id, search), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_security_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def get_security_profile(db, security_id: int) -> Optional[Dict]:
        """Get security staff profile"""
        return db._execute(
            """SELECT u.*, s.name, s.shift, s.mobile, s.joining_date,
                      s.salary_per_shift, s.active
               FROM users u
               LEFT JOIN security_staff s ON s.id = u.linked_id
               WHERE u.id=%s""",
            (security_id,), fetch_one=True
        )
    
    @staticmethod
    def create_security(db, society_id: int, name: str, mobile: str = None,
                       shift: str = None, salary_per_shift: float = 0) -> Optional[int]:
        """Create new security staff"""
        result = db._execute(
            """INSERT INTO security_staff 
               (society_id, name, mobile, shift, salary_per_shift)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (society_id, name, mobile, shift, salary_per_shift), fetch_one=True
        )
        return result['id'] if result else None

# ═════════════════════════════════════════════════════════════════════════════
# PAYMENTS & RECEIVABLES LOADER
# ═════════════════════════════════════════════════════════════════════════════

class PaymentLoader:
    """Load payment and receivable data"""
    
    @staticmethod
    def get_pending_receivables(db, society_id: int, 
                               entity_type: str = None) -> List[Dict]:
        """Get pending receivables"""
        query = "SELECT * FROM receivables WHERE society_id=%s AND status='pending'"
        params = [society_id]
        
        if entity_type:
            query += " AND entity_type=%s"
            params.append(entity_type)
        
        query += " ORDER BY due_date ASC"
        
        return db._execute(query, tuple(params), fetch_all=True) or []
    
    @staticmethod
    def get_pending_payments(db, society_id: int, 
                            entity_type: str = None) -> List[Dict]:
        """Get pending payments"""
        query = "SELECT * FROM payments WHERE society_id=%s AND status='pending'"
        params = [society_id]
        
        if entity_type:
            query += " AND entity_type=%s"
            params.append(entity_type)
        
        query += " ORDER BY due_date ASC"
        
        return db._execute(query, tuple(params), fetch_all=True) or []
    
    @staticmethod
    def create_receivable(db, society_id: int, entity_id: int, 
                         entity_type: str, charge_type: str, 
                         amount: float, description: str = None,
                         due_date: date = None) -> Optional[int]:
        """Create receivable"""
        result = db._execute(
            """INSERT INTO receivables 
               (society_id, entity_id, entity_type, charge_type, amount, 
                description, due_date, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending') 
               RETURNING id""",
            (society_id, entity_id, entity_type, charge_type, amount, 
             description, due_date), fetch_one=True
        )
        return result['id'] if result else None
    
    @staticmethod
    def create_payment(db, society_id: int, entity_id: int, entity_type: str,
                      amount: float, payment_type: str = None,
                      payment_method: str = None) -> Optional[int]:
        """Create payment"""
        result = db._execute(
            """INSERT INTO payments 
               (society_id, entity_id, entity_type, amount, payment_type, 
                payment_method, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'pending') 
               RETURNING id""",
            (society_id, entity_id, entity_type, amount, payment_type, 
             payment_method), fetch_one=True
        )
        return result['id'] if result else None
    
    @staticmethod
    def verify_payment(db, payment_id: int, user_id: int) -> bool:
        """Verify payment - triggers auto receipt creation"""
        db._execute(
            """UPDATE payments SET status='verified', confirmed_by=%s, 
               confirmed_at=NOW() WHERE id=%s""",
            (user_id, payment_id)
        )
        # SQL trigger will auto-create receipt and process receivables
        return True

# ═════════════════════════════════════════════════════════════════════════════
# RECEIPTS & EXPENSES LOADER
# ═════════════════════════════════════════════════════════════════════════════

class ReceiptLoader:
    """Load receipts and expenses"""
    
    @staticmethod
    def create_receipt(db, society_id: int, acc_id: int, particulars: str,
                      amount: float, mode: str = 'cash', 
                      entity_id: int = None, entity_type: str = None,
                      user_id: int = None) -> Optional[int]:
        """Create receipt - directly creates transaction"""
        result = db._execute(
            """INSERT INTO receipts 
               (society_id, user_id, entity_id, entity_type, receipt_date, acc_id,
                particulars, amount, mode, status)
               VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, 'confirmed')
               RETURNING id""",
            (society_id, user_id, entity_id, entity_type, acc_id, 
             particulars, amount, mode), fetch_one=True
        )
        return result['id'] if result else None
    
    @staticmethod
    def create_expense(db, society_id: int, acc_id: int, particulars: str,
                      amount: float, mode: str = 'cash',
                      entity_id: int = None, entity_type: str = None,
                      user_id: int = None) -> Optional[int]:
        """Create expense - directly creates transaction"""
        result = db._execute(
            """INSERT INTO expenses 
               (society_id, user_id, entity_id, entity_type, expense_date, acc_id,
                particulars, amount, mode, status)
               VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, 'confirmed')
               RETURNING id""",
            (society_id, user_id, entity_id, entity_type, acc_id, 
             particulars, amount, mode), fetch_one=True
        )
        return result['id'] if result else None

# ═════════════════════════════════════════════════════════════════════════════
# ACCOUNTS LOADER
# ═════════════════════════════════════════════════════════════════════════════

class AccountLoader:
    """Load accounts data"""
    
    @staticmethod
    def list_accounts(db, society_id: int, search: str = None,
                     page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load accounts list
        Uses: fn_accounts_list(society_id, search)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_accounts_list(%s, %s)""",
            (society_id, search), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_accounts_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def get_account_balance(db, account_id: int) -> float:
        """Get current account balance"""
        result = db._execute(
            """SELECT COALESCE(SUM(
                    CASE WHEN drcr_account='Cr' THEN amount ELSE -amount END
                ), 0) + bf_amount AS balance
               FROM accounts a
               LEFT JOIN transactions t ON t.acc_id = a.id AND t.status='paid'
               WHERE a.id=%s""",
            (account_id,), fetch_one=True
        )
        return float(result['balance']) if result else 0.0

# ═════════════════════════════════════════════════════════════════════════════
# EVENTS & CONCERNS LOADER
# ═════════════════════════════════════════════════════════════════════════════

class EventLoader:
    """Load events data"""
    
    @staticmethod
    def list_events(db, society_id: int, search: str = None,
                   page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load events list
        Uses: fn_events_list(society_id, search)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_events_list(%s, %s)""",
            (society_id, search), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_events_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def create_event(db, society_id: int, title: str, event_date: date,
                    venue: str = None, description: str = None,
                    open_to: str = 'all') -> Optional[int]:
        """Create event"""
        result = db._execute(
            """INSERT INTO events 
               (society_id, title, event_date, venue, description, open_to)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (society_id, title, event_date, venue, description, open_to),
            fetch_one=True
        )
        return result['id'] if result else None

class ConcernLoader:
    """Load concerns data"""
    
    @staticmethod
    def list_concerns(db, society_id: int, search: str = None,
                     status: str = None, page: int = 1, 
                     page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load concerns list
        Uses: fn_concerns_list(society_id, search, status)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_concerns_list(%s, %s, %s)""",
            (society_id, search, status), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_concerns_list(%s, %s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, status, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def create_concern(db, society_id: int, flat_no: str, 
                      concern_type: str, description: str = None,
                      preferred_time: str = None) -> Optional[int]:
        """Create concern"""
        result = db._execute(
            """INSERT INTO concerns 
               (society_id, flat_no, concern_type, description, preferred_time)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (society_id, flat_no, concern_type, description, preferred_time),
            fetch_one=True
        )
        return result['id'] if result else None

# ═════════════════════════════════════════════════════════════════════════════
# CASHBOOK LOADER
# ═════════════════════════════════════════════════════════════════════════════

class CashbookLoader:
    """Load cashbook/transaction data"""
    
    @staticmethod
    def list_cashbook(db, society_id: int, search: str = None,
                     page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """Load cashbook with running balance"""
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM transactions 
               WHERE society_id=%s AND status='paid'""",
            (society_id,), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM vw_cashbook 
               WHERE society_id=%s 
               ORDER BY trx_date DESC, id DESC
               LIMIT %s OFFSET %s""",
            (society_id, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total
    
    @staticmethod
    def get_cashbook_summary(db, society_id: int) -> Dict:
        """Get cashbook summary"""
        result = db._execute(
            """SELECT 
                COALESCE(SUM(CASE WHEN drcr_account='Cr' THEN amount ELSE 0 END), 0) AS receipts,
                COALESCE(SUM(CASE WHEN drcr_account='Dr' THEN amount ELSE 0 END), 0) AS expenses,
                COALESCE(SUM(CASE WHEN drcr_account='Cr' THEN amount ELSE -amount END), 0) AS balance
               FROM vw_cashbook 
               WHERE society_id=%s""",
            (society_id,), fetch_one=True
        )
        
        return {
            'total_receipts': float(result['receipts']) if result else 0,
            'total_expenses': float(result['expenses']) if result else 0,
            'net_balance': float(result['balance']) if result else 0
        }

# ═════════════════════════════════════════════════════════════════════════════
# SOCIETIES LOADER (Master Admin)
# ═════════════════════════════════════════════════════════════════════════════

class SocietyLoader:
    """Load societies data"""
    
    @staticmethod
    def list_societies(db, search: str = None, plan: str = None,
                      page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load societies list
        Uses: fn_societies_list(search, plan)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_societies_list(%s, %s)""",
            (search, plan), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_societies_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (search, plan, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total

# ═════════════════════════════════════════════════════════════════════════════
# ASSET LOADER
# ═════════════════════════════════════════════════════════════════════════════

class AssetLoader:
    """Load asset register data"""
    
    @staticmethod
    def list_assets(db, society_id: int, search: str = None,
                   page: int = 1, page_size: int = 15) -> Tuple[List[Dict], int]:
        """
        Load assets list
        Uses: fn_asset_list(society_id, search)
        """
        offset = (page - 1) * page_size
        
        # Get total count
        count_result = db._execute(
            """SELECT COUNT(*) as cnt FROM fn_asset_list(%s, %s)""",
            (society_id, search), fetch_one=True
        )
        total = count_result['cnt'] if count_result else 0
        
        # Get paginated results
        rows = db._execute(
            """SELECT * FROM fn_asset_list(%s, %s)
               LIMIT %s OFFSET %s""",
            (society_id, search, page_size, offset), 
            fetch_all=True
        ) or []
        
        return rows, total

# ═════════════════════════════════════════════════════════════════════════════
# EXPORT ALL LOADERS
# ═════════════════════════════════════════════════════════════════════════════

__all__ = [
    'ApartmentLoader', 'VendorLoader', 'SecurityLoader',
    'PaymentLoader', 'ReceiptLoader', 'AccountLoader',
    'EventLoader', 'ConcernLoader', 'CashbookLoader',
    'SocietyLoader', 'AssetLoader'
]
