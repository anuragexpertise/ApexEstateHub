# EstateHub
### The Complete Society Management Platform

> **Multi-tenant · Role-aware · Real-time · Zero-reload**
> Built on Python Dash + Flask + PostgreSQL (Aiven) · Hosted on Render

> 📌 **Schema source of truth:** `database/estatehub.sql` — see [§22 Database Migrations](#22-deployment--utility-notes) for details.

> 🆕 **Recent release — fund segregation & the Agreement print fix.** Agreement
> Print/Save-as-PDF/Email was broken app-wide by a one-character typo in the
> shared letterhead JS; it now works, along with every other PDF export that
> uses the same helper. Fund Management gained **Appropriate Income → Fund**
> (moving a locked fund's earned interest into a spendable fund) and **Fund
> Deposit Routing** (per-fund destination bank account, with per-account bank
> reconciliation to match). Start at
> [§9 Fund Deposit Routing](#fund-deposit-routing--fund_bank_account_map),
> [§16](#16-postgresql-function-index) for the new functions, and
> [§19](#19-known-bugs--fixes-applied) for the full list of what was broken.

---

## Table of Contents

1. [What is EstateHub?](#1-what-is-estatehub)
2. [Feature Highlights](#2-feature-highlights)
3. [Architecture Overview](#3-architecture-overview)
4. [The Five Portals](#4-the-five-portals)
    - [4.6 Concern Lifecycle (`concerns_assigns`)](#46-concern-lifecycle-concerns_assigns)
5. [Portal Data Scoping](#5-portal-data-scoping)
6. [Drill-Down Navigation Engine](#6-drill-down-navigation-engine)
7. [Authentication & Security](#7-authentication--security)
8. [KPI Dashboard System](#8-kpi-dashboard-system)
9. [Financial Module](#9-financial-module)
10. [Pay Dues — Five Paths](#10-pay-dues--five-paths)
11. [QR Code & Access Control Architecture](#11-qr-code--access-control-architecture)
12. [Default Profile (No KPI Selected)](#12-default-profile-no-kpi-selected)
13. [Customize Tab — Layout Editor & KPI Inspector](#13-customize-tab--layout-editor--kpi-inspector)
14. [File & Image Management](#14-file--image-management)
15. [Tech Stack Reference](#15-tech-stack-reference)
16. [PostgreSQL Function Index](#16-postgresql-function-index)
17. [Codebase Map](#17-codebase-map)
18. [Critical Dash Rules](#18-critical-dash-rules)
19. [Known Bugs & Fixes Applied](#19-known-bugs--fixes-applied)
20. [🚩 Open Design Subtleties & Flagged Caveats](#20--open-design-subtleties--flagged-caveats)
21. [🧹 Legacy Code Cleanup Status](#21--legacy-code-cleanup-status)
22. [Deployment & Utility Notes](#22-deployment--utility-notes)
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
| **Statutory** | UP AOA compliance layer (bye-laws 7/39/49, undivided interest, s.22, cash limits) as **data-driven rules** · loans to owners · Funds Account schedule |
| **Entities** | Apartments · Vendors · Security Staff · Societies · Accounts · Assets |
| **Operations** | Events · Concerns/Complaints · Gate Logs · Attendance · NOC |
| **Gate Pass** | Fernet-encrypted QR · Dual-mode camera scanner · Entry IN / Exit OUT |
| **Reports** | XLSX export on every list · KPI Audit Report |
| **Customization** | Drag-and-drop KPI layout editor per portal+tab · KPI SQL Inspector |
| **Images** | WebP compression · Logo · Login background · Secretary sign · Profile photos |
| **DB** | PostgreSQL `fn_*` stored functions · `%s` parameterised queries via psycopg2 |
| **Security Portal** | Pending receipt creation → admin verification workflow |
| **NOC** | Eligibility check → rich-text editor → Print / Save as PDF / Email (shared letterhead) |
| **Gate Pass (NFC)** | Web NFC API — write signed pass payload directly to an NFC tag from the browser |
| **Patrol** | Interactive Leaflet map for patrol-location create/reissue, with geofencing |
| **Bank Reconciliation** | Per-bank-account Excel statement upload, exact + fuzzy matching against receipts/expenses, per-row manual reconcile |
| **Fund Management** | Statutory fund balances with lock/drawable split · Utilize Fund (honours `statutory_lock_pct`) · **Appropriate Income → Fund** (Dr income / Cr fund) with pending→confirm workflow · **Fund Deposit Routing** (per-fund destination bank account) |
| **Fund Deposit Routing** | A fund's contributions can be banked into a separately-held account/FD instead of the society's primary account; enforced at posting time by `fn_resolve_bank_leg`, and statement uploads are matched per account |
| **Society Onboarding** | First-time Setup Wizard (charges, GST/TDS defaults, brought-forward, plus a read-only **UP AOA Compliance** step tabulating the governing Act / Rules / Bye-laws from `legal_instrument_catalog`, and a **Bye-Laws Adoption** step where the admin records which Model Bye-Laws clauses the Association is adopting — provisional until a General Body resolution is recorded) + Agreement flow with Print / Save as PDF and an Email button that opens your mail app (`mailto:`; nothing is sent server-side) (shared letterhead: logo · watermark · secretary signature · verification QR) |
| **Bulk Enrollment** | Excel upload for apartments/vendors/security with template download |

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
│   ├── bulk_enroll_callbacks.py  ← Excel bulk upload for members/staff
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

### 4.6 Concern Lifecycle (`concerns_assigns`)

A concern's state lives in **one row per assignee** in `concerns_assigns`, keyed
by `(concern_id, role, entity_id)` where `role` is `ADM` / `VND` / `SEC`.
`concerns.status` is **not** written by application code after the initial
INSERT — it is a read-only aggregate cache maintained by one trigger,
`fn_trg_sync_concern_status` → `fn_sync_concern_status(concern_id)`.

**Per-role stage chains**

| Role | Chain | How they get on the concern |
|---|---|---|
| `VND` (vendor) | `invited` → `bid_submitted` → `assigned` → `resolved` → `closed` (or `declined` from `invited`) | **Invite** → **Bid** (may submit *and revise* while `invited` or `bid_submitted`) |
| `SEC` (security) | `assigned` → `resolved` → `closed` | **Assign** only — see below |
| `ADM` (admin) | `assigned` → `accepted` → `resolved` → `closed` (or `declined` from `assigned`) | **Assign** (admins never bid) |

**Security do not bid.** There is no invitation round for them: an `invited`
`SEC` row has no legal way forward, because `Bid`/`Decline` are vendor-only and
`bid_submitted` is not reachable from any security action. The Invite modal's
`SEC` branch therefore writes the row straight at `assigned`, and
`loaders.invite_concern_assignee()` rejects `SEC` outright with a pointer to
Assign. Their **Resolved** button needs *both* halves of the gate — the guard's
own row at `assigned` **and** an admin row on the same concern having reached
`accepted`. Checking the admin row alone (as the code once did) offered the
button to guards who were never assigned, or had already resolved.

**The `concerns.status` aggregate counts "touched" rows only** — rows that
reached `assigned` or beyond. Candidates still at `invited` / `bid_submitted` /
`declined` are excluded entirely, so a losing bidder can never hold a concern
back at `assigned` after its actual assignee has resolved.

| Condition (over touched rows) | `concerns.status` |
|---|---|
| no touched rows | `open` |
| all `closed` | `closed` |
| all `resolved` or `closed` | `resolved` |
| otherwise | `assigned` |

`open` is a bucket covering three different situations — nobody invited yet,
candidates invited and bidding, and every candidate declined — so the profile
banner derives its wording from the actual assignment rows rather than from
this column alone.

**Invariants — do not break these**

- Every helper in `loaders.py` is a **stage transition**, not an unconditional
  write. Re-invite refuses to touch a row at `assigned` / `accepted` /
  `resolved` / `closed` (`RE_INVITE_BLOCKED_STAGES`); re-assign refuses
  `accepted` / `resolved` / `closed` (`REASSIGN_BLOCKED_STAGES`) but *does*
  allow re-pointing a still-`assigned` row, which is a legitimate mid-flight
  correction. Each guard reads the row under `SELECT … FOR UPDATE` so a
  rejection can name the stage that blocked it.
- `close_concern()` requires at least one assignment row and no row still at
  `assigned` / `accepted` (`CLOSE_BLOCKING_STAGES`). Without that it reported
  "Concern closed" on a concern with no assignees — the write matched nothing,
  the trigger left `concerns.status` at `open`, and a close push still went out.
  `loaders.concern_is_closable()` is the same predicate and gates the button.
- Unchecking someone in the Assign modal must not erase committed work:
  `accepted` rows are protected exactly like `resolved` / `closed`.
- A concern's content is **frozen** once any row reaches `bid_submitted` or
  beyond — `_save_concern`'s edit branch refuses, because the
  `v.service_type ILIKE concern_type` match is what decides which vendors can
  be invited at all.
- The `concerns.preferred_time` column is `TIME`: an unset form value must be
  `NULL`, never the string `"anytime"`.
- `concerns.concern_type` defaults to `field_config.DEFAULT_CONCERN_TYPE`
  (`"general"`), shared by the form pre-fill and the save handler so the two
  cannot disagree. The default decides which vendors a blank concern can ever
  be assigned to.
- Owner-initiated Invite / Assign / Close are restricted to concerns whose
  `created_by` is the caller, checked server-side on every path (button
  visibility is not a guard).
- **Only Admin and Owner may raise a concern.** `("vendor", "concerns")` and
  `("security", "concerns")` are **view-only** — a `"new"` perm renders a
  `New` button on the list card that routes to `form_concern_new`, where
  `apartment_id` is `ADMIN_ONLY`-editable and therefore read-only and empty
  for those roles, so the only thing it could ever produce is an orphan
  concern with `apartment_id = NULL` that no owner can see, invite for, or
  close. `_save_concern` refuses such a write server-side too, so a directly
  posted callback cannot get around the perm. (Note that
  `field_config.get_validation()` has **no callers** — every `_save_*` handler
  validates its own fields by hand, so `"required"` in `FIELD_CONFIG` is
  documentation, not enforcement.)

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

**Plan expiry (A13).** A paid society whose `plan_validity` has passed can no longer log in, and open sessions are cut off at the router with a "Plan Expired" page. The `Free` plan never expires and Master (no society) is exempt. `PLAN_GRACE_DAYS` (env, default 7) keeps an expired society usable for a few days after the validity date; set it to `0` for a hard cut-off. The rule lives in `app/security/plan_guard.py`; Master renews by editing the society's validity date.

1. User enters email → `request_password_reset()` → SHA-256 token stored in DB with a 1h expiry (`RESET_TOKEN_HOURS`)
2. Token is emailed via `app/services/mailer.py` (uses the `SMTP_*` settings). If SMTP is not configured or the send fails, the token is written to the server log so an operator can relay it. The user always sees the same message, "Reset mail sent if account available in database.", whether or not the account exists or the mail went out. The mail server should offer **STARTTLS**; if it does not, the mail is still sent but a warning is logged and the message travels unencrypted
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

### EstateHub Compliance — Statutory Framework Coverage

Mapped against the consolidated statutory framework for Indian RWAs/CHS/AOAs (`database/Statutory Compliance Framework for Indian RWAs.pdf`) — both its core statutory table (Income Tax Act, TDS, GST, earmarked-fund/bye-law regime) and its Section 1 internal-audit checklist, which is where the Labour & Safety row below comes from. ✅ = implemented and live-verified. 🟡 = partially covered or not yet built (see note). State Cooperative Societies Acts / Model Bye-laws vary by state — coverage below is UP AOA 2010–first, with a jurisdiction table so other states can be added without a schema change.

| Regulatory Area / Statute | Governing Sections / Rules | Statutory Requirement & Scope | EstateHub Coverage |
|---|---|---|---|
| Income Tax Act, 1961 — Taxability & Mutuality | Sec. 2(31), Sec. 4, Doctrine of Mutuality | Member maintenance is exempt under Mutuality; non-mutual income (bank interest, rentals, cell towers) is taxable at AOP rates | ✅ `accounts.mutuality_nature` tags every income account mutual/non-mutual; `fn_income_tax_summary_fy` + Mutuality Summary export (`income_tax_export.py`) segregate the two automatically |
| Income Tax Act, 1961 — Deductions | Sec. 80P(2)(c) / 80P(2)(d) | Deduction on interest from cooperative banks, claimed via annual return | 🟡 Not yet tracked — no 80P deduction computation; would sit alongside the mutuality report |
| Income Tax Act, 1961 — Return of Income | Sec. 139(1), Sec. 44AB | Annual ITR-5 filing; tax audit if commercial turnover exceeds threshold | 🟡 Out of e-filing scope by design (EstateHub is a books-of-account system, not a TRACES/ITR e-filer); no Sec. 44AB turnover-threshold flag yet |
| TDS (Income Tax Act, 1961) | Sec. 194A, 194C, 194H, 194-I, 194-IA/IB/IC, 194J | Deduct TDS on vendor payouts (contracts, professional fees, rent, brokerage, etc.), remit, file 26Q | ✅ `tds_compliance.py` — full section/rate/PAN-vs-no-PAN engine (`fn_compute_tds_pct`), single-bill & annual-aggregate threshold logic, no-PAN warn/block setting; `tds_export.py` produces a structured 26Q-shaped quarterly export (a CA transcribes it into the government portal — not a live TRACES integration) |
| Labour & Safety Compliances | EPF & MP Act, 1952 / ESI Act, 1948 / Contract Labour (Regulation & Abolition) Act, 1970 | Minimum-wage/EPF/ESIC compliance for direct employees; manpower agencies (security, housekeeping) must furnish monthly PF/ESIC challans (ECR) before their invoice is cleared | 🟡 Not tracked at all — no ECR/PF/ESIC challan capture, verification, or invoice-hold gate exists anywhere in the vendor payment flow (`fn_save_expense`/`fn_verify_expense`); this is a genuine gap, not a partial implementation, and would need a new challan-attachment + hold-until-verified step ahead of TDS deduction |
| GST (CGST Act, 2017) | Sec. 22(1), Notification 12/2017-CT(R) Entry 77 | ≤ ₹7,500/month/member exempt; above that, 18% on the entire amount if society turnover > ₹20L (₹10L special-category states); RCM on unregistered vendors | ✅ `gst_rates` table (replacing hardcoded 18%), registration-threshold gate, segregated RCM CGST/SGST/IGST Payable + ITC-Receivable accounts, interstate/IGST determination via `societies.state`/`vendors.state`; `gst_export.py` produces a GSTR-1/3B-shaped summary |
| Reserve Fund | Societies Registration Act / State Cooperative Societies Acts (e.g. MCS Act Sec. 66 / 154B-17) | Statutory reserve from net surplus, for long-term solvency. Under the UP regime the ½% transfer fee does **not** go here: bye-law 39 sends it to the Major Repair Fund (3270) | ✅ Mapped to the `RESERVE_FUND` statutory head (UP AOA regime); ledger-segregated from operating income, verified via reserve-fund-segregation test scenarios. **The net-surplus appropriation is automatic** — closing a financial year transfers the bye-laws' fixed share of that year's surplus into the reserve (see How Money Enters Each Fund below) |
| Sinking Fund | Model Bye-laws (13(c)/14(c)) / State Apartment Ownership Acts | Dedicated fund for structural overhauls, lifts, DG sets; ~0.25–0.33%/yr of construction cost | ✅ Dedicated `Sinking Fund Reserve` ledger account, per-society rate config (`sinking_fund_rate_basis`: per-sq-ft or construction-cost), state-specific statutory rate defaults (UP/MH) in `state_compliance_thresholds`, auto-billed monthly |
| Repair & Maintenance Fund | Model Bye-laws (13(a)/14(b)) | Routine upkeep of common areas/plumbing/electricals; typically ≥ 0.75%/yr of construction cost | ✅ Dedicated `Repair & Maintenance Fund Reserve` ledger account, same rate-config/billing pipeline as Sinking Fund |
| | Corpus Fund | RERA Act, 2016 (Sec. 11(4)(g), Sec. 17) / State Apartment Ownership Acts | One-time builder-handover capital receipt; principal inviolable, only interest deployable | ✅ Dedicated `Corpus Fund` ledger account, mapped to its statutory head; balance sheet treats it as a capital reserve, not operating income (per the three-statement report's I&E vs. Balance Sheet split). **Principal protected at the ledger level** — `accounts.statutory_lock_pct` (100.00 for the seeded Corpus Fund) is enforced by `fn_process_fund_utilization()`, which refuses any draw that would breach the locked share and reports the deployable amount separately |
| UP Apartment Act 2010 / Model Bye-Laws 2011 — Major Repair Fund | Model Bye-Laws bye-law 39 | ½% of the transfer value goes to the association for major repairs; No Dues Certificate deemed granted if not refused within 15 days | ✅ Engine + card — `fn_record_apartment_transfer` levies the fee as a receivable into account 3270 (head `MAJOR_REPAIR_FUND`) with its accrual leg; `fn_nodues_certificate_status` tracks the 15-day deemed grant; `fn_ensure_major_repair_fund` creates 3270 idempotently. UI: **UP AOA Compliance** card §3 |
| UP Apartment Act 2010 — Undivided interest | Act s.5(2), s.12(1)(f), s.18(1) | Common expenses are shared by each flat's percentage of undivided interest in the Declaration | ✅ Engine + card — `apartments.undivided_interest_pct` (flat area ÷ total area × 100 until the Declaration's own figure is entered) + `fn_undivided_interest_report/summary` + `fn_backfill_undivided_interest`. Billing can run **by undivided interest** (`apt_charges_fines_basis.billing_basis`, monthly budget × %); default stays per sq ft, and a flat without a % falls back to per sq ft. Sinking/repair levies stay per sq ft. Switch it on the UP AOA Compliance card §2 |
| UP Model Bye-Laws — Bye-law 49 filings | bye-law 49 | Audited statement by 31 Jul, copy to competent authority by 15 Aug, summary to owners within 15 days, owner and loanee lists attached | ✅ Engine + card — `fn_statutory_calendar` + `aoa_statutory_filings` (upsert per `fy_start_year`); `fn_aoa_owner_list` / `fn_aoa_loanee_list`. UI: UP AOA Compliance card §1, including an Excel download of both lists |
| UP Model Bye-Laws — Bye-law 7 | bye-law 7 | Owners with arrears over 60 days cannot vote or stand for the Board | ✅ Engine + card — `fn_bye_law7_eligibility` / `fn_bye_law7_cutoff_date`. Whether "year" means financial or calendar year is contested; default is financial year, switchable via `regime_rule_parameters.bye_law7_year_basis`, the `p_basis` argument, or the card's basis dropdown. Uses the balance outstanding when called. Card §4 |
| UP Apartment Act 2010 — Section 22 | s.22 | Essential services may be cut only after >6 months default, 7 days notice, a general-body resolution, certified copy to the competent authority and owner, a one-month wait, a displayed notice and the appeal window | ✅ Engine + card — `service_cutoff_proceedings` + `fn_service_cutoff_check` reports blockers and the earliest lawful date; it never cuts anything itself, and the card refuses to record a cut-off the check does not allow. Card §5 |
| UP Model Bye-Laws — Cash and cheque limits | financial provisions (bye-laws 46-52) | Petty cash ceiling ₹20,000; payments above ₹2,500 by cheque | ✅ Engine + card — `fn_verify_expense` flags cash payments over the threshold (`compliance_flags`), or refuses them when `societies.cash_limit_mode='block'`; `fn_petty_cash_check` compares cash-in-hand with the ceiling; `fn_disburse_owner_loan` applies the same limit to cash disbursals. Card §7 is read-only |
| UP Model Bye-Laws — Loans to owners | bye-law 3(1)(f) | The association may lend to owners | ✅ Engine + card — `fn_disburse_owner_loan` (Dr Loans to Owners 1410 / Cr cash or bank; resolution reference mandatory; cash limit applies) and `fn_repay_owner_loan` (Cr 1410 principal, Cr Interest on Owner Loans 4116 interest). Loans entered before this change stay register-only and cannot be repaid through the ledger. See [Owner Loans & Loanees](#owner-loans--loanees-bye-law-31f) |

### UP AOA Regime Parameters — `regime_rule_parameters`

Every statutory threshold the UP layer enforces is **data, not code**, in `regime_rule_parameters (regime_code, rule_key, value, value_text, unit, source_reference, effective_from, effective_to)`. Looked up through `fn_regime_param_num(society_id, key, on DATE DEFAULT CURRENT_DATE)` / `fn_regime_param_text(...)`, which pick the latest row whose `effective_from <= p_on` and whose `effective_to` is NULL or still open — so a rule change is a data migration, never a redeploy.

A society reaches these rows only through `society_legal_regime` (assigned by `seed.py:seed_society_legal_regime()` where `societies.state = 'Uttar Pradesh'` → `UP_AOA_2010`, `effective_from 2011-11-16`). **If that row is absent, every function in this layer returns empty/`NULL` rather than a default** — see the "rule not applicable ≠ compliant" note below.

| `rule_key` | Value | Unit | What it drives |
|---|---|---|---|
| `transfer_fee_pct` | `0.5` | % of value | Bye-law 39 fee on a flat transfer → Major Repair Fund. **Also the on/off switch for the whole card** |
| `nodues_deemed_days` | `15` | days | No Dues Certificate deemed granted if not refused within 15 days |
| `petty_cash_limit` | `20000` | INR | Cash-in-hand ceiling (`fn_petty_cash_check`) |
| `cash_payment_cheque_threshold` | `2500` | INR | Cash above this must be cheque/bank. Only `mode='cash'` counts as a breach — the threshold pre-dates UPI/NEFT |
| `cash_limit_default_mode` | `'warn'` | text | Engine policy: `warn` records a `compliance_flags` row and still posts; `block` refuses |
| `statement_publish_due_month` / `_day` | `7` / `31` | month/day | Bye-law 49 audited statements published |
| `authority_copy_due_month` / `_day` | `8` / `15` | month/day | Bye-law 49 copy to the competent authority |
| `owner_summary_days` | `15` | days | Summary to every owner after publication |
| `arrears_disqualify_days` | `60` | days | Bye-law 7: arrears beyond this bar voting / standing |
| `bye_law7_year_basis` | `'financial_year'` | text | Whether "the year before" is the financial or calendar year (contested — advocates differ) |
| `s22_default_months` | `6` | months | s.22 service cut-off only after **more than** 6 months' default |
| `s22_notice_days` | `7` | days | s.22 notice to the defaulter |
| `s22_wait_months` | `1` | months | Wait after the certified copy goes to the authority and the owner |
| `s22_appeal_days` | `15` | days | Owner appeal window |
| `s20_recovery_months` | `12` | months | Seeded, but **no function in this layer reads it** |

Three override tiers sit on top: **per call** (`p_basis` on the bye-law 7 functions, exposed as the card's basis dropdown) → **per society** (`societies.cash_limit_mode`, set by master in **Master → AOA Rule Editor**) → **per regime + effective date** (insert a new `regime_rule_parameters` row).

> **A rule the society's regime doesn't define returns empty/`NULL`, never a default and never "compliant".** Callers must read that as *rule not applicable*. `fn_bye_law7_eligibility` returns **zero rows** (not "everyone is eligible") when `arrears_disqualify_days` is unset, and the card hides itself entirely when `fn_regime_param_num(society_id, 'transfer_fee_pct') IS NULL`.

### AOA Rule Editor (Master → AOA Rule Editor)

Master-only maintenance of the rule tables behind the UP AOA layer: `app/services/regime_rules_admin.py`, `pages/master_rules_page.py`, `callbacks/master_rules_callbacks.py` (ids prefixed `mrl-`). The role is read from the server-side session, never the browser's auth-store.

| Area | How it changes | Guards |
|---|---|---|
| `regime_rule_parameters` | **New dated version** (`effective_from` ≥ tomorrow, after every existing version); the row it replaces gets `effective_to = start − 1` | Only seeded keys; type/range check per key; bye-law 49 dates must be real and publish ≤ authority copy; unchanged value refused; statutory keys need the amending instrument cited (different from the one on file) plus an explicit confirmation; reason required |
| `legal_instrument_catalog` | Status / applicability / provisions / source / last-verified | Never deleted — retire with `status = 'superseded'`; no future verified date |
| `societies.cash_limit_mode` | `warn` / `block` / blank = regime default | Society must exist; reason required |

Every write is one SQL statement that also inserts into `regime_rule_audit` (append-only; a trigger rejects UPDATE/DELETE), so change and audit commit together. **Integrate to DB** now refuses INSERT / UPDATE / DELETE / TRUNCATE / ALTER / DROP / COPY on `regime_rule_parameters`, `legal_instrument_catalog`, `legal_regime_profiles`, `society_legal_regime` and `regime_rule_audit` — a guardrail, not a security boundary.

**State → regime sync.** `societies.state` is written as a code (`UP`) by the wizard, but every `fn_regime_param_*` / compliance function reads `society_legal_regime`, which only `seed.py` ever filled (matching the full name `Uttar Pradesh`). `fn_sync_society_regime` + trigger `societies_sync_regime` now assign the active regime for a state on insert/update (code or full name; a draft regime such as MH is never assigned; a state with no active regime leaves any existing row untouched).

Owner loans in the dues checks are governed by three policy switches in this editor — see Owner Loans & Loanees.

### Bye-Laws Acceptance & Governance

How a society's own decisions — not just the statute — reach the engine. Tables `society_bye_laws`, `meetings`, `resolutions`, `decision_types`, `resolution_effects`; service `regime_rules_admin.py`; functions `fn_resolve_rule`, `fn_get_standing`.

**Four layers; a lower layer never loosens a higher one.**

| Layer | Source | Who decides | Stored as |
|---|---|---|---|
| 0 | UP Apartment Act 2010 / Rules 2011 | Locked | Baseline inside `fn_resolve_rule` (bye-laws 7, 39, 46, 49; ss. 20, 22) and `regime_rule_parameters` |
| 1 | Model Bye-Laws 2011 — per clause: **adopt as-is / adopt with variation / not adopted** | General Body, 2/3 (`ADOPT_BYE_LAW`) | `society_bye_laws.layer = 1` |
| 2 | Society policy — may only tighten a Layer-1 clause | General Body, 2/3 (`SET_SOCIETY_POLICY`) | `layer = 2` |
| 3 | Board decision — operational limits | Managing Committee (`SET_BOARD_PARAM`) | `layer = 3` |

**Provisional → active.** A choice saved without a resolution is stored `status = 'provisional'` and remembers the intended outcome in `proposed_status`; the engine ignores it. It becomes active when the society admin records a **passed** resolution (`gov_save_resolution` activates the matching provisional choice automatically; `link_provisional_to_resolution` remains as a service-level manual path). `_check_resolution` refuses a resolution that is not this society's, not passed, for a different clause, of the wrong decision type for the layer, taken at a meeting with no recorded quorum, or (for GBM-bodied types) not taken at a GBM/EGM. `create_resolution` will not record a resolution as passed on a smaller majority than its decision type requires. The four statute-backed clauses (`STATUTE_BACKED_CLAUSES`: BL_07 arrears bar, BL_39 No Dues / transfer fee, BL_49 cash limits and statement filings, BL_55 Act prevails) cannot be "not adopted" unless the society's `droppable_BL_xx` policy (Setup Wizard → Bye-Laws Adoption → Society resolution settings, active once a passed resolution is recorded) says otherwise. Clause numbers and titles follow the Model Bye-Laws notified 16 Nov 2011 (No. 3977/8-1-11-115D.A./02T.C.-I); which clauses are non-droppable is a legal call, so confirm with an advocate. BL_55 can never take a variation. Other Setup Wizard policies: `nodues_blocks_on` (loans only | dues and loans), `vote_ineligibility_basis` (any overdue bill | arrears over 60 days) and `vote_loan_basis` (loan over 60 days past due | any loan past due) for "no dues" polls. Bye-law 7 itself governs Board elections only; poll eligibility is engine policy. Arrears of exactly 60 days are still eligible.

**Where each choice is made**

| Where | Who | What |
|---|---|---|
| Setup Wizard → **Bye-Laws Adoption** | Society admin (own society only) | Radio per clause → provisional Layer-1 row, saved on click (`record_wizard_adoption`). Clauses left alone follow the Model Bye-Laws / Act as written |
| Master → AOA Rule Editor → Society Bye-Laws | Master | Radio form for any layer, with an optional passed-resolution id; register shows layer, state (Provisional / Active) and the intended outcome |
| Master → AOA Rule Editor → Meetings & Resolutions | Master | Record GBM / EGM / MC meetings (quorum flag, minutes path) and resolutions; link a provisional choice to a passed resolution (service-level; the admin's governance screen activates it automatically) |

Every write also inserts into `regime_rule_audit`.

**`fn_resolve_rule(society, clause, date)`** returns the most specific *active* adoption — Layer 3 over 2 over 1 — and falls back to the Layer-0 baseline. `provisional`, `not_adopted` and resolution-less rows never resolve. `adopted_as_is` resolves to the baseline text.

**`fn_get_standing(society, apartment, date)`** is the one defaulter definition behind No Dues / NOC, poll voting, bye-law 7 candidacy and s.22:

| Column | Meaning |
|---|---|
| `dues_outstanding` / `dues_overdue` | Pending + partial receivables / those past `due_date` |
| `arrears_bye_law7` | Receivables more than `arrears_disqualify_days` (60) past due |
| `loan_outstanding` / `loan_overdue` | Owner-loan balance / the part past the bye-law 7 margin (policy `owner_loan_counts_bye_law7`) |
| `ineligible_vote` | Any overdue receivable, or an overdue loan — used by `fn_cast_vote` for "no dues" polls |
| `ineligible_stand` | `arrears_bye_law7 > 0` or overdue loan — bye-law 7 candidacy. *Merely overdue is not enough: arrears must exceed the margin* |
| `noc_blocked` | Any outstanding dues, or an outstanding loan when `owner_loan_blocks_nodues` |
| `s22_blocked` | No receivable beyond `s22_default_months` (and no counted loan) — cut-off not allowed |

**Polls.** `polls.quorum_pct` (default 33.33) and `majority_pct` (default 50). `fn_declare_results` returns `(success, message, results)`. A poll that misses quorum or majority is **not** declared — it stays as it was and the admin sees why; only a poll that carries is marked `results_declared` and notified.

**How the modules are governed**

| Module | Governed by | In the engine today |
|---|---|---|
| Enrollment of apartments / members | Bye-law 29 (register of members), 40 (succession) | 🟡 Register only — no rule-driven check |
| Receivables / receipts | Bye-laws 15, 38 (levy), s.18(1) | ✅ Billing by area or undivided interest. 🟡 s.20 (recovery after 12 months) is only a baseline string in `fn_resolve_rule`; nothing enforces it |
| Payables / expenses | Bye-law 46–47 (cash/cheque, petty cash) | ✅ `fn_verify_expense` flags or blocks; `fn_petty_cash_check` |
| Funds | Bye-laws 16–18, 39, 48 | ✅ Fund accounts, FY-close appropriation, ½% transfer fee → Major Repair Fund |
| Owner loans | Bye-law 3(1)(f), resolution mandatory | ✅ Ledger-posted; counted in No Dues / bye-law 7 per policy |
| Transfers / NOC | Bye-law 39 | ✅ `fn_get_standing.noc_blocked`; 15-day deemed grant |
| Polls / voting | Bye-laws 7, 33; quorum | ✅ Eligibility via `fn_get_standing`; quorum + majority at declaration |
| Board elections | Bye-law 7 | ✅ `fn_bye_law7_eligibility` (60-day arrears) |
| Service cut-off | s.22 | ✅ `fn_service_cutoff_check`; resolution reference recorded |
| Statements & filings | Bye-law 49–52 | ✅ Calendar, filings, owner and loanee lists |
| Concerns, Channels | Bye-law 9 (Board powers), 13 (committees) | 🟡 Not linked to any bye-law or resolution |
| Vendors, Security | Bye-law 19 (staff), 27 | 🟡 Not linked to any bye-law or resolution |

**Known gaps (not yet built)**
- `fn_get_standing` reads `regime_rule_parameters`, **not** `fn_resolve_rule` — an adopted variation (e.g. a 45-day arrears margin) is recorded and shown but does not yet change the engine. Wiring it needs a parameter grammar for `variation_text` (whitelisted keys, tighten-only comparison).
- `resolution_effects` has no writer, so Master's "pending enactments" list is always empty; provisional → active happens automatically when the admin records a passed resolution (`link_provisional_to_resolution` is the manual service-level path).
- "Tighten only" for Layers 2/3 is a rule in this section, not a check — free-text variations cannot be compared.
- Meetings and resolutions are recorded by Master; there is no admin/secretary entry screen and no read-only mirror on the Admin UP AOA Compliance card.
- A poll that carries does not create a resolution; ratification at a GBM is manual.

> Confirm bye-law numbers and the statute-backed clause list with an advocate before relying on them in a filing.

### UP AOA Compliance Card (Admin → Financials)

Nav tile `kpi_up_compliance` (group `Financials`, icon `fa-gavel`) → card `form_up_compliance`, bypasses `DRILLDOWN_MAP` like `kpi_fund_management`. Present **only** in `DEFAULT_LAYOUTS["admin"]["financials"]`. Admin-only is enforced in **three independent places** — the tile click (`drilldown_callbacks.py`), the card render, and `up_compliance_callbacks._ctx()` on every write — and `society_id`/`user_id` always come from the server session, never the browser. Non-admins (including `master`) get "Admin only."

The card **records and checks**; it never files with an authority, never disqualifies a member and never cuts a service itself. Its standing disclaimer: *"Confirm bye-law numbers with an advocate before relying on them in a filing."* When the regime isn't UP, it renders a single alert pointing at the State field in Society Details.

| § | Section | What the admin does | Component id prefix |
|---|---|---|---|
| 1 | Statement filings (bye-law 49) | Records the three filing dates + auditor, ticks the owner/loanee list attachments (upsert on `(society_id, fy_start_year)`), **downloads the owner + loanee annexures as a 2-sheet XLSX** | `upc-fil-*`, `upc-export-*` |
| 2 | Undivided interest & billing basis | Backfills missing `%` from area share, switches society-wide maintenance billing between `per_sqft` and `undivided_interest` with a monthly budget | `upc-ui-*`, `upc-basis-*` |
| 3 | Transfers: Major Repair Fund & No Dues | Records a flat transfer and levies the ½% fee; then sets No Dues requested / refused / issued dates | `upc-tr-*`, `upc-nd-*` |
| 4 | Who can vote or stand (bye-law 7) | Picks an election date + year basis → lists only the **blocked** flats with overdue amount, oldest due date and days overdue | `upc-b7-*` |
| 5 | Cutting an essential service (s.22) | Opens a proceeding, records each of the 7 steps, and sees the exact blocker list + earliest lawful cut-off date | `upc-s22-*` |
| 6 | Loans to owners (bye-law 3(1)(f)) | Records a disbursement and repayments — see below | `upc-ln-*`, `upc-rp-*` |
| 7 | Cash & cheque limits | **Read-only**: petty-cash badge + the last 10 `compliance_flags` | — |

Python side is `app/services/up_aoa_actions.py` (every handler returns `(ok, message)` and re-checks society ownership via `_owns()` before touching a browser-supplied id) plus `app/dash_apps/pages/up_compliance_card.py` (renderer). **The rules are enforced in SQL**; `up_aoa_actions` only validates form input and calls them.

> **`app/services/up_aoa_compliance_service.py` is currently dead code** — a thin read-only wrapper over nine of these functions with zero importers; the card uses `up_aoa_actions` instead. Its docstring is still the clearest statement of the contract ("These functions REPORT. They never cut a service, never disqualify a member and never file anything"), so keep it or delete it, but don't wire both in and let them drift.

### Owner Loans & Loanees (bye-law 3(1)(f))

**The society lends money to a member**, not the reverse. Account `1410 Loans to Owners` is a **Dr** asset under `1400 Loans & Advances Given`, mapped to statutory head `LOANS_GIVEN`; the opposite direction is the separate `2110 Loans & Advances Taken` / `LOANS_TAKEN`. There is no separate "loanees" table and no loanee id — **"loanees" is just the set of flats with an outstanding `owner_loans` balance**, i.e. the annexure bye-law 49 requires.

**How the money moves** — a direct balanced journal into `transactions`, *not* a receipt and *not* a `receivables` row, so it deliberately bypasses the five-path Pay Dues FIFO:

| Action | Function | Legs |
|---|---|---|
| Disburse | `fn_disburse_owner_loan(society_id, apartment_id, loan_date, principal, rate_pct, mode, purpose, resolution_ref, created_by)` → `{loan_id, msg}` | `Dr 1410 principal` / `Cr <primary bank> principal` |
| Repay | `fn_repay_owner_loan(loan_id, repay_date, principal, interest, mode, created_by)` → `{repayment_id, msg}` | `Dr <primary bank> (principal + interest)` / `Cr 1410 principal` / `Cr 4116 interest` |

Both post with `role='apartment'`, `status='paid'`, and a shared `journal_id` from `seq_transaction_number`. The **credit leg is omitted when `mode='cash'`** because `fn_resolve_bank_leg` returns NULL for `cash`/`journal` — cash-in-hand is derived from the cash book, never posted to directly. `fn_repay_owner_loan` takes a `FOR UPDATE` row lock on the loan and re-checks the outstanding balance.

**Validation is engine policy, not statute** (the SQL says so in a comment): a **resolution reference is mandatory** (`"Error: a Board / general-body resolution reference is required"`), `mode='journal'` is refused, and the cash-payment limit applies to cash disbursals. `fn_ensure_owner_loan_accounts(society_id)` idempotently creates 1410 and 4116 and maps 1410 → `LOANS_GIVEN`.

**Interest is simple interest on the outstanding principal, per annum, 365-day year, and it is an estimate — not an accrual:**

```
fn_owner_loan_interest_estimate(loan_id, asof) =
    ROUND( (principal − repaid_amount) × rate_pct / 100
           × GREATEST( asof − GREATEST(loan_date, MAX(repay_date)), 0 ) / 365.0, 2)
```

No journal is ever posted for accrued interest; income is booked **only** when cash actually arrives through `fn_repay_owner_loan` (which validates the principal against the outstanding balance but accepts any interest figure). The clock restarts on *any* repayment, including an interest-only one. Do not confuse the per-loan rate with `setup_wizard.MAX_INTEREST_RATE_PCT` — that is the late-payment cap on maintenance receivables.

**Lifecycle:** there is no status column. The only axis is the derived `owner_loans.ledger_posted BOOLEAN`. Rows inserted directly into the table (i.e. predating the ledger change) are **register-only**: shown in the table and in `fn_aoa_loanee_list`, tagged "register only", excluded from the repayment dropdown, and refused by `fn_repay_owner_loan` with *"this loan is a register-only entry (never posted to the ledger); repay it by editing the register"*. Fully-repaid loans simply fall out of the loanee list and the dropdown. There is **no** requested → approved → disbursed → repaid state machine and **no** two-stage pending/confirm flow as on the Fund Management card — an admin's click posts the full journal immediately.

**Where it lands in the reports:** 1410 is on the Balance Sheet under Assets (`statement_section='Assets'`, head `LOANS_GIVEN`, `has_bf = TRUE` so it carries forward); 4116 is Income in the I&E (`tab_name='Inc'`) and carries `mutuality_nature='mutual'`, so it flows into `fn_income_tax_summary_fy` as exempt income. Loan legs inherit `bank_reconciled = TRUE`, so they never appear as unmatched in bank reconciliation.

> **Owner loans are NOT receivables** — no `receivables` row is ever created — so `fn_apartment_outstanding` (which also drives the NOC check and the flat-deactivation guard) still reports **₹0 for a flat with an unpaid loan**. That function is deliberately unchanged. The loan is instead wired into the three compliance checks, each behind an **engine-policy switch** that master edits in **Master → AOA Rule Editor** (dated, audited; none is a statutory figure, so none needs the amendment confirmation):
>
> | Check | Switch (default) | Behaviour |
> |---|---|---|
> | No Dues (bye-law 39) | `owner_loan_blocks_nodues` (**1**) | `fn_nodues_issue_check` refuses to record the certificate as **issued** while any loan principal is outstanding on the flat — whether or not it has a repayment date. Recording a **refusal** is never blocked. The bye-law's 15-day deemed grant still runs by the calendar, so the Board must refuse inside the window; the Transfers table shows a red *Loan o/s* figure for exactly that |
> | Bye-law 7 | `owner_loan_counts_bye_law7` (**1**) | `fn_bye_law7_eligibility` adds the outstanding balance of a loan whose `due_date` is on or before *cut-off − arrears days* to `overdue_amount`, `oldest_due_date` and `days_overdue` (so a loanee can be ineligible; the amount is not split out) |
> | Section 22 | `owner_loan_counts_s22` (**0**) | Off by default: s.22 concerns unpaid charges, so an overdue loan does not by itself justify cutting a service. When on, an overdue loan counts toward the "dues remain" blocker in `fn_service_cutoff_check`. Whether it may is a legal question — get advice before enabling |
>
> **`owner_loans.due_date`** (nullable, `CHECK (due_date >= loan_date)`) is what makes a loan *overdue*. A loan with no repayment date can never be overdue, so it blocks No Dues but is invisible to bye-law 7 and s.22. Existing loans have none until someone sets it: the card has a *Repay by* field on the new-loan form and a *Set repayment date* control for existing loans (`fn_set_owner_loan_due_date`; blank clears it). `fn_apartment_dues_position(apartment_id, asof)` returns receivables, loan outstanding, loan overdue, an interest estimate and the total for one flat. Not changed: `fn_aoa_owner_list.outstanding_dues` still excludes loans (the Loanees sheet carries them); `start_cutoff` still records receivables only as `arrears_amount`.

Tables: `owner_loans` (`principal > 0`, `repaid_amount >= 0`, `ledger_posted`, `disbursal_mode`, `journal_id` — the trailing `register only` comment on its `CREATE TABLE` is now stale) and `owner_loan_repayments` (`CHECK (principal_amount + interest_amount > 0)`, immutable, no status column). Note `owner_loan_repayments.created_at` is always `NOW()` — a back-dated repayment still records a current creation timestamp; the value date is `repay_date`.

**The loanee annexure** — `fn_aoa_loanee_list(society_id)` returns `sr_no, flat_number, owner_name, loan_date, principal, interest_rate_pct, repaid_amount, outstanding, resolution_ref` for rows where `principal > repaid_amount`, and is written to the `Loanees` sheet of `UP_AOA_Annexures_Owners_and_Loanees.xlsx` (`annexure_workbook_bytes()`, alongside the `Owners` sheet from `fn_aoa_owner_list`). No totals row, no overdue flag, and it does **not** filter on `ledger_posted` — register-only loans appear in the statutory annexure.

**Tests** (both **live-Postgres**, skipped unless `PGHOST` is set; load `estatehub.sql`, run `seed.py`, then point `PGHOST`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` at it):

```bash
python -m pytest test/test_up_aoa_compliance_live.py -v -k "loan or loanee"
python -m pytest test/test_up_compliance_ui_live.py -v
```

### Capital Account vs Corpus Fund — Key Distinction under RWA Laws

| Aspect | **Capital Account (3100)** | **Corpus Fund (3230)** |
|---|---|---|
| **Legal Source** | UP Apartment Act 2010, Sec 14(5); Model Bye-Laws 2011, bye-laws 5 and 46 | RERA 2016, Sec 11(4)(g), 17; State Apartment Acts |
| **Origin** | Member contributions: share subscriptions, entrance fees, common profits (nucleus of reserve fund). UP transfer fees are not capital: bye-law 39 routes the ½% to the Major Repair Fund (3270) | **Builder handover** — one-time payment from developer at society formation (RERA mandatory) |
| **Nature** | Society's **owned equity** — grows/shrinks with member admissions/exits | **Capital reserve** — principal **inviolable** (cannot be spent) |
| **Usage (Principal)** | Capital expenditure, loan repayment, asset acquisition — **General Body approval** | **Never** — only **interest income** deployable |
| **Usage (Interest/Returns)** | Entire surplus available for society purposes | Only **interest earnings** usable (for maintenance/capex) |
| **Accounting** | Cr-normal equity account; balance = members' paid-up capital | Cr-normal reserve; balance = builder corpus + accrued interest (segregated) |
| **Governance** | General Body resolution | General Body (but stricter — RERA-mandated protection) |
| **Tax Treatment** | Not income; capital receipt | Principal = capital receipt (exempt); interest = taxable income |

**In short:** Capital Account = *Members' money* (society owns it, can deploy for capex with GB approval). Corpus Fund = *Builder's money* (society is trustee; principal locked forever, only interest usable).

---

### How Money Enters Each Fund (Current Implementation)

| Fund | Source | Automation | Key Code |
|------|--------|------------|----------|
| **Sinking Fund (3210)** | Monthly member contribution (per sq ft rate) | ✅ **Auto** — `sp_generate_monthly_bills()` creates receivable, `fn_post_receivable_accrual()` credits on payment | `estatehub.sql:2760-2853` |
| **Repair & Maintenance Fund (3220)** | Monthly member contribution (per sq ft rate) | ✅ **Auto** — same pipeline as Sinking Fund | `estatehub.sql:2760-2853` |
| **Reserve Fund (3220)** | 25% net surplus + entrance fees + common profits (UP transfer fee goes to Major Repair Fund 3270, not here) | ✅ **Auto** — `fn_fy_close_preview()` shows the proposed appropriation and every blocker before you commit; `fn_fy_close_reserve_appropriation()` posts it (Dr Income Expenditure A/c → Cr Reserve Fund) and records the closure on the FY Closing card | `estatehub.sql` — `fn_fy_close_preview`, `fn_fy_close_reserve_appropriation`, `fy_closures` |
| **Major Repair Fund (3270)** | ½% of the transfer value on every flat sale (UP Model Bye-Laws 2011, bye-law 39) | ✅ **Semi-auto** — `fn_record_apartment_transfer()` levies it as a receivable with its accrual leg; collect it like any other dues | `estatehub.sql` — `fn_record_apartment_transfer`, `apartment_transfers`; UI: Compliance card |
| **Capital Account (3100)** | Share subscriptions + entrance fees | ❌ **Manual** — onboarding/transfer events | Admin receipt / journal entry |
| **Corpus Fund (3230)** | Builder handover (RERA Sec 11(4)(g)) | ❌ **One-time** — at society formation | One-time setup |
| **Any fund — interest earned on it** | Bank / FD interest on the fund's own balance | ❌ **Manual** — credited to an **income** account, never back to the fund | **Appropriate Income → Fund** on the Fund Management card (`fn_appropriate_income_to_fund`) |

**Sinking & Repair Fund auto-billing details:** `sp_generate_monthly_bills()` calculates per-apartment amounts from `apt_charges_fines_basis.apt_sinking_fund_rate` / `apt_repair_fund_rate` (per sq ft/month), creates `receivables` rows with `acc_id` pointing to the fund accounts, and `fn_post_receivable_accrual()` credits the fund (Cr) when the member pays. Because the receivable row itself carries the fund's `acc_id`, the Fund Management routing below follows the same money automatically on every collection path.

**Statutory reserve appropriation (FY close):** closing a financial year from the FY Closing card automatically transfers the bye-laws' fixed share of that year's net surplus (25% under the UP AOA regime) into the Repair & Maintenance Fund Reserve. The transfer is one balanced two-leg journal, the receiving account is resolved through `account_statutory_mappings` for the society's own legal regime — preferring an unlocked fund over the law-protected Corpus Fund, which shares the same `RESERVE_FUND` statutory head — and the remaining surplus stays in the P&L and keeps reporting as Reserves & Surplus on the Balance Sheet. Closes are idempotent (`UNIQUE (society_id, financial_year)` plus a `unique_violation` guard), so a double click or two admins racing cannot appropriate the reserve twice; the second attempt reports `already_closed` having posted nothing. A deficit year is still closeable and records `no_surplus` with no journal, because a loss year carries forward *against* the reserve rather than being funded from it — blocking it would leave the year permanently open. The close refuses to run on books that do not balance.

**Interest appropriation (ad-hoc, any time):** the FY close above only handles the surplus reserve. A **locked** fund's own interest is a separate case: because its principal is inviolable, `fn_process_fund_utilization` refuses any draw against it, so that interest is credited to an **income** account (`4110 Interest Income`, and a locked Corpus Fund in particular earns it) and stays there. Moving it into a spendable fund is `fn_appropriate_income_to_fund` — a Dr income / Cr fund journal on the Fund Management card, `mode='journal'` because the rupees were already banked when the interest was credited. `fn_process_fund_utilization` cannot do this and must not be extended to: it requires a **Dr**-natured debit leg, and an income account is Cr, so it raises *"must be a Dr (expense/asset) account"* on exactly this case. Non-admin callers get a `pending` row that an admin action later confirms via `fn_confirm_fund_appropriation`.

> **Available balance is a subtree figure, never a single row.** The account an admin picks is usually a *rollup* — `4110 Interest Income` has no transactions of its own, its children `4111/4112/4113` carry the postings. Both `fn_appropriate_income_to_fund` and `loaders.get_income_accounts_for_appropriation` therefore sum the account **and every descendant**. An account-only sum reports ₹0 forever and makes the feature look broken on a society that has in fact earned interest.

### Fund Deposit Routing — `fund_bank_account_map`

Fund segregation is enforced at the ledger level (dedicated Cr-natured accounts, never commingled with operating income/expenditure) **and now also at the physical-bank-account level**.

| Layer | Mechanism |
|---|---|
| Which bank a fund's money lands in | `fund_bank_account_map (society_id, fund_acc_id) → bank_acc_id`, edited on the Fund Management card → `fn_set_fund_bank_mapping(society_id, fund_acc_id, bank_acc_id, user_id)`. `p_bank_acc_id = NULL` clears the mapping and reverts the fund to `societies.primary_bank_account_id`. |
| Who sets it | Admin only, **and scoped to their own society** — the function resolves the acting user inside `p_society_id`, so an admin of society A cannot re-route society B's funds. Master admins and unassigned seeded admins (NULL `society_id`) stay permitted. |
| Where it is enforced | `fn_resolve_bank_leg(society_id, mode, credit_acc_id)`. The 3rd argument is **optional and NULL by default**, so every call site that isn't about a fund is byte-for-byte unaffected. It returns NULL for `cash`/`journal` before the mapping is ever consulted. |
| Which call sites pass it | `fn_verify_receipt`, `fn_verify_receivable`, `fn_save_receipt` (one known credit account each), **and both "Pay Dues" engines** — see below. |
| Reconcile the right statement | `bank_statement_lines.bank_acc_id` + a Bank Account selector on the upload modal; candidates are restricted to rows whose money provably landed in that account. |

**The FIFO / selective "Pay Dues" split.** One dues payment routinely settles rows carrying *different* `acc_id`s — a Sinking Fund line (3210), a Repair Fund line (3220), a Maintenance line (4210). `fn_apply_apartment_dues_fifo_core` and `fn_apply_apartment_dues_selective_core` therefore resolve a bank account **per settled row**, accumulate a `{bank_acc_id: amount}` map, and emit **one Dr leg per distinct account** instead of one lump leg to the primary. The invariant is `Σ legs = Σ row takes + overpayment = p_amount`, identical to the single-leg version it replaces; any overpayment goes to the primary account (an advance is maintenance income, not a fund contribution). With no mapping configured the output is exactly the old single primary leg.

> **Both engines must stay in step.** They were originally left pointing at the primary account while the single-verify paths honoured the mapping, which made routing silently inconsistent: verifying dues one flat at a time banked into the mapped account, paying the same dues through FIFO did not. A society with a second account could reconcile an SBI statement against money that had gone to ICICI.

### Fund Management — Write Contract (Do Not Collapse These Two Phases)

Every write callback in `fund_management_callbacks.py` — **Utilize Fund**, **Appropriate Income → Fund**, **Confirm/Cancel** a pending appropriation, and **Save Routing** — is deliberately split into two phases:

| Phase | Scope | On failure |
|---|---|---|
| **1 — the write** | `fn_process_fund_utilization` / `fn_appropriate_income_to_fund` / `fn_confirm_fund_appropriation` / `fn_cancel_fund_appropriation` / `fn_set_fund_bank_mapping` only | Red toast reading **`Not saved: <reason>`**; every other output is `no_update` so the form keeps what was typed |
| **2 — the refresh** | reload loaders + rebuild the balances/log/mapping tables | **The committed outcome line is kept**, wrapped in a warning that reads *"The entry was saved, but this card could not refresh: … Do not submit again."* (`_committed_with_refresh_failure`). Card outputs stay `no_update`; the form is **still cleared**, because the journal exists |

> **This split is a correctness requirement, not cosmetics.** The two phases used to share one `try`, so any *rendering* bug in the card reported a *committed* journal as `Error: ...` — and an admin who reads that and clicks again posts the same appropriation twice. Nothing in the database can catch it: the income account simply had enough balance to cover both. If you add a write to this module, keep the SQL call alone in the first `try` and every loader/builder call in the second.

The same file also owns the shared card builders (`build_balances_table`, `build_fund_options`, `build_income_source_options`, `build_appropriation_log_table`, `build_fund_bank_mapping_rows`, `build_log_table`) — the card renderer imports these rather than hand-rolling a second copy (Rule 11 in [§18](#18-critical-dash-rules)).

> **Log tables format `created_at` through `_log_date()`, never `value[:10]`.** `fund_appropriations.created_at` and the utilization log's are `TIMESTAMP` columns, so psycopg2 hands back a `datetime.datetime`, which is not subscriptable. The renderer and the callbacks share one helper so the first render and the post-submit render cannot disagree about the format.

### Table Roles

| Table | Type | Who creates | Status flow | Posts to transactions |
|---|---|---|---|---|
| `receivables` | Auto-calculated credits | `fn_auto_generate_receivables` | pending → partial → paid | On admin verify |
| `receipts` | Manual credits | Admin / Security | pending → confirmed / cancelled | On create (admin) or verify (security) |
| `payables` | Auto-calculated debits | `fn_auto_generate_payables` | pending → verified / cancelled | On admin verify |
| `expenses` | Manual debits | Admin | confirmed immediately | On create |
| `transactions` | Immutable ledger | All of above | paid | Source of truth |
| `fund_appropriations` | Manual credits (income → fund) | `fn_appropriate_income_to_fund` | pending → confirmed / cancelled | On confirm (admin), never on insert |
| `owner_loans` | Manual credits (society lends to a flat) | `fn_disburse_owner_loan` | `ledger_posted` boolean; no status column | On create, single `Dr 1410` leg (+ bank leg unless cash) |
| `owner_loan_repayments` | Manual debits (loan collected) | `fn_repay_owner_loan` | immutable — no status | On create, `Dr` bank + `Cr 1410` / `Cr 4116` |
| `apartment_transfers` | Register + transfer-fee accrual | `fn_record_apartment_transfer` | `nodues_requested_on` / `_refused_on` / `_issued_on` | Only the ½% fee, as a `receivables` row on 3270 |
| `service_cutoff_proceedings` | Register of s.22 steps | Admin, via the UP AOA card | in_progress → cut_off / withdrawn / restored | **Never** — the card records dates only |
| `aoa_statutory_filings` | Bye-law 49 filing record | Admin, via the UP AOA card | upsert per `(society_id, fy_start_year)` | Never |
| `compliance_flags` | Rule-breach log | `fn_verify_expense`, `fn_disburse_owner_loan` | none — `UNIQUE (source_table, source_id, rule_code)` de-dupes | Never; the posting continues in `warn` mode |
| `regime_rule_parameters` | Statutory thresholds (data, not code) | `seed.py` / manual migration | effective-dated | Never |

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

> **Owner-loan interest is a different formula entirely** — simple interest on the outstanding principal over a **365-day** year, not this 30-day pro-rata, and it is only ever an *estimate*. See [Owner Loans & Loanees](#owner-loans--loanees-bye-law-31f). Do not reuse `fn_apply_receivable_interest`'s constants for it, or vice versa.
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
| `fn_resolve_bank_leg(society_id, mode, credit_acc_id DEFAULT NULL)` | Resolves the bank account for an incoming payment. 2-arg form → `societies.primary_bank_account_id` (all pre-existing call sites unchanged). 3-arg form → `fund_bank_account_map` first, so a fund's contributions reach the account the admin mapped it to. NULL for `cash`/`journal` |
| `fn_set_fund_bank_mapping(society_id, fund_acc_id, bank_acc_id, user_id)` | Admin-only, society-scoped upsert of `fund_bank_account_map`. `p_bank_acc_id = NULL` clears. Validates the fund is Cr-natured and the bank is Dr-natured |
| `fn_appropriate_income_to_fund(society_id, income_acc_id, fund_acc_id, particulars, amount, created_by, approval_ref, approval_date)` | Dr income / Cr fund book entry. The only route for moving a locked fund's earned interest into a spendable fund. Balance-checked over the income account's **whole subtree**; admin → `confirmed` + journal, non-admin → `pending` |
| `fn_confirm_fund_appropriation(appropriation_id, confirmed_by)` | Admin-only, society-scoped. Re-checks the accrued balance *and* both accounts' Dr/Cr nature, then posts the journal and flips `pending → confirmed`. Refuses to run twice |
| `fn_cancel_fund_appropriation(appropriation_id, cancelled_by)` | Withdraws a still-`pending` request. Only ever legal on `pending` — a posted journal can never be orphaned by a status flip |
| `fn_apply_apartment_dues_fifo_core` / `fn_apply_apartment_dues_selective_core` | The two "Pay Dues" engines. Both resolve a bank account **per settled row** and emit one Dr leg per distinct account, so a mixed Sinking+Repair+Maintenance payment reaches each fund's mapped account |
| `fn_funds_account_fy(society_id, fy)` | 5th Financial Statement — Funds Account schedule (Opening B/F, Additions, Deductions, Closing C/F) per statutory fund |

**UP AOA layer** (all seeded from `regime_rule_parameters`; see [§9](#up-aoa-regime-parameters--regime_rule_parameters))

| Function | Purpose |
|---|---|
| `fn_regime_param_num(society_id, key, on DEFAULT CURRENT_DATE)` / `fn_regime_param_text(...)` | Effective-dated statutory-threshold lookup for the society's `society_legal_regime`. NULL = rule not applicable, never a default |
| `fn_statutory_calendar(society_id, asof, years DEFAULT 3)` | Bye-law 49 filing calendar: 3 FYs × 3 steps (publish / copy to authority / owner summary) with `done · overdue · due_soon · upcoming` (`due_soon` = within 30 days) |
| `fn_aoa_owner_list(society_id)` | Annexure — one row per active flat with undivided-interest % and `outstanding_dues`. **Excludes owner loans** |
| `fn_aoa_loanee_list(society_id)` | Annexure — flats with `principal > repaid_amount`: principal, rate, repaid, outstanding, resolution ref. No status, no totals, and does not filter on `ledger_posted` |
| `fn_backfill_undivided_interest(society_id, overwrite DEFAULT FALSE)` | Fills NULL `apartments.undivided_interest_pct` from area share (6 dp), pushing the sub-0.001 residual onto the largest flat. The Declaration is authoritative — this is a convenience |
| `fn_undivided_interest_summary(society_id)` | `{apartments_total, apartments_missing, total_declared_pct, balanced}` (balanced = no NULL and \|total − 100\| ≤ 0.001) |
| `fn_undivided_interest_report(society_id)` | Per-flat drift from the area share: `missing · matches_area · differs_from_area` |
| `fn_undivided_interest_bill_preview(society_id, monthly_budget)` | Splits a budget by undivided-interest %; tested, not wired to a card |
| `fn_bye_law7_eligibility(society_id, election_date, basis DEFAULT NULL)` | Flats barred from voting/standing. **Zero rows when the rule is unset** — not "everyone is eligible". Uses the balance outstanding at call time |
| `fn_bye_law7_cutoff_date(society_id, election_date, basis DEFAULT NULL)` | FY basis → Apr 1 of the FY − 1 day; calendar basis → Jan 1 of the election year − 1 day |
| `fn_service_cutoff_check(proceeding_id, asof)` | s.22 preconditions: `can_cut_off`, `earliest_cutoff_date`, `blockers[]`. Reports only — it does not cut anything |
| `fn_nodues_certificate_status(transfer_id, asof)` | `not_found · issued · not_requested · refused · deemed_granted · pending`; `deemed_on = requested_on + 15` |
| `fn_petty_cash_check(society_id, asof)` | `{cash_in_hand, limit_amount, breach}` against the ₹20,000 ceiling |
| `fn_cash_limit_mode(society_id)` / `fn_check_cash_payment_limit(society_id, amount, mode)` | `warn`/`block` resolution; the check returns a message only for `mode='cash'` over threshold |
| `fn_record_apartment_transfer(society_id, apartment_id, transfer_date, transfer_value, transferor, transferee, created_by)` | Bye-law 39: ½% fee as a `receivables` row on 3270 + its accrual leg, plus the transfer register. **Does not change `apartments.owner_name`** |
| `fn_ensure_major_repair_fund(society_id)` | Idempotently creates 3270 and its `MAJOR_REPAIR_FUND` statutory mapping |
| `fn_ensure_owner_loan_accounts(society_id)` | Idempotently creates 1410 (Dr) / 4116 (Cr, `mutuality_nature='mutual'`) and maps 1410 → `LOANS_GIVEN`. Silently no-ops if parents 1400 / 4110 are missing |
| `fn_disburse_owner_loan(society_id, apartment_id, loan_date, principal, rate_pct, mode, purpose, resolution_ref, created_by)` | `Dr 1410 / Cr cash-or-bank`, `ledger_posted = TRUE`. Resolution reference mandatory (engine policy, not statute); refuses `mode='journal'`, negative principal/rate, an unknown or inactive flat, and over-limit cash when `cash_limit_mode='block'` |
| `fn_repay_owner_loan(loan_id, repay_date, principal, interest, mode, created_by)` | `Dr bank (principal + interest) / Cr 1410 / Cr 4116` under a `FOR UPDATE` row lock. Refuses over-repayment and register-only loans. **Interest is not validated against anything** — it posts straight to income |
| `fn_owner_loan_interest_estimate(loan_id, asof DEFAULT CURRENT_DATE)` | Scalar simple-interest estimate on the outstanding principal (365-day year). A Board aid, never an accrual |

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
│   │   ├── callbacks/                        ← 39 modules; see registration order below
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
│   │   │   ├── bulk_enroll_callbacks.py      ← Excel bulk upload for members/staff
│   │   │   ├── bank_reconcile_callbacks.py   ← Bank statement upload and reconciliation, per bank account (Bank Account selector on the upload modal; candidates filtered by where the money actually landed)
│   │   │   ├── assign_to_callbacks.py        ← Assign-To modal (concern → admin/vendor/security)
│   │   │   ├── concern_bid_callbacks.py      ← Vendor "Save Bid" on a concern
│   │   │   ├── invite_to_callbacks.py        ← Invite vendors to bid on a concern; security are placed straight at 'assigned' (they don't bid)
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
│   │   │   ├── financial_statements_callbacks.py ← 6 Statements card Print / PDF / Email (clientside)
│   │   │   ├── fund_management_callbacks.py  ← Fund Management: utilize, income→fund appropriation (+pending confirm/cancel), fund→bank deposit routing. Every write is split into a write phase and a refresh phase — see [§9 Fund Management — Write Contract](#fund-management--write-contract-do-not-collapse-these-two-phases). Also owns the shared card builders (`build_balances_table`, `build_fund_options`, `build_income_source_options`, `build_appropriation_log_table`, `build_fund_bank_mapping_rows`, `build_log_table`) |
│   │   │   ├── up_compliance_callbacks.py   ← UP AOA Compliance card: 11 write callbacks (filings, annexure export, undivided-interest fill/basis, transfers + No Dues, bye-law 7, s.22, owner loan + repayment). Each returns through `_run()` → (toast, re-rendered body); `_ctx()` gates on role + resolves the society from the session |
│   │   │   ├── debug_callbacks.py            ← KPI audit + SQL tester
│   │   │   ├── admin_callbacks.py            ← No-op registration slot (all callbacks pruned — see file docstring); kept so future admin-only callbacks have a documented slot
│   │   │   ├── security_callbacks.py         ← Gate-alert buttons (School Bus/Taxi escalate, visitor notify, walk-in, QR validate, attendance). Wired in as step 6b
│   │   │   └── print_letterhead.py           ← Shared letterhead helper (logo · login_background watermark · secretary sign · verification QR) used by receipt, NOC, event-ticket, and any future print/PDF/email flow; not a callbacks module, imported by the print callback modules
│   │   ├── drilldown/
│   │   │   ├── loaders.py                    ← All DB reads, verify_*, pay_dues_fifo. Fund Management: `get_fund_balances`, `get_expense_bank_accounts`, `get_fund_utilization_log`, `get_fund_bank_mappings`, `get_income_accounts_for_appropriation`, `get_fund_appropriation_log`
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
│   │       ├── setup_wizard.py               ← First-time society setup wizard (imports `statutory_rules.STEP_ROWS` for its Acts & Rules panel)
│   │       ├── up_compliance_card.py         ← UP AOA Compliance card renderer — 7 sections, all component ids prefixed `upc-`. `render_up_compliance_body()` returns sections only so a save can swap the body without losing the toast (it reads `card.children[2].children` positionally)
│   │       └── router.py                     ← Page routing definitions
│   ├── services/
│   │   ├── auth_service.py                   ← authenticate_user(), reset flow
│   │   ├── qr_service.py                     ← generate_static_qr_code(), validate_qr_code()
│   │   ├── statutory_rules.py                ← Acts & Rules summary rows for the Setup Wizard's right-hand panel, plus the Act/Rules/Bye-laws loader (`instruments_for_society()`) that reads `legal_instrument_catalog` (Master Portal → RWA Compliance (UP)) for the wizard's "UP AOA Compliance" step, falling back to `LEGAL_INSTRUMENTS_UP_AOA` in seed.py when that table isn't integrated yet. **Presentation strings only** — the enforced thresholds live in `regime_rule_parameters` (§9), not here
│   │   ├── up_aoa_actions.py                 ← The live UP AOA service: every handler returns `(ok, message)` and re-checks society ownership via `_owns()`; also `load_card_data()` (the single read path the renderer consumes) and `annexure_workbook_bytes()` (openpyxl, `Owners` + `Loanees` sheets)
│   │   └── up_aoa_compliance_service.py      ← ⚠️ Dead code — a read-only wrapper over nine SQL functions with zero importers; the card uses `up_aoa_actions`. Keep as the documented "these functions report only" contract, or delete it — don't wire both
│   └── assets/                               ← Static files + uploaded images
│
├── database/
│   ├── db_manager.py                         ← db._execute() → Aiven
│   ├── estatehub.sql                         ← Full schema + all fn_* functions (incl. the UP AOA compliance layer)
│   ├── migrate.py                            ← Schema initialization (delegates demo seeding to seed.py)
│   ├── seed.py                               ← Idempotent demo/seed data (society, users, accounts, events, concerns). Also assigns `society_legal_regime` for UP societies and the `UP_AOA_ACCOUNT_MAPPINGS` statutory heads
│   └── reset_database.py                     ← Destructive DB reset and schema reload utility
│
├── test/                                    ← pytest suite (no pytest.ini/pyproject — run from the repo root)
│   ├── conftest.py / fake_db.py              ← FakeDB singleton + per-test reset; backs the non-DB scenarios
│   ├── test_scenario_*.py                    ← Scenario A–K, T, GST — FakeDB, no Postgres needed
│   ├── test_up_aoa_compliance_live.py        ← UP AOA engine, 30 tests. **Live Postgres**, skipped unless PGHOST is set
│   └── test_up_compliance_ui_live.py         ← UP AOA renderer/callback/handler wiring, 9 tests. **Live Postgres**
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
(module names match the files in [§17](#17-codebase-map) above):

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
"up_compliance_callbacks"    # 13g. UP AOA Compliance card (admin only; registered as a standalone custom card)
"bulk_enroll_callbacks"      # 14. Excel bulk upload
"bank_reconcile_callbacks"   # 14a2. Bank statement reconciliation
"assign_to_callbacks"        # 14b. Concern assignment
"concern_bid_callbacks"      # 14c. Vendor bid on concern
"invite_to_callbacks"        # 14d. Invite vendors to bid; security are assigned directly (no bidding)
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

Rule 10: Any component id a callback names in Input/State/Output MUST be emitted by the
         renderer on every path that callback can fire from — including the error path.
         A card that returns early on `if error:` drops the whole body, and every id
         inside it; a callback still referencing those ids then fails at invocation.

Rule 11: One builder per surface, imported by both the renderer and the callback.
         Hand-rolling a "close enough" table or dropdown in renderers.py means the card's
         FIRST render and its post-submit/Reload render are two different components —
         and the two quietly drift. Render into a container div (id=...-table) whose
         children the callback then replaces, rather than putting the id on the built
         component itself.

Rule 12: dbc.Label/Button take ONE positional arg (children). dbc.Label("x", html.Small(...))
         raises at import/build time, not at render time — wrap multiple children in a list.
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
| `def buildLetterheadPdfDoc` in the shared JS helper | A Python keyword inside the `LETTERHEAD_JS` string literal is a hard JS **`SyntaxError`**. Because that helper is prepended into *every* Print/PDF clientside callback, Save-as-PDF was broken everywhere it was used — Agreement, NOC, Receipts, Event Tickets, Vendor Pass, Expense, 6 Statements. The `buildLetterheadPdfDoc({… password: …})` option it referenced (`pdf-lib`) does not exist — pdf-lib has no encryption API | Rewrote it as a real `function` that renders via `html2pdf.js` (already on the allow-listed cdnjs CDN), waits for images, wraps the body in `#pdf-root`, and drops the fictional password option |
| Agreement Email button silently failed/truncated | The button was a bare `mailto:` with the **entire** agreement text URL-encoded into the body — well past most mail clients' ~2 000-char limit, so the compose window came up empty or truncated | Short body plus a full-text copy to the clipboard whenever the encoded length would exceed the safe limit; recipient now prefilled from the society's `secretary_email` |
| "6 Statements" PDF asked for a password that was then thrown away | `fin-stmt-password` was collected and passed to the (broken) `buildLetterheadPdfDoc`, which ignored it. pdf-lib has no encryption API and the surrounding JS did not parse | Removed the field, the `State`, and the `password` argument rather than collect a secret the app cannot honour. Real encryption needs a server-side pikepdf/qpdf step on a streaming route — a browser-side html2pdf pipeline cannot provide it |
| `fn_appropriate_income_to_fund` always reported "Available: ₹0" | The balance check summed only the named account. The account an admin picks is the rollup `4110 Interest Income`, which has no transactions of its own — its children `4111/4112/4113` carry the postings — so the feature was dead on arrival for any society that had actually earned interest | Balance is now summed over the account's **whole subtree** via a recursive CTE, matching how the trial balance already rolls a parent up on top of its children. Same fix in `loaders.get_income_accounts_for_appropriation` so the dropdown shows the same figure the function enforces |
| `pending` appropriations were permanently inert | The non-admin branch inserted a `pending` row and told the user "submitted for approval", but **nothing could ever action it** — no confirm function existed, so no journal was ever posted and the row sat there forever | Added `fn_confirm_fund_appropriation` / `fn_cancel_fund_appropriation`, plus Confirm/Cancel buttons on the log table. Both re-check the accrued balance and both accounts' Dr/Cr nature at action time |
| Both new fund functions authorised on `users.id` alone | `SELECT (role='admin' OR is_master_admin) FROM users WHERE id = p_created_by` — the *accounts* were society-validated but the *permission* was not, so an admin of society A could re-route or appropriate society B's funds | Acting user is now resolved **inside** `p_society_id`; cross-society callers get the same refusal as a non-admin. Master admins and unassigned seeded admins (NULL `society_id`) stay permitted |
| `IF drcr_account != 'Cr'` let null-natured accounts through | `accounts.drcr_account` is **nullable** (the rollup "Balance Sheet Root" has no Dr/Cr nature), and `NULL != 'Cr'` evaluates to NULL, not TRUE — so `IF` treated it as false and the guard passed silently | `IS DISTINCT FROM 'Cr'` in every new guard |
| Fund→bank routing was inconsistent between collection paths | `fn_verify_receipt`/`fn_verify_receivable`/`fn_save_receipt` passed `p_credit_acc_id` to `fn_resolve_bank_leg`, but both FIFO and selective "Pay Dues" did not. Verifying dues one flat at a time banked into the mapped account; paying the same dues through the ordinary FIFO path did not | Both engines now resolve a bank account per settled row and emit one Dr leg per distinct account. Invariant `Σ legs = p_amount` verified across cash / mixed / overpayment / no-mapping branches; with no mapping the output is byte-identical to the old single leg |
| Bank reconciliation matched the wrong account's statement | `bank_statement_lines` had no bank-account column, so uploading a second account's statement auto-reconciled against the primary account's receipts of the same amount | Added `bank_statement_lines.bank_acc_id` (NULL = primary, so all existing history stays valid) + a Bank Account selector on the upload modal. Candidates are narrowed only when a row's landing account is **provably** different — unknown is never excluded, so a single-account society behaves exactly as before |
| Fund Management card showed two different tables | `renderers.py` hand-rolled its own balances table and utilization log alongside the ones in `fund_management_callbacks.py`. The card's *first* render showed a gross "Available Balance" with **no statutory-lock column**, and switched to the drawable/locked presentation on the first Reload click | Both tables and both `FUND_TYPE_PATTERNS` copies deleted; the card now imports the same builders the callbacks use, so first render and post-submit render cannot disagree |
| `psycopg2` "invalid dsn: extra key/value separator" | `db_manager._build_dsn` appended `&options=-c timezone=...` without percent-encoding the `=`, killing the connection pool — **only** for deployments using discrete `PGHOST`/`PGUSER`/`PGPASSWORD` env vars instead of a single `DATABASE_URL` | `quote("=", safe="")` (and `/` and `+`) applied to the option key and value. A no-op for the single-connection-string path |
| `MUTUALITY_NATURE_MAP` / `TDS_SECTION_MAP` side-dicts in `seed.py` | The values they carried were already inline columns on `accounts` (`mutuality_nature`, `tds_section`); the two dicts were a second, drifting copy of the same 12 + 6 facts | Deleted; `seed_accounts` reads the two inline fields directly from the `ACCOUNTS` tuple. All 83 rows verified to carry 10 fields with the same tags the dicts produced |
| Fund log tables crashed on `'datetime.datetime' object is not subscriptable` | `fund_appropriations.created_at` is a `TIMESTAMP`, so psycopg2 returns a `datetime`, but both log builders sliced it as a string (`value[:10]`). Clicking **Appropriate to Fund** raised it on every click once a log row existed | `_log_date()` formats by type (`strftime` for datetimes, slice for strings) and is shared by `build_log_table` and `build_appropriation_log_table`, so first render and post-submit render can't disagree |
| A committed fund journal reported itself as `Error: ...` | The write and the card rebuild shared one `try`, so a *render* bug surfaced as a *failed transaction*. The admin resubmits and the same appropriation posts twice — nothing in the DB can catch it, the income account simply had the balance | Every write callback split into a write phase (failure → `Not saved: …`, form preserved) and a refresh phase (failure → `_committed_with_refresh_failure`, which keeps the outcome line and warns "do not submit again"). Applied to utilize, appropriate, confirm/cancel and routing |
| `submit_appropriation` returned 10 values for 11 Outputs | The Particulars field is an Output but was never returned as `None`, so **every successful** appropriation would fail with "Incorrect number of output values" and leave the form filled — masked until the datetime crash above stopped firing first | Sixth `None` added; the form now clears completely. Note `render_up_compliance_body()` has the same class of coupling (positional `card.children[2].children`) |
| UP AOA had SQL but no UI | Neither `fn_appropriate_income_to_fund`-class function had a Python caller; the fund functions existed, the card did not | Fund Management card: 4 sections, 6 shared builders, and the reload path wired to all of them |
| `up_aoa_compliance_service.py` never imported | Added with the SQL engine, then superseded — the card calls `up_aoa_actions` directly, so the module has zero callers | Documented in [§17](#17-codebase-map) as dead code rather than left silently drifting |
| Security's "Resolved" button was gated on the wrong row | `renderers.py` and the handler both checked only whether *any* admin row on the concern was `accepted`, never security's own row. A guard who was never assigned — or who had already resolved — was offered the button and then got "No active (assigned) assignment found for you on this concern" | Both now require the caller's **own** `SEC` row at `assigned` *in addition to* the admin-accepted condition, via `loaders.get_concern_assignment_status()` |
| Security was inviteable but could never do anything with it | The Invite modal wrote `SEC` rows at `invited`, but `Bid` and `Decline` are vendor-only and there is no other path off `invited` except a direct Assign — so security sat stuck at a stage the UI offered no button for | Security are no longer invited. `loaders.invite_concern_assignee()` rejects `SEC` with a pointer to Assign; the Invite modal's `SEC` branch writes straight at `assigned` |
| Re-invite / re-assign silently demoted working rows | Both guards excluded only `resolved` / `closed`. Re-inviting reset an `assigned` (or `accepted`) row back to `invited` and wiped its `bid_amount`; re-assigning dropped an admin's `accepted` back to `assigned` | Stage-specific exclusion lists (`RE_INVITE_BLOCKED_STAGES`, `REASSIGN_BLOCKED_STAGES`) plus a `SELECT … FOR UPDATE` pre-check, so a refusal names the stage that blocked it. The Assign modal's uncheck handler now protects `accepted` rows too |
| `close_concern` had no precondition | It reported "Concern closed" and fired a close push on a concern with **zero** assignment rows — the UPDATE matched nothing, the trigger left `concerns.status` at `open`, and the success toast was a lie. It also stamped `invited` / `bid_submitted` / `declined` rows `closed` on an untouched concern. The Close button rendered at every stage, including `open` | Refuses when there are no assignment rows or anyone is still `assigned` / `accepted`; `concern_is_closable()` is the same predicate and gates the button |
| A vendor could not revise a bid, but a ₹0 bid was accepted | `Bid` was hidden the moment the row reached `bid_submitted`, and `submit_concern_bid` only matched `status='invited'`, so a vendor who fat-fingered their figure was stuck with it. The guard was `bid < 0` while the error read "must be positive", so a ₹0 bid went through | Bid is offered across the whole candidate window (`invited` **or** `bid_submitted`) and the write accepts both; guard corrected to `bid <= 0` |
| `preferred_time` defaulted to `"anytime"` on a `TIME` column | An untouched optional time input came back as `""`, and the save handler substituted the string `"anytime"`, which Postgres rejects — `invalid input syntax for type time` — so a new concern submitted without a preferred time failed to insert at all. On edit the same default applied, so *clearing* the field raised the same error instead of nulling it | `_concern_time_value()` normalises `""` / `None` / whitespace to `NULL` on both the insert and the update |
| `concern_type` had two different defaults | `field_config.py` declared `"general"`, the save handler wrote `"other"`. Not cosmetic: candidate queries match `v.service_type ILIKE concern_type`, so the default decided which vendors a blank concern could ever be assigned to — and `"other"` matched nothing | Single source of truth `field_config.DEFAULT_CONCERN_TYPE = "general"`, imported by the save handler and both modals |
| "Your involvement" never showed a bid amount, and had no `declined` state | The banner read `assign_bid_amount`, but `_assignments` comes from `fn_concern_assignments()`, which returns the column as `bid_amount` — so the key was always absent. `declined` was missing from `_CONCERN_STAGE_LABEL` entirely, so a caller who had declined fell through to a generic `.title()` pill with no actions explained | Reads `bid_amount`; `'declined'` added to the label map |
| The `open` banner was one fixed, wrong string | It always read "awaiting invitation/assignment" — including while three vendors had already bid, and after every candidate had declined (which puts the aggregate straight back to `open`, indistinguishable from a concern nobody has looked at). `resolved` said "pending close" to vendors and security, who have no Close button. The owner portal, which has no assignment row of its own, saw no assignee names and no bid count at all | `_concern_status_banner_text()` derives the wording from the actual rows; `resolved` is role-aware; `_concern_team_banner_text()` gives every portal the assignee list and bid count |
| The new-concern form promised a bidding round that hadn't started | "please wait for bids from vendors/security" — but nobody has been invited yet, and security never bid. The actual next step is inviting | Reworded to point at Invite → Assign, and to say explicitly that security are assigned directly and don't bid |
| A concern's content was editable at any stage | An owner could rewrite the description, type or preferred time after bids, after assignment, or after closure — invalidating the `service_type` match that decides who gets invited. The save path also had no `created_by` check (the 6b row-ownership block only covers apartment / vendor / security *profiles*), and since `apartment_id` is force-stamped to the caller's own flat, a forged `id` could re-point someone else's concern onto their own flat | Edit refused once any row reaches `bid_submitted` or beyond, and non-admin callers must own the concern (`created_by = caller`) |
| Vendor portal could raise concerns it had no flat for | `("vendor", "concerns")` carried `"new"`, which renders a `New` button on the concerns list routing to `form_concern_new` — where `apartment_id` is `ADMIN_ONLY`-editable, so it renders read-only and **empty** for a vendor. The result was a concern with `apartment_id = NULL`: no owner could ever see, invite for, or close it, yet `notify_concern_created` still fired at the missing flat. `field_config`'s `"required"` rule did not help — `get_validation()` has no callers | Perm is now **view-only** for vendor and security. `_save_concern` additionally refuses any non-admin write with no `apartment_id`, covering a directly posted callback. Admin stays exempt so a society-level concern with no flat remains legal (the column is nullable by design) |
| `ca.pem`, `service.cert`, `service.key`, `setup_aiven_db.sh` were committed | `.gitignore` covered `.env` and `*.json` but nothing matched `*.pem` / `*.crt` / `*.key`, so a fresh clone handed everyone Aiven's CA cert **and the server's own private key** (which is what Postgres uses to authenticate the app). `.gitignore` listing them had no effect — the files were tracked | Removed from the index (files left on disk so the local connection and `setup_aiven_db.sh` keep working) and ignore rules added. **The credentials themselves must be rotated on the Aiven project — that is an ops action, not a repo change, and is still outstanding** |

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

### UP AOA Layer — Invariants Not to Break

- **The rules are data.** Every threshold is a `regime_rule_parameters` row
  resolved through `fn_regime_param_*`, which honours `effective_from` /
  `effective_to`. Hardcoding a percentage or a day count in either SQL or the
  card puts it out of reach of the override tiers, and the card's own prose
  already drifts from the data (see below).
- **"Rule not applicable" must never render as "compliant."** An unset
  parameter returns `NULL`/zero rows, and callers must say so. That is why
  `fn_bye_law7_eligibility` returns **zero rows** rather than everyone, and why
  the whole card hides itself when `transfer_fee_pct` is absent.
- **The card records, it does not act.** It never files with an authority,
  never disqualifies a member and never cuts a service. `fn_service_cutoff_check`
  only *reports* blockers, and the card refuses to write a `cut_off_on` the
  check does not allow. Keep it that way — the Board and the competent
  authority act, and anything this card decides by itself is a legal opinion
  the software has no business making.
- **Society ownership is re-derived, never accepted from the browser.**
  `up_aoa_actions._owns()` re-checks every id against the session's society
  before touching it. A new handler that skips this is a cross-tenant write.
- **The card's threshold prose is hard-coded and will drift.** It says
  "31 July", "15 August", "₹20,000", "₹2,500" as literal strings while the
  tables read from `regime_rule_parameters`. Change a parameter in SQL and the
  numbers in the tables move but the sentences do not.
- **`societies.cash_limit_mode` has no UI.** `warn` vs `block` is DB-only;
  the card shows the current value in parentheses. Don't assume the card can
  set it.
- **Regime assignment is seed-time only.** `society_legal_regime` is written
  by `seed_society_legal_regime()` (and only for `state = 'Uttar Pradesh'`),
  and that function returns early if a row already exists. The card's advice
  to "set the State in Society Details" does **not** switch the rules on by
  itself — an existing society needs the seed or a manual insert.
- **`cash_limit_default_mode` is engine policy, not statute.** It is seeded
  with `source_reference` saying so. Don't cite it in a filing.
- **Only `mode='cash'` counts as a cash-limit breach** (the ₹2,500 threshold
  pre-dates UPI/NEFT, per its own source note). A ₹50,000 cheque is never
  flagged, by design.
- **Undivided-interest backfill is a convenience, not a legal computation.**
  The SQL says "*The Declaration is authoritative*". `fn_undivided_interest_report`
  deliberately reports `differs_from_area` as a drift, and the card renders it
  in the same amber as a due-soon date rather than "fixing" it.
- **s.22 blockers include live dues, not just elapsed time.** A proceeding
  also raises `'no outstanding dues remain for this apartment'`, so a cut-off
  is unreachable while the flat is actually paid up. That reads like a bug and
  is not.
- **Once `appeal_filed_on` is recorded, the cut-off is unreachable from the
  UI** — the card can set `appeal_outcome='pending'` but nothing sets
  `dismissed`, and `withdrawn`/`restored` are equally unreachable. These need
  a direct SQL update today; add UI before relying on that path.

### Owner Loans — Invariants & Sharp Edges

- **Owner loans are deliberately not receivables.** No `receivables` row is
  created, so `fn_apartment_outstanding` (NOC, deactivation guard) still reports
  ₹0 for a flat with an unpaid loan. The loan reaches the compliance checks
  separately: it blocks *issuing* a No Dues Certificate, counts toward bye-law 7
  once past its `due_date` (null = never overdue), and counts toward s.22 only if
  master switches `owner_loan_counts_s22` on (default off). See the policy table
  under Owner Loans & Loanees.
- **Known, not fixed:** `fn_bye_law7_eligibility` and `fn_service_cutoff_check`
  read receivables with `status = 'pending'` only, so a *partly paid* receivable
  (`status = 'partial'`, which `fn_apartment_outstanding` does include) is
  invisible to both.
- **The resolution reference is mandatory by engine policy, not statute.**
  The SQL comment says so explicitly. It is nonetheless the right rule —
  a loan without a GB/MC resolution has no authority behind it.
- **`ledger_posted` is the whole lifecycle.** There is no status column and
  no pending/confirm stage. Register-only rows (`ledger_posted = FALSE`, i.e.
  inserted before the ledger change) are refused by `fn_repay_owner_loan` and
  must be corrected by editing the register — and they still appear in the
  statutory loanee annexure, which does not filter on the flag.
- **Interest is an estimate, never an accrual.** `fn_owner_loan_interest_estimate`
  is a Board aid. `fn_repay_owner_loan` validates the **principal** against
  the outstanding balance but accepts **any** interest figure, which posts
  straight to income 4116. Nothing cross-checks the two.
- **Any repayment resets the interest clock.** The estimate keys off
  `MAX(repay_date)`, so an interest-only repayment (`principal = 0`) silently
  discards accrued-but-unbooked interest for the elapsed period.
- **Cash disbursals and cash repayments post a single leg.** `fn_resolve_bank_leg`
  returns NULL for `cash`, so only the `Dr 1410` / `Cr 1410`+`Cr 4116` side is
  written and the cash side is left to the cash book. A cash loan therefore
  does **not** balance on its own in `transactions` — that is intended, and a
  test asserts it exactly.
- **There is no correction path.** No edit, no delete, no reversal for either
  table, and no compensating-entry UI. A wrong disbursal or repayment can
  only be fixed by direct SQL.
- **`PAY_MODES` includes `'transfer'`, which is not a legal `transactions.mode`.**
  The CHECK allows `cash · cheque · upi · card · bank · crypto · journal ·
  neft · rtgs · imp`. Picking **Transfer** passes both the Python and the SQL
  guard and then dies on the INSERT with a raw constraint violation instead
  of a clean message. Conversely `card`/`neft`/`rtgs`/`crypto` are legal in
  the DB and unreachable from the UI. Fix the tuple, not the guard.
- **The card's loan table is `LIMIT 20`**, and the repayment dropdown is built
  from it — a society with more than 20 loans **cannot repay an older one
  through the UI at all**.
- **`4116` has no `account_statutory_mappings` row** (only 1410 does), so it
  reports a NULL statutory head in the I&E. And `fn_ensure_owner_loan_accounts`
  silently no-ops when parents 1400 / 4110 are missing — the caller only
  errors for the 1410 case.
- **`owner_loan_repayments.created_at` is always `NOW()`**, so a back-dated
  repayment carries a current creation timestamp. `repay_date` is the value
  date that reaches `transactions.trx_date`.

### Deferred / Not-Yet-Built

- **Cashbook `Cr LF` / `Dr LF` (ledger folio) columns are deliberately
  omitted** from `_CASHBOOK_LIST_COLUMNS` in `schema_introspect.py` —
  waiting on the Ledger Index/pagination feature that would actually
  assign folio numbers.
- **`MST` (master admin) has no QR entry at all, by design** — a
  platform-level onboarding role with no `society_id` or gate/entity
  identity to represent (`qr_service.py`). Don't add one without first
  deciding what a master-level QR would even mean.
- **PDF password protection is not built.** `buildLetterheadPdfDoc` offers
  no `password` option and the UI no longer asks for one. html2pdf.js
  cannot encrypt, and pdf-lib has no encryption API, so this needs a
  server-side pikepdf/qpdf pass over a route that streams the PDF — a
  separate piece of work, not a one-line change to the existing helper.
- **The UP AOA card records dates, it does not handle documents.** Bye-law 49
  and s.22 notices, GB minutes and auditor certificates are typed in as dates
  and free text; there is no notice generation, no minutes upload and no
  attachment storage anywhere in this feature. A loan's `resolution_ref` is a
  string, not a linked resolution.
- **The UP AOA tables have no migration file.** `regime_rule_parameters`,
  `apartment_transfers`, `service_cutoff_proceedings`, `compliance_flags`,
  `aoa_statutory_filings`, `owner_loans` and `owner_loan_repayments` exist
  only as `CREATE TABLE IF NOT EXISTS` / guarded `ALTER` blocks in
  `estatehub.sql`. An already-provisioned database gets them only by
  re-running the DDL (see the change-kind table in §22).

### Fund Money — Invariants Not to Break

- **Never merge a write and its card refresh into one `try`.** The
  two-phase contract in [Fund Management — Write Contract](#fund-management--write-contract-do-not-collapse-these-two-phases)
  exists because a committed transaction reported as `Error: ...` invites a
  duplicate posting that the database cannot detect. `save_fund_bank_mappings`
  was the last holdout; it now follows the same shape.
- **`fn_resolve_bank_leg` must keep its 3rd argument optional.** It was added
  as `p_credit_acc_id INT DEFAULT NULL` specifically so that every pre-existing
  2-argument call site (`fn_verify_expense`, `fn_verify_payment`,
  `fn_save_expense`, pass sales, asset buy/dispose, `fn_pay_rcm_liability`)
  keeps resolving to `primary_bank_account_id` untouched. Dropping the default,
  or reordering the parameters, silently re-routes every one of them.
- **The two "Pay Dues" cores must be changed together.** Routing lives in
  both `fn_apply_apartment_dues_fifo_core` and
  `fn_apply_apartment_dues_selective_core`. They were briefly out of step —
  one honoured the mapping, the other didn't — and the symptom was a society
  whose bank balances disagreed with its statements depending on which screen
  the payment was entered from. If you touch one, check the other.
- **The bank leg is emitted from an accumulator, not from `p_amount`.** In both
  cores the Dr legs are built from a `jsonb` map of `{bank_acc_id: amount}`
  accumulated per settled row, and their sum is
  `Σ row takes + overpayment = p_amount`. Adding a term to one side without the
  other unbalances the journal. Overpayment deliberately goes to the *primary*
  account: an advance is maintenance income, not a fund contribution.
- **`fn_appropriate_income_to_fund` checks the income account's SUBTREE, and
  the confirm function must too.** An account-only `SUM` is always ₹0 for a
  rollup like `4110 Interest Income` and makes the whole feature look dead.
  The check is repeated at confirm time because two pending requests can race
  for the same interest — the pending row reserves nothing.
- **Corpus Fund's interest lands on an income account, not back on Corpus.**
  That is the intended design (the principal is 100% statutory-locked, so only
  its *interest* is deployable), not an oversight. Moving it into a spendable
  fund is the explicit `Appropriate Income → Fund` action, which wants a
  General Body / Managing Committee approval reference recorded against it.
  `fn_process_fund_utilization` must keep refusing it: that function requires a
  Dr-natured debit leg, and an income account is Cr. Extending it to "allow"
  the case would be a regression, not a feature.
- **The statutory lock constrains outflow only, never inflow.** That is why
  the appropriation destination dropdown uses `build_appropriation_fund_options`
  (all funds, none disabled) and not `build_fund_options` (which disables funds
  with no drawable headroom). Topping up a 100%-locked fund is precisely the
  operation the feature exists for.

### Data-Scoping Invariants Added Alongside

- **"Unknown" is never treated as "the primary account".** Two places resolve
  a payment's landing bank account: the reconciliation candidate filter and the
  per-row Reconcile picker. Both resolve it from the posted bank leg
  (`source_table`/`source_id` + the opposite `entry_side` — `Dr` for receipts,
  `Cr` for expenses) and both treat an unresolvable row as *matching anything*,
  never as belonging to the primary. Narrowing on a guess would drop matches
  that were previously found; a society that never configures a second account
  must see no behavioural change at all.

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
| Concerns | 11 | Mixed types/statuses (`open`, `assigned`, `resolved`, `closed`); several pre-assigned to a vendor or security guard via `concerns_assigns` |
| Chart-of-accounts | 83 | Full tree across Assets / Liabilities / Equity & Reserves & Funds / Income / Expenses, incl. the statutory funds (Sinking 3210, Repair 3220, Corpus 3230). `mutuality_nature` and `tds_section` are **inline fields on the `ACCOUNTS` tuple** (not side-dicts) and are written straight into the `accounts` columns of the same name |

> **The chart of accounts is jurisdiction-agnostic by lookup, not by id.** No
> function hardcodes `3210`/`3220`/`3230`. Funds are resolved by walking the
> subtree of whichever account is named `ILIKE '%Equity%'`, income accounts by
> `ILIKE '%Income%'`, bank accounts by their parent's name — the same approach
> in SQL (`fn_funds_account_fy`) and in Python
> (`loaders.get_fund_balances`, `get_fund_bank_mappings`,
> `get_income_accounts_for_appropriation`,
> `get_expense_bank_accounts`), so a society on a different chart of accounts
> numbering still works. See [§20](#20--open-design-subtleties--flagged-caveats)
> for why a hardcoded id list broke the fund dropdowns before.

Re-running the seed is safe — every insert is guarded by an existence check
(`ON CONFLICT` or a `SELECT ... WHERE NOT EXISTS`-style guard), so it will
only fill in missing rows rather than duplicate demo data. Note that the
guard is existence-based, not update-based: a row that already exists is
**left untouched**, so re-seeding will not retroactively apply a changed
`mutuality_nature`/`tds_section` to an existing account.

```bash
python3 database/seed.py                 # standalone
python3 database/migrate.py --seed       # schema init + seed in one step
```

Two seed functions are specifically about the **UP AOA layer**, and they only run from `run_seed` — not from a bare account insert:

- `seed_society_legal_regime()` writes `society_legal_regime = ('UP_AOA_2010', effective_from 2011-11-16)` **only** where `societies.state = 'Uttar Pradesh'`, and returns early if a row already exists. This is the gate that makes every rule in `regime_rule_parameters` reachable — without it the UP AOA card renders its "rules are not active" alert even though every threshold row exists. There is no UI that assigns a regime.
- `seed_account_statutory_mappings()` applies `UP_AOA_ACCOUNT_MAPPINGS` — every account→statutory-head binding for the regime, with `regime_code` and `effective_from` hard-coded (`1400`/`1410` → `LOANS_GIVEN`, `2110` → `LOANS_TAKEN`, `3270` → `MAJOR_REPAIR_FUND`, `3230` → `IFMS_CORPUS`, and the whole tax/GST/CASH_BANK set). Note `4116 Interest on Owner Loans` is deliberately **not** in that mapping, so it reports a NULL statutory head in the I&E.

The rule-parameter rows themselves live in `estatehub.sql`, not `seed.py`.

### Database Migrations

> **`database/estatehub.sql` is the single source of truth for the schema.** Every table, view, and `fn_*` stored function is defined there — it is what `database/reset_database.py` loads to rebuild the database from scratch, and it is the file to consult (or diff) before trusting any other description of the schema, including the summaries elsewhere in this README.

All database stored procedures and queries are prefixed with `fn_` and use `%s` positional parameter placeholders (psycopg2 style). Schema changes require updating:
1. The corresponding SQL function definitions in `database/estatehub.sql`.
2. The corresponding database query inside `app/dash_apps/drilldown/loaders.py`.
3. The parameter list in `_save_*` inside `app/dash_apps/callbacks/drilldown_callbacks.py` (for database writes).

Use `database/migrate.py` to auto-initialize the schema and seed mock accounts from `database/EstateAcc.xlsx`:
```bash
python3 database/migrate.py --seed
```

**`migrate.py` re-runs the full DDL on every invocation** (the
`--fresh`/`--force` flag only governs whether demo data is re-seeded). Schema
changes therefore only ever need to land in `database/estatehub.sql` — no
numbered migration file is required. Additive changes to *existing* tables
must still be written idempotently, because `CREATE TABLE IF NOT EXISTS` is a
no-op against an already-provisioned database:

| Change kind | Required pattern |
|---|---|
| New table | `CREATE TABLE IF NOT EXISTS` + a `COMMENT ON` + `CREATE INDEX IF NOT EXISTS` |
| New column on an existing table | Add the column to the `CREATE TABLE` (fresh installs) **and** a guarded `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint ...) $$` block for provisioned databases |
| New index / constraint | `CREATE INDEX IF NOT EXISTS`, or a `DO $$ ... pg_constraint ... $$` guard for named constraints (a plain `ADD CONSTRAINT` re-run raises "already exists") |
| New / changed function | `CREATE OR REPLACE` **plus** `DROP FUNCTION IF EXISTS <name>(<exact old signature>) CASCADE` when the parameter list changed — `CREATE OR REPLACE` only replaces a signature that matches exactly, so an un-dropped old overload lingers as an orphan and calls become ambiguous |

> `bank_statement_lines.bank_acc_id` is the reference example: column in
> `CREATE TABLE`, then a `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint
> WHERE conname = 'fk_bank_lines_account') $$` block for the composite
> `(society_id, bank_acc_id) → accounts (society_id, id)` FK. That composite
> target is valid because `accounts`' primary key **is** `(society_id, id)` —
> the same pattern `fund_bank_account_map` and `fund_appropriations` use.

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
| **Admin → Fund Management** | Sidebar: Financials → `kpi_fund_management` nav tile → `form_fund_management` card: Fund Balances (gross / statutory lock / drawable) → **Utilize Fund** (honours `statutory_lock_pct`) → **Appropriate Income → Fund** (Dr income / Cr fund; non-admins get a `pending` row) → **Fund Deposit Routing** (per-fund destination bank account) → Recent Utilizations + Recent Appropriations logs with Confirm/Cancel on pending rows; **Reload Data** refreshes all four surfaces | Admin-only. See [§9 Financial Module](#9-financial-module) for the accounting and segregation rules |
| **Admin → Bank Reconcile** | Receipts / Expenses list → **Bulk Reconcile** (or per-row **Reconcile**) → pick the **Bank Account** the statement is from → download template → upload Excel → auto-matched / needs-review / unmatched summary; **Post Unmatched** / **Delete Unreconciled** | Reconcile an uploaded statement against receipts/expenses, restricted to rows whose money actually landed in the chosen account |
| **Admin → UP AOA Compliance** | Sidebar: Financials → `kpi_up_compliance` nav tile → `form_up_compliance` card, 7 sections: ① **Bye-law 49 filings** — record the 3 filing dates + auditor, tick the owner/loanee annexures, **download the Owners + Loanees XLSX** ② **Undivided interest & billing basis** — backfill missing % from area, switch society-wide maintenance to per-% billing with a monthly budget ③ **Transfers & No Dues** — record a flat transfer (auto-levies the ½% Major Repair Fund fee), set No Dues requested/refused/issued ④ **Bye-law 7** — election date + year basis → the list of flats barred from voting/standing ⑤ **s.22 service cut-off** — open a proceeding, record each of the 7 steps, see the blocker list and earliest lawful date ⑥ **Loans to owners** — record a disbursement (resolution ref mandatory) and repayments ⑦ **Cash & cheque limits** — read-only petty-cash badge + compliance flags. **Reload Data** refreshes the whole card | Admin-only, and only for societies whose `society_legal_regime` is `UP_AOA_2010` — otherwise the card says so and hides. The card records and checks; it never files, disqualifies or cuts. See [§9](#up-aoa-compliance-card-admin--financials) |
| **Admin → Channels** | Sidebar: Channels → 3 KPI cards (`kpi_channels_total`, `kpi_channels_active`, `kpi_channels_pending`) → `list_channels` → `profile_channel` → Create / Subscribe / Trigger Alert / View Subscribers | Manage school bus, taxi, visitor alert channels and subscriptions |
| **Admin → Assets** | Sidebar: Assets → 2 KPI cards (`kpi_assets_count`, `kpi_assets_value`) → `list_assets` → `profile_asset` → Edit / Dispose | Buy, manage, depreciate, and dispose of society assets |
| **Admin → Events** | Sidebar: Events → 2 KPI cards (`kpi_events_total`, `kpi_events_tickets`) → `list_events` / `list_event_ticket_items` → profile → Edit / Sell Tickets | Create/edit events, sell/manage event tickets |
| **Admin → Concerns** | Sidebar: Concerns → 2 KPI cards (`kpi_concerns_not_closed`, `kpi_concerns_total`) → `list_concerns` → `profile_concern` → Invite / Assign / Accept / Decline / Resolved / Close (Close appears only once every assignee has resolved) | Full concern lifecycle management |
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
| **Owner → Concerns** | Sidebar: Concerns → 2 KPIs (`kpi_concerns_not_closed`, `kpi_concerns_total`) → `list_concerns` → `profile_concern` → Raise New / Invite / Assign / Close (Invite, Assign and Close restricted to concerns the owner raised; Close only once every assignee has resolved) | Raise, track, and close own concerns |
| **Owner → Polls** | Sidebar: Polls → 2 KPIs (`kpi_polls_total`, `kpi_polls_active`) → `list_polls` → `profile_poll` (vote) | View and vote in community polls |
| **Owner → Settings** | Sidebar: Settings → 1 KPI (`kpi_owner_member_since`) → `list_apartments` (self-scoped) → `profile_apartment` → Edit | View/edit own apartment profile |

#### 🟡 VENDOR Portal (role: `vendor`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Vendor → My Dashboard** | Sidebar: Dashboard → 5 KPIs (`kpi_my_pass_expiry`, `kpi_gate_logs`, `kpi_concerns_invited`, `kpi_concerns_assigned`, `kpi_events_total`) → drill panel | Gate pass status, assigned concerns, events overview |
| **Vendor → Financials** | Sidebar: Financials → 2 KPIs (`kpi_receipts_total`, `kpi_ven_charges_count`) → `list_receipts` / `list_ven_charges` | View own receipts and charge rules |
| **Vendor → Passes** | Sidebar: Passes → 2 KPIs (`kpi_my_pass_expiry`, `kpi_vendors_passes`) → `list_vendors` (self-scoped) → `profile_vendor` → Buy Pass / Gate Pass | View/buy own gate passes |
| **Vendor → Events** | Sidebar: Events → 1 KPI (`kpi_events_total`) → `list_events` → `profile_event` → Buy Tickets | View events and buy tickets |
| **Vendor → Concerns** | Sidebar: Concerns → 3 KPIs (`kpi_concerns_invited`, `kpi_concerns_assigned`, `kpi_concerns_resolved`) → `list_concerns` (read-only — no New button) → `profile_concern` → Bid (submit **and revise** until assigned) / Decline (only while unbid) / Resolved (only once assigned); Manual QR concern lookup | Vendor concern workflow: receive invites, bid, get assigned, resolve |
| **Vendor → Settings** | Sidebar: Settings → 1 KPI (`kpi_vendors_date`) → `list_vendors` (self-scoped) → `profile_vendor` → Edit | View/edit own vendor profile |

#### 🔴 SECURITY Portal (role: `security`)

| Name of Workflow | Sequence of Interaction on UI/UX | Goal of Workflow |
|---|---|---|
| **Security → Pass Evaluation** | Sidebar: Pass Eval → QR Scanner → Entry IN / Exit OUT / NFC Patrol; KPIs (`kpi_events_total`, `kpi_concerns_assigned`); Manual QR entry; Recent Scans; Emergency button | Primary gate duty: scan QR passes for entry/exit, NFC patrol check-ins |
| **Security → Channels** | Sidebar: Channels → 5 KPIs (`kpi_channels_total`, `kpi_channels_pending`, `kpi_channels_pending_bus`, `kpi_channels_pending_taxi`, `kpi_presumed_visitor`) → lists | Monitor and act on pending gate alerts (bus/taxi/visitor) |
| **Security → Attendance** | Sidebar: Attendance → Clock In / Clock Out buttons | Clock in/out for shift duty |
| **Security → Receipts** | Sidebar: Receipts → 1 KPI (`kpi_security_receipts`) → `list_receipts` (self-scoped) | View own collected receipts |
| **Security → Events** | Sidebar: Events → 1 KPI (`kpi_events_total`) → `list_events` | View upcoming events |
| **Security → Concerns** | Sidebar: Concerns → 2 KPIs (`kpi_concerns_assigned`, `kpi_concerns_resolved`) → `list_concerns` → `profile_concern` → Resolved (read-only until assigned by an admin, and until an admin has **accepted** the concern; security are never invited and never bid) | View and resolve assigned concerns |
| **Security → Users** | Sidebar: Users → 3 KPIs (`kpi_security_total`, `kpi_security_on_duty`, `kpi_security_off_duty`) → `list_security` → `profile_security` | View fellow security staff duty roster |
| **Security → Settings** | Sidebar: Settings → 1 KPI (`kpi_time_qr`) → Attendance QR | View/manage own profile, attendance QR |

---

*EstateHub — Built for societies that mean business.*
