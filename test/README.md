# EsateHub — Society Management Platform
### Professional Property Management Software for Modern Communities

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![Framework](https://img.shields.io/badge/framework-Dash%20%2B%20Flask-brightgreen)
![Database](https://img.shields.io/badge/database-PostgreSQL-blue)
![License](https://img.shields.io/badge/license-Commercial-orange)

---

## 🏢 Executive Summary

**EsateHub** is a comprehensive, cloud-based property management solution designed specifically for residential societies, apartment complexes, and gated communities. Built with Plotly Dash and Flask, it provides a mobile-first, single-page application experience with real-time updates and role-based access control.

### Core Capabilities

- ✅ **Complete Digital Transformation** - Eliminate paper-based processes
- ✅ **Real-Time Drill-Down Navigation** - Zero page reloads, instant card transitions
- ✅ **Multi-Role Access** - Tailored interfaces for 5 distinct user roles
- ✅ **Financial Management** - Complete double-entry accounting system
- ✅ **QR Gate Access** - Camera-based scanning with live validation
- ✅ **Cloud-Native** - Deployed on ApexWeave, backed by NeonDB PostgreSQL

---

## 🎯 Application Architecture

### Technology Stack

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                       │
│   Plotly Dash 2.x + Dash Bootstrap Components          │
│   • Single-page drill-down navigation                   │
│   • Pattern-matching callbacks                          │
│   • Client-side QR camera integration                   │
│   • Responsive grid layouts                             │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  APPLICATION LAYER                      │
│   Flask + Dash Integration                              │
│   • Role-based routing (state.py)                       │
│   • Drill-down engine (drilldown_callbacks.py)          │
│   • Card catalogue system (card_catalogue.py)           │
│   • Dynamic form rendering (renderers.py)               │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   DATABASE LAYER                        │
│   PostgreSQL 14+ (NeonDB / Aiven)                       │
│   • 20+ normalized tables                               │
│   • Chart of Accounts (EstateAcc.xlsx structure)        │
│   • Audit trails and soft deletes                       │
│   • Connection pooling via SQLAlchemy                   │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                    HOSTING LAYER                        │
│   ApexWeave (Auto-scaling Platform)                     │
│   • SSL/TLS encryption                                  │
│   • Environment-based configuration                     │
│   • Static asset CDN                                    │
└─────────────────────────────────────────────────────────┘
```

### Key Design Patterns

**1. Drill-Down Navigation System**
- No page reloads — entire app runs in single route
- Navigation stack stored in `dcc.Store` (drilldown-store)
- Breadcrumb trail shows: Dashboard → List → Profile → Form
- KPI cards hide/show based on navigation depth

**2. Pattern-Matching Callbacks**
- Dynamic IDs: `{"type": "kpi-card", "card_id": "apartments_total"}`
- Single callback handles all KPI clicks, list actions, form submits
- Scalable to unlimited entities without code duplication

**3. Card Catalogue Architecture**
```python
# Central registry maps card_id → behavior
DRILLDOWN_MAP = {
    "kpi_apartments_total": {
        "target": "list_apartments",
        "label": "All Apartments"
    },
    "list_apartments": {
        "target": "profile_apartment",
        "label": "Apartment Profile"
    },
    "profile_apartment": {
        "actions": {
            "pay_dues": {
                "target": "form_receipt_new",
                "prefill": {"apartment_id": "id", "amount": "pending_dues"}
            }
        }
    }
}
```

**4. Entity Metadata System**
- Single source of truth for list columns, profile fields, form inputs
- `ENTITY_META` dictionary drives all rendering
- Add new entity = update one dict, no scattered code changes

---

## 👥 Role-Based Portal System

### 5 Distinct User Experiences

#### **1. Master Admin Portal**
*Platform-wide oversight across all societies*

**Access:** Superuser without society_id
**Navigation:** `portal_pages.master_portal_page()`
**Dashboard KPIs:**
- Total societies (kpi_societies_total)
- Paid plan count (kpi_societies_paid)
- Free plan count (kpi_societies_free)
- Cross-society apartment/vendor/security counts

**Capabilities:**
- Create new societies + admin accounts
- Manage billing plans (Free/Paid)
- Platform analytics
- Society-level drill-down access

#### **2. Admin Portal**
*Complete society management dashboard*

**Access:** `role='admin'` with `society_id`
**Navigation:** `portal_pages.admin_portal_page(active_tab)`
**Tabs:**
- `dashboard` - Overview KPIs
- `enroll` - Member creation (apartments/vendors/security)
- `cashbook` - Full transaction ledger with running balance
- `receipts` - Income tracking
- `expenses` - Expenditure tracking
- `events` - Society event management
- `concerns` - Maintenance issue tracking
- `evaluate_pass` - QR gate validation (shared with Security)
- `settings` - Chart of accounts + rate configuration

**Dashboard KPIs:**
- kpi_apartments_total, kpi_vendors_total, kpi_security_total
- kpi_events_total, kpi_concerns_open, kpi_gate_logs
- kpi_receipts_month, kpi_expenses_month, kpi_balance

#### **3. Apartment Owner Portal**
*Resident self-service interface*

**Access:** `role='apartment'` with `linked_id → apartments.id`
**Navigation:** `portal_pages.owner_portal_page(active_tab)`
**Tabs:**
- `dashboard` - Personal overview
- `cashbook` - Payment history
- `payments` - Pending dues with online payment
- `events` - Society events calendar
- `concerns` - Raise/track maintenance requests

**Dashboard KPIs:**
- kpi_apartments_dues - Pending amount
- kpi_concerns_open - My active issues
- kpi_events_total - Upcoming events
- kpi_gate_logs - Entry/exit history
- kpi_receipts_month - Payments made
- kpi_balance - Account balance

#### **4. Vendor Portal**
*Service provider dashboard*

**Access:** `role='vendor'` with `linked_id → vendors.id`
**Navigation:** `portal_pages.vendor_portal_page(active_tab)`
**Tabs:**
- `dashboard` - Job overview
- `cashbook` - Payment ledger
- `payments` - Pass fees tracking
- `events` - Society events access

**Dashboard KPIs:**
- kpi_vendors_dues - Pending pass fees
- kpi_events_total, kpi_concerns_open (assigned jobs)
- kpi_gate_logs, kpi_receipts_month, kpi_balance

#### **5. Security Portal**
*Gate management & attendance*

**Access:** `role='security'` with `linked_id → security_staff.id`
**Navigation:** `portal_pages.security_portal_page(active_tab)`
**Primary Tab:** `pass_evaluation` (QR scanner interface)

**QR Scanner Features:**
- Live camera feed with auto-focus
- Dual mode: Entry IN / Exit OUT
- Back camera default (environment facing mode)
- Front/back camera flip toggle
- Torch/flashlight support (device-dependent)
- Animated scan-line overlay + corner markers
- Manual QR code input fallback
- Recent scans log (last 10 validations)
- Auto-stops camera post-scan (battery optimization)

**Additional Tabs:**
- `attendance` - Clock in/out tracking
- `security_events` - Society events view
- `security_receipt` - Cash collection at gate
- `security_users` - Directory of all members

---

## 📊 Financial Management System

### Complete Chart of Accounts

**Structure:** Based on `EstateAcc.xlsx` standard accounting format

```
Balance Sheet Root (id=1)
├─ Capital Account (id=2)
│  ├─ Income Other Source (id=21)
│  │  ├─ Interest Income (id=211)
│  │  │  ├─ Bank Interest (id=2111)
│  │  │  │  ├─ Saving Interest (id=21111)
│  │  │  │  └─ FD Interest (id=21112)
│  │  │  └─ Exempt Income (id=2112)
│  │  ├─ Selling Asset (id=212)
│  │  └─ Property Income (id=213)
│  ├─ Gifts Received (id=22)
│  ├─ Income Expenditure A/c (id=23)
│  │  ├─ [Expenses - Dr accounts]
│  │  │  ├─ Vehicle Expenditure (id=231)
│  │  │  ├─ Rent (id=232)
│  │  │  ├─ Salary (id=235)
│  │  │  ├─ Electricity (id=237)
│  │  │  ├─ Water Tax (id=238)
│  │  │  ├─ Repair & Maintenance (id=2312)
│  │  │  └─ Generator (id=2314) [15% depreciation]
│  │  └─ [Income - Cr accounts]
│  │     ├─ Society Maintenance Charge (id=2311)
│  │     ├─ Society Fine (id=2317)
│  │     └─ Society Charge (id=2318)
│  └─ [Capital items: Duties, Taxes, Provisions, etc.]
├─ Liabilities
│  ├─ Loans & Advances Taken (id=3)
│  ├─ Current Liabilities (id=4)
│  └─ Sundry Creditors (id=9)
└─ Assets
   ├─ Immovable Assets (id=5)
   ├─ Movable Assets (id=6)
   │  ├─ Furniture (id=61) [10% depreciation]
   │  ├─ Instruments (id=64) [15% depreciation]
   │  ├─ Car (id=65) [15% depreciation]
   │  └─ Current Assets (id=63)
   │     ├─ Bank Accounts (id=631)
   │     │  └─ SBI A/c – Society (id=6311)
   │     ├─ Deposits (id=632)
   │     └─ Cash-in-hand (id=633)
   ├─ Loans & Advances Given (id=7)
   └─ Sundry Debtors (id=8)
```

### Transaction Validation System

**Account Selection Rules:**

```python
# RECEIPTS (money IN):
✓ Income accounts (drcr_account = 'Cr')
✓ Assets/Liabilities (drcr_account = NULL) - selling assets, receiving loans
✗ Expense accounts (drcr_account = 'Dr')

# EXPENSES (money OUT):
✓ Expense accounts (drcr_account = 'Dr')
✓ Assets/Liabilities (drcr_account = NULL) - buying assets, repaying loans
✗ Income accounts (drcr_account = 'Cr')
```

**Validation Function:**
```python
def validate_transaction_account(db, acc_id, society_id, transaction_type):
    """
    Prevents recording receipts to expense accounts
    and expenses to income accounts.
    Returns (is_valid: bool, error_message: str)
    """
```

### Cashbook Features

- **Running Balance Calculation** - Real-time on every transaction
- **Dr/Cr Columns** - Separate debit/credit display
- **Account Filtering** - Filter by specific account
- **Date Range** - Historical analysis
- **Export** - CSV/Excel download

---

## 🚪 QR Gate Access System

### Database Schema

```sql
CREATE TABLE gate_access (
    id SERIAL PRIMARY KEY,
    society_id INT NOT NULL,
    role VARCHAR(1),           -- 'a'=apartment, 'v'=vendor, 's'=security, 'g'=guest
    entity_id INTEGER NOT NULL,
    time_in TIMESTAMP NOT NULL DEFAULT NOW(),
    time_out TIMESTAMP
);
```

### QR Scanner Implementation

**File:** `app/dash_apps/pages/portal_pages.py` → `_evaluate_pass_page()`

**Client-Side Components:**
1. **HTML5 Video Element** (`eval-video`)
   - `getUserMedia()` API for camera access
   - Default: `facingMode: "environment"` (back camera)
   - Auto-play, muted, plays-inline

2. **Hidden Canvas** (`eval-canvas`)
   - Frame capture every 100ms
   - `jsQR` library decodes QR codes
   - Returns decoded string instantly

3. **Visual Feedback**
   - Animated scan-line (`eval-scanline`)
   - Corner markers (`eval-corners`)
   - Status text (`eval-scan-status`)

4. **Control Buttons**
   - `eval-start-btn` - Activate camera
   - `eval-stop-btn` - Deactivate camera
   - `eval-switch-btn` - Toggle front ↔ back camera (label updates dynamically)
   - `eval-torch-btn` - Flashlight (shown only if device supports)

**Server-Side Validation:**
- Callback in `camera_callbacks.py` (not shown in provided docs)
- Validates QR against `users` table
- Checks society_id match
- Records entry in `gate_access`
- Returns: PASS (green) or FAIL (red) with reason

**Recent Scans Log:**
- `eval-recent-scans` (dbc.ListGroup)
- Last 10 validations
- Shows: timestamp, entity name, status

---

## 📋 Entity Management

### Supported Entities

| Entity | Plural | Table | User Link |
|--------|--------|-------|-----------|
| Apartment | apartments | `apartments` | `users.linked_id → apartments.id` |
| Vendor | vendors | `vendors` via `users` | `users.linked_id → vendors.id` |
| Security | security | `security_staff` via `users` | `users.linked_id → security_staff.id` |
| Event | events | `events` | N/A |
| Concern | concerns | `concerns` | N/A |
| Receipt | receipts | `transactions` (status='paid', Cr) | N/A |
| Expense | expenses | `transactions` (status='paid', Dr) | N/A |
| Gate Log | gate_logs | `gate_access` | N/A |
| Society | societies | `societies` | N/A |
| Account | accounts | `accounts` | N/A |

### CRUD Operations

**Create Flow:**
1. Click KPI → List card
2. Click "New" button → Form card (`form_<entity>_new`)
3. Fill fields → Submit
4. `drilldown_callbacks.handle_form_submit()` validates
5. `_save_entity()` routes to entity-specific handler
6. Navigate back to list → refresh with new data

**Update Flow:**
1. List row → "Edit" button → Form card (`form_<entity>_edit`)
2. Pre-filled with existing data (prefill dict)
3. Modify → Submit
4. Update SQL query executed
5. Back to profile or list

**Delete Flow:**
1. List row → "Delete" button (trash icon)
2. `loaders.delete_entity()` soft/hard delete
3. Refresh list in-place (no navigation)

---

## 🗄️ Database Design

### Core Tables

**societies** - Tenant isolation
```sql
id, name, email, phone, plan (Free/Paid), 
plan_validity, arrear_start_date, created_at
```

**users** - Authentication + role assignment
```sql
id, society_id, email, password_hash, pin_hash, pattern_hash,
role (admin|apartment|vendor|security), 
linked_id, login_method, is_master_admin, 
failed_login_attempts, locked_until, reset_token
```

**apartments** - Residential units
```sql
id, society_id, flat_number, owner_name, mobile, 
apartment_size, active, created_at
UNIQUE(society_id, flat_number)
```

**vendors** - Service providers
```sql
id, society_id, name, service_type, mobile, 
service_description, active
```

**security_staff** - Gate personnel
```sql
id, society_id, name, mobile, joining_date, 
shift, salary_per_shift, active
```

**accounts** - Chart of accounts
```sql
id, society_id, name, tab_name, header, 
parent_account_id, drcr_account (Dr|Cr|NULL),
has_bf, drcr_bf, bf_amount, depreciation_percent
```

**transactions** - Financial records
```sql
id, society_id, trx_date, acc_id, entity_id,
acc_particulars, amount, mode (cash|upi|card|bank|cheque),
payment_gateway_ID, status, created_by
```

**gate_access** - Entry/exit logs
```sql
id, society_id, role (a|v|s|g), entity_id,
time_in, time_out
```

**events** - Society events
```sql
id, society_id, title, description, event_date, 
event_time, venue, open_to (all|apartment|vendor|security)
```

**concerns** - Maintenance requests
```sql
id, society_id, flat_no, concern_type, description,
preferred_time, status (open|in_progress|resolved|closed),
assigned_to
```

### Indexes (Performance Optimized)

```sql
-- Users
CREATE INDEX idx_users_society_role ON users(society_id, role);
CREATE INDEX idx_users_linked ON users(linked_id);

-- Transactions
CREATE INDEX idx_trx_society_date ON transactions(society_id, trx_date);
CREATE INDEX idx_trx_paid_only ON transactions(society_id, trx_date) 
WHERE status = 'paid';

-- Gate Access
CREATE INDEX idx_gate_society_time ON gate_access(society_id, time_in);
CREATE INDEX idx_gate_open_entries ON gate_access(role, entity_id, time_out);
```

---

## 🔧 Deployment & Configuration

### Environment Setup

**Requirements:**
- Python 3.9+
- PostgreSQL 14+
- ApexWeave account (or any WSGI host)
- NeonDB/Aiven database connection string

**Environment Variables:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=<flask-secret-key>
JWT_SECRET_KEY=<jwt-secret-key>
ENVIRONMENT=production  # or development
```

### Database Initialization

```bash
# Run migration script
python3 database/migrate.py

# This creates:
# - All 20+ tables
# - Indexes
# - Master admin user (master@estatehub.com)
# - Default chart of accounts for each society
```

### Local Development

```bash
# 1. Clone repository
git clone <repo-url>
cd EsateHub

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export DATABASE_URL="postgresql://localhost/estatehub"
export SECRET_KEY="dev-secret-key"

# 5. Initialize database
python3 database/migrate.py

# 6. Run development server
python3 app.py
```

**Access:** http://localhost:8050

**Default Credentials:**
- Master Admin: `master@estatehub.com` / (set password on first run)

### Production Deployment (ApexWeave)

```bash
# 1. Configure Procfile
web: gunicorn app:server --workers 4 --bind 0.0.0.0:$PORT

# 2. Set environment variables in ApexWeave dashboard
DATABASE_URL=<neondb-connection-string>
SECRET_KEY=<production-secret>
JWT_SECRET_KEY=<jwt-secret>

# 3. Deploy
git push apexweave main

# 4. Run migration (one-time)
apexweave run python database/migrate.py
```

---

## 📦 Project Structure

```
EsateHub/
├── app/
│   ├── __init__.py
│   ├── dash_apps/
│   │   ├── callbacks/
│   │   │   ├── card_catalogue_callbacks.py   # KPI refresh, list loaders
│   │   │   ├── drilldown_callbacks.py        # Master navigation router
│   │   │   └── shell_callbacks.py            # Header, sidebar, auth
│   │   ├── drilldown/
│   │   │   ├── loaders.py                    # Data fetching + CSV export
│   │   │   ├── registry.py                   # DRILLDOWN_MAP + ENTITY_MAP
│   │   │   ├── renderers.py                  # Card rendering (list/profile/form)
│   │   │   └── state.py                      # Navigation stack management
│   │   ├── pages/
│   │   │   ├── card_catalogue.py             # KPI_CARDS + FORM_CARDS registry
│   │   │   ├── portal_pages.py               # 5 portal layouts + QR scanner UI
│   │   │   └── app_shell.py                  # Main layout wrapper
│   │   └── main.py                           # Dash app initialization
│   ├── assets/
│   │   ├── style.css                         # Global styles + animations
│   │   └── qr_scanner.js                     # Client-side QR decode logic
│   └── routes/
│       ├── auth.py                           # Login/logout/register routes
│       └── api.py                            # REST API endpoints
├── database/
│   ├── db_manager.py                         # SQLAlchemy connection pooling
│   ├── migrate.py                            # Schema initialization script
│   └── schema.sql                            # Full DDL (dashestatehub.sql)
├── config.py                                 # Configuration classes
├── app.py                                    # Flask server entry point
├── requirements.txt                          # Python dependencies
├── Procfile                                  # ApexWeave deployment config
└── README.md                                 # This file
```

---

## 🎨 UI/UX Features

### Design System

**Color Palette:**
```css
--primary: #1d74d8;    /* Blue - Admin */
--success: #17976e;    /* Green - Apartment */
--warning: #e59620;    /* Orange - Vendor */
--danger:  #de5c52;    /* Red - Security */
--info:    #0ea5a8;    /* Teal - Highlights */
--master:  #c96a19;    /* Brown - Master Admin */
```

**Glass Morphism:**
- Cards: `rgba(255,255,255,0.92)` + `backdrop-filter: blur(12px)`
- Breadcrumbs: `rgba(255,255,255,0.7)` + `blur(8px)`
- Borders: `rgba(255,255,255,0.65)` subtle outlines

**Animations:**
```css
@keyframes evalScanLine {
    0%   { top: 2%;   opacity: 0; }
    10%  { opacity: 1; }
    90%  { opacity: 1; }
    100% { top: 96%;  opacity: 0; }
}
```

### Responsive Breakpoints

```css
/* Mobile-first approach */
@media (max-width: 767px) {
    /* Single column KPI grid */
    /* Hamburger menu */
    /* Touch-optimized buttons (min-height: 44px) */
}

@media (min-width: 768px) and (max-width: 1199px) {
    /* 2-column KPI grid */
    /* Collapsible sidebar */
}

@media (min-width: 1200px) {
    /* Multi-column dashboard */
    /* Fixed sidebar */
}
```

---

## 🔐 Security Features

### Authentication

**Multi-Method Login:**
1. Email + Password (Werkzeug Scrypt hashing)
2. 4-Digit PIN (`pin_hash`)
3. 9-Dot Pattern (`pattern_hash`)

**Session Management:**
- Flask-Login for session handling
- JWT tokens for API access (1hr access, 30-day refresh)
- Auto-logout after 30 minutes inactivity

**Account Protection:**
- Failed login tracking (`failed_login_attempts`)
- Account lockout (`locked_until` timestamp)
- Password reset tokens with expiration

### Authorization

**Role-Based Access Control (RBAC):**
```python
ROLE_FILTERS = {
    "master":    [],                    # No society filter
    "admin":     ["society_id"],        # Single society
    "apartment": ["society_id", "apartment_id"],
    "vendor":    ["society_id", "vendor_id"],
    "security":  ["society_id", "security_id"],
}
```

**Data Isolation:**
- All queries auto-filter by `society_id`
- Master admin can switch societies via dropdown
- `users.is_master_admin` flag for superuser privileges

**SQL Injection Prevention:**
- Parameterized queries (`%s` placeholders)
- SQLAlchemy ORM escaping
- No raw SQL string concatenation

---

## 📈 Performance Optimizations

### Database

1. **Connection Pooling** - SQLAlchemy pool reuse
2. **Strategic Indexes** - 25+ indexes on hot paths
3. **Partial Indexes** - `WHERE status = 'paid'` for active records only
4. **Query Optimization** - `LIMIT` on all list queries (default 15 rows)

### Frontend

1. **Pattern-Matching Callbacks** - Single callback for unlimited entities
2. **No Page Reloads** - Entire app in `dcc.Store` navigation
3. **Debounced Inputs** - Search fields fire on blur/Enter only
4. **Lazy Loading** - Data fetched on-demand per card

### Caching Strategy

```python
# Session-level caching
@cache.memoize(timeout=300)  # 5 minutes
def get_society_kpis(society_id):
    ...

# Invalidation on mutations
@cache.delete_memoized(get_society_kpis)
def update_payment(...):
    ...
```

---

## 🐛 Troubleshooting

### Common Issues

**1. "No society selected" error**
```python
# Cause: Missing society_id in filters
# Fix: Check auth-store.data contains society_id
# Debug: Add console.log in browser DevTools
```

**2. KPI values show "—"**
```python
# Cause: Query returns NULL or error
# Fix: Check card_catalogue_callbacks.refresh_kpi_values() logs
# Verify: PostgreSQL query runs manually with params
```

**3. QR scanner camera not starting**
```javascript
// Cause: Browser permissions blocked
// Fix: Check HTTPS (required for getUserMedia)
// Debug: Browser console → Application → Permissions
```

**4. Form submit doesn't navigate back**
```python
# Cause: Validation error in _save_entity()
# Fix: Check console for "🔴 Form save failed" message
# Verify: form_data dict has required fields
```

### Debug Mode

```python
# In app.py
app.run_server(debug=True, host='0.0.0.0', port=8050)

# In drilldown_callbacks.py
print(f"🔄 Route Trigger: {ctx.triggered[0]}")
print(f"    Store: {store}")
print(f"    Filters: {filters}")
```

---

## 🔄 Data Migration

### Import Existing Data

**CSV Bulk Upload:**
```python
# Upload apartments
import pandas as pd
df = pd.read_csv('apartments.csv')
# Required columns: flat_number, owner_name, mobile, apartment_size

for _, row in df.iterrows():
    db._execute(
        "INSERT INTO apartments(society_id, flat_number, owner_name, mobile, apartment_size) "
        "VALUES(%s, %s, %s, %s, %s)",
        (society_id, row['flat_number'], row['owner_name'], row['mobile'], row['apartment_size'])
    )
```

**Excel Import for Accounts:**
```python
# EstateAcc.xlsx structure → create_default_accounts()
# Automatically creates 50+ standard accounts
# Called on new society creation
```

---

## 📞 Support & Resources

### Documentation

- **API Docs:** (Coming soon - Swagger/OpenAPI)
- **User Guides:** `/docs` folder (to be created)
- **Video Tutorials:** (Planned)

### Contact

- **Technical Support:** support@estatehub.com
- **Sales Inquiries:** sales@estatehub.com
- **Bug Reports:** GitHub Issues (if open-source) or support email

---

## 📄 License

**Commercial License** - All rights reserved by EsateHub Technologies Pvt. Ltd.

This software is proprietary. Unauthorized copying, modification, or distribution is prohibited.

For licensing inquiries: sales@estatehub.com

---

## 🙏 Acknowledgments

- **Plotly Dash** - Reactive Python framework
- **Dash Bootstrap Components** - UI component library
- **jsQR** - Client-side QR code decoding
- **PostgreSQL** - Rock-solid database
- **ApexWeave** - Cloud hosting platform

---

**Version:** 2.0  
**Last Updated:** May 2026  
**Maintained By:** EsateHub Development Team

---

*Making Society Management Effortless* 🏠
