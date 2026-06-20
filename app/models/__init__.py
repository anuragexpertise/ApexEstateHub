# app/models/__init__.py
"""
OOP Models for EstateHub
Uses dataclasses with validation and type safety
"""

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from enum import Enum

# ════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════

class UserRole(str, Enum):
    ADMIN = "admin"
    APARTMENT = "apartment"
    VENDOR = "vendor"
    SECURITY = "security"
    MASTER_ADMIN = "master_admin"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransactionStatus(str, Enum):
    PAID = "paid"
    PENDING = "pending"
    CANCELLED = "cancelled"

class ReceivableStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"

class ConcernStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"

class SocietyPlan(str, Enum):
    FREE = "Free"
    NINE_APTS = "9Apts"
    NINETY_NINE_APTS = "99Apts"
    NINE_NINETY_NINE_APTS = "999Apts"
    UNLIMITED = "unlimited"

# ════════════════════════════════════════════════════════════════
# SOCIETY & USERS
# ════════════════════════════════════════════════════════════════

@dataclass
class Society:
    id: int
    name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    logo: Optional[str] = None
    login_background: Optional[str] = None
    plan: SocietyPlan = SocietyPlan.FREE
    plan_validity: date = field(default_factory=date.today)
    calc_start_date: date = field(default_factory=date.today)
    secretary_name: Optional[str] = None
    secretary_phone: Optional[str] = None
    secretary_sign: Optional[str] = None
    created_at: Optional[datetime] = None
    _image_society_id: Optional[int] = None  # For image resolution
    
    def to_dict(self):
        return asdict(self)
    
    def is_plan_active(self) -> bool:
        return self.plan_validity >= date.today()

@dataclass
class User:
    id: int
    email: str
    role: UserRole
    society_id: Optional[int] = None
    name: Optional[str] = None
    linked_id: Optional[int] = None
    login_method: str = "password"
    is_master_admin: bool = False
    push_enabled: bool = False
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self):
        data = asdict(self)
        data['role'] = self.role.value
        return data

# ════════════════════════════════════════════════════════════════
# APARTMENTS
# ════════════════════════════════════════════════════════════════

@dataclass
class Apartment:
    id: int
    society_id: int
    flat_number: str
    owner_name: Optional[str] = None
    owner_photo: Optional[str] = None
    id_proof: Optional[str] = None
    photo: Optional[str] = None
    mobile: Optional[str] = None
    apartment_size: int = 0
    active: bool = True
    created_at: Optional[datetime] = None
    
    # Calculated fields from list view
    months_due: Optional[int] = None
    total_maintenance: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    pending_amount: Optional[Decimal] = None
    late_fee: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            for key in ['months_due', 'total_maintenance', 'paid_amount', 
                       'pending_amount', 'late_fee', 'grand_total']:
                data.pop(key, None)
        return data
    
    @property
    def display_name(self) -> str:
        return f"Flat {self.flat_number} - {self.owner_name or 'Unknown'}"

# ════════════════════════════════════════════════════════════════
# VENDORS
# ════════════════════════════════════════════════════════════════

@dataclass
class Vendor:
    id: int
    society_id: int
    name: str
    service_type: Optional[str] = None
    mobile: Optional[str] = None
    logo: Optional[str] = None
    license: Optional[str] = None
    photo: Optional[str] = None
    service_description: Optional[str] = None
    active: bool = True
    created_at: Optional[datetime] = None
    
    # From list view
    pending_dues: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    active_passes: Optional[int] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            for key in ['pending_dues', 'paid_amount', 'active_passes']:
                data.pop(key, None)
        return data

# ════════════════════════════════════════════════════════════════
# SECURITY STAFF
# ════════════════════════════════════════════════════════════════

@dataclass
class SecurityStaff:
    id: int
    society_id: int
    name: str
    mobile: Optional[str] = None
    photo: Optional[str] = None
    id_proof: Optional[str] = None
    joining_date: date = field(default_factory=date.today)
    shift: Optional[str] = None
    salary_per_shift: Optional[Decimal] = None
    active: bool = True
    created_at: Optional[datetime] = None
    
    # From list view
    days_worked: Optional[int] = None
    salary_due: Optional[Decimal] = None
    salary_paid: Optional[Decimal] = None
    salary_pending: Optional[Decimal] = None
    active_fines: Optional[Decimal] = None
    current_status: Optional[str] = None
    today_duty: Optional[str] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            for key in ['days_worked', 'salary_due', 'salary_paid', 'salary_pending',
                       'active_fines', 'current_status', 'today_duty']:
                data.pop(key, None)
        return data

# ════════════════════════════════════════════════════════════════
# ACCOUNTING
# ════════════════════════════════════════════════════════════════

@dataclass
class Account:
    id: int
    society_id: int
    name: str
    tab_name: Optional[str] = None
    header: Optional[str] = None
    parent_account_id: Optional[int] = None
    drcr_account: Optional[str] = None  # 'Dr' or 'Cr'
    bf_amount: Decimal = Decimal('0.00')
    depreciation_percent: Decimal = Decimal('100.00')
    is_depreciable: bool = False
    created_at: Optional[datetime] = None
    
    # From list/profile view
    current_balance: Optional[Decimal] = None
    parent_account_name: Optional[str] = None
    transaction_count: Optional[int] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            for key in ['current_balance', 'parent_account_name', 'transaction_count']:
                data.pop(key, None)
        return data

@dataclass
class Transaction:
    id: int
    society_id: int
    trx_date: date
    acc_id: int
    amount: Decimal
    particulars: Optional[str] = None
    entity_id: Optional[int] = None
    mode: str = "cash"
    status: TransactionStatus = TransactionStatus.PAID
    payment_gateway_id: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    
    # From cashbook view
    account_name: Optional[str] = None
    account_group: Optional[str] = None
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        data['status'] = self.status.value if isinstance(self.status, TransactionStatus) else self.status
        if not include_calculated:
            for key in ['account_name', 'account_group', 'debit', 'credit', 'balance']:
                data.pop(key, None)
        return data

# ════════════════════════════════════════════════════════════════
# RECEIVABLES & PAYMENTS
# ════════════════════════════════════════════════════════════════

@dataclass
class Receivable:
    id: int
    society_id: int
    entity_id: int
    entity_type: str  # 'apartment', 'vendor', 'security'
    charge_type: str  # 'maintenance', 'fine', 'vendor_pass', etc.
    amount: Decimal
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: ReceivableStatus = ReceivableStatus.PENDING
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    # From list view
    entity_name: Optional[str] = None
    days_overdue: Optional[int] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        data['status'] = self.status.value
        if not include_calculated:
            for key in ['entity_name', 'days_overdue']:
                data.pop(key, None)
        return data

@dataclass
class Payment:
    id: int
    society_id: int
    entity_id: int
    entity_type: str
    amount: Decimal
    status: PaymentStatus = PaymentStatus.PENDING
    user_id: Optional[int] = None
    payment_type: Optional[str] = None
    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None
    due_date: Optional[date] = None
    paid_at: Optional[datetime] = None
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self):
        data = asdict(self)
        data['status'] = self.status.value
        return data

# ════════════════════════════════════════════════════════════════
# FEATURES
# ════════════════════════════════════════════════════════════════

@dataclass
class Event:
    id: int
    society_id: int
    title: str
    event_date: date
    description: Optional[str] = None
    event_time: Optional[str] = None
    venue: Optional[str] = None
    open_to: str = "all"
    created_at: Optional[datetime] = None
    
    # From list view
    attendees_count: Optional[int] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            data.pop('attendees_count', None)
        return data

@dataclass
class Concern:
    id: int
    society_id: int
    flat_no: str
    concern_type: str
    description: Optional[str] = None
    preferred_time: Optional[str] = None
    status: ConcernStatus = ConcernStatus.OPEN
    assigned_to: Optional[str] = None
    created_at: Optional[datetime] = None
    
    # From list view
    priority: Optional[str] = None
    days_open: Optional[int] = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        data['status'] = self.status.value
        if not include_calculated:
            for key in ['priority', 'days_open']:
                data.pop(key, None)
        return data

# ════════════════════════════════════════════════════════════════
# FACTORY FUNCTIONS (for converting DB rows to models)
# ════════════════════════════════════════════════════════════════

def dict_to_apartment(row: dict) -> Apartment:
    """Convert DB row to Apartment model"""
    return Apartment(**{k: v for k, v in row.items() if k in Apartment.__annotations__})

def dict_to_vendor(row: dict) -> Vendor:
    """Convert DB row to Vendor model"""
    return Vendor(**{k: v for k, v in row.items() if k in Vendor.__annotations__})

def dict_to_security(row: dict) -> SecurityStaff:
    """Convert DB row to SecurityStaff model"""
    return SecurityStaff(**{k: v for k, v in row.items() if k in SecurityStaff.__annotations__})

def dict_to_society(row: dict) -> Society:
    """Convert DB row to Society model"""
    return Society(**{k: v for k, v in row.items() if k in Society.__annotations__})

def dict_to_account(row: dict) -> Account:
    """Convert DB row to Account model"""
    return Account(**{k: v for k, v in row.items() if k in Account.__annotations__})

def dict_to_transaction(row: dict) -> Transaction:
    """Convert DB row to Transaction model"""
    data = {k: v for k, v in row.items() if k in Transaction.__annotations__}
    if 'status' in data and isinstance(data['status'], str):
        try:
            data['status'] = TransactionStatus(data['status'])
        except ValueError:
            pass
    return Transaction(**data)

def dict_to_receivable(row: dict) -> Receivable:
    """Convert DB row to Receivable model"""
    data = {k: v for k, v in row.items() if k in Receivable.__annotations__}
    if 'status' in data and isinstance(data['status'], str):
        try:
            data['status'] = ReceivableStatus(data['status'])
        except ValueError:
            pass
    return Receivable(**data)

def dict_to_event(row: dict) -> Event:
    """Convert DB row to Event model"""
    return Event(**{k: v for k, v in row.items() if k in Event.__annotations__})

def dict_to_concern(row: dict) -> Concern:
    """Convert DB row to Concern model"""
    data = {k: v for k, v in row.items() if k in Concern.__annotations__}
    if 'status' in data and isinstance(data['status'], str):
        try:
            data['status'] = ConcernStatus(data['status'])
        except ValueError:
            pass
    return Concern(**data)
