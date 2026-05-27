# app/models/__init__.py
"""
EsateHub Models - Complete OOP Layer
Thin wrapper around SQL functions for business logic
"""

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Optional, Tuple

# ═════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═════════════════════════════════════════════════════════════════════════════

class UserRole(Enum):
    """User role enumeration"""
    MASTER_ADMIN = "admin"  # Across all societies
    ADMIN = "admin"  # Society-level admin
    APARTMENT = "apartment"
    VENDOR = "vendor"
    SECURITY = "security"

class PaymentStatus(Enum):
    """Payment/Receivable status"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransactionStatus(Enum):
    """Transaction status in cashbook"""
    PAID = "paid"
    PENDING = "pending"
    FAILED = "failed"

class EntityType(Enum):
    """Entity type for receivables/payments"""
    APARTMENT = "apartment"
    VENDOR = "vendor"
    SECURITY = "security"

# ═════════════════════════════════════════════════════════════════════════════
# BASE MODEL
# ═════════════════════════════════════════════════════════════════════════════

class BaseModel:
    """Base model with common functionality"""
    
    def __init__(self, db):
        self.db = db
    
    def _execute(self, query: str, params: tuple = None, fetch_one: bool = False, 
                 fetch_all: bool = True):
        """Execute SQL query"""
        return self.db._execute(query, params or (), 
                               fetch_one=fetch_one, fetch_all=fetch_all)
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

# ═════════════════════════════════════════════════════════════════════════════
# SOCIETY MODEL
# ═════════════════════════════════════════════════════════════════════════════

class Society(BaseModel):
    """Society model with full CRUD"""
    
    def __init__(self, db, society_id: int = None, **kwargs):
        super().__init__(db)
        self.id = society_id
        self.name = kwargs.get('name')
        self.email = kwargs.get('email')
        self.phone = kwargs.get('phone')
        self.logo = kwargs.get('logo')  # filename
        self.address = kwargs.get('address')
        self.plan = kwargs.get('plan', 'Free')
        self.plan_validity = kwargs.get('plan_validity', date.today())
        self.arrear_start_date = kwargs.get('arrear_start_date', date.today())
        self.secretary_name = kwargs.get('secretary_name')
        self.secretary_phone = kwargs.get('secretary_phone')
        self.secretary_sign = kwargs.get('secretary_sign')  # filename
        self.login_background = kwargs.get('login_background')  # filename
        self.created_at = kwargs.get('created_at')
    
    @classmethod
    def get_by_id(cls, db, society_id: int) -> Optional['Society']:
        """Get society by ID"""
        row = db._execute(
            "SELECT * FROM societies WHERE id = %s",
            (society_id,), fetch_one=True
        )
        return cls(db, **row) if row else None
    
    @classmethod
    def list_all(cls, db, search: str = None) -> List['Society']:
        """List all societies - uses fn_societies_list"""
        result = db._execute(
            "SELECT * FROM fn_societies_list(%s, %s)",
            (search, None), fetch_all=True
        )
        return [cls(db, **row) for row in (result or [])]
    
    def save(self) -> bool:
        """Create or update society"""
        if self.id:
            self.db._execute(
                """UPDATE societies SET name=%s, email=%s, phone=%s, logo=%s, 
                   address=%s, plan=%s, plan_validity=%s, arrear_start_date=%s,
                   secretary_name=%s, secretary_phone=%s, secretary_sign=%s,
                   login_background=%s WHERE id=%s""",
                (self.name, self.email, self.phone, self.logo, self.address,
                 self.plan, self.plan_validity, self.arrear_start_date,
                 self.secretary_name, self.secretary_phone, self.secretary_sign,
                 self.login_background, self.id)
            )
        else:
            result = self.db._execute(
                """INSERT INTO societies (name, email, phone, logo, address, plan,
                   plan_validity, arrear_start_date, secretary_name, secretary_phone,
                   secretary_sign, login_background)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (self.name, self.email, self.phone, self.logo, self.address,
                 self.plan, self.plan_validity, self.arrear_start_date,
                 self.secretary_name, self.secretary_phone, self.secretary_sign,
                 self.login_background), fetch_one=True
            )
            self.id = result['id'] if result else None
        return bool(self.id)
    
    def delete(self) -> bool:
        """Delete society (cascade deletes all related data)"""
        if not self.id:
            return False
        self.db._execute("DELETE FROM societies WHERE id = %s", (self.id,))
        return True

# ═════════════════════════════════════════════════════════════════════════════
# APARTMENT MODEL
# ═════════════════════════════════════════════════════════════════════════════

class Apartment(BaseModel):
    """Apartment model with maintenance tracking"""
    
    def __init__(self, db, apartment_id: int = None, **kwargs):
        super().__init__(db)
        self.id = apartment_id
        self.society_id = kwargs.get('society_id')
        self.flat_number = kwargs.get('flat_number')
        self.owner_name = kwargs.get('owner_name')
        self.mobile = kwargs.get('mobile')
        self.apartment_size = kwargs.get('apartment_size', 0)
        self.active = kwargs.get('active', True)
        self.created_at = kwargs.get('created_at')
    
    @classmethod
    def get_by_id(cls, db, apartment_id: int) -> Optional['Apartment']:
        """Get apartment by ID"""
        row = db._execute(
            "SELECT * FROM apartments WHERE id = %s",
            (apartment_id,), fetch_one=True
        )
        return cls(db, **row) if row else None
    
    @classmethod
    def list_by_society(cls, db, society_id: int, search: str = None, 
                       has_dues: bool = None) -> List['Apartment']:
        """List apartments with maintenance breakdown - uses fn_apartments_list"""
        result = db._execute(
            "SELECT * FROM fn_apartments_list(%s, %s, %s)",
            (society_id, search, has_dues), fetch_all=True
        )
        return [cls(db, **row) for row in (result or [])]
    
    def get_maintenance_breakdown(self) -> Dict:
        """Get complete maintenance breakdown"""
        row = self.db._execute(
            "SELECT * FROM fn_apartments_list(%s, NULL, NULL) WHERE id = %s",
            (self.society_id, self.id), fetch_one=True
        )
        if row:
            return {
                'total_maintenance': row.get('total_maintenance', 0),
                'paid_amount': row.get('paid_amount', 0),
                'pending_amount': row.get('pending_amount', 0),
                'late_fee': row.get('late_fee', 0),
                'grand_total': row.get('grand_total', 0),
                'months_due': row.get('months_due', 0)
            }
        return {}
    
    def save(self) -> bool:
        """Create or update apartment"""
        if self.id:
            self.db._execute(
                """UPDATE apartments SET flat_number=%s, owner_name=%s, mobile=%s,
                   apartment_size=%s, active=%s WHERE id=%s""",
                (self.flat_number, self.owner_name, self.mobile, 
                 self.apartment_size, self.active, self.id)
            )
        else:
            result = self.db._execute(
                """INSERT INTO apartments (society_id, flat_number, owner_name, 
                   mobile, apartment_size, active)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (self.society_id, self.flat_number, self.owner_name, 
                 self.mobile, self.apartment_size, self.active), fetch_one=True
            )
            self.id = result['id'] if result else None
        return bool(self.id)
    
    def delete(self) -> bool:
        """Delete apartment"""
        if not self.id:
            return False
        self.db._execute("DELETE FROM apartments WHERE id = %s", (self.id,))
        return True

# ═════════════════════════════════════════════════════════════════════════════
# ACCOUNT MODEL
# ═════════════════════════════════════════════════════════════════════════════

class Account(BaseModel):
    """Chart of Accounts"""
    
    def __init__(self, db, account_id: int = None, **kwargs):
        super().__init__(db)
        self.id = account_id
        self.society_id = kwargs.get('society_id')
        self.name = kwargs.get('name')
        self.tab_name = kwargs.get('tab_name')
        self.header = kwargs.get('header')
        self.parent_account_id = kwargs.get('parent_account_id')
        self.drcr_account = kwargs.get('drcr_account')  # Dr or Cr
        self.bf_amount = Decimal(kwargs.get('bf_amount', 0))
        self.drcr_bf = kwargs.get('drcr_bf', 'Dr')
        self.depreciation_percent = Decimal(kwargs.get('depreciation_percent', 100))
        self.is_depreciable = kwargs.get('is_depreciable', False)
        self.created_at = kwargs.get('created_at')
    
    @classmethod
    def get_by_id(cls, db, account_id: int) -> Optional['Account']:
        """Get account by ID"""
        row = db._execute(
            "SELECT * FROM accounts WHERE id = %s",
            (account_id,), fetch_one=True
        )
        return cls(db, **row) if row else None
    
    @classmethod
    def list_by_society(cls, db, society_id: int, search: str = None) -> List['Account']:
        """List accounts - uses fn_accounts_list"""
        result = db._execute(
            "SELECT * FROM fn_accounts_list(%s, %s)",
            (society_id, search), fetch_all=True
        )
        return [cls(db, **row) for row in (result or [])]
    
    def get_current_balance(self) -> Decimal:
        """Calculate current balance from transactions"""
        row = self.db._execute(
            """SELECT COALESCE(SUM(
                    CASE WHEN drcr_account='Cr' THEN amount ELSE -amount END
                ), 0) + %s AS balance
               FROM transactions WHERE acc_id=%s AND status='paid'""",
            (float(self.bf_amount), self.id), fetch_one=True
        )
        return Decimal(row['balance']) if row else self.bf_amount
    
    def save(self) -> bool:
        """Create or update account"""
        if self.id:
            self.db._execute(
                """UPDATE accounts SET name=%s, tab_name=%s, header=%s,
                   parent_account_id=%s, drcr_account=%s, bf_amount=%s,
                   drcr_bf=%s, depreciation_percent=%s, is_depreciable=%s
                   WHERE id=%s""",
                (self.name, self.tab_name, self.header, self.parent_account_id,
                 self.drcr_account, float(self.bf_amount), self.drcr_bf,
                 float(self.depreciation_percent), self.is_depreciable, self.id)
            )
        else:
            result = self.db._execute(
                """INSERT INTO accounts (id, society_id, name, tab_name, header,
                   parent_account_id, drcr_account, bf_amount, drcr_bf,
                   depreciation_percent, is_depreciable)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (self.id, self.society_id, self.name, self.tab_name, self.header,
                 self.parent_account_id, self.drcr_account, float(self.bf_amount),
                 self.drcr_bf, float(self.depreciation_percent), self.is_depreciable),
                fetch_one=True
            )
            self.id = result['id'] if result else None
        return bool(self.id)

# ═════════════════════════════════════════════════════════════════════════════
# TRANSACTION MODEL (CASHBOOK)
# ═════════════════════════════════════════════════════════════════════════════

class Transaction(BaseModel):
    """Transaction (Cashbook entry)"""
    
    def __init__(self, db, transaction_id: int = None, **kwargs):
        super().__init__(db)
        self.id = transaction_id
        self.society_id = kwargs.get('society_id')
        self.trx_date = kwargs.get('trx_date', date.today())
        self.acc_id = kwargs.get('acc_id')
        self.entity_id = kwargs.get('entity_id')
        self.acc_particulars = kwargs.get('acc_particulars')
        self.amount = Decimal(kwargs.get('amount', 0))
        self.mode = kwargs.get('mode', 'cash')
        self.status = kwargs.get('status', 'paid')
        self.created_by = kwargs.get('created_by')
        self.created_at = kwargs.get('created_at')
    
    @classmethod
    def get_by_id(cls, db, transaction_id: int) -> Optional['Transaction']:
        """Get transaction by ID"""
        row = db._execute(
            "SELECT * FROM transactions WHERE id = %s",
            (transaction_id,), fetch_one=True
        )
        return cls(db, **row) if row else None
    
    def save(self) -> bool:
        """Create transaction"""
        if self.id:
            return False  # Transactions are immutable
        
        result = self.db._execute(
            """INSERT INTO transactions (society_id, trx_date, acc_id, entity_id,
               acc_particulars, amount, mode, status, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (self.society_id, self.trx_date, self.acc_id, self.entity_id,
             self.acc_particulars, float(self.amount), self.mode, 
             self.status, self.created_by), fetch_one=True
        )
        self.id = result['id'] if result else None
        return bool(self.id)

# ═════════════════════════════════════════════════════════════════════════════
# PAYMENT/RECEIVABLE MODEL
# ═════════════════════════════════════════════════════════════════════════════

class Receivable(BaseModel):
    """Receivable (Auto-generated credit)"""
    
    def __init__(self, db, receivable_id: int = None, **kwargs):
        super().__init__(db)
        self.id = receivable_id
        self.society_id = kwargs.get('society_id')
        self.entity_id = kwargs.get('entity_id')
        self.entity_type = kwargs.get('entity_type')  # apartment, vendor, security
        self.charge_type = kwargs.get('charge_type')
        self.description = kwargs.get('description')
        self.amount = Decimal(kwargs.get('amount', 0))
        self.due_date = kwargs.get('due_date')
        self.status = kwargs.get('status', 'pending')
        self.source_table = kwargs.get('source_table')
        self.source_id = kwargs.get('source_id')
        self.confirmed_by = kwargs.get('confirmed_by')
        self.confirmed_at = kwargs.get('confirmed_at')
        self.created_at = kwargs.get('created_at')
    
    def confirm(self, user_id: int) -> bool:
        """Confirm receivable for payment"""
        self.db._execute(
            """UPDATE receivables SET status='confirmed', confirmed_by=%s, 
               confirmed_at=NOW() WHERE id=%s""",
            (user_id, self.id)
        )
        return True
    
    def cancel(self) -> bool:
        """Cancel receivable"""
        self.db._execute(
            "UPDATE receivables SET status='cancelled' WHERE id=%s",
            (self.id,)
        )
        return True

class Payment(BaseModel):
    """Payment (Manual or auto-generated debit)"""
    
    def __init__(self, db, payment_id: int = None, **kwargs):
        super().__init__(db)
        self.id = payment_id
        self.society_id = kwargs.get('society_id')
        self.user_id = kwargs.get('user_id')
        self.entity_id = kwargs.get('entity_id')
        self.entity_type = kwargs.get('entity_type')
        self.amount = Decimal(kwargs.get('amount', 0))
        self.payment_type = kwargs.get('payment_type')
        self.payment_method = kwargs.get('payment_method')
        self.transaction_id = kwargs.get('transaction_id')
        self.status = kwargs.get('status', 'pending')
        self.due_date = kwargs.get('due_date')
        self.paid_at = kwargs.get('paid_at')
        self.confirmed_by = kwargs.get('confirmed_by')
        self.confirmed_at = kwargs.get('confirmed_at')
        self.created_at = kwargs.get('created_at')
    
    def save(self) -> bool:
        """Create or update payment"""
        if self.id:
            self.db._execute(
                """UPDATE payments SET amount=%s, payment_method=%s, status=%s
                   WHERE id=%s""",
                (float(self.amount), self.payment_method, self.status, self.id)
            )
        else:
            result = self.db._execute(
                """INSERT INTO payments (society_id, user_id, entity_id, entity_type,
                   amount, payment_type, payment_method, transaction_id, status, due_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (self.society_id, self.user_id, self.entity_id, self.entity_type,
                 float(self.amount), self.payment_type, self.payment_method,
                 self.transaction_id, self.status, self.due_date), fetch_one=True
            )
            self.id = result['id'] if result else None
        return bool(self.id)
    
    def verify(self, user_id: int, payment_method: str) -> bool:
        """Verify payment and create transaction"""
        self.db._execute(
            """UPDATE payments SET status='verified', confirmed_by=%s,
               confirmed_at=NOW(), payment_method=%s WHERE id=%s""",
            (user_id, payment_method, self.id)
        )
        return True

# ═════════════════════════════════════════════════════════════════════════════
# IMAGE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

class ImageManager:
    """Manage image paths and file operations"""
    
    # Path patterns
    PATHS = {
        'society': '/assets/{society_id}/{filename}',
        'apartment': '/assets/{society_id}/apartment/{pk}/{filename}',
        'vendor': '/assets/{society_id}/vendor/{pk}/{filename}',
        'security': '/assets/{society_id}/security/{pk}/{filename}',
        'default': '/assets/default/{entity}/{filename}'
    }
    
    @staticmethod
    def get_image_url(entity: str, filename: str, society_id: int = None, 
                      pk: int = None) -> str:
        """Get full image URL from filename"""
        if not filename or str(filename).strip() == '':
            return None
        
        if filename.startswith(('http://', 'https://', 'data:')):
            return filename
        
        if filename.startswith('/assets/'):
            return filename
        
        path = ImageManager.PATHS.get(entity, ImageManager.PATHS['default'])
        
        if entity == 'society' and pk:
            return path.format(society_id=pk, filename=filename)
        elif society_id and pk and entity in ImageManager.PATHS:
            return path.format(society_id=society_id, pk=pk, filename=filename)
        elif society_id:
            return path.format(society_id=society_id, entity=entity, filename=filename)
        else:
            return ImageManager.PATHS['default'].format(entity=entity, filename=filename)
    
    @staticmethod
    def save_uploaded_file(uploaded_data, entity: str, society_id: int, 
                          pk: int = None) -> Optional[str]:
        """Save uploaded file and return filename"""
        import os
        from pathlib import Path
        
        if not uploaded_data or not uploaded_data.get('filename'):
            return None
        
        filename = uploaded_data['filename']
        content = uploaded_data.get('content')
        
        if entity == 'society':
            folder = Path(f'app/assets/{pk}')
        elif pk:
            folder = Path(f'app/assets/{society_id}/{entity}/{pk}')
        else:
            folder = Path(f'app/assets/{society_id}/{entity}')
        
        folder.mkdir(parents=True, exist_ok=True)
        
        filepath = folder / filename
        if content:
            filepath.write_bytes(content)
        
        return filename

# ═════════════════════════════════════════════════════════════════════════════
# RBAC MODEL
# ═════════════════════════════════════════════════════════════════════════════

class RBAC:
    """Role-Based Access Control"""
    
    # Default permissions by role
    DEFAULT_PERMISSIONS = {
        'admin': {
            'dashboard': ['view'],
            'apartments': ['view', 'list', 'create', 'edit', 'delete'],
            'payments': ['view', 'list', 'create', 'verify'],
            'receipts': ['view', 'list', 'create'],
            'expenses': ['view', 'list', 'create'],
            'transactions': ['view'],
            'accounts': ['view', 'edit'],
            'events': ['view', 'list', 'create', 'edit', 'delete'],
            'concerns': ['view', 'list', 'assign'],
            'vendors': ['view', 'list', 'create', 'edit'],
            'security': ['view', 'list', 'create', 'edit'],
            'reports': ['view'],
            'settings': ['edit'],
        },
        'apartment': {
            'dashboard': ['view'],
            'payments': ['view', 'list', 'create'],
            'receipts': ['view'],
            'concerns': ['view', 'list', 'create'],
            'events': ['view', 'list'],
            'reports': ['view_own'],
        },
        'vendor': {
            'dashboard': ['view'],
            'payments': ['view', 'list'],
            'receipts': ['view'],
            'concerns': ['view', 'list', 'create'],
            'events': ['view', 'list'],
        },
        'security': {
            'gate': ['view', 'create'],
            'roster': ['view'],
            'events': ['view', 'list'],
            'receipts': ['view', 'create'],
        }
    }
    
    def __init__(self, db):
        self.db = db
    
    def has_permission(self, user_id: int, resource: str, action: str, 
                      society_id: int = None) -> bool:
        """Check if user has permission for resource action"""
        # Get user role
        user = self.db._execute(
            "SELECT role, society_id FROM users WHERE id = %s",
            (user_id,), fetch_one=True
        )
        if not user:
            return False
        
        role = user['role']
        
        # Check custom permissions
        custom = self.db._execute(
            """SELECT allowed FROM role_permissions 
               WHERE role=%s AND resource=%s AND action=%s
               AND (society_id=%s OR society_id IS NULL)
               ORDER BY society_id DESC LIMIT 1""",
            (role, resource, action, society_id), fetch_one=True
        )
        
        if custom:
            return custom['allowed']
        
        # Check default permissions
        defaults = self.DEFAULT_PERMISSIONS.get(role, {})
        return action in defaults.get(resource, [])
    
    def grant_permission(self, society_id: int, role: str, resource: str, 
                        action: str, allowed: bool = True) -> bool:
        """Grant or revoke permission"""
        self.db._execute(
            """INSERT INTO role_permissions (society_id, role, resource, action, allowed)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (society_id, role, resource, action)
               DO UPDATE SET allowed=%s""",
            (society_id, role, resource, action, allowed, allowed)
        )
        return True
    
    def list_permissions_for_role(self, role: str, society_id: int = None) -> Dict:
        """List all permissions for a role"""
        perms = self.db._execute(
            """SELECT resource, action, allowed FROM role_permissions 
               WHERE role=%s AND (society_id=%s OR society_id IS NULL)
               ORDER BY resource, action""",
            (role, society_id), fetch_all=True
        )
        
        result = {}
        for perm in (perms or []):
            res = perm['resource']
            if res not in result:
                result[res] = []
            if perm['allowed']:
                result[res].append(perm['action'])
        
        return result

# ═════════════════════════════════════════════════════════════════════════════
# EXPORT ALL MODELS
# ═════════════════════════════════════════════════════════════════════════════

__all__ = [
    'UserRole', 'PaymentStatus', 'TransactionStatus', 'EntityType',
    'Society', 'Apartment', 'Account', 'Transaction',
    'Receivable', 'Payment', 'ImageManager', 'RBAC'
]
