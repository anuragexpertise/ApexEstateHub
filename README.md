# EstateHub
### The Complete Society Management Platform

> **Multi-tenant · Role-aware · Real-time · Zero-reload**
> Built on Python Dash + Flask + PostgreSQL (Aiven) · Hosted on Render

---

## Table of Contents

1. [What is EstateHub?](#1-what-is-estatehub)
2. [Feature Highlights](#2-feature-highlights)
3. [Architecture Overview](#3-architecture-overview)
4. [The Five Portals](#4-the-five-portals)
5. [Portal Data Scoping](#5-portal-data-scoping)
6. [Drill-Down Navigation Engine](#6-drill-down-navigation-engine)
7. [Authentication & Security](#7-authentication--security)
8. [KPI Dashboard System](#8-kpi-dashboard-system)
9. [Financial Module](#9-financial-module)
10. [Pay Dues — Five Paths](#10-pay-dues--five-paths)
11. [Gate Pass & QR Scanning](#11-gate-pass--qr-scanning)
12. [Default Profile (No KPI Selected)](#12-default-profile-no-kpi-selected)
13. [Customize Tab — Layout Editor & KPI Inspector](#13-customize-tab--layout-editor--kpi-inspector)
14. [File & Image Management](#14-file--image-management)
15. [Tech Stack Reference](#15-tech-stack-reference)
16. [PostgreSQL Function Index](#16-postgresql-function-index)
17. [Codebase Map](#17-codebase-map)
18. [Critical Dash Rules](#18-critical-dash-rules)
19. [Known Bugs & Fixes Applied](#19-known-bugs--fixes-applied)
20. [🚩 Open Design Subtleties & Flagged Caveats](#20--open-design-subtleties--flagged-caveats)
21. [🗑️ Legacy Code Removal Guide](#21-️-legacy-code-removal-guide)
22. [Deployment Notes](#22-deployment-notes)
23. [Table of Workflows](#23-table-of-workflows)

---

## 1. What is EstateHub?

**EstateHub** is a **multi-tenant society management web application** that gives housing societies, apartment complexes, and gated communities a single platform to manage residents, vendors, security staff, finances, events, and gate access — all without page reloads.

Each society gets its own fully isolated data silo scoped by `society_id`. A **Master Admin** oversees all societies on the platform. Within each society, an **Admin** manages day-to-day operations across five role-scoped portals, each seeing only data relevant to them.

---

## 2. Feature Highlights

| Category | Features |
|---|---|
| **Portals** | Master Admin · Society Admin · Apartment Owner · Vendor · Security |
| **Auth** | Password · PIN · Pattern · JWT tokens · Master Admin flag |
| **Navigation** | Zero-reload SPA — KPI → List → Profile → Form drill-down |
| **Financials** | Cashbook · Receipts · Expenses · Receivables · payables · FIFO Pay Dues |
| **Entities** | Apartments · Vendors · Security Staff · Societies · Accounts · Assets |
| **Operations** | Events · Concerns/Complaints · Gate Logs · Attendance · NOC |
| **Gate Pass** | Fernet-encrypted QR · Dual-mode camera scanner · Entry IN / Exit OUT |
| **Reports** | CSV & XLS export on every list · KPI Audit Report |
| **Customization** | Drag-and-drop KPI layout editor per portal+tab · KPI SQL Inspector |
| **Images** | WebP compression · Logo · Login background · Secretary sign · Profile photos |
| **DB** | PostgreSQL `fn_*` stored functions · `%s` parameterised queries via psycopg2 |
| **Security Portal** | Pending receipt creation → admin verification workflow |
| **NOC** | Eligibility check → rich-text editor → Print / Save HTML / Email |
| **Gate Pass (NFC)** | Web NFC API — write signed pass payload directly to an NFC tag from the browser |
| **Patrol** | Interactive Leaflet map for patrol-location create/reissue, with geofencing |
| **Bank Reconciliation** | CSV/Excel bank-statement upload, exact + fuzzy matching against receipts/expenses, per-row manual reconcile |
| **Society Onboarding** | First-time Setup Wizard (charges, GST/TDS defaults, brought-forward) + Agreement e-sign flow with Print/PDF/Email |
| **Bulk Enrollment** | CSV upload for apartments/vendors/security with template download |

---

## 3. Architecture Overview

```
Browser (Dash SPA)
│
├── auth/                     ← JWT handler and authentication logic
├── models/                   ← SQLAlchemy models (User, Transaction, Apartment, etc.)
├── routes/                   ← Flask routes and API endpoints
├── services/                 ← Core business logic (auth, qr)
│
├── app_shell.py              ← Top-level layout: header, sidebar, modals, stores
│
├── callbacks/                ← 34 modules registered in a single ordered
│   │                            sequence by callbacks/__init__.py; the core
│   │                            navigation/auth modules below, plus one
│   │                            module per feature area (receipts, events,
│   │                            vendor passes, expenses, bulk enroll, bank
│   │                            reconciliation, channels, polls, patrol
│   │                            locations/NFC, QR reissue, etc.)
│   ├── shell_callbacks.py        ← URL routing, auth guard, sidebar, toast
│   ├── login_callbacks.py        ← Password / PIN / Pattern / Master login
│   ├── card_catalogue_callbacks.py  ← KPI value refresh (pattern-matched ALL)
│   ├── drilldown_callbacks.py    ← Master router: KPI→List→Profile→Form
│   ├── drillin_callbacks.py      ← Entity-picker / Bill-Group-pay modals
│   ├── qr_callbacks.py           ← QR modal, camera, gate scan, emergency
│   ├── qr_reissue_callbacks.py   ← Admin-only QR revoke/reissue (Settings tab)
│   ├── patrol_map_callbacks.py   ← Leaflet map init for patrol locations
│   ├── camera_callbacks.py       ← Image capture JS injection
│   ├── noc_callbacks.py          ← Print / PDF / Email NOC (clientside)
│   ├── agreement_callbacks.py    ← Print / PDF / Email society Agreement
│   ├── customize_callbacks.py    ← DnD layout editor
│   ├── customize_kpi_callbacks.py← KPI Inspector cascading dropdowns
│   ├── list_inspector_callbacks.py / form_inspector_callbacks.py ← column/field config
│   ├── setup_wizard_callbacks.py ← First-time society setup wizard
│   ├── bulk_enroll_callbacks.py  ← CSV bulk upload for members/staff
│   ├── bank_reconcile_callbacks.py ← Bank statement upload + reconciliation
│   ├── channel_callbacks.py / poll_callbacks.py ← Alert channels · Polls
│   ├── assign_to_callbacks.py / invite_to_callbacks.py / concern_bid_callbacks.py ← Concern workflow
│   ├── receipt_callbacks.py / expense_callbacks.py / event_ticket_callbacks.py / vendor_pass_callbacks.py ← Print/Save/Email actions
│   ├── form_autofill_callbacks.py / mode_conditional_callbacks.py / qty_stepper_callbacks.py ← form UX helpers (clientside)
│   ├── account_callbacks.py      ← Self-service change password
│   └── debug_callbacks.py        ← KPI Audit Report + SQL Tester
│
├── drilldown/
│   ├── loaders.py            ← All DB reads (fn_* functions + raw SQL)
│   ├── renderers.py          ← HTML builders for list/profile/form/pay-dues/NOC cards
│   ├── drillin.py            ← DRILLIN_CONFIG for entity-picker/Bill-Group modals
│   ├── state.py              ← Navigation stack (drilldown-store)
│   ├── registry.py           ← DRILLDOWN_MAP, ENTITY_MAP, PK_MAP
│   ├── profile_actions.py    ← Per-entity action button definitions + FIELD_VISIBILITY
│   ├── schema_introspect.py  ← Live schema → entity metadata (lazy-cached)
│   └── image_utils.py        ← WebP compression helper
│
└── pages/
    ├── portal_pages.py       ← 5 portal page layouts (KPI rows + drill panel)
    └── card_catalogue.py     ← KPI_CARDS dict · DEFAULT_LAYOUTS · make_kpi_card()
```

> See [§17 Codebase Map](#17-codebase-map) for the full, current file-by-file
> breakdown (kept in sync with `callbacks/__init__.py`'s actual registration
> order, not a hand-maintained summary).

### Single-Page Flow

```
Login → auth-store populated
    └─► shell_callbacks.route_page()
            ├── renders portal page into #portal-content
            └── writes portal-content-store {"rendered": True}

portal-content-store change
    └─► drilldown_callbacks.route_drilldown()  [page-load trigger]
            └── active_card = "dashboard_*"
                └─► _render_default_profile()  → user's own profile shown below KPIs

KPI card click
    └─► route_drilldown()
            ├─► loaders.load_list()          → DB via fn_*
            ├─► renderers.render_list_card() → HTML table
            └─► kpi-row hidden, drill-content populated

List row click
    └─► route_drilldown()
            ├─► loaders.load_profile()           → DB
            └─► renderers.render_profile_card()  → HTML

Profile action / Form submit
    └─► handle_form_submit()
            └─► _save_entity() → DB write → navigate_back() → list refresh
```

---

## 4. The Five Portals

### 4.1 Master Admin Portal
Accessible only to users flagged `is_master_admin = TRUE` in DB. `society_id = NULL`.

- Platform-wide KPIs: total societies, plan distribution, all apartments/vendors/security
- Drill into any society → view/edit profile, manage plan validity
- Create new societies with admin credentials

### 4.2 Admin Portal (Society Admin)
Primary management console. Scoped to `society_id`.

**Tabs:** Dashboard · Enroll · Cashbook · Receipts · Expenses · Events · Concerns · Gate Pass · Customize · Settings

- Full CRUD on all entities (apartments, vendors, security staff)
- Financial ledger: auto-generated receivables, FIFO pay dues, receipts, expenses
- NOC issuance with eligibility check
- Verify pending receipts created by security portal
- KPI dashboard customization (drag-and-drop layout editor)
- Concern assignment and status tracking

### 4.3 Apartment Portal (Owner / Family / Tenant / Visitor)
Self-service for residents. Scoped to `[society_id, apartment_id]`.

**Tabs:** Dashboard · My payables · My Charges · Events · Concerns · Cashbook · Settings

- View own pending dues, payment history, charges
- Raise and track maintenance concerns
- View upcoming events, own gate pass QR
- Default view: own apartment profile card below KPIs

#### Apartment User Type Permissions Matrix

| User Type | View Bills | Raise Concerns | Approve Gate Pass | Add Users |
|---|---|---|---|---|
| **owner** | Yes | Yes | Yes | family, tenant, visitor |
| **family** | Yes | Yes | Yes | visitor only |
| **tenant** | No | Yes | Yes | visitor only |
| **visitor** | No | No | No | None |


### 4.4 Vendor Portal
For registered service vendors. Scoped to `[society_id, vendor_id]`.

**Tabs:** Dashboard · My Cashbook · My Charges · Events · Settings

- View pass fees and payment status
- Gate pass QR generation and validity
- Default view: own vendor profile card below KPIs

### 4.5 Security Portal
For gate security staff. Scoped to `[society_id, security_id]`.

**Tabs:** Gate Pass Evaluation · Attendance · All Users · My Cashbook · Receipts · Events · Settings

- **Primary:** QR code camera scanning — Entry IN / Exit OUT
- Create cash receipts at gate (saved as `status='pending'`, verified by admin)
- Attendance clock-in / clock-out
- View apartments, vendors, events (read-only)
- Default view: own security profile card below KPIs

---

## 5. Portal Data Scoping

Every list, profile, KPI, and form is filtered at the data layer by the portal's identity. This is enforced at two points:

### 5.1 KPI Scoping (`card_catalogue_callbacks.py`)

```python
# Admin / Master: use KPI's own SQL with society_id
params = tuple(sid for _ in range(n_params))

# Apartment portal: override to entity-specific SQL
"kpi_apartments_dues": (
    "SELECT COALESCE(SUM(amount-paid_amount),0) AS v FROM receivables
     WHERE entity_id=%s AND role='apartment' AND status IN ('pending','partial')",
    (apt_id,),
)

# Vendor portal: override with vendor_id
# Security portal: override with sec_staff_id
```

### 5.2 List / Profile Scoping (`drilldown_callbacks._apply_portal_filters`)

```python
def _apply_portal_filters(filters, auth):
    role = auth.get("role")
    if role == "apartment":
        filters["apartment_id"] = auth.get("apartment_id") or auth.get("linked_id")
    elif role == "vendor":
        filters["vendor_id"] = auth.get("user_id")      # fn_vendors_list uses users.id
    elif role == "security":
        filters["security_id"] = auth.get("linked_id")  # security_staff.id
    return filters
```

`loaders.load_list()` short-circuits to single-row query when portal entity filter present:
```python
if entity == "apartments" and p_apt_id:
    rows = db._execute("SELECT * FROM fn_apartments_list(%s,%s,NULL) WHERE id=%s", ...)
    return rows, len(rows)
```

### 5.3 Scoping Summary

| Portal | society_id | apartment_id | vendor_id | security_id |
|---|---|---|---|---|
| Master | ✗ (all) | ✗ | ✗ | ✗ |
| Admin | ✓ | ✗ | ✗ | ✗ |
| Apartment | ✓ | ✓ (`linked_id`) | ✗ | ✗ |
| Vendor | ✓ | ✗ | ✓ (`user_id`) | ✗ |
| Security | ✓ | ✗ | ✗ | ✓ (`linked_id`) |

---

## 6. Drill-Down Navigation Engine

The heart of the UX. All navigation is **stateful and stackable** — no page reloads.

### Navigation Stack (`drilldown-store`)

```json
{
  "stack": [
    {"card_id": "dashboard_admin",    "label": "Dashboard",  "filters": {"society_id": 1}, "entity_pk": null},
    {"card_id": "list_apartments",    "label": "Apartments", "filters": {"society_id": 1}, "entity_pk": null},
    {"card_id": "profile_apartment",  "label": "Flat A-101", "filters": {"society_id": 1}, "entity_pk": 42},
    {"card_id": "form_pay_dues_new",  "label": "Pay Dues",   "prefill": {"amount": 3500},  "entity_pk": 42}
  ],
  "active_card": "form_pay_dues_new",
  "filters":     {"society_id": 1},
  "prefill":     {"entity_id": 42, "role": "apartment", "amount": 3500}
}
```

### Card ID Convention

| Prefix | Example | Meaning |
|---|---|---|
| `dashboard_` | `dashboard_admin` | Home card — shows default profile |
| `kpi_` | `kpi_apartments_total` | Clickable KPI metric |
| `list_` | `list_apartments` | Paginated data table |
| `profile_` | `profile_apartment` | Single record detail view |
| `form_<entity>_new` | `form_receipt_new` | Create form |
| `form_<entity>_edit` | `form_apartment_edit` | Edit form (pre-filled) |
| `form_pay_dues_new` | — | Special FIFO payment form |
| `form_noc_print` | — | NOC rich-text editor |
| `modal_qr` | — | Gate pass QR modal |

### Portal Permission Matrix

```python
_PORTAL_PERMS = {
    ("admin",     "*"):            {"view", "edit", "delete", "new"},
    ("master",    "societies"):    {"view", "edit", "new"},
    ("master",    "*"):            {"view"},
    ("apartment", "concerns"):     {"view", "new"},
    ("apartment", "*"):            {"view"},   # own data only
    ("vendor",    "*"):            {"view"},   # own data only
    ("security",  "receipts"): {"view", "new"},
    ("security",  "*"):            {"view"},
}
```

### DRILLDOWN_MAP — Key Entries

```python
# KPI → List (examples)
"kpi_apartments_total":   {"target": "list_apartments",  "label": "All Apartments"},
"kpi_apartments_dues":    {"target": "list_apartments",  "label": "Apartments With Dues",
                           "filter": {"has_dues": True}},
"kpi_receivables_total":  {"target": "list_receivables", "label": "Receivables Total"},  # ← fixed
"kpi_receipts_month":     {"target": "list_receipts","label": "Receipts This Month"},

# List → Profile
"list_apartments":    {"target": "profile_apartment",    "label": "Apartment Profile"},
"list_receivables":   {"target": "profile_receivable",   "label": "Receivable Details"},
"list_receipts":  {"target": "profile_receipt_entry","label": "Receipt Details"},

# Profile actions in registry.py
"profile_apartment": {"actions": {
    "pay_dues":   {"target": "form_pay_dues_new",  ...},
    "gate_pass":  {"target": "modal_qr",           ...},
    "new_concern":{"target": "form_concern_new",   ...},
    "issue_noc":  {"target": "form_noc_print",     ...},
}},
```

---

## 7. Authentication & Security

### Login Methods

```
Login modal:
  [Password]   email + password  → authenticate_user(method="password")
  [PIN]        email + 4-digit   → authenticate_user(method="pin")
  [Pattern]    email + dot-grid  → authenticate_user(method="pattern")
  [Master]     email + password  + is_master_admin=TRUE DB check
```

### Auth Store Schema

```python
{
    "user_id":       int,
    "email":         str,
    "role":          "admin" | "apartment" | "vendor" | "security",
    "society_id":    int | None,   # None for master admin
    "linked_id":     int,          # FK → apartments.id / vendors.id / security_staff.id
    "apartment_id":  int | None,   # = linked_id when role="apartment"
    "vendor_id":     int | None,   # vendors.id (NOT users.id)
    "authenticated": True,
    "token":         str           # JWT
}
```

> **Note:** `vendor_id` in auth-store is `vendors.id` (via `linked_id`), but `fn_vendors_list` returns `users.id` as the row `id`. When loading a vendor profile or applying portal filters, use `auth.get("user_id")` to match `fn_vendors_list`'s `id` column.

### Forgot Password Flow

1. User enters email → `request_password_reset()` → SHA-256 token stored in DB with 2h expiry
2. Token printed to server log (email delivery hookable in `auth_service.py`)
3. User enters token + new password → `reset_password()` → hash updated, token cleared

---

## 8. KPI Dashboard System

### How KPIs Work

1. **Definition** — each KPI is a dict entry in `KPI_CARDS` (`card_catalogue.py`)
2. **Shell rendered** — `make_kpi_card()` creates the clickable card with `id={"type":"kpi-value","card_id":"..."}` showing `"—"` placeholder
3. **Value filled** — `refresh_kpi_values()` pattern-matches ALL `kpi-value` IDs, runs each SQL query on `url.pathname` or `auth-store` change
4. **Portal scoping** — apartment/vendor/security portals use entity-specific SQL overrides, not the global `society_id`-scoped query
5. **Click action** — `DRILLDOWN_MAP` maps each `kpi_*` id to a target list card + optional filter

### KPI Definition Schema

```python
"kpi_apartments_total": {
    "query":  "SELECT COUNT(*) AS v FROM apartments WHERE society_id=%s AND active=TRUE",
    "params": 1,          # number of %s bindings (all are society_id repeats)
    "format": "number",   # number | currency | percent | date | text
    "icon":   "fa-home",
    "color":  "#1859b8",
    "title":  "Apartments",
    "group":  "active",   # subtitle shown under value
},
```

### Format Types

| Format | Example Output | Notes |
|---|---|---|
| `number` | `1,234` | Integer with comma separator |
| `currency` | `₹2.50L` / `₹1.20Cr` / `₹850` | Auto-abbreviates at 1L / 1Cr |
| `percent` | `12.5%` | One decimal place |
| `date` | `in 14d` / `3d ago` / `24 Jun 2025` | Relative within 30d, absolute beyond |
| `text` | `Active` | `.title()` cased |

### KPI Audit Report

Navigate to **Admin → Customize → KPI Audit** and click **Run Full Audit**:
- Executes every KPI query against the live DB with your `society_id`
- Status per KPI: ✓ OK / ⚠ NULL / ✗ ERROR / ⊕ DUPLICATE KEY
- Shows raw value, formatted value, execution time (ms)
- Detects duplicate keys in `KPI_CARDS` dict via source-file regex scan

---

## 9. Financial Module

### Table Roles

| Table | Type | Who creates | Status flow | Posts to transactions |
|---|---|---|---|---|
| `receivables` | Auto-calculated credits | `fn_auto_generate_receivables` | pending → partial → paid | On admin verify |
| `receipts` | Manual credits | Admin / Security | pending → confirmed / cancelled | On create (admin) or verify (security) |
| `payables` | Auto-calculated debits | `fn_auto_generate_payables` | pending → verified / cancelled | On admin verify |
| `expenses` | Manual debits | Admin | confirmed immediately | On create |
| `transactions` | Immutable ledger | All of above | paid | Source of truth |

`transactions.role` (`'apartment' / 'vendor' / 'security' / 'other' / 'assets'`) is written on every insert alongside `entity_id`, mirroring the `role` column already on `receivables`/`receipts`/`payables`/`expenses`. It exists because `entity_id` alone is not a safe join key — an apartment id and a vendor id can collide — so any query resolving an entity's display name (`fn_account_ledger_fy`, `fn_cashbook_paired_v3`, `fn_cashbook_month_page`) must join `apartments`/`vendors`/`security_staff` **with `AND t.role = '...'`**, not on `entity_id` alone. `role = 'assets'` covers asset purchase/sale/writeoff legs, where `entity_id` points at `assets.id` — a distinct ID space that should never match an entity-name join.

### Two Financial Engines — Use Only Engine 1

**Engine 1 (canonical):** `fn_verify_receivable()` / `fn_verify_payment()` → INSERT into `transactions`. Called by Python `loaders.verify_receivable()` / `loaders.verify_payment()`.

**Engine 2 (deprecated):** Status-cache approach that writes pass/fail back into status columns on list page load. Do not call.

### Account Types

| `drcr_account` | Used For | Validation |
|---|---|---|
| `Cr` | Income accounts — Receipts | Cannot use for Expenses |
| `Dr` | Expense accounts — Expenses | Cannot use for Receipts |
| `NULL` / `''` | Asset / Balance-sheet accounts | Allowed for both |

### fn_save_receipt / fn_save_expense — Correct Argument Order

```python
# CORRECT call order (p_society_id, p_acc_id, p_particulars, p_amount, entity_id, role, mode, date, user_id, cheque_no, trx_id, source_reference)
db._execute(
    "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    (sid, acc_id, particulars, amt, entity_id, role, mode, date, user_id, cheque_no, trx_id, source_reference)
)
# NOTE: entity_id and role come AFTER amount, not before acc_id
```

### Receivables Auto-Generation

`fn_auto_generate_receivables(society_id)` is called inside `fn_apartments_list()` on every list load. It:
1. Reads `calc_start_date` from `societies`
2. Loops all active apartments
3. Finds charge rule from `apt_charges_fines_basis` (per-apartment or society-wide)
4. Inserts one `receivables` row per month from `calc_start_date` to now (ON CONFLICT DO NOTHING)

**Bug fixed:** When no charge rule exists, the fallback previously set `acc_id = NULL` and `interest_acc_id = NULL`, causing `fn_verify_receivable` to refuse with "No income account set". Fix: fallback now looks up accounts by name:

```sql
SELECT id INTO v_fallback_maint_acc FROM accounts
WHERE society_id = p_society_id AND name ILIKE '%Society Maintenance%' AND drcr_account='Cr' LIMIT 1;
```

One-time patch to fix existing NULL rows:
```sql
UPDATE receivables r
SET acc_id = (SELECT id FROM accounts WHERE society_id=r.society_id AND name ILIKE '%Society Maintenance%' AND drcr_account='Cr' LIMIT 1),
    interest_acc_id = COALESCE(r.interest_acc_id, (SELECT id FROM accounts WHERE society_id=r.society_id AND name ILIKE '%Interest Income%' AND drcr_account='Cr' LIMIT 1))
WHERE r.acc_id IS NULL AND r.role='apartment' AND r.status IN ('pending','partial');
```

### Interest Calculation & Subtleties

EstateHub calculates simple interest on overdue maintenance receivables dynamically. Key subtleties to note regarding financial calculations:

1. **Daily Pro-Rata Formula**: Interest is calculated using a standard banking 30-day month pro-rata basis:
   `Interest = Unpaid Principal × Monthly Rate × (Total Days Elapsed / 30.0)`.
   This ensures that partial months (including the current incomplete month) are fairly calculated down to the exact day.
2. **Compound Interest Prevention**: To comply with standard housing society by-laws, interest is calculated strictly on the *unpaid principal* (the base amount), never on accumulated past interest.
3. **Database Precision**: The `interest_months_applied` column in the `receivables` table is defined as `NUMERIC(10,4)` to handle the exact decimal fraction of months elapsed (e.g., 28 days = `0.9333` months).
4. **FIFO Allocation**: When an apartment pays dues, the `fn_pay_apartment_dues_fifo` function applies the payment to the oldest outstanding receivable first. Within a specific receivable, payments are applied to clear interest first, then the principal base amount.
5. **Component Breakdown**: When rendering the "My Transactions" ledger, the system runs a Common Table Expression (CTE) to fetch a grouped string (e.g. `Society Maint: 1500, Sinking Fund: 200`) representing the different journal entry legs that made up the receivable.
---

## 10. Pay Dues — Five Paths

All five paths ultimately call `fn_pay_apartment_dues_fifo(apartment_id, amount, mode, confirmed_by, particulars)` which processes payables FIFO (oldest due_date first).

### Path 1 — Admin: KPI → Apartments List → Profile → Pay Dues

```
kpi_apartments_dues (DRILLDOWN_MAP → list_apartments, filter: has_dues=True)
  → list_apartments (fn_apartments_list)
    → profile_apartment (load_profile)
      → [Pay Dues] button (profile_actions.py: action_id="pay_dues", roles=["admin"])
        → form_pay_dues_new (renderers.render_pay_dues_card)
          → handle_form_submit → _save_pay_dues → loaders.pay_apartment_dues_fifo
```

### Path 2 — Security Portal: Manual Receipt → Pending → Admin Verify → FIFO

```
Security creates receipt (receipts → New)
  → _save_receipt_v3 detects caller_role="security"
    → fn_save_receipt (status='pending', no transaction yet)

Admin: list_receipts → profile_receipt_entry
  → [Verify & Post] button (profile_actions.py: action_id="verify_receipt", roles=["admin"])
    → loaders.verify_receipt → fn_verify_receipt
      → INSERT into transactions + UPDATE receipts SET status='confirmed'
      → BEFORE UPDATE trigger issues SHA256 receipt_number
```

> Security portal cannot create `partial` receipts — blocked in `_save_receipt_v3`.

### Path 3 — Admin: KPI → Receivables List → Profile → Pay Due

```
kpi_receivables_total (DRILLDOWN_MAP → list_receivables)
  → list_receivables (fn_receivables_named)
    → profile_receivable (load_profile "receivable")
      → [Pay Due] button (profile_actions.py: action_id="pay_due_receivable", roles=["admin"])
        → handler reads receivable.entity_id → loads apartment
          → form_pay_dues_new (pre-filled with receivable amount)
            → _save_pay_dues → fn_pay_apartment_dues_fifo
```

### Path 4 — Admin: KPI → Receipts List → New Receipt → Manual Entry

```
kpi_receipts_month (DRILLDOWN_MAP → list_receipts)
  → [New] button → form_receipt_new
    → Admin fills amount, account, particulars, mode, date
      → _save_receipt_v3 (caller_role="admin")
        → fn_save_receipt (posts immediately to transactions, status='confirmed')
```

### Path 5 — Admin: Apartment Profile → Pay Dues (direct)

```
Any path to profile_apartment
  → [Pay Dues] button
    → same as Path 1 from the profile step onwards
```

---

## 11. QR Code & Access Control Architecture

The platform relies heavily on QR codes for access control, asset tracking, and auditing. Unlike simple static text, the QR architecture uses cryptographic signing to prevent forgery and a versioning system to allow for remote revocation of lost or stolen passes.

### Core Cryptography & Generation
- **Payload Format:** `<society_id>-<ROLE_CODE>-<entity_id>-<qr_version>-<signature>`.
- **Signing (`SIGNING_SECRET`):** Each society configures a unique `SIGNING_SECRET` in their Setup Wizard (encrypted at rest in the database). This secret is used to generate an HMAC-SHA256 signature for the QR payload. This guarantees that a printed, static QR code cannot be forged by simply guessing sequential entity IDs.
- **Legacy Unsigned Codes:** If a society hasn't configured a secret yet, or if they have old codes printed before the signing requirement, the system falls back to a 3-part unsigned payload (`<society_id>-<ROLE_CODE>-<entity_id>`).

### Identity & Versioning (Revocable Passes)
Certain roles represent long-term identities (like a resident or a vendor). These passes are **versioned**, meaning their QR payload includes a `qr_version` nonce (a random 4-digit number).
- **Versioned Roles:** Apartments (`APT`), Vendors (`VND`), Security Staff (`SEC`), Patrol Locations (`PTL`), and Admins (`ADM`).
- **Revocation (`revoke_and_reissue`):** If a physical pass is lost or stolen, an Admin can revoke it. The system derives a completely new 4-digit nonce and updates the entity's `qr_version` column in the database. Because the database version no longer matches the version printed on the lost QR code, the old code instantly fails signature validation without affecting anyone else's pass.
- **Admin Edge-Case:** A promoted apartment owner's Admin badge rides on their `apartments.qr_version` counter. A seeded first-admin falls back to their `users.qr_version` counter.

### Lookup & Utility Tags (Unversioned)
Some QR codes act as immutable, physical lookup tags rather than access credentials. These are **unversioned** and cannot be "revoked" via `revoke_and_reissue`.
- **Receipts (`RPT`)**: Scans perform a pure read against the `receipts` table to verify authenticity and current status (Pending/Confirmed).
- **Assets (`AST`)**: Functions as a physical asset tag. Scans verify name, purchase value, and disposal status.
- **Concerns (`CON`)**: Acts as a physical tag for a logged issue (e.g., stuck on a door). Scans return the concern type and real-time resolution status.

### Actionable Workflows
- **Visitors (`VIS`)**: Scans enforce a strict Two-Actor security policy. Only pre-approved passes (`status='approved'`) are admitted instantly on scan. Pending passes resolve to `PENDING_CONFIRMATION` which triggers an app alert, forcing the guard to wait for explicit owner approval before entry is granted.
- **Event Tickets (`EVT`)**: Scans verify ticket validity and **immediately mark the ticket as used** (`UPDATE event_ticket_items SET used = true`) to prevent double-scanning at the venue door.
- **Patrol Locations (`PTL`)**: Scans enforce strict anti-spoofing via GPS geo-fencing (guard must be within 50 meters) and time-speed checks against their last scan (travel speed > 25km/h is rejected). Valid scans mark the assigned patrol task as `COMPLETED`.
- **Security Attendance (`ATD`)**: Security guards clock in/out using a dynamically generated, 60-second expiring epoch QR code (`attendance_entry`). This time-boxes the scan to prevent replay attacks.

### Physical NFC Integration
For long-term physical passes (like vendor ID cards) or fixed patrol checkpoints, the dashboard integrates with the **Web NFC API**. An admin can click the "Write to NFC Tag" button on a QR modal to transmit the exact QR payload string directly into an NDEF-formatted physical NFC tag. Security guards can then tap the NFC tag with their phones instead of relying purely on the camera scanner.

### Camera Scanner (Security Portal)

```
[Entry IN] → getUserMedia({facingMode:'environment'})
    → setInterval(captureAndSend, 800ms)
        → POST /api/scan-qr (server-side QR decode)
            → on success: stop camera → setReact(qr-scan-mode, qr-scan-input)
                → click qr-validate-btn → validate_qr_scanned callback
                    → PASS: INSERT gate_access (time_in=NOW())
                    → FAIL: show denial reason

[Exit OUT] → same camera flow
    → UPDATE gate_access SET time_out=NOW() WHERE entity_id=? AND time_out IS NULL
       ORDER BY time_in DESC LIMIT 1
```

Additional controls: **Flip** (front/back toggle) · **Torch** (flashlight via `applyConstraints`) · **Emergency** (creates society-wide event) · **Call Admin** (shows admin phone from society profile)

---

## 12. Default Profile (No KPI Selected)

When the user logs in and no KPI has been clicked, the drill panel shows the user's own profile card below a visual divider. This is implemented via:

1. **`portal-content-store` as Input** — shell_callbacks writes `{"rendered":True}` on every page load; `route_drilldown` listens with `prevent_initial_call="initial_duplicate"`.
2. **`dashboard_*` handler in `_render_card`** — when `active_card` is `"dashboard_admin"` / `"dashboard_apartment"` etc., calls `_render_default_profile()`.
3. **`_render_default_profile()`** — role-keyed config selects which entity/PK to load:

| Role | Shows | Entity PK source |
|---|---|---|
| `admin` | Society profile (no edit buttons) | `auth.society_id` |
| `apartment` | Flat profile + action buttons | `auth.apartment_id` or `auth.linked_id` |
| `vendor` | Vendor profile + action buttons | `auth.user_id` (matches `fn_vendors_list` id) |
| `security` | Security profile + action buttons | `auth.user_id` |

The divider label reads **"Your Profile"** (non-admin) or **"Society Overview"** (admin).

Breadcrumb back-navigation to index 0 also re-renders the default profile because `navigate_back(store, 0)` sets `active_card` back to the home `dashboard_*` card, which then hits the same handler.

---

## 13. Customize Tab — Layout Editor & KPI Inspector

### Layout Editor

Accessible at **Admin → Customize → Layout Editor**.

- Filter KPI palette by **Portal** and **Tab** using cascading dropdowns
- Drag cards from **Palette** into **Active Zone** (max 12)
- Layout saved to `Dashboard_settings` table per `(society_id, portal, tab)` key: `"dashboard_layout_{portal}_{tab}"`
- Reset to role-level default

### KPI Inspector

Accessible at **Admin → Customize → KPI Inspector**.

1. Select Portal → Tab → KPI (duplicate-safe `_KPI_PORTAL_ENTRIES` list-of-tuples)
2. View raw SQL, metadata: format, group, color, icon, param count, portal, tab
3. **Test SQL Query** — runs live with your `society_id`, returns raw + formatted + ms
4. **Export SQL** — downloads `.sql` block with KPI metadata header
5. **Entity Reference** panel — shows list columns, profile fields, profile actions

---

## 14. File & Image Management

### Upload Flow

```
dcc.Upload → handle_image_upload() callback
    → image_utils.compress_to_webp()   (Pillow: resize max 1920px, WebP quality=85, ≤25KB)
    → safe_filename = f"{field}_{timestamp}.webp"   # built AFTER compression
    → Save to /app/assets/{society_id}/{entity}/{pk}/{filename}
    → Returns filename only (not full path) into hidden form field
    → On form save: _move_temp_images() moves from /assets/default/{entity}/
      to final path once PK is known
```

### Camera Capture Flow

```
Camera [Snap] → canvas.toDataURL('image/jpeg') → data:image/jpeg;base64,...
    → injected into hidden Dash Input via native setter + dispatchEvent
    → handle_form_submit detects data: prefix → compress_to_webp → save to disk
    → filename stored in form_data (replaces base64)
```

### Asset Directory Structure

```
app/assets/
├── {society_id}/                     ← society logo, login background, secretary sign
│   ├── apartment/{apt_id}/           ← owner photo, ID proof
│   ├── vendor/{vendor_id}/           ← logo, photo, license
│   ├── security/{sec_id}/            ← photo, ID proof
│   ├── concern/{concern_id}/         ← complaint photos
│   └── event/{event_id}/             ← event banners
└── default/                          ← temp staging before PK is assigned
    ├── apartment/ · vendor/ · society/ · security/ · concern/ · event/
```

Always construct full asset URLs at render time using `renderers.get_image_url(filename, society_id, entity, pk)`. Only filenames are stored in the DB.

---

## 15. Tech Stack Reference

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Python Dash 2.x + React 18 | SPA, no page reloads |
| UI | Dash Bootstrap Components (DBC) | Cards, modals, badges |
| Backend | Flask (embedded in Dash) | `app.server` for Flask routes |
| Auth | JWT (PyJWT) + Werkzeug password hashing | Multi-method |
| Database | PostgreSQL via Aiven | Managed PostgreSQL |
| DB Driver | psycopg2 + SQLAlchemy text() | Named params via `_to_pyformat()` |
| ORM | SQLAlchemy `db.Model` + raw SQL | SQLAlchemy models in `app/models/` alongside `fn_*` stored functions |
| Image Processing | Pillow (PIL) | WebP compression to ≤25KB |
| Excel Export | pandas + openpyxl | |
| QR | `qrcode[pil]` + `cryptography.Fernet` | Encrypted payloads |
| Camera | jsQR (clientside) + `/api/scan-qr` | Server-side decode |
| Hosting | Render | Gunicorn |

---

## 16. PostgreSQL Function Index

| Function | Purpose |
|---|---|
| `fn_auto_generate_receivables(society_id)` | Creates monthly receivable rows per apartment |
| `fn_apply_receivable_interest(society_id)` | Accrues interest on overdue receivables |
| `fn_auto_generate_payables(society_id)` | Creates salary payment rows per security shift |
| `fn_pay_apartment_dues_fifo(apt_id, amount, mode, confirmed_by, particulars)` | FIFO payment → marks receivables paid → creates receipt + transaction |
| `fn_verify_receivable(receivable_id, confirmed_by, mode)` | Posts pending receivable to transactions |
| `fn_verify_payment(payment_id, confirmed_by, mode)` | Posts pending salary payment to transactions |
| `fn_save_receipt(society_id, acc_id, particulars, amount, entity_id, role, mode, date, created_by, cheque_no, trx_id, source_reference)` | Self-determining: admin→confirmed+transactions, others→pending. Issues SHA256 receipt_number on confirmation. |
| `fn_verify_receipt(receipt_id, confirmed_by, mode)` | Promotes pending→confirmed, posts double-entry transactions, issues SHA256 receipt_number |
| `fn_save_expense(society_id, acc_id, particulars, amount, entity_id, role, mode, date, created_by, cheque_no, trx_id, source_reference)` | Self-determining: admin→confirmed+transactions, others→pending. |
| `fn_verify_expense(expense_id, confirmed_by, mode)` | Promotes pending→confirmed, posts double-entry transactions, issues SHA256 receipt_number |
| `fn_sell_vendor_pass(user_id, pass_type, acc_id, mode, created_by, issued_date, particulars)` | Creates vendor pass + receipt (pending/confirmed by role) + transaction |
| `fn_buy_asset(society_id, name, type, value, acc_id, date, mode, user_id, particulars)` | Purchases asset + expense + transaction |
| `fn_dispose_asset(asset_id, sale_value, mode, user_id, date, particulars)` | Disposes asset + receipt + transaction |
| `fn_check_noc_eligibility(apartment_id)` | Returns `{eligible, reason, outstanding}` |
| `fn_evaluate_gate_pass(role, entity_id)` | Returns `{passed, reason, amount_due}` |
| `fn_apartments_list(society_id, search, has_dues)` | Apartment list with dues summary |
| `fn_vendors_list(society_id, search)` | Vendor list with pass status |
| `fn_security_list(society_id, search)` | Security list with salary/duty status |
| `fn_receivables_named(society_id, search, status, entity_id, entity_role)` | Receivables with account names |
| `fn_receipts_list(society_id, search, entity_id, entity_role)` | Receipts with entity names |
| `fn_cashbook_paired_v3(society_id, entity_id, entity_role, search, start, end)` | Paired Cr/Dr cashbook, mode-excludes `'journal'` entries; entity name/role filter keyed off `transactions.role` |
| `fn_cashbook_month_page(society_id, month, entity_id, entity_role)` | Single-month Cashbook page (12 monthly sheets, Apr–Mar); same `transactions.role`-keyed entity join as `fn_cashbook_paired_v3` |
| `fn_account_ledger_fy(account_id, society_id, financial_year)` | Per-account ledger folio for the Ledger Index card drilldown; resolves entity name via `transactions.role`-keyed join |
| `fn_accounts_list / fn_account_profile` | Chart of accounts |
| `fn_societies_list / fn_society_profile` | Master portal society data |
| `fn_gate_logs_named(society_id, search, date)` | Gate access with entity names |

---

## 17. Codebase Map

```
EstateHub/
│
├── app/
│   ├── auth/                                 ← JWT handler and token logic
│   ├── models/                               ← SQLAlchemy models (User, Transaction, Apartment, etc.)
│   ├── routes/                               ← Flask routes and API endpoints
│   ├── dash_apps/
│   │   ├── app_shell.py                      ← Layout root + all dcc.Store definitions
│   │   ├── layout.py                         ← Shared page layout and UI components
│   │   ├── callbacks/                        ← 34 modules; see registration order below
│   │   │   ├── __init__.py                   ← Registration order & loader rules (source of truth — read this file directly for the current wiring, it's kept well-commented)
│   │   │   ├── shell_callbacks.py            ← URL routing, auth guard, sidebar, toast
│   │   │   ├── login_callbacks.py            ← All login methods + password reset
│   │   │   ├── card_catalogue_callbacks.py   ← KPI refresh (single callback, ALL pattern)
│   │   │   ├── drilldown_callbacks.py        ← Master router + form submit + default profile
│   │   │   ├── drillin_callbacks.py          ← Entity-picker modal (FK fields) + Bill-Group Pay picker
│   │   │   ├── qr_callbacks.py               ← QR modal, camera JS, gate scan, emergency, NFC write
│   │   │   ├── qr_reissue_callbacks.py       ← Admin-only Settings-tab Re-issue QR (revoke_and_reissue)
│   │   │   ├── patrol_map_callbacks.py       ← Clientside Leaflet map init for patrol locations
│   │   │   ├── camera_callbacks.py           ← Image capture JS (entity forms)
│   │   │   ├── noc_callbacks.py              ← Print / PDF / Email NOC (clientside)
│   │   │   ├── agreement_callbacks.py        ← Print / PDF / Email society Agreement (clientside)
│   │   │   ├── customize_callbacks.py        ← DnD layout editor
│   │   │   ├── customize_kpi_callbacks.py    ← KPI Inspector + _KPI_PORTAL_ENTRIES
│   │   │   ├── list_inspector_callbacks.py   ← List column configuration
│   │   │   ├── form_inspector_callbacks.py   ← Form field configuration
│   │   │   ├── setup_wizard_callbacks.py     ← First-time society setup wizard
│   │   │   ├── bulk_enroll_callbacks.py      ← CSV bulk upload for members/staff
│   │   │   ├── bank_reconcile_callbacks.py   ← Bank statement upload and reconciliation
│   │   │   ├── assign_to_callbacks.py        ← Assign-To modal (concern → admin/vendor/security)
│   │   │   ├── concern_bid_callbacks.py      ← Vendor "Save Bid" on a concern
│   │   │   ├── invite_to_callbacks.py        ← Invite vendors/security to bid on a concern
│   │   │   ├── channel_callbacks.py          ← Channel creation, subscribe/unsubscribe
│   │   │   ├── poll_callbacks.py             ← Owner voting and poll management
│   │   │   ├── account_callbacks.py          ← Account settings / change password
│   │   │   ├── mode_conditional_callbacks.py ← Clientside field visibility (cheque_no/txn_id by Mode)
│   │   │   ├── qty_stepper_callbacks.py      ← Clientside +/- quantity stepper (event ticket qty)
│   │   │   ├── form_autofill_callbacks.py    ← Particulars auto-suggestion for Receipts/Expenses
│   │   │   ├── receipt_callbacks.py          ← Receipt Print / Save / Email
│   │   │   ├── event_ticket_callbacks.py     ← Event ticket Print / Save / Email
│   │   │   ├── vendor_pass_callbacks.py      ← Vendor pass Print / Save / Email
│   │   │   ├── expense_callbacks.py          ← Expense voucher Print / Save / Email
│   │   │   ├── debug_callbacks.py            ← KPI audit + SQL tester
│   │   │   ├── admin_callbacks.py            ← No-op registration slot (all callbacks pruned — see file docstring); kept so future admin-only callbacks have a documented slot
│   │   │   ├── security_callbacks.py         ← Gate-alert buttons (School Bus/Taxi escalate, visitor notify, walk-in, QR validate, attendance). Wired in as step 6b
│   │   │   └── print_letterhead.py           ← Shared letterhead helper (logo · login_background watermark · secretary sign · verification QR) used by receipt, NOC, event-ticket, and any future print/PDF/email flow; not a callbacks module, imported by the print callback modules
│   │   ├── drilldown/
│   │   │   ├── loaders.py                    ← All DB reads, verify_*, pay_dues_fifo
│   │   │   ├── renderers.py                  ← list/profile/form/pay-dues/NOC card HTML
│   │   │   ├── drillin.py                    ← DRILLIN_CONFIG for entity-picker/Bill-Group modals
│   │   │   ├── state.py                      ← navigate_to, navigate_back, initial_state
│   │   │   ├── registry.py                   ← DRILLDOWN_MAP, ENTITY_MAP, PK_MAP, helpers
│   │   │   ├── profile_actions.py            ← PROFILE_ACTIONS + FIELD_VISIBILITY dicts
│   │   │   ├── schema_introspect.py          ← Live schema → entity meta (lazy-cached)
│   │   │   ├── image_utils.py                ← compress_to_webp()
│   │   │   └── `__init__ ().py`              ← ⚠️ Stray duplicate of `__init__.py` (note the space + parens in the filename) — looks like an accidental extra save, not imported by anything; safe to delete, see [§21](#21--legacy-code-cleanup-status)
│   │   └── pages/
│   │       ├── portal_pages.py               ← 5 portal page layouts
│   │       ├── card_catalogue.py             ← KPI_CARDS, DEFAULT_LAYOUTS, make_kpi_card()
│   │       ├── customize_layout.py           ← KPI Customize layout views
│   │       ├── login_system.py               ← Login and pattern/PIN authentication views
│   │       └── router.py                     ← Page routing definitions
│   ├── services/
│   │   ├── auth_service.py                   ← authenticate_user(), reset flow
│   │   └── qr_service.py                     ← generate_static_qr_code(), validate_qr_code()
│   └── assets/                               ← Static files + uploaded images
│
├── database/
│   ├── db_manager.py                         ← db._execute() → Aiven
│   ├── estatehub.sql                         ← Full schema + all fn_* functions
│   ├── migrate.py                            ← Schema initialization (delegates demo seeding to seed.py)
│   ├── seed.py                               ← Idempotent demo/seed data (society, users, accounts, events, concerns)
│   └── reset_database.py                     ← Destructive DB reset and schema reload utility
│
├── cleanup.py                                ← Cleanup script for removing redundant files
├── run.py                                    ← Local server launcher (dash)
├── wsgi.py                                   ← WSGI entry point for production hosting
└── requirements.txt
```

### Callback Registration Order (`callbacks/__init__.py`)

`__init__.py` iterates a `CALLBACK_MODULES` list in a loop. For each
module it imports it and calls **every function whose name starts with
`register_`** — so a module like `drillin_callbacks.py` that exposes
both `register_drillin_callbacks` and `register_pay_dues_bill_callbacks`
has both called automatically from a single list entry. Each module is
wrapped in a `try/except`, so one broken module logs a `⚠️` and is
skipped rather than crashing the whole app on boot. A startup-time check
also warns if any `*_callbacks.py` file on disk defines a `register_*`
function but is absent from `CALLBACK_MODULES`. Current order
(module names match the files in [§17](#3-architecture-overview) above):

```python
"shell_callbacks"            # 1.  URL routing MUST be first
"login_callbacks"            # 2.  Auth before data callbacks
"drilldown_callbacks"        # 3.  Navigation engine (owns drill-content)
"patrol_map_callbacks"       #     Leaflet map init (module-level clientside_callback)
"card_catalogue_callbacks"   # 4.  KPI refresh
"customize_callbacks"        # 5.  DnD layout editor
"qr_callbacks"               # 6.  QR gate pass
"security_callbacks"         # 6b. Gate alerts — previously never called (fixed)
"camera_callbacks"           # 7.  Image capture JS
"customize_kpi_callbacks"    # 8.  KPI inspector
"list_inspector_callbacks"   # 8b. List column configuration
"form_inspector_callbacks"   #     Form field configuration
"setup_wizard_callbacks"     # 9.  First-time society setup wizard
"debug_callbacks"            # 10. Dev tools
"noc_callbacks"              # 10. NOC actions (clientside)
"agreement_callbacks"        # 10b. Agreement actions (clientside)
"admin_callbacks"            # 11. No-op slot (all callbacks pruned)
"form_autofill_callbacks"    # 12. Particulars auto-suggestion
"receipt_callbacks"          # 13. Receipt Print/Save/Email
"event_ticket_callbacks"     # 13b. Event ticket Print/Save/Email
"vendor_pass_callbacks"      # 13c. Vendor pass Print/Save/Email
"expense_callbacks"          # 13d. Expense Print/Save/Email
"bulk_enroll_callbacks"      # 14. CSV bulk upload
"bank_reconcile_callbacks"   # 14a2. Bank statement reconciliation
"assign_to_callbacks"        # 14b. Concern assignment
"concern_bid_callbacks"      # 14c. Vendor bid on concern
"invite_to_callbacks"        # 14d. Invite vendors/security to bid
"drillin_callbacks"          # 14e. Entity-picker modal + Bill Group Pay (both register_* fns auto-called)
"channel_callbacks"          # 15. Channels
"poll_callbacks"             # 16. Polls
"account_callbacks"          # 17. Change password
"mode_conditional_callbacks" # 18. Clientside field visibility
"qty_stepper_callbacks"      # 19. Clientside qty stepper
"qr_reissue_callbacks"       # 21. Admin QR revoke/reissue (Settings tab)
```

`owner_callbacks.py` no longer exists in the codebase (removed).

> **Note on `admin_callbacks.py`:** registered as a documented no-op — all
> of its callbacks were pruned because their target component IDs didn't
> exist (see step 11 above). `security_callbacks.py` **is** registered
> (step 6b); it was previously an unintentional gap now fixed. `owner_callbacks.py`
> has been deleted from the repo entirely.

> **Note on `print_letterhead.py`:** this file lives in `callbacks/` by
> convention (shared utilities alongside the print callbacks that use it)
> but it is **not** a callbacks module — it defines no `register_*`
> function and is not listed in `CALLBACK_MODULES`. The startup-time dead-
> code check skips it correctly because it contains no `register_` symbol.

---

## 18. Critical Dash Rules

```
Rule 1: allow_duplicate=True + prevent_initial_call=False      → CRASH at startup
Rule 2: allow_duplicate=True + prevent_initial_call=True       → OK (user triggers only)
Rule 3: allow_duplicate=True + prevent_initial_call="initial_duplicate" → OK (fires on load + user)

Rule 4: ENTITY_META must be lazily initialised — never build at module import time.
        Use get_entity_meta() which builds and caches on first callback invocation.

Rule 5: SQL parameter style is psycopg2 %s (not SQLAlchemy :param).
        All db._execute() calls use positional %s parameters.

Rule 6: fn_save_receipt arg order: (society_id, acc_id, particulars, amount, entity_id, role, ...)
        NOT (society_id, entity_id, role, acc_id, particulars, amount, ...).
        Wrong order = silent data corruption (no Python error, wrong columns written).

Rule 7: Always build safe_filename AFTER WebP compression, not before.
        Always force .webp extension regardless of upload source format.

Rule 8: _save_entity must stamp user_id from auth-store into merged before dispatch.
        Forms never collect user_id — it must come from auth.

Rule 9: portal-content-store is the page-load trigger for the drilldown router.
        Do not remove it. Do not replace with prevent_initial_call=False on the main router
        (that causes conflicts with allow_duplicate outputs).
```

---

## 19. Known Bugs & Fixes Applied

| Bug | Symptom | Fix Applied |
|---|---|---|
| `fn_auto_generate_receivables` NULL acc_id | `fn_verify_receivable` returns "No income account set" | Fallback now looks up accounts by name; one-time UPDATE patches existing rows |
| `fn_save_receipt` arg order wrong | Silent data corruption — role written to acc_id column | Fixed arg order in `_save_receipt_v3` to match SQL signature |
| `fn_save_expense` arg order wrong | Same as above | Fixed arg order in `_save_expense_v3` |
| `kpi_receivables_total` → wrong target | Clicked KPI opened receipts list instead of receivables | Fixed `DRILLDOWN_MAP` entry: `"list_receipts"` → `"list_receivables"` |
| Default profile not showing | `_render_card("dashboard_admin")` fell through to `_empty_state` | Added `dashboard_*` handler + `_render_default_profile()` + `portal-content-store` Input |
| KPI `prevent_initial_call=True` blocked page-load refresh | KPI values stayed `"—"` until user clicked | Changed to `"initial_duplicate"` |
| `portal-content-store` guard blocked KPI refresh | KPI callback gated on store having `rendered=True` then crashed | Removed blocking guard |
| Camera `mode` captured before `stopCamera()` clears `S.mode` | Wrong mode (`null`) sent to validate callback | Saved `currentMode` before `stopCamera()` call |
| Leftover `render_default_profile` in `shell_callbacks.py` | Pylance undefined-variable errors on `loaders`, `renderers`, `nav_state` | Delete that callback block — functionality moved to `drilldown_callbacks.py` |
| `fn_account_ledger_fy` referenced `t.role` | `Error: column t.role does not exist` on Ledger Index card → IncExp drilldown | Added `transactions.role` column (mirrors `receipts`/`expenses`/`payables`.role); every `INSERT INTO transactions` now writes it; `fn_account_ledger_fy` / `fn_cashbook_paired_v3` / `fn_cashbook_month_page` join `apartments`/`vendors`/`security_staff` on `entity_id` **and** `role`, since `entity_id` alone can collide across those tables |
| Patrol Locations map blank | `L.map()` initialization skipped on page load | Fixed `prevent_initial_call=False` in `patrol_map_callbacks.py` so map mounts immediately |
| Patrol Location not saving | Form submitted `"patrol_location_new"` but handler only checked `"patrol_location"` | Fixed string-matching condition in `_save_patrol_location` inside `drilldown_callbacks.py` |
| Patrol Locations list empty | List generation SQL was completely missing from `loaders.py` | Added `patrol_locations` branch to `load_list` in `loaders.py` using direct SQL query |
| Duplicate list columns | `active` and `scan_interval` appeared twice in Patrol Locations list | Removed `patrol_locations` from `_COMPUTED_FIELDS` in `schema_introspect.py` since schema introspector already natively discovers them |
| No NFC programming UI | "Program NFC" button opened generic QR modal with no way to write NFC | Added "Write to NFC Tag" button to `_qr_modal` (`app_shell.py`) and wired Web NFC API `NDEFReader().write()` callback (`qr_callbacks.py`) |
| Security portal Gate Alert buttons non-functional | `security_callbacks.py` was fully implemented and its render function imported by `portal_pages.py`, but `register_security_callbacks(app)` itself was never called in `callbacks/__init__.py` — every School Bus/Taxi/Visitor gate-alert button rendered with no listener | Added the missing `register_security_callbacks(app)` call (step 6b) in `callbacks/__init__.py` |

---

## 20. 🚩 Open Design Subtleties & Flagged Caveats

Behaviors the code deliberately implements a specific (non-obvious) way, or
explicitly defers — not bugs, but easy to break by accident if a future
change doesn't know the reasoning below. Distinct from [§19](#19-known-bugs--fixes-applied),
which is already-fixed bugs, and [§18](#18-critical-dash-rules), which is
Dash-framework footguns.

### Concurrency / "First Writer Wins" Patterns

- **The DB driver layer exposes no `cur.rowcount`.** Every place that needs
  to detect "did my write actually win a race" (visitor admission in
  `qr_service.validate_visitor_qr`, alert state transitions in
  `alert_service.py`) uses a conditional `UPDATE ... WHERE <still-pending>
  RETURNING id` and checks whether a row came back — not a rowcount check.
  Any new concurrent-write code must follow the same `RETURNING`-based
  pattern; a naive `UPDATE` + assume-success will not be race-safe here.
- **`entity_id` alone collides across `apartments`/`vendors`/`security_staff`.**
  Already caused one shipped bug (`fn_account_ledger_fy`, see §19) — every
  join against those three tables on `entity_id` must also filter on
  `role`, since the ids are independent per-table sequences, not a shared
  namespace.

### Trust Boundary

- **Client-supplied `profile_action` / `auth_data` fields are never trusted
  directly for identity-bearing actions.** `toggle_qr_modal` re-derives
  `role`/`society_id`/`user_id` from the server session for the caller's
  *own* QR, and separately re-validates admin/master + same-society scope
  before minting a gate pass *for another entity* from `profile_action`
  (`qr_callbacks.py`). The comments there call out that this was previously
  a real vulnerability (QR identity sourced from client-editable
  `auth-store`) — any new profile action that mints a credential or writes
  `confirmed_by`/`user_id` needs the same re-derivation, not a pass-through
  of whatever the client sent.

### Deferred / Not-Yet-Built

- **Cashbook `Cr LF` / `Dr LF` (ledger folio) columns are deliberately
  omitted** from `_CASHBOOK_LIST_COLUMNS` in `schema_introspect.py` —
  waiting on the Ledger Index/pagination feature that would actually
  assign folio numbers.
- **`MST` (master admin) has no QR entry at all, by design** — a
  platform-level onboarding role with no `society_id` or gate/entity
  identity to represent (`qr_service.py`). Don't add one without first
  deciding what a master-level QR would even mean.

---

## 21. 🧹 Legacy Code Cleanup Status

All dead, superseded, or bug-inducing code identified in previous phases has been **successfully cleaned up and removed** from the repository to ensure optimal performance, prevent startup crashes, and keep the codebase tidy:

| File | What was Removed | Lines | Status |
|---|---|---|---|
| `shell_callbacks.py` | Stale `render_default_profile` callback | ~120 | ✅ Removed |
| `card_catalogue_callbacks.py` | Callbacks #2–#10 (stale list loaders) | ~280 | ✅ Removed |
| `card_catalogue.py` | `FORM_CARDS` dict + `make_form_card()` | ~480 | ✅ Removed |
| `card_catalogue.py` | Duplicate `format_kpi_value()` | ~60 | ✅ Removed |
| `card_catalogue.py` | Unused `calculate_maintenance_*` helpers | ~90 | ✅ Removed |
| `drilldown_callbacks.py` | Duplicate `_apply_portal_filters()` definition | ~15 | ✅ Removed |
| `loaders.py` | Typed entity loader functions (redundant wrappers) | ~250 | ✅ Removed |
| `savers.py` | Entire redundant file | ~230 | ✅ Removed |

**Total codebase reduction: ~1,500 lines of dead code.**

### Additional items cleaned up since last README pass

| File | Status |
|---|---|
| `app/dash_apps/callbacks/kpi_rule_links_callbacks.py` | ✅ Removed — `register_kpi_rule_links_callbacks()` was dead code; confirmed absent from working tree |
| `app/dash_apps/drilldown/__init__ ().py` | ✅ Removed — stray duplicate file (space + parens in name) confirmed gone |

---

## 22. Deployment & Utility Notes

### Environment Variables

```env
DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require
SECRET_KEY=<flask-session-secret>
JWT_SECRET=<jwt-signing-secret>
FERNET_KEY=<base64-fernet-key>   # for QR encryption
```

### Render / Gunicorn

```bash
gunicorn app:server -w 4 -b 0.0.0.0:8050 --timeout 120
```

- Set `debug=False` in `app.run_server()` for production.
- `/app/assets/` must be writable for image uploads.
- Aiven: use `?sslmode=require` and connection pooling.
- `suppress_callback_exceptions=True` is required in `app = Dash(...)` because list, profile, and form components are rendered dynamically.

### Database Reset Utility

A utility script `database/reset_database.py` is provided to perform a destructive reset of the database schema:
```bash
python3 database/reset_database.py
```
This script connects to the target database, recreates the `public` schema CASCADE, executes all schema definitions and functions inside `database/estatehub.sql`, and runs a validation suite to verify the active table count, view count, and stored procedures.

### Demo / Seed Data (`database/seed.py`)

`database/migrate.py --seed` delegates to `database/seed.py`, which idempotently
seeds a single demo society ("Sunrise Residency", `society_id = 1`) with:

| Entity | Count | Notes |
|---|---|---|
| Master admin | 1 | `master@estatehub.com` |
| Society admin | 1 | `admin@sunriseresidency.com` |
| Apartment owners | 13 | Flats across A/B/C blocks; mix of rate-based and fixed-amount maintenance charge histories |
| Vendors | 12 | 12 distinct service types (Plumbing, Gardening, Electrical, Carpentry, Painting, Pest Control, Housekeeping, CCTV & Security, AC Repair, Elevator Maintenance, Catering, Landscaping) |
| Security staff | 12 | Mixed morning/evening/night shifts, roster + gate-log attendance for the first two guards |
| Events | 12 | Spread across the demo financial year, all `open_to = 'all'` |
| Concerns | 12 | Mixed types/statuses (`open`, `in_progress`, `resolved`, `closed`); several pre-assigned to a vendor or security guard via `concerns_assigns` |
| Chart-of-accounts | 50 | Identical to the legacy `migrate.py` account tree |

Re-running the seed is safe — every insert is guarded by an existence check
(`ON CONFLICT` or a `SELECT ... WHERE NOT EXISTS`-style guard), so it will
only fill in missing rows rather than duplicate demo data.

```bash
python3 database/seed.py                 # standalone
python3 database/migrate.py --seed       # schema init + seed in one step
```

### Database Migrations

All database stored procedures and queries are prefixed with `fn_` and use `%s` positional parameter placeholders (psycopg2 style). Schema changes require updating:
1. The corresponding SQL function definitions in `database/estatehub.sql`.
2. The corresponding database query inside `app/dash_apps/drilldown/loaders.py`.
3. The parameter list in `_save_*` inside `app/dash_apps/callbacks/drilldown_callbacks.py` (for database writes).

Use `database/migrate.py` to auto-initialize the schema and seed mock accounts from `database/EstateAcc.xlsx`:
```bash
python3 database/migrate.py --seed
```

### Required PostgreSQL Extensions

The application requires the `pgcrypto` extension for SHA-256 receipt hashing and chain verification. Setup scripts automatically create this extension if missing:
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

All application tables, functions, triggers, and views live in the standard `public` schema. No custom schema or `search_path` overrides are required at runtime.

### VS Code / Pylance Setup

If VS Code shows missing import warnings on Flask/Dash components, it is usually because it is not pointing to the correct virtual environment. You can fix this by creating/updating:

```json
// .vscode/settings.json
{
    "python.pythonPath": "./venv/bin/python",
    "python.analysis.extraPaths": ["./"],
    "python.analysis.reportMissingModuleSource": "none"
}
```

Or press `Ctrl+Shift+P` → **Python: Select Interpreter** and select your active virtual environment.

## 23. Table of Workflows

### Overview

The following tables map every user-reachable workflow in the application, organized by Portal → Tab → KPI/Quick-link → Drill Target, with the goal of each workflow. 

> **Note on KPI Groups:** The `group` attribute for all KPIs in `card_catalogue.py` has been semantically aligned with the **Name of Workflow** listed below. When using the Customize Layout editor or KPI Inspector, you will see KPIs grouped precisely by these workflow names (e.g., *Society Dashboard*, *Financials*, *Pass Evaluation*).

#### 🟠 MASTER Portal (role: `master`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Master → Society Overview** | Sidebar: Societies → Dashboard tab → 7 KPI cards (`kpi_societies_total`, `kpi_societies_free`, `kpi_societies_9apts`, `kpi_societies_99apts`, `kpi_societies_999apts`, `kpi_societies_unlimited`, `kpi_societies_expiring_soon`) → click any → `list_master_societies` → row → `profile_society` → Edit / Compliance Settings | View/manage all societies on the platform, monitor plan distribution and expirations |
| **Master → KPI Inspector** | Sidebar: Settings → `master-settings` tab → Inspector KPI sub-tab → Select Portal/Tab/KPI → View SQL, Test SQL, Export, Integrate | Inspect, test, and edit KPI SQL queries; run KPI Audit |
| **Master → List Inspector** | Sidebar: Settings → `master-settings` tab → Inspector List sub-tab → Select list → Load SQL → View result box | Inspect list SQL queries and data; run List Audit |
| **Master → Form Inspector** | Sidebar: Settings → `master-settings` tab → Inspector Form sub-tab → Select form → Preview | Inspect and audit all schema-driven forms |

#### 🔵 ADMIN Portal (role: `admin`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Admin → Society Dashboard** | Sidebar: Dashboard → 12 KPI cards (`kpi_apartments_dues`, `kpi_vendors_passes`, `kpi_security_on_duty`, `kpi_attendance_count`, `kpi_events_total`, `kpi_concerns_not_closed`, `kpi_concerns_assigned`, `kpi_gate_logs`, `kpi_assets_count`, `kpi_receipts_pending`, `kpi_channels_total`, `kpi_nocs_total`) → drill panel | High-level society health overview; one-click drill into any entity |
| **Admin → Enrolled Members** | Sidebar: Enrolled → 3 KPI cards (`kpi_apartments_total`, `kpi_vendors_total`, `kpi_security_total`) → `list_apartments` / `list_vendors` / `list_security` → profile → Edit / Gate Pass / Pay Dues / Sell Pass / Toggle Duty | CRUD for apartments, vendors, security staff; sidebar `+` quick-link for New |
| **Admin → Financials** | Sidebar: Financials → 10 KPI cards (`kpi_receipts_month`, `kpi_receipts_total`, `kpi_expenses_month`, `kpi_expenses_total`, `kpi_security_salaries_due`, `kpi_cash_in_hand`, `kpi_bank_balance`, `kpi_cashbook_open`, `kpi_ledger_open`, `kpi_fy_closing_report`) → lists / reports; sidebar `+` New Receipt / `−` New Expense | Track income/expenses, cashbook, ledger; create receipts/expenses; FY closing report |
| **Admin → Channels** | Sidebar: Channels → 3 KPI cards (`kpi_channels_total`, `kpi_channels_active`, `kpi_channels_pending`) → `list_channels` → `profile_channel` → Create / Subscribe / Trigger Alert / View Subscribers | Manage school bus, taxi, visitor alert channels and subscriptions |
| **Admin → Assets** | Sidebar: Assets → 2 KPI cards (`kpi_assets_count`, `kpi_assets_value`) → `list_assets` → `profile_asset` → Edit / Dispose | Buy, manage, depreciate, and dispose of society assets |
| **Admin → Events** | Sidebar: Events → 2 KPI cards (`kpi_events_total`, `kpi_events_tickets`) → `list_events` / `list_event_ticket_items` → profile → Edit / Sell Tickets | Create/edit events, sell/manage event tickets |
| **Admin → Concerns** | Sidebar: Concerns → 2 KPI cards (`kpi_concerns_not_closed`, `kpi_concerns_total`) → `list_concerns` → `profile_concern` → Invite / Assign / Accept / Decline / Resolved / Close | Full concern lifecycle management |
| **Admin → Polls** | Sidebar: Polls → 2 KPI cards (`kpi_polls_total`, `kpi_polls_active`) → `list_polls` → `profile_poll` → Edit / Declare Results / Close | Create, manage, and close community polls |
| **Admin → Evaluate Pass** | Sidebar: Evaluate Pass → QR Scanner → Entry IN / Exit OUT / NFC Patrol; Manual QR entry; Recent Scans; KPIs (`kpi_events_total`, `kpi_concerns_assigned`) | Gate access control via QR scanning (shared with Security portal) |
| **Admin → Customize** | Sidebar: Customize → Layout Editor → Select Portal/Tab → Drag-and-drop KPIs → Save/Reset | Customize KPI dashboard layout per portal/tab per society |
| **Admin → Settings** | Sidebar: Settings → 10 KPI cards (`kpi_societies_calc_start_date`, `kpi_plan_validity`, `kpi_accounts_count`, `kpi_apt_charges_count`, `kpi_ven_charges_count`, `kpi_compliance_settings`, `kpi_time_qr`, `kpi_patrol_locations`, `kpi_tds_rates`, `kpi_qr_reissue`) → drill into respective entities | Society config: accounts, charge rules, compliance, attendance QR, patrol, TDS, QR reissue |

#### 🟢 OWNER (Apartment) Portal (role: `apartment`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Owner → My Dashboard** | Sidebar: Dashboard → 7 KPI cards (`kpi_my_pending_dues`, `kpi_my_overdue_dues`, `kpi_advance_credits`, `kpi_gate_logs`, `kpi_concerns_not_closed`, `kpi_events_total`, `kpi_channels_total`) → drill panel | Personal overview: dues, gate logs, concerns, events, channels |
| **Owner → Members** | Sidebar: Members → 1 KPI (`kpi_apartment_members`) → `list_apartment_users` → `profile_apartment_user` | View family members, tenants, visitors registered to the flat |
| **Owner → Financials** | Sidebar: Financials → 4 KPIs (`kpi_my_pending_dues`, `kpi_my_overdue_dues`, `kpi_maintenance_charges`, `kpi_my_ledger`) → receivables / charges / My Transactions passbook | View personal dues, charge rules, and transaction history |
| **Owner → Channels** | Sidebar: Channels → 3 KPIs (`kpi_channels_total`, `kpi_channels_active`, `kpi_channels_pending`) → `list_channels` → `profile_channel` → Subscribe | Subscribe to school bus/taxi/visitor alert channels |
| **Owner → Bills Paid** | Sidebar: Bills Paid → KPI (`kpi_receipts_total`) → `list_receipts` → `profile_receipt` → Print | View own confirmed receipts and print them |
| **Owner → Events** | Sidebar: Events → 2 KPIs (`kpi_events_total`, `kpi_events_tickets`) → `list_events` / `list_event_ticket_items` → profile → Buy Tickets | View events, buy tickets, view purchased tickets |
| **Owner → Concerns** | Sidebar: Concerns → 2 KPIs (`kpi_concerns_not_closed`, `kpi_concerns_total`) → `list_concerns` → `profile_concern` → Invite / Assign / Close | Raise, track, and close own concerns |
| **Owner → Polls** | Sidebar: Polls → 2 KPIs (`kpi_polls_total`, `kpi_polls_active`) → `list_polls` → `profile_poll` (vote) | View and vote in community polls |
| **Owner → Settings** | Sidebar: Settings → 1 KPI (`kpi_owner_member_since`) → `list_apartments` (self-scoped) → `profile_apartment` → Edit | View/edit own apartment profile |

#### 🟡 VENDOR Portal (role: `vendor`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Vendor → My Dashboard** | Sidebar: Dashboard → 5 KPIs (`kpi_my_pass_expiry`, `kpi_gate_logs`, `kpi_concerns_invited`, `kpi_concerns_assigned`, `kpi_events_total`) → drill panel | Gate pass status, assigned concerns, events overview |
| **Vendor → Financials** | Sidebar: Financials → 2 KPIs (`kpi_receipts_total`, `kpi_ven_charges_count`) → `list_receipts` / `list_ven_charges` | View own receipts and charge rules |
| **Vendor → Passes** | Sidebar: Passes → 2 KPIs (`kpi_my_pass_expiry`, `kpi_vendors_passes`) → `list_vendors` (self-scoped) → `profile_vendor` → Buy Pass / Gate Pass | View/buy own gate passes |
| **Vendor → Events** | Sidebar: Events → 1 KPI (`kpi_events_total`) → `list_events` → `profile_event` → Buy Tickets | View events and buy tickets |
| **Vendor → Concerns** | Sidebar: Concerns → 3 KPIs (`kpi_concerns_invited`, `kpi_concerns_assigned`, `kpi_concerns_resolved`) → `list_concerns` → `profile_concern` → Bid / Decline / Resolved; Manual QR concern lookup | Vendor concern workflow: receive invites, bid, get assigned, resolve |
| **Vendor → Settings** | Sidebar: Settings → 1 KPI (`kpi_vendors_date`) → `list_vendors` (self-scoped) → `profile_vendor` → Edit | View/edit own vendor profile |

#### 🔴 SECURITY Portal (role: `security`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Security → Pass Evaluation** | Sidebar: Pass Eval → QR Scanner → Entry IN / Exit OUT / NFC Patrol; KPIs (`kpi_events_total`, `kpi_concerns_assigned`); Manual QR entry; Recent Scans; Emergency button | Primary gate duty: scan QR passes for entry/exit, NFC patrol check-ins |
| **Security → Channels** | Sidebar: Channels → 5 KPIs (`kpi_channels_total`, `kpi_channels_pending`, `kpi_channels_pending_bus`, `kpi_channels_pending_taxi`, `kpi_presumed_visitor`) → lists | Monitor and act on pending gate alerts (bus/taxi/visitor) |
| **Security → Attendance** | Sidebar: Attendance → Clock In / Clock Out buttons | Clock in/out for shift duty |
| **Security → Receipts** | Sidebar: Receipts → 1 KPI (`kpi_security_receipts`) → `list_receipts` (self-scoped) | View own collected receipts |
| **Security → Events** | Sidebar: Events → 1 KPI (`kpi_events_total`) → `list_events` | View upcoming events |
| **Security → Concerns** | Sidebar: Concerns → 2 KPIs (`kpi_concerns_assigned`, `kpi_concerns_resolved`) → `list_concerns` → `profile_concern` → Resolved | View and resolve assigned concerns |
| **Security → Users** | Sidebar: Users → 3 KPIs (`kpi_security_total`, `kpi_security_on_duty`, `kpi_security_off_duty`) → `list_security` → `profile_security` | View fellow security staff duty roster |
| **Security → Settings** | Sidebar: Settings → 1 KPI (`kpi_time_qr`) → Attendance QR | View/manage own profile, attendance QR |

---

*EstateHub — Built for societies that mean business.*
