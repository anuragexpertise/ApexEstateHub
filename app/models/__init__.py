# app/models/__init__.py
"""
OOP Models for EstateHub
Uses dataclasses with validation and type safety
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional  # noqa: UP035, F401

from app.models.poll import Poll, PollVote
from app.utils import IST, now_ist, today_ist  # noqa: F401

# ════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════

class UserRole(str, Enum):
    # Exactly the users.role CHECK constraint in database/estatehub.sql — nothing
    # more may be added here. There is deliberately NO "master"/"master_admin"
    # member: the platform role is never persisted, it is derived per row by
    # app.security.roles.resolve_role() (admin + no society + is_master_admin).
    # A persisted "master_admin" was rejected by the DB CHECK and would have
    # disagreed with roles.py, which is the single role vocabulary.
    # See app/security/roles.py.
    ADMIN = "admin"
    APARTMENT = "apartment"
    VENDOR = "vendor"
    SECURITY = "security"

class payablestatus(str, Enum):
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
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    CLOSED = "closed"

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
    email: str | None
    phone: str | None
    address: str | None
    logo: str | None = None
    login_background: str | None = None
    plan: SocietyPlan = SocietyPlan.FREE
    plan_validity: date = field(default_factory=date.today)
    calc_start_date: date = field(default_factory=date.today)
    secretary_name: str | None = None
    secretary_phone: str | None = None
    secretary_sign: str | None = None
    created_at: datetime | None = None
    _image_society_id: int | None = None  # For image resolution
    
    def to_dict(self):
        return asdict(self)
    
    def is_plan_active(self) -> bool:
        return self.plan_validity >= today_ist()

@dataclass
class User:
    id: int
    email: str
    role: UserRole
    society_id: int | None = None
    name: str | None = None
    linked_id: int | None = None
    login_method: str = "password"
    is_master_admin: bool = False
    push_enabled: bool = False
    last_login: datetime | None = None
    created_at: datetime | None = None
    
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
    owner_name: str | None = None
    owner_photo: str | None = None
    id_proof: str | None = None
    mobile: str | None = None
    apartment_size: int = 0
    active: bool = True
    created_at: datetime | None = None
    
    # Calculated fields from list view
    months_due: int | None = None
    total_maintenance: Decimal | None = None
    paid_amount: Decimal | None = None
    pending_amount: Decimal | None = None
    late_fee: Decimal | None = None
    grand_total: Decimal | None = None
    
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
    service_type: str | None = None
    mobile: str | None = None
    logo: str | None = None
    license: str | None = None
    photo: str | None = None
    service_description: str | None = None
    active: bool = True
    created_at: datetime | None = None
    
    # From list view
    pending_dues: Decimal | None = None
    paid_amount: Decimal | None = None
    active_passes: int | None = None
    
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
    mobile: str | None = None
    photo: str | None = None
    id_proof: str | None = None
    joining_date: date = field(default_factory=date.today)
    shift: str | None = None
    salary_per_shift: Decimal | None = None
    active: bool = True
    created_at: datetime | None = None
    
    # From list view
    days_worked: int | None = None
    salary_due: Decimal | None = None
    salary_paid: Decimal | None = None
    salary_pending: Decimal | None = None
    active_fines: Decimal | None = None
    current_status: str | None = None
    today_duty: str | None = None
    
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
    tab_name: str | None = None
    header: str | None = None
    parent_account_id: int | None = None
    drcr_account: str | None = None  # 'Dr' or 'Cr'
    bf_amount: Decimal = Decimal('0.00')
    depreciation_percent: Decimal = Decimal('100.00')
    is_depreciable: bool = False
    created_at: datetime | None = None
    
    # From list/profile view
    current_balance: Decimal | None = None
    parent_account_name: str | None = None
    transaction_count: int | None = None
    
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
    particulars: str | None = None
    entity_id: int | None = None
    mode: str = "cash"
    status: TransactionStatus = TransactionStatus.PAID
    payment_gateway_id: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    
    # From cashbook view
    account_name: str | None = None
    account_group: str | None = None
    debit: Decimal | None = None
    credit: Decimal | None = None
    balance: Decimal | None = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        data['status'] = self.status.value if isinstance(self.status, TransactionStatus) else self.status
        if not include_calculated:
            for key in ['account_name', 'account_group', 'debit', 'credit', 'balance']:
                data.pop(key, None)
        return data

# ════════════════════════════════════════════════════════════════
# RECEIVABLES & payables
# ════════════════════════════════════════════════════════════════

@dataclass
class Receivable:
    id: int
    society_id: int
    entity_id: int
    role: str  # 'apartment', 'vendor', 'security'
    charge_type: str  # 'maintenance', 'fine', 'vendor_pass', etc.
    amount: Decimal
    description: str | None = None
    due_date: date | None = None
    status: ReceivableStatus = ReceivableStatus.PENDING
    source_table: str | None = None
    source_id: int | None = None
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    created_at: datetime | None = None
    
    # From list view
    entity_name: str | None = None
    days_overdue: int | None = None
    
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
    role: str
    amount: Decimal
    status: payablestatus = payablestatus.PENDING
    user_id: int | None = None
    payment_type: str | None = None
    payment_method: str | None = None
    transaction_id: str | None = None
    due_date: date | None = None
    paid_at: datetime | None = None
    source_table: str | None = None
    source_id: int | None = None
    confirmed_by: int | None = None
    confirmed_at: datetime | None = None
    created_at: datetime | None = None
    
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
    description: str | None = None
    event_time: str | None = None
    venue: str | None = None
    open_to: str = "all"
    created_at: datetime | None = None
    
    # From list view
    attendees_count: int | None = None
    
    def to_dict(self, include_calculated=False):
        data = asdict(self)
        if not include_calculated:
            data.pop('attendees_count', None)
        return data

@dataclass
class Concern:
    id: int
    society_id: int
    apartment_id: int
    concern_type: str
    description: str | None = None
    preferred_time: str | None = None
    status: ConcernStatus = ConcernStatus.OPEN
    assigned_to: str | None = None
    created_at: datetime | None = None
    
    # From list view
    priority: str | None = None
    days_open: int | None = None
    
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

@dataclass
class ConcernInvite:
    id: int
    concern_id: int
    society_id: int
    role: str
    entity_id: int
    bid_amount: Decimal | None = None
    status: str = "invited"
    invited_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    entity_name: str | None = None

    def to_dict(self, include_calculated: bool = False) -> dict:
        data = asdict(self)
        return data

def dict_to_concern_invite(row: dict) -> ConcernInvite:
    """Convert DB row to ConcernInvite model"""
    return ConcernInvite(**{k: v for k, v in row.items() if k in ConcernInvite.__annotations__})

# ════════════════════════════════════════════════════════════════
# POLLING
# ════════════════════════════════════════════════════════════════

def dict_to_poll(row: dict) -> Poll:
    """Convert DB row to Poll model"""
    return Poll(**{k: v for k, v in row.items() if k in Poll.__annotations__})

def dict_to_poll_vote(row: dict) -> PollVote:
    """Convert DB row to PollVote model"""
    return PollVote(**{k: v for k, v in row.items() if k in PollVote.__annotations__})
