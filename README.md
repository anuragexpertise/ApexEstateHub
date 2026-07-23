# ApexEstateHub
### The Complete Society Management Platform

> **Multi-tenant · Role-aware · Real-time · Zero-reload**
> Built on Python Dash + Flask + PostgreSQL (NeonDB/Aiven) · Hosted on ApexWeave

---

## Table of Contents

1. [What is ApexEstateHub?](#1-what-is-apexestatehub)
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
20. [🗑️ Legacy Code Removal Guide](#20-️-legacy-code-removal-guide)
21. [Deployment Notes](#21-deployment-notes)

---

## 1. What is ApexEstateHub?

**ApexEstateHub** (also referred to internally as *EstateHub*) is a **multi-tenant society management web application** that gives housing societies, apartment complexes, and gated communities a single platform to manage residents, vendors, security staff, finances, events, and gate access — all without page reloads.

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

---

## 3. Architecture Overview

```
Browser (Dash SPA)
│
├── app_shell.py              ← Top-level layout: header, sidebar, modals, stores
│
├── callbacks/
│   ├── shell_callbacks.py        ← URL routing, auth guard, sidebar, toast
│   ├── login_callbacks.py        ← Password / PIN / Pattern / Master login
│   ├── card_catalogue_callbacks.py  ← KPI value refresh (pattern-matched ALL)
│   ├── drilldown_callbacks.py    ← Master router: KPI→List→Profile→Form
│   ├── qr_callbacks.py           ← QR modal, camera, gate scan, emergency
│   ├── camera_callbacks.py       ← Image capture JS injection
│   ├── noc_callbacks.py          ← Print / PDF / Email NOC (clientside)
│   ├── customize_callbacks.py    ← DnD layout editor
│   ├── customize_kpi_callbacks.py← KPI Inspector cascading dropdowns
│   └── debug_callbacks.py        ← KPI Audit Report + SQL Tester
│
├── drilldown/
│   ├── loaders.py            ← All DB reads (fn_* functions + raw SQL)
│   ├── renderers.py          ← HTML builders for list/profile/form/pay-dues/NOC cards
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

### 4.3 Owner Portal (Apartment)
Self-service for residents. Scoped to `[society_id, apartment_id]`.

**Tabs:** Dashboard · My payables · My Charges · Events · Concerns · Cashbook · Settings

- View own pending dues, payment history, charges
- Raise and track maintenance concerns
- View upcoming events, own gate pass QR
- Default view: own apartment profile card below KPIs

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

## 11. Gate Pass & QR Scanning

### QR Code Format

QR payload is `Fernet`-encrypted JSON:
```json
{"entity_id": 42, "role": "apartment", "society_id": 1, "name": "Flat A-101", "ts": 1718000000}
```

Generated via `qr_service.generate_static_qr_code()` using `cryptography.Fernet` + `qrcode[pil]`.

### Gate Pass Evaluation Logic by Entity

| Entity | PASS condition | FAIL condition |
|---|---|---|
| Apartment | No `pending` receivables (due_date < today) | Has overdue receivables > 0 |
| Vendor | `vendor_passes` row with `valid_until >= CURRENT_DATE` | No active pass |
| Security | `gate_access` row with `time_out IS NULL` (on duty) | Not checked in |

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

### gate_access Table

```sql
gate_access (id, society_id, role, entity_id, time_in, time_out)
-- role: 'a'=apartment, 'v'=vendor, 's'=security
```

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
| Database | PostgreSQL via NeonDB / Aiven | Serverless PostgreSQL |
| DB Driver | psycopg2 + SQLAlchemy text() | Named params via `_to_pyformat()` |
| ORM | None — raw SQL via `db._execute()` | All logic in `fn_*` stored functions |
| Image Processing | Pillow (PIL) | WebP compression to ≤25KB |
| Excel Export | pandas + openpyxl | |
| QR | `qrcode[pil]` + `cryptography.Fernet` | Encrypted payloads |
| Camera | jsQR (clientside) + `/api/scan-qr` | Server-side decode |
| Hosting | ApexWeave | Gunicorn |

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
| `fn_cashbook_paired(society_id, entity_id, entity_role, search, start, end)` | Paired Cr/Dr cashbook |
| `fn_accounts_list / fn_account_profile` | Chart of accounts |
| `fn_societies_list / fn_society_profile` | Master portal society data |
| `fn_gate_logs_named(society_id, search, date)` | Gate access with entity names |

---

## 17. Codebase Map

```
ApexEstateHub/
│
├── app/
│   ├── dash_apps/
│   │   ├── app_shell.py                      ← Layout root + all dcc.Store definitions
│   │   ├── layout.py                         ← Shared page layout and UI components
│   │   ├── callbacks/
│   │   │   ├── __init__.py                   ← Registration order & loader rules
│   │   │   ├── shell_callbacks.py            ← URL routing, auth guard, sidebar, toast
│   │   │   ├── login_callbacks.py            ← All login methods + password reset
│   │   │   ├── card_catalogue_callbacks.py   ← KPI refresh (single callback, ALL pattern)
│   │   │   ├── drilldown_callbacks.py        ← Master router + form submit + default profile
│   │   │   ├── qr_callbacks.py               ← QR modal, camera JS, gate scan, emergency
│   │   │   ├── camera_callbacks.py           ← Image capture JS (entity forms)
│   │   │   ├── noc_callbacks.py              ← Print / PDF / Email NOC (clientside)
│   │   │   ├── customize_callbacks.py        ← DnD layout editor
│   │   │   ├── customize_kpi_callbacks.py    ← KPI Inspector + _KPI_PORTAL_ENTRIES
│   │   │   ├── debug_callbacks.py            ← KPI audit + SQL tester
│   │   │   ├── admin_callbacks.py            ← [Disabled] Admin specific actions (unregistered)
│   │   │   ├── owner_callbacks.py            ← [Disabled] Owner portal specific actions (unregistered)
│   │   │   └── security_callbacks.py         ← [Disabled] Security portal specific actions (unregistered)
│   │   ├── drilldown/
│   │   │   ├── loaders.py                    ← All DB reads, verify_*, pay_dues_fifo
│   │   │   ├── renderers.py                  ← list/profile/form/pay-dues/NOC card HTML
│   │   │   ├── state.py                      ← navigate_to, navigate_back, initial_state
│   │   │   ├── registry.py                   ← DRILLDOWN_MAP, ENTITY_MAP, PK_MAP, helpers
│   │   │   ├── profile_actions.py            ← PROFILE_ACTIONS + FIELD_VISIBILITY dicts
│   │   │   ├── schema_introspect.py          ← Live schema → entity meta (lazy-cached)
│   │   │   └── image_utils.py                ← compress_to_webp()
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
│   ├── db_manager.py                         ← db._execute() → NeonDB/Aiven
│   ├── estatehub.sql                         ← Full schema + all fn_* functions
│   ├── migrate.py                            ← Account seeding + schema initialization
│   └── reset_database.py                     ← Destructive DB reset and schema reload utility
│
├── cleanup.py                                ← Cleanup script for removing redundant files
├── run.py                                    ← Local server launcher (dash)
├── wsgi.py                                   ← WSGI entry point for production hosting
└── requirements.txt
```

### Callback Registration Order (`callbacks/__init__.py`)

```python
register_shell_callbacks(app)          # 1. URL routing MUST be first
register_login_callbacks(app)          # 2. Auth before data callbacks
register_drilldown_callbacks(app)      # 3. Navigation engine (owns drill-content)
register_card_catalogue_callbacks(app) # 4. KPI refresh
register_customize_callbacks(app)      # 5. DnD layout editor
register_qr_callbacks(app)             # 6. QR gate pass
register_camera_callbacks(app)         # 7. Image capture JS
register_customize_kpi_callbacks(app)  # 8. KPI inspector
register_debug_callbacks(app)          # 9. Dev tools
register_noc_callbacks(app)            # 10. NOC actions (last — dynamic IDs)
```

> **Note on disabled callback modules:** `admin_callbacks.py`, `owner_callbacks.py`, and `security_callbacks.py` are intentionally **not registered** in `register_callbacks(app)` to prevent Dash from throwing a `NonExistentIdException` on startup. Gate scanning and payment actions are instead fully handled by `qr_callbacks.py` and the main `drilldown_callbacks.py` form handling engine.

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

---

## 20. 🧹 Legacy Code Cleanup Status

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

---

## 21. Deployment & Utility Notes

### Environment Variables

```env
DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require
SECRET_KEY=<flask-session-secret>
JWT_SECRET=<jwt-signing-secret>
FERNET_KEY=<base64-fernet-key>   # for QR encryption
```

### ApexWeave / Gunicorn

```bash
gunicorn app:server -w 4 -b 0.0.0.0:8050 --timeout 120
```

- Set `debug=False` in `app.run_server()` for production.
- `/app/assets/` must be writable for image uploads.
- NeonDB: use `?sslmode=require` and connection pooling.
- `suppress_callback_exceptions=True` is required in `app = Dash(...)` because list, profile, and form components are rendered dynamically.

### Database Reset Utility

A utility script `database/reset_database.py` is provided to perform a destructive reset of the database schema:
```bash
python3 database/reset_database.py
```
This script connects to the target database, drops the `defaultdb` schema CASCADE, recreates it, executes all schema definitions and functions inside `database/estatehub.sql`, and runs a validation suite to verify the active table count, view count, and stored procedures.

### Database Migrations

All database stored procedures and queries are prefixed with `fn_` and use `%s` positional parameter placeholders (psycopg2 style). Schema changes require updating:
1. The corresponding SQL function definitions in `database/estatehub.sql`.
2. The corresponding database query inside `app/dash_apps/drilldown/loaders.py`.
3. The parameter list in `_save_*` inside `app/dash_apps/callbacks/drilldown_callbacks.py` (for database writes).

Use `database/migrate.py` to auto-initialize the schema and seed mock accounts from `database/EstateAcc.xlsx`:
```bash
python3 database/migrate.py --seed
```

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

---

*ApexEstateHub — Built for societies that mean business.*
