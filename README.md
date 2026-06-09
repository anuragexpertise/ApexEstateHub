# ApexEstateHub
### The Complete Society Management Platform

> **Multi-tenant · Role-aware · Real-time · Zero-reload**
> Built on Python Dash + Flask-Login + PostgreSQL (NeonDB) + JWT

---

## Table of Contents

1. [What is ApexEstateHub?](#1-what-is-apexestatehub)
2. [Feature Highlights](#2-feature-highlights)
3. [Architecture Overview](#3-architecture-overview)
4. [The Five Portals](#4-the-five-portals)
5. [Drill-Down Navigation Engine](#5-drill-down-navigation-engine)
6. [Authentication & Security](#6-authentication--security)
7. [KPI Dashboard System](#7-kpi-dashboard-system)
8. [Financial Module](#8-financial-module)
9. [Gate Pass & QR Scanning](#9-gate-pass--qr-scanning)
10. [Customize Tab — Layout Editor & KPI Inspector](#10-customize-tab--layout-editor--kpi-inspector)
11. [File & Image Management](#11-file--image-management)
12. [Tech Stack Reference](#12-tech-stack-reference)
13. [Codebase Map](#13-codebase-map)
14. [🗑️ Legacy Code Removal Guide](#14-️-legacy-code-removal-guide)
15. [Deployment Notes](#15-deployment-notes)

---

## 1. What is ApexEstateHub?

**ApexEstateHub** (also referred to internally as *EstateHub*) is a **multi-tenant society management web application** that gives housing societies, apartment complexes, and gated communities a single platform to manage residents, vendors, security staff, finances, events, and gate access — all without page reloads.

Each society gets its own isolated data silo. A **Master Admin** oversees all societies on the platform. Within each society, an **Admin** manages day-to-day operations across five role-scoped portals.

---

## 2. Feature Highlights

| Category | Features |
|---|---|
| **Portals** | Master Admin · Society Admin · Apartment Owner · Vendor · Security |
| **Auth** | Password · PIN · Pattern · JWT tokens · Master Admin flag |
| **Navigation** | Zero-reload SPA — KPI → List → Profile → Form drill-down |
| **Financials** | Cashbook · Receipts · Expenses · Receivables · Payables · Opening Balances |
| **Entities** | Apartments · Vendors · Security Staff · Societies |
| **Operations** | Events · Concerns/Complaints · Gate Logs · Attendance |
| **Gate Pass** | QR code generation · Camera-based scanning · Entry IN / Exit OUT |
| **Reports** | CSV & XLS export on every list · KPI Audit Report |
| **Customization** | Drag-and-drop KPI layout editor per portal · KPI SQL Inspector |
| **Images** | Logo · Login background · Secretary signature · Profile photos |
| **DB** | PostgreSQL `fn_*` stored functions · `%s` parameterised queries |

---

## 3. Architecture Overview

```
Browser (Dash SPA)
│
├── app_shell.py          ← Top-level layout: header, sidebar, portal-content, modals
│
├── shell_callbacks.py    ← Tab switching, URL routing, auth guard, toast renderer
│
├── callbacks/
│   ├── login_callbacks.py        ← Password / PIN / Pattern / Master login
│   ├── card_catalogue_callbacks.py  ← KPI value refresh (pattern-matched ALL)
│   ├── drilldown_callbacks.py    ← Master router: KPI→List→Profile→Form
│   └── debug_callbacks.py        ← KPI Audit Report + SQL Tester
│
├── drilldown/
│   ├── loaders.py        ← All DB reads (fn_* functions + raw SQL)
│   ├── renderers.py      ← HTML builders for list/profile/form cards
│   ├── state.py          ← Navigation stack (drilldown-store)
│   ├── registry.py       ← DRILLDOWN_MAP, ENTITY_MAP, PK_MAP
│   └── savers.py         ← CRUD write helpers (OOP class-based)
│
├── pages/
│   ├── portal_pages.py   ← All 5 portal page layouts (KPI shells + drill panel)
│   └── card_catalogue.py ← KPI_CARDS dict · FORM_CARDS dict · make_card()
│
└── database/
    └── db_manager.py     ← db._execute() wrapper → NeonDB PostgreSQL
```

### Single-Page Flow

```
URL change (dcc.Location)
    │
    ├─► shell_callbacks.py   → renders correct portal page into #portal-content
    │
    └─► card_catalogue_callbacks.py → fills KPI values via pattern-match ALL

KPI card click
    └─► drilldown_callbacks.route_drilldown()
            │
            ├─► loaders.load_list()      → DB query
            ├─► renderers.render_list_card()  → HTML
            └─► writes #drill-content, #drill-breadcrumb, drilldown-store

List row/button click
    └─► drilldown_callbacks.route_drilldown()
            ├─► loaders.load_profile()   → DB query
            └─► renderers.render_profile_card() → HTML

Profile action / Form submit
    └─► drilldown_callbacks.handle_form_submit()
            └─► _save_entity() → DB write → navigate_back()
```

---

## 4. The Five Portals

### 4.1 Master Admin Portal
Accessible only to users flagged `is_master_admin = TRUE` in the DB.

- Platform-wide KPIs: total societies, plan distribution, all apartments/vendors/security
- Drill into any society → view/edit profile, manage plan validity
- Create new societies with admin credentials
- New society button auto-provisions: society row + admin user + asset folder

### 4.2 Admin Portal (Society Admin)
The primary management console for a single society.

**Tabs:** Dashboard · Enroll · Cashbook · Receipts · Expenses · Events · Concerns · Gate Pass · Customize · Settings

- Full CRUD on all entities (apartments, vendors, security)
- Financial ledger: double-entry cashbook, Dr/Cr account validation
- Concern assignment and status tracking
- KPI dashboard customization (drag-and-drop layout editor)
- Plan validity monitoring and account chart management

### 4.3 Owner Portal (Apartment)
Self-service portal for apartment residents.

**Tabs:** Dashboard · My Payments · My Charges · Events · Concerns · Cashbook · Settings

- View own pending dues and payment history
- Raise and track maintenance concerns
- View upcoming events
- Read-only access — data filtered to own `apartment_id`

### 4.4 Vendor Portal
For registered service vendors operating within the society.

**Tabs:** Dashboard · My Cashbook · My Charges · Events · Settings

- View assigned jobs / concerns
- Track pass fees and payment status
- Gate pass QR generation
- Data filtered to own `vendor_id`

### 4.5 Security Portal
For security staff stationed at the gate.

**Tabs:** Gate Pass Evaluation · Attendance · All Users · My Cashbook · My Charges · My Payments · Events · New Receipt · Settings

- Primary function: QR code scanning for Entry IN / Exit OUT
- Create receipts (cash collection at gate)
- Attendance clock-in / clock-out
- View-only access to apartments, vendors, events, concerns

---

## 5. Drill-Down Navigation Engine

The heart of the UX. All navigation is **stateful and stackable** — no page reloads.

### Navigation Stack (drilldown-store)

```json
{
  "stack": [
    {"card_id": "list_apartments", "label": "Apartments",
     "filters": {"society_id": 1}, "prefill": {}, "entity_pk": null},
    {"card_id": "profile_apartment", "label": "Flat A-101",
     "filters": {"society_id": 1}, "prefill": {}, "entity_pk": 42},
    {"card_id": "form_receipt_new", "label": "Pay Dues",
     "filters": {"society_id": 1}, "prefill": {"acc_id": 5, "amount": 3500},
     "entity_pk": 42}
  ],
  "active_card": "form_receipt_new"
}
```

### Card ID Convention

| Prefix | Example | Meaning |
|---|---|---|
| `kpi_` | `kpi_apartments_total` | Clickable KPI metric |
| `list_` | `list_apartments` | Paginated data table |
| `profile_` | `profile_apartment` | Single record detail view |
| `form_<entity>_new` | `form_apartment_new` | Create form |
| `form_<entity>_edit` | `form_apartment_edit` | Edit form (pre-filled) |

### Portal Permission Matrix

| Role | New | View | Edit | Delete |
|---|---|---|---|---|
| Admin | ✓ all | ✓ all | ✓ all | ✓ all |
| Master | societies only | ✓ | societies | — |
| Apartment | concerns | own data | — | — |
| Vendor | — | own data | — | — |
| Security | receipts | most lists | — | — |

---

## 6. Authentication & Security

### Login Methods

```
/dashboard/...  (protected)
    │
    └── guard_modal callback checks auth-store
            ├── NOT authenticated → opens login-modal
            └── authenticated     → renders portal page

Login modal tabs:
  [Password]  email + password  → authenticate_user()
  [PIN]       email + 4-digit PIN
  [Pattern]   email + dot-pattern string
  [Master]    email + password + is_master_admin DB check
```

### Auth Store Schema

```python
{
    "user_id":       int,
    "email":         str,
    "role":          "admin" | "apartment" | "vendor" | "security",
    "society_id":    int | None,   # None for master admin
    "linked_id":     int,          # FK to apartments/vendors/security_staff
    "apartment_id":  int | None,   # portal scoping
    "vendor_id":     int | None,   # portal scoping
    "authenticated": True,
    "token":         str           # JWT
}
```

### Forgot Password Flow

1. User enters email → `request_password_reset()` → SHA-256 token stored in DB
2. Token emailed (hook in `auth_service.py`)
3. User enters token + new password → `reset_password()` → hash updated, token cleared

---

## 7. KPI Dashboard System

### How KPIs Work

1. **Definition** — each KPI is a dict entry in `KPI_CARDS` (`card_catalogue.py`)
2. **Shell rendered** — `_kpi()` in `portal_pages.py` creates the clickable card with `id={"type":"kpi-value","card_id":"..."}` showing `"—"` placeholder
3. **Value filled** — `refresh_kpi_values()` in `card_catalogue_callbacks.py` pattern-matches ALL `kpi-value` IDs and runs each SQL query on `url.pathname` change
4. **Click action** — `DRILLDOWN_MAP` in `registry.py` maps each `kpi_*` id to a target list card

### KPI Definition Schema

```python
"kpi_apartments_total": {
    "query":  "SELECT COUNT(*) AS v FROM apartments WHERE society_id = %s AND active = TRUE",
    "params": 1,          # number of %s placeholders (all are society_id)
    "format": "number",   # number | currency | percent | date | text
    "icon":   "fa-home",
    "color":  "#1859b8",
    "title":  "Apartments",
    "group":  "active",   # subtitle shown under value
},
```

### Format Types

| Format | Example Output |
|---|---|
| `number` | `1,234` |
| `currency` | `₹2.50L` / `₹1.20Cr` / `₹850` |
| `percent` | `12.5%` |
| `date` | `in 14d` / `3d ago` / `24 Jun 2025` |
| `text` | `Active` |

### KPI Audit Report

Navigate to **Admin → Customize → KPI Audit** tab and click **Run Full Audit** to:
- Execute every KPI query against the live DB
- See OK / NULL / ERROR / DUPLICATE KEY status per KPI
- View raw value, formatted value, and execution time (ms)
- Detect duplicate keys in `KPI_CARDS` dict

---

## 8. Financial Module

### Account Types

| `drcr_account` | Used For |
|---|---|
| `Cr` (Credit) | Income accounts — used in Receipts |
| `Dr` (Debit) | Expense accounts — used in Expenses |

The system validates at save time: you cannot post a Receipt to a Dr account or an Expense to a Cr account.

### Cashbook Logic

```
Opening Balance (bf_amount, drcr_bf)
    + All Cr transactions (receipts, maintenance, pass fees)
    − All Dr transactions (expenses, salaries, AMC)
    = Current Balance
```

### Receivables Calculation

Maintenance due is auto-calculated from `societies.arrear_start_date`:

```sql
months_due = EXTRACT(YEAR FROM AGE(CURRENT_DATE, arrear_start_date)) * 12
           + EXTRACT(MONTH FROM AGE(CURRENT_DATE, arrear_start_date))

maintenance_due = apartment_size × rate_per_sqft × GREATEST(months_due, 0)
```

Late fees accrue at **2% per month** on overdue pending payments.

### Transaction Save Flow

```
Form submit → handle_form_submit()
    → _save_transaction(db, data, sid, "receipt"|"expense")
        → validates account exists and Dr/Cr type matches
        → INSERT INTO transactions(...) VALUES(...)
        → navigate_back() → refresh list
```

---

## 9. Gate Pass & QR Scanning

### QR Generation

Each entity (apartment / vendor / security) can generate a gate pass QR code. The QR encodes:

```json
{"entity_id": 42, "role": "apartment", "society_id": 1, "name": "Flat A-101"}
```

Triggered via **profile action** `show_qr` → fires `profile-action-trigger` store → QR modal renders.

### Camera Scanner (Security Portal)

The **Gate Pass Evaluation** page provides:

- **Entry IN** button → starts back camera → scans QR → logs `time_in` in `gate_access`
- **Exit OUT** button → starts back camera → scans QR → updates `time_out`
- **Flip** button → toggles front/back camera
- **Torch** button → toggles flashlight (hardware permitting)
- **Recent Scans** panel → last 10 scan results with timestamps
- **Emergency** button → triggers alert
- **Call Admin** button → shows admin phone from society profile

### Gate Log DB Schema

```sql
gate_access (
    id, society_id, role,      -- 'a'=apartment, 'v'=vendor, 's'=security, 'g'=guest
    entity_id, time_in, time_out
)
```

---

## 10. Customize Tab — Layout Editor & KPI Inspector

### Layout Editor

Accessible at **Admin → Customize → Layout Editor**.

- Drag KPI cards from the **Palette** into the **Active Dashboard** zone
- Filter palette by portal and tab
- Save layout to DB — persists across sessions
- Reset to default layout per portal
- Maximum 4 active KPIs displayed (configurable)

### KPI Inspector

Accessible at **Admin → Customize → KPI Inspector**.

1. Select Portal → Tab → KPI from cascading dropdowns
2. View the raw SQL query in a read-only editor
3. See full metadata: format, group, color, icon, parameter count
4. Click **Test SQL Query** — runs against live DB with your `society_id`, shows raw value + formatted value + execution time

---

## 11. File & Image Management

### Upload Flow

```
dcc.Upload → handle_image_upload() callback
    → PIL resize to max 1920px width
    → JPEG compress at quality=85
    → Save to /app/assets/{society_id}/{entity}/{pk}/{filename}
    → Returns web path /assets/... stored in hidden form field
    → On form save: _move_temp_images() moves from /assets/default/
      to final location when new entity gets its PK
```

### Asset Directory Structure

```
app/assets/
├── {society_id}/                    ← society logo, login background, secretary sign
│   ├── {logo.jpg}
│   ├── apartment/{apt_id}/          ← apartment profile images
│   ├── vendor/{vendor_id}/          ← vendor logo, photos
│   ├── security/{sec_id}/           ← security staff photos, ID proof
│   ├── concern/{concern_id}/        ← complaint photos
│   └── event/{event_id}/            ← event banners
└── default/                         ← temp staging before PK is known
    ├── apartment/
    ├── vendor/
    └── society/
```

---

## 12. Tech Stack Reference

| Layer | Technology |
|---|---|
| Frontend | Python Dash 2.14 + React 16 |
| UI Components | Dash Bootstrap Components (DBC) |
| Backend | Flask (embedded in Dash) |
| Auth | Flask-Login + JWT (PyJWT) |
| Database | PostgreSQL via NeonDB (serverless) |
| DB Driver | psycopg2 |
| ORM | None — raw SQL via `db._execute()` wrapper |
| Image Processing | Pillow (PIL) |
| Excel Export | pandas + openpyxl |
| Hosting | ApexWeave |
| Password Hashing | Werkzeug `generate_password_hash` |

### Critical Dash Rules (hard-won)

```
Rule 1: allow_duplicate=True + prevent_initial_call=False  → CRASH
Rule 2: allow_duplicate=True + prevent_initial_call=True   → OK (no initial fire)
Rule 3: allow_duplicate=True + prevent_initial_call="initial_duplicate" → OK (fires initially)

Rule 4: Every Output in a callback using prevent_initial_call="initial_duplicate"
        MUST carry allow_duplicate=True — even outputs that are unique to that callback.

Rule 5: One callback = one canonical writer per (component_id, property).
        Two callbacks writing the same Output = "Duplicate callback outputs" error at startup.
```

---

## 13. Codebase Map

```
app/
├── dash_apps/
│   ├── app_shell.py                  ← Layout root
│   ├── callbacks/
│   │   ├── __init__.py               ← Registration order
│   │   ├── shell_callbacks.py        ← URL routing, tab switching, auth guard
│   │   ├── login_callbacks.py        ← All login methods + password reset
│   │   ├── card_catalogue_callbacks.py  ← KPI refresh ONLY
│   │   ├── drilldown_callbacks.py    ← Master drill-down router + form submit
│   │   └── debug_callbacks.py        ← KPI audit + SQL tester
│   ├── drilldown/
│   │   ├── __init__.py
│   │   ├── loaders.py                ← All DB reads
│   │   ├── renderers.py              ← All HTML card builders
│   │   ├── state.py                  ← Navigation stack manager
│   │   ├── registry.py               ← Maps, PK defs, helpers
│   │   └── savers.py                 ← CRUD write classes
│   └── pages/
│       ├── portal_pages.py           ← 5 portal layouts
│       └── card_catalogue.py         ← KPI_CARDS + FORM_CARDS dicts
├── services/
│   └── auth_service.py               ← authenticate_user(), reset flow
├── security/
│   └── rbac.py                       ← RBACManager, Permission enum
├── models.py                         ← Dataclasses + dict_to_* converters
└── assets/                           ← Static files + uploaded images

database/
└── db_manager.py                     ← db._execute() → NeonDB
```

---

## 14. 🗑️ Legacy Code Removal Guide

The following code exists in the codebase but is **no longer called, superseded by the drilldown engine, or actively causing bugs**. Remove it to clean up the codebase.

---

### 14.1 `card_catalogue_callbacks.py` — Remove List Loader Callbacks (2–10)

These callbacks duplicated `Output` IDs already owned by `make_form_card()` in `card_catalogue.py`, causing **"Duplicate callback outputs"** errors on startup. The drilldown engine (`drilldown_callbacks.py`) now owns all list rendering via `#drill-content`. **These callbacks are dead.**

**Remove everything between these markers:**

```python
# ❌ REMOVE: callbacks 2–10 in register_card_catalogue_callbacks()
# from this line:
    # ── 2. SOCIETIES LIST ─────────────────────────────────────────────────────
    @app.callback(
        Output("societies-list-table", "children"),
        ...
    )
    def load_societies_list(pathname, auth_data):
        ...

# through this line (inclusive):
    # ── 10. CHARGES LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("charges-list-table", "children"),
        ...
    )
    def load_charges_list(pathname, auth_data):
        ...
        except Exception as exc:
            ...
            return [...], _err_toast(exc)
```

**Keep only:** `format_kpi_value()`, `_err_toast()`, and the single `refresh_kpi_values` callback (#1).

---

### 14.2 `card_catalogue.py` — `FORM_CARDS` Static Table Bodies

The `FORM_CARDS` dict and `make_form_card()` function define list tables with `html.Tbody(id=cfg["list_id"])` for the **old static layout system**. These IDs (`societies-list-table`, `entities-list-table`, etc.) clash with the callback outputs above. The drilldown engine renders lists dynamically into `#drill-content` — these static shells are never populated.

**Status:** Safe to remove `FORM_CARDS` entirely if `make_form_card()` is not called from any active portal page. Before removing, run:

```bash
grep -r "make_form_card\|FORM_CARDS" app/ --include="*.py"
```

If the only usage is inside `card_catalogue.py` itself (the `make_card()` dispatcher and the DnD palette in the Customize tab), you can safely delete:

```python
# ❌ REMOVE OR ARCHIVE: the entire FORM_CARDS dict (~400 lines)
FORM_CARDS = {
    "society_profile": { ... },
    "society_create":  { ... },
    "society_list":    { ... },   # ← these list entries specifically cause the ID clash
    "entity_profile":  { ... },
    "entity_create":   { ... },
    "entity_list":     { ... },   # ← ID clash: "entities-list-table"
    "account_profile": { ... },
    "account_list":    { ... },   # ← ID clash: "accounts-list-table"
    "payment_list":    { ... },   # ← ID clash: "payments-list-table"
    "cashbook_list":   { ... },   # ← ID clash: "cashbook-full-table"
    "event_list":      { ... },   # ← ID clash: "events-list-table"
    "gate_log_list":   { ... },   # ← ID clash: "gate-logs-list-table"
    "concern_list":    { ... },   # ← ID clash: "concerns-list-table"
    "charge_list":     { ... },   # ← ID clash: "charges-list-table"
    ...
}

# ❌ REMOVE: make_form_card() function — renders the above static shells
def make_form_card(card_id: str) -> html.Div:
    ...

# ❌ REMOVE: make_card() dispatcher (calls make_form_card)
def make_card(card_id: str, value: str = "—") -> html.Div:
    ...
```

**Minimum fix (if you want to keep `FORM_CARDS` for the DnD palette):** Remove only the `*_list` entries from `FORM_CARDS` since those are the ones with clashing `list_id` values.

---

### 14.3 `card_catalogue.py` — Duplicate `format_kpi_value()`

There are **two identical implementations** of `format_kpi_value()`:

```python
# ❌ REMOVE: the copy at the bottom of card_catalogue.py (~60 lines)
def format_kpi_value(value, format_type: str) -> str:
    """
    Format a KPI value based on its type.
    ...
    """
    from datetime import date, datetime
    ...
```

**Keep:** Only the canonical version in `card_catalogue_callbacks.py`. The one in `card_catalogue.py` is imported by `debug_callbacks.py` via:

```python
from app.dash_apps.callbacks.card_catalogue_callbacks import format_kpi_value
```

So `debug_callbacks.py` already uses the correct source. The copy in `card_catalogue.py` is unreferenced.

---

### 14.4 `drilldown_callbacks.py` — Duplicate `_apply_portal_filters()`

This function is **defined twice** in the same file:

```python
# ❌ REMOVE: the first definition (around line 120, inside the module scope
#    before register_drilldown_callbacks())
def _apply_portal_filters(filters: dict, auth: dict) -> dict:
    """
    Augment DB filters so each portal only sees its own data.
    ...
    """
    role = auth.get("role", "admin")
    f = dict(filters)
    if role == "apartment":
        ...
    elif role == "vendor":
        ...
    return f
```

**Keep:** The second definition at the **bottom of the file** (after all the `_save_*` helpers). Both are identical — remove the first one.

---

### 14.5 `loaders.py` — Typed Entity-Specific Loader Functions

The bottom half of `loaders.py` contains typed wrappers (`load_apartments_list()`, `load_vendor_profile()`, etc.) that wrap `db._execute()` calls and return model objects via `dict_to_*` converters. These are **never called** — the drilldown engine uses the generic `load_list()` and `load_profile()` dispatchers at the top of the file which return plain dicts.

```python
# ❌ REMOVE: all typed loader functions below the generic dispatchers
# Starting from:
def load_apartments_list(
    society_id: int, search: str = "", has_dues: bool = None,
    page: int = 1, page_size: int = PAGE_SIZE
) -> tuple[list[Apartment], int]:
    ...

# Through:
def load_cashbook_profile(transaction_id: int) -> Transaction | None:
    ...
# (approximately 250 lines)
```

Also check the SQL introspection helpers — if `get_function_sql()`, `get_kpi_functions()`, `get_portal_kpis()` are not called from any active callback, remove those too:

```python
# ❌ LIKELY REMOVABLE: SQL introspection helpers (verify no callers first)
def get_function_sql(function_name: str) -> str: ...
def get_kpi_functions() -> list[dict]: ...
def get_portal_kpis(portal: str = None) -> list[dict]: ...
```

---

### 14.6 `savers.py` — OOP Saver Classes (Unused)

`savers.py` defines `ApartmentSaver`, `VendorSaver`, `SecuritySaver`, `EventSaver`, `ConcernSaver` classes with `create()`, `update()`, `delete()` static methods. The actual save logic in `drilldown_callbacks.py` uses the **inline `_save_*()` functions** — `savers.py` is never imported or called.

```python
# ❌ REMOVE: entire savers.py file, or keep as future refactor target
# Verify with:
grep -r "from app.dash_apps.drilldown.savers import\|from .savers import\|savers\." app/ --include="*.py"
# If zero results → safe to delete
```

---

### 14.7 `portal_pages.py` — Stale `evaluate_pass_card_body()` in Customize Tab

The `_evaluate_pass_card_body()` function inside `portal_pages.py` renders a second, older QR scanner (using IDs `eval-video`, `eval-canvas`, `eval-start-btn`, etc.). The **active scanner** uses IDs `qr-video`, `qr-canvas`, `qr-entry-start-btn` etc. defined in `_evaluate_pass_page()`. The `eval-*` version is only reachable via `make_form_card("evaluate_pass")` which is part of the legacy `FORM_CARDS` system.

```python
# ❌ REMOVE: once FORM_CARDS is cleaned up
def _evaluate_pass_card_body():
    """
    Evaluate Pass card body.
    Features: Manual QR input + Validate button + Camera preview...
    DOM IDs consumed by camera_callbacks.py:
        eval-qr-input, eval-validate-btn, eval-result, eval-scan-status,
        eval-video, eval-canvas, eval-scanline, eval-start-btn ...
    """
    return dbc.CardBody([...])  # ~180 lines using eval-* IDs
```

---

### 14.8 `card_catalogue.py` — `calculate_maintenance_for_apartment()` and `calculate_security_salary_due()`

These are standalone calculation functions at the bottom of `card_catalogue.py` that take a `db` parameter. They duplicate logic already present in the KPI SQL queries and are not called by any callback.

```python
# ❌ REMOVE: standalone calculation helpers (logic lives in KPI SQL queries)
def calculate_maintenance_for_apartment(db, apartment_id: int, society_id: int) -> dict:
    ...  # ~50 lines

def calculate_security_salary_due(db, security_id: int, society_id: int) -> dict:
    ...  # ~40 lines
```

---

### Summary Removal Checklist

| File | What to Remove | Lines (approx) | Risk |
|---|---|---|---|
| `card_catalogue_callbacks.py` | Callbacks #2–#10 (list loaders) | ~280 | ✅ Safe — confirmed dead |
| `card_catalogue.py` | `FORM_CARDS` `*_list` entries | ~100 | ✅ Safe |
| `card_catalogue.py` | `make_form_card()`, `make_card()` | ~80 | ⚠️ Verify DnD palette first |
| `card_catalogue.py` | Duplicate `format_kpi_value()` | ~60 | ✅ Safe |
| `card_catalogue.py` | `calculate_maintenance_for_apartment()` | ~50 | ✅ Safe |
| `card_catalogue.py` | `calculate_security_salary_due()` | ~40 | ✅ Safe |
| `drilldown_callbacks.py` | First `_apply_portal_filters()` def | ~15 | ✅ Safe |
| `loaders.py` | Typed entity loader functions | ~250 | ✅ Safe — verify no callers |
| `loaders.py` | SQL introspection helpers | ~30 | ⚠️ Verify no callers |
| `savers.py` | Entire file | ~230 | ⚠️ Verify no imports |
| `portal_pages.py` | `_evaluate_pass_card_body()` | ~180 | ⚠️ After FORM_CARDS removed |

**Total removable:** ~1,300 lines of dead code.

---

## 15. Deployment Notes

### Environment Variables Required

```
DATABASE_URL=postgresql://user:pass@host/dbname   # NeonDB connection string
SECRET_KEY=<flask-session-secret>
JWT_SECRET=<jwt-signing-secret>
```

### ApexWeave Hosting

- Set `debug=False` in `app.run_server()` for production
- Gunicorn recommended: `gunicorn app:server -w 4 -b 0.0.0.0:8050`
- `/app/assets/` must be writable for image uploads
- NeonDB connection pooling: use `?sslmode=require` in `DATABASE_URL`

### Database Migrations

All DB functions are prefixed `fn_` and use `%s` parameter syntax (psycopg2 style — **not** `:param` style). Schema changes require updating both the PostgreSQL function and the corresponding `loaders.py` query.

### Callback Registration Order (`callbacks/__init__.py`)

```python
# Order matters — register in this sequence:
register_shell_callbacks(app)        # 1. URL routing must be first
register_login_callbacks(app)        # 2. Auth before any data callbacks
register_card_catalogue_callbacks(app)  # 3. KPI refresh
register_drilldown_callbacks(app)    # 4. Navigation engine
register_debug_callbacks(app)        # 5. Dev tools last
```

---

*ApexEstateHub — Built for societies that mean business.*
