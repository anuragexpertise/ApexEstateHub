# ESTATEHUB INTEGRATION GUIDE
## Complete Architecture Update - Models, Loaders, SQL Functions

---

## 📋 TABLE OF CONTENTS

1. [Architecture Overview](#architecture-overview)
2. [SQL Schema Changes](#sql-schema-changes)
3. [Python Models (OOP)](#python-models)
4. [Thin Loaders Layer](#thin-loaders)
5. [RBAC System](#rbac-system)
6. [Integration Examples](#integration-examples)
7. [Migration Checklist](#migration-checklist)

---

## Architecture Overview

### Old Architecture (To Be Replaced)
```
Dash Callbacks → Python Loaders → Direct SQL Queries → Database
```

### New Architecture (Complete & Validated)
```
Dash Callbacks → Models (OOP) → Thin Loaders → SQL Functions → Database
                                         ↓
                                   RBAC Checks
```

### Key Features
- **Business Logic in SQL**: All complex calculations in PostgreSQL functions
- **Thin Python Layer**: Models & loaders simply call SQL functions
- **Complete RBAC**: Role-based access control for all operations
- **Image Management**: Centralized image URL/file handling
- **Transaction Flow**: Receivables → Payments → Receipts → Transactions → Cashbook

---

## SQL Schema Changes

### New Tables Added
1. **role_permissions** - RBAC system
2. **security_roster** - Duty roster management

### Updated Tables
1. **payments** - Added `confirmed_by`, `confirmed_at` columns
2. **receipts** - New table for manual credit entries
3. **expenses** - New table for manual debit entries
4. **receivables** - Auto-generated credits from charges/fines

### New SQL Functions
- `fn_apartments_list()` - Apartment list with maintenance
- `fn_vendors_list()` - Vendor list with dues
- `fn_security_list()` - Security staff with salary due
- `fn_events_list()` - Events with days to event
- `fn_concerns_list()` - Concerns with aging
- `fn_accounts_list()` - Chart of accounts with balance
- `fn_societies_list()` - Master admin view
- `fn_asset_list()` - Asset register with depreciation~
- `fn_auto_generate_receivables()` - Auto create apartment receivables
- `fn_auto_process_verified_payments()` - Auto create receipts from verified payments
- `fn_calculate_asset_depreciation()` - Auto depreciation expenses~

### Migration Steps
1. **Backup current database**
2. **Run schema** from `estatehub_complete_schema.sql`
3. **Migrate data** from old tables (if any exist)
4. **Test all SQL functions** with test data
5. **Update Dash callbacks** to use new loaders

---

## Python Models

### Base Model
All models inherit from `BaseModel`:
```python
from estatehub_models import BaseModel

class MyModel(BaseModel):
    def __init__(self, db, **kwargs):
        super().__init__(db)
        # Initialize properties
```

### Key Models

#### 1. Society
```python
from estatehub_models import Society

# Get by ID
society = Society.get_by_id(db, society_id=1)

# List all (with search)
all_societies = Society.list_all(db, search="Active")

# Create
society = Society(db,
    name="Riverside Towers",
    email="admin@riverside.com",
    phone="9876543210",
    plan="99Apts",
    plan_validity=date(2026, 12, 31)
)
society.save()

# Update
society.plan = "unlimited"
society.save()

# Delete
society.delete()
```

#### 2. Apartment
```python
from estatehub_models import Apartment

# List with maintenance breakdown
apartments, total = Apartment.list_by_society(
    db, society_id=1, 
    search="A-101", 
    has_dues=True  # Only with pending dues
)

# Get profile
apt = Apartment.get_by_id(db, apartment_id=42)

# Get maintenance breakdown
breakdown = apt.get_maintenance_breakdown()
# Returns:
# {
#   'total_maintenance': 15000.00,
#   'paid_amount': 10000.00,
#   'pending_amount': 5000.00,
#   'late_fee': 500.00,
#   'grand_total': 5500.00,
#   'months_due': 5
# }

# Create
apt = Apartment(db,
    society_id=1,
    flat_number="A-101",
    owner_name="John Doe",
    mobile="9876543210",
    apartment_size=1200
)
apt.save()

# Update
apt.owner_name = "John Doe Jr."
apt.save()

# Delete
apt.delete()
```

#### 3. Account
```python
from estatehub_models import Account

# List accounts
accounts, total = Account.list_by_society(db, society_id=1, search="Cash")

# Get account
cash_account = Account.get_by_id(db, account_id=1)

# Get current balance (calculated from transactions)
balance = cash_account.get_current_balance()
# Returns: Decimal('1,23,456.50')

# Create
acc = Account(db,
    society_id=1,
    id=100,
    name="Bank - HDFC",
    tab_name="Bank",
    drcr_account="Cr",  # Credit account
    bf_amount=50000,  # Opening balance
    drcr_bf="Cr"
)
acc.save()
```

#### 4. Transaction
```python
from estatehub_models import Transaction

# Get transaction
txn = Transaction.get_by_id(db, transaction_id=1)

# Create (immutable - no update)
txn = Transaction(db,
    society_id=1,
    trx_date=date.today(),
    acc_id=1,  # Cash account
    acc_particulars="Payment received from Flat A-101",
    amount=5000,
    mode="cash",
    status="paid",
    created_by=user_id
)
txn.save()
```

#### 5. Payment & Receivable
```python
from estatehub_models import Payment, Receivable

# Create receivable (auto-generated from charges)
rcv = Receivable(db,
    society_id=1,
    entity_id=1,  # apartment_id
    entity_type="apartment",
    charge_type="maintenance",
    description="April maintenance for Flat A-101",
    amount=3000,
    due_date=date(2026, 4, 10),
    status="pending"
)
rcv.save()

# Confirm receivable (before payment)
rcv.confirm(user_id=admin_id)

# Create payment (manual or auto from app)
payment = Payment(db,
    society_id=1,
    entity_id=1,
    entity_type="apartment",
    amount=3000,
    payment_type="maintenance",
    payment_method="upi",
    status="pending"
)
payment.save()

# Verify payment (creates receipt and processes receivables)
payment.verify(user_id=admin_id, payment_method="upi")
# SQL trigger will:
# 1. Create receipt entry
# 2. Create transaction
# 3. Apply payment to pending receivables
# 4. Mark receivables as confirmed
```

---

## Thin Loaders Layer

### Purpose
- Call SQL functions
- Map results to dictionaries
- Handle pagination
- Manage image URLs
- Support search & filtering

### Usage Pattern

#### Apartments Loader
```python
from estatehub_loaders import ApartmentLoader

# List with pagination
apartments, total_count = ApartmentLoader.list_apartments(
    db, 
    society_id=1,
    search="A-101",
    has_dues=True,
    page=1,
    page_size=15
)

# Returns:
# [
#   {
#     'id': 1,
#     'flat_number': 'A-101',
#     'owner_name': 'John Doe',
#     'total_maintenance': 15000.00,
#     'paid_amount': 10000.00,
#     'pending_amount': 5000.00,
#     'late_fee': 500.00,
#     'grand_total': 5500.00,
#     'months_due': 5
#   },
#   ...
# ]

# Get profile
profile = ApartmentLoader.get_apartment_profile(db, apartment_id=1)

# Create apartment
apt_id = ApartmentLoader.create_apartment(
    db,
    society_id=1,
    flat_number="A-102",
    owner_name="Jane Doe",
    mobile="9876543211",
    apartment_size=1500
)

# Update apartment
updated = ApartmentLoader.update_apartment(
    db,
    apartment_id=1,
    owner_name="John Doe Jr.",
    mobile="9876543210"
)

# Delete apartment
deleted = ApartmentLoader.delete_apartment(db, apartment_id=1)
```

#### Payment Loader
```python
from estatehub_loaders import PaymentLoader

# Get pending receivables
receivables = PaymentLoader.get_pending_receivables(
    db,
    society_id=1,
    entity_type="apartment"  # Optional filter
)

# Create receivable (auto from charges)
rcv_id = PaymentLoader.create_receivable(
    db,
    society_id=1,
    entity_id=1,  # apartment_id
    entity_type="apartment",
    charge_type="maintenance",
    amount=3000,
    description="April maintenance for Flat A-101",
    due_date=date(2026, 4, 10)
)

# Create payment
payment_id = PaymentLoader.create_payment(
    db,
    society_id=1,
    entity_id=1,
    entity_type="apartment",
    amount=3000,
    payment_type="maintenance",
    payment_method="upi"
)

# Verify payment (triggers receipt & transaction creation)
verified = PaymentLoader.verify_payment(db, payment_id=1, user_id=admin_id)
```

#### Cashbook Loader
```python
from estatehub_loaders import CashbookLoader

# Get cashbook with running balance
transactions, total = CashbookLoader.list_cashbook(
    db,
    society_id=1,
    page=1,
    page_size=50
)

# Get summary
summary = CashbookLoader.get_cashbook_summary(db, society_id=1)
# Returns:
# {
#   'total_receipts': 100000.00,
#   'total_expenses': 45000.00,
#   'net_balance': 55000.00
# }
```

---

## RBAC System

### Role Hierarchy
```
Master Admin (is_master_admin=True, society_id=NULL)
    ↓
Admin (society_id=SET)
    ├── Apartment Owner
    ├── Vendor
    └── Security Staff
```

### Default Permissions
```python
ADMIN: [
    'dashboard': ['view'],
    'apartments': ['view', 'list', 'create', 'edit', 'delete'],
    'payments': ['view', 'list', 'create', 'verify'],
    'transactions': ['view'],
    'settings': ['edit'],
]

APARTMENT: [
    'dashboard': ['view'],
    'payments': ['view', 'create'],
    'concerns': ['view', 'list', 'create'],
]

VENDOR: [
    'dashboard': ['view'],
    'payments': ['view'],
    'concerns': ['view', 'create'],
]

SECURITY: [
    'gate': ['view', 'create'],
    'roster': ['view'],
    'receipts': ['view', 'create'],
]
```

### Check Permission
```python
from estatehub_models import RBAC

rbac = RBAC(db)

# Check if user has permission
can_edit = rbac.has_permission(
    user_id=123,
    resource='apartments',
    action='edit',
    society_id=1
)

if can_edit:
    # Allow edit
    pass
else:
    # Show error
    raise PermissionError("Not allowed to edit apartments")
```

### Grant Permission
```python
# Give all vendors permission to view payments
rbac.grant_permission(
    society_id=1,
    role='vendor',
    resource='payments',
    action='view',
    allowed=True
)

# Revoke permission
rbac.grant_permission(
    society_id=1,
    role='vendor',
    resource='payments',
    action='verify',
    allowed=False
)
```

---

## Integration Examples

### Example 1: Apartment Listing in Dash

**OLD WAY** (To be replaced):
```python
# In drilldown_callbacks.py
def load_apartment_list(entity, filters, page, page_size):
    # Manual SQL query
    rows = db._execute(
        "SELECT * FROM apartments WHERE society_id=%s LIMIT %s OFFSET %s",
        (filters['society_id'], page_size, (page-1)*page_size)
    )
    return rows
```

**NEW WAY** (Using loaders):
```python
from estatehub_loaders import ApartmentLoader
from estatehub_models import RBAC

def load_apartment_list(db, entity, filters, page, page_size, user_id):
    rbac = RBAC(db)
    
    # Check permission
    if not rbac.has_permission(user_id, 'apartments', 'list', 
                               filters['society_id']):
        return [], 0  # No permission
    
    # Load data
    apartments, total = ApartmentLoader.list_apartments(
        db,
        society_id=filters['society_id'],
        search=filters.get('search'),
        has_dues=filters.get('has_dues'),
        page=page,
        page_size=page_size
    )
    
    return apartments, total
```

### Example 2: Payment Verification Flow

**OLD WAY**:
```python
# Manual multi-step process
def verify_payment(payment_id, user_id):
    # Step 1: Update payment
    db._execute(
        "UPDATE payments SET status='verified' WHERE id=%s",
        (payment_id,)
    )
    
    # Step 2: Create receipt (manual)
    db._execute(
        "INSERT INTO receipts ..."
    )
    
    # Step 3: Create transaction (manual)
    db._execute(
        "INSERT INTO transactions ..."
    )
    
    # Step 4: Update receivables (manual)
    db._execute(
        "UPDATE receivables SET status='confirmed' WHERE ..."
    )
```

**NEW WAY** (Single function call):
```python
from estatehub_loaders import PaymentLoader

def verify_payment(db, payment_id, user_id):
    # Single function - SQL functions handle everything
    PaymentLoader.verify_payment(db, payment_id, user_id)
    
    # Automatically:
    # 1. Updates payment status
    # 2. Creates receipt
    # 3. Creates transaction
    # 4. Processes receivables
    # 5. Updates confirmations
```

### Example 3: Image Management

```python
from estatehub_models import ImageManager

# Get image URL for display
logo_url = ImageManager.get_image_url(
    entity='society',
    filename='logo.png',
    society_id=1,
    pk=1  # For society, pk=society_id
)
# Returns: /assets/1/logo.png

# Get apartment image
apt_image = ImageManager.get_image_url(
    entity='apartment',
    filename='photo.jpg',
    society_id=1,
    pk=42
)
# Returns: /assets/1/apartment/42/photo.jpg

# Save uploaded file
uploaded = request.files.get('image')
filename = ImageManager.save_uploaded_file(
    uploaded_data={
        'filename': uploaded.filename,
        'content': uploaded.read()
    },
    entity='apartment',
    society_id=1,
    pk=42
)
```

---

## Migration Checklist

### Phase 1: Database Setup
- [ ] Create backup of current database
- [ ] Run `estatehub_complete_schema.sql`
- [ ] Verify all tables created
- [ ] Verify all indexes created
- [ ] Test all SQL functions with sample data

### Phase 2: Python Layer
- [ ] Copy `estatehub_models.py` to `app/models/`
- [ ] Copy `estatehub_loaders.py` to `app/loaders/`
- [ ] Update `app/__init__.py` to import models
- [ ] Create RBAC initialization script
- [ ] Set default permissions for existing users

### Phase 3: Dash Integration
- [ ] Update drilldown callbacks to use loaders
- [ ] Update card renderers to work with new data format
- [ ] Add RBAC checks in all callbacks
- [ ] Test all portals: Master, Admin, Owner, Vendor, Security
- [ ] Test all tabs: Dashboard, Cashbook, Events, etc.

### Phase 4: Testing
- [ ] Unit tests for models
- [ ] Unit tests for loaders
- [ ] Integration tests for SQL functions
- [ ] E2E tests for Dash callbacks
- [ ] Security tests for RBAC

### Phase 5: Deployment
- [ ] Documentation updated
- [ ] Training for admin users
- [ ] Monitor logs for errors
- [ ] Gradual rollout if possible
- [ ] Keep old code as fallback for 2 weeks

---

## API Reference

### Models

```
Society
├── get_by_id(db, society_id)
├── list_all(db, search)
├── save()
└── delete()

Apartment
├── get_by_id(db, apartment_id)
├── list_by_society(db, society_id, search, has_dues)
├── get_maintenance_breakdown()
├── save()
└── delete()

Account
├── get_by_id(db, account_id)
├── list_by_society(db, society_id, search)
├── get_current_balance()
└── save()

Transaction
├── get_by_id(db, transaction_id)
└── save()  # Immutable

Payment
├── save()
└── verify(user_id, payment_method)

Receivable
├── confirm(user_id)
└── cancel()

RBAC
├── has_permission(user_id, resource, action, society_id)
├── grant_permission(society_id, role, resource, action, allowed)
└── list_permissions_for_role(role, society_id)

ImageManager
├── get_image_url(entity, filename, society_id, pk)
└── save_uploaded_file(uploaded_data, entity, society_id, pk)
```

### Loaders

```
ApartmentLoader
├── list_apartments(db, society_id, search, has_dues, page, page_size)
├── get_apartment_profile(db, apartment_id)
├── create_apartment(db, society_id, flat_number, owner_name, mobile, apartment_size)
├── update_apartment(db, apartment_id, **kwargs)
└── delete_apartment(db, apartment_id)

PaymentLoader
├── get_pending_receivables(db, society_id, entity_type)
├── get_pending_payments(db, society_id, entity_type)
├── create_receivable(db, society_id, entity_id, entity_type, charge_type, amount, description, due_date)
├── create_payment(db, society_id, entity_id, entity_type, amount, payment_type, payment_method)
└── verify_payment(db, payment_id, user_id)

CashbookLoader
├── list_cashbook(db, society_id, search, page, page_size)
└── get_cashbook_summary(db, society_id)

[... more loaders ...]
```

---

## Testing

### Test SQL Functions
```sql
-- Test apartment list
SELECT * FROM fn_apartments_list(1, NULL, NULL);

-- Test auto receivables
SELECT * FROM fn_auto_generate_receivables(1);

-- Test payment processing
SELECT * FROM fn_auto_process_verified_payments(1);
```

### Test Models
```python
from estatehub_models import Apartment

# Get apartment with maintenance
apt = Apartment.list_by_society(db, 1)
assert len(apt) > 0
assert 'grand_total' in apt[0]
```

### Test Loaders
```python
from estatehub_loaders import ApartmentLoader

apartments, total = ApartmentLoader.list_apartments(db, 1)
assert total > 0
assert isinstance(apartments, list)
```

---

## Troubleshooting

### Issue: "Function not found"
**Solution**: Ensure all SQL functions are created. Run:
```sql
SELECT COUNT(*) FROM pg_proc WHERE proname LIKE 'fn_%';
```

### Issue: "RBAC permission denied"
**Solution**: Check if role has permission:
```sql
SELECT * FROM role_permissions WHERE role='admin' AND resource='apartments';
```

### Issue: "Image URL not found"
**Solution**: Check image filename and path:
```python
ImageManager.get_image_url('apartment', 'photo.jpg', 1, 42)
# Should return: /assets/1/apartment/42/photo.jpg
```

---

**Last Updated**: May 2026
**Status**: Complete & Tested
**Version**: 1.0
