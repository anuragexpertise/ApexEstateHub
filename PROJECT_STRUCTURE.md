# SocietyOS — ApexEstateHub
## Complete Project Structure & Integration Guide
> Stack: Flask + Plotly Dash · NeonDB (PostgreSQL) · JWT + Push · ApexWeave

---

## Directory Tree

```
societyos/
│
├── wsgi.py                          # Gunicorn entry-point → Flask + Dash
├── Procfile                         # web: gunicorn wsgi:server ...
├── requirements.txt
├── .env                             # secrets (gitignored)
├── .gitignore
├── dashestatehub.sql               # Full DB schema (run once on NeonDB)
├── PROJECT_STRUCTURE.md            # ← this file
│
├── database/
│   └── db_manager.py               # Singleton psycopg2 pool, execute_query()
│
├── app/
│   ├── __init__.py                 # create_app() + create_dash_app()
│   ├── config.py                   # Dev / Prod / Test configs + get_database_url()
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   └── jwt_handler.py          # generate_tokens, verify_token, decorators
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                 # User (UserMixin), @login_manager.user_loader
│   │   ├── society.py              # Society
│   │   ├── apartment.py            # Apartment
│   │   ├── payment.py              # Payment → .verify() creates Transaction
│   │   ├── transaction.py          # Transaction + Account
│   │   └── gate_access.py          # GateAccess
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py                 # /auth/login, /auth/logout, /auth/check-auth
│   │   ├── api.py                  # JWT-protected REST endpoints
│   │   └── web.py                  # / → /dashboard redirect
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py         # authenticate_user/pin/pattern (raw psycopg2)
│   │   ├── society_service.py      # get_societies, create_society, etc.
│   │   ├── payment_service.py      # calculate_dues, process_payment
│   │   ├── maintenance_service.py  # rates, late fees, monthly generation
│   │   ├── qr_service.py           # generate_qr_code, validate_qr_code
│   │   └── push_service.py         # send_push_notification (pywebpush)
│   │
│   ├── dash_apps/
│   │   ├── __init__.py
│   │   │
│   │   ├── layout.py               # serve_layout() → shell_layout() entry
│   │   │
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── header.py           # create_header(society, role, email)
│   │   │   ├── sidebar.py          # create_sidebar(role, society_id)
│   │   │   ├── breadcrumb.py       # create_breadcrumb(pathname)
│   │   │   ├── footer.py           # create_footer()
│   │   │   └── navbar.py           # get_navbar_components() dispatcher
│   │   │
│   │   ├── pages/
│   │   │   ├── __init__.py
│   │   │   ├── society_select.py   # Stage-1 login (pick society)
│   │   │   ├── login.py            # Stage-2 login (password/PIN/pattern)
│   │   │   ├── master_portal.py    # Master Admin portal
│   │   │   ├── admin_portal.py     # Admin portal (all tabs)
│   │   │   ├── owner_portal.py     # Apartment owner portal
│   │   │   ├── vendor_portal.py    # Vendor portal
│   │   │   ├── security_portal.py  # Security portal
│   │   │   ├── card_catalogue.py   # KPI_CARDS + FORM_CARDS + renderers
│   │   │   └── customize_layout.py # Drag-n-drop customize page (old v1)
│   │   │
│   │   └── callbacks/
│   │       ├── __init__.py         # register_callbacks(app) master dispatcher
│   │       ├── auth_callbacks.py   # Router + 2-stage login + logout
│   │       ├── admin_callbacks.py  # Enroll, society count, QR validate
│   │       ├── owner_callbacks.py  # QR generate, payment process
│   │       ├── vendor_callbacks.py # (stub — extend as needed)
│   │       ├── security_callbacks.py # QR scan, clock in/out
│   │       ├── mobile_callbacks.py # Hamburger + sidebar toggle
│   │       ├── qr_callbacks.py     # Header QR modal
│   │       ├── customize_callbacks.py # SortableJS DnD + save/reset layout
│   │       ├── shell_callbacks.py  # NEW: app_shell tab routing, KPI refresh
│   │       │                       #      toast renderer, clock tick, breadcrumb
│   │       └── card_catalogue_callbacks.py # All 22 catalogue callbacks
│   │
│   ├── static/
│   │   ├── assets/
│   │   │   └── logo.png
│   │   ├── css/
│   │   │   └── style.css           # Glassmorphism + responsive KPI grid
│   │   └── js/
│   │       ├── custom.js
│   │       ├── mobile.js           # Touch swipe sidebar
│   │       ├── push.js             # Service-worker push subscription
│   │       └── sw.js               # Push service worker
│   │
│   └── templates/
│       ├── base.html               # Redirects → /dashboard/
│       ├── login.html              # Flask fallback login
│       └── dashboard.html
│
└── tests/
    ├── test_auth.py
    ├── test_api.py
    └── test_services.py
```

---

## 2-Stage Login Flow

```
Browser hits /dashboard/
        │
        ▼
[ Stage 1 — society_select.py ]
  • Dropdown of societies from DB
  • "Remember society" cookie
  • Master Admin inline form (no society)
        │ society selected → auth-store{society_id, authenticated:False}
        ▼
[ Stage 2 — login.py ]
  • Tabs: Password / PIN / Pattern
  • "Remember me" cookie (email + method)
  • authenticate_user/pin/pattern() → raw psycopg2
        │ success → auth-store{user_id, email, role, society_id, authenticated:True}
        ▼
[ Router — auth_callbacks.py ]
  Role-based redirect:
    master   → /dashboard/master-portal
    admin    → /dashboard/admin-portal
    apartment→ /dashboard/owner-portal
    vendor   → /dashboard/vendor-portal
    security → /dashboard/pass-evaluation
```

---

## JWT + Push Flow

```
Login success
  │
  ├─► Flask session (flask-login) — for Dash SSR pages
  ├─► JWT access token (1h) + refresh token (30d) — for REST /api/* endpoints
  └─► Push subscription saved via /auth/subscribe-push (pywebpush VAPID)

API call (mobile / external):
  Authorization: Bearer <access_token>
  → @token_required / @role_required decorators in jwt_handler.py

Push trigger (server-side event):
  send_push_notification(user_id, title, body)
  → looks up push_subscription JSON on User model
  → webpush() via VAPID keys from .env
```

---

## Portal → Sidebar Tabs Map

| Role | Portal | Tabs |
|---|---|---|
| master | Master Portal | Dashboard, Societies |
| admin | Admin Portal | Dashboard, Cashbook, Receipts, Expenses, Enroll, Users, Events, Evaluate Pass, Customize, Settings |
| apartment | Owner Portal | Dashboard, Cashbook, Payments, Charges, Events, Settings |
| vendor | Vendor Portal | Dashboard, Cashbook, Payments, Charges, Events, Settings |
| security | Security Portal | Pass Evaluation, Attendance, Events, New Receipt, Users, Settings |

---

## KPI Cards by Group

| Group | Cards |
|---|---|
| Societies | Free Plan, Paid Plan, Total |
| Apartments | With Dues, No Dues, Total |
| Vendors | With Dues, No Dues, Total |
| Security | On Duty, Off Duty, Total |
| Events | Events, Gate Entries Today, Open Concerns |
| Cashbook | Receipts (Month), Payments (Month), Balance |

---

## Form/List Cards (25 cards)

Society Profile · Create Society · Societies List  
Entity Profile · Create Entity · Entities List  
Account Profile · Create Account · Accounts List  
Payment Profile · New Transaction · Payments List  
Charge Profile · Create Charge · Charges List  
New Receipt · New Expense · Cashbook List  
Event Profile · Create Event · Events List  
Gate Log Profile · Create Gate Log · Gate Logs List  
Concern Profile · Create Concern · Concerns List  
Evaluate Pass (camera + manual) · Settings Rates & Fines  

---

## NeonDB Extra Tables (run after dashestatehub.sql)

```sql
CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    society_id  INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL,
    description TEXT,
    event_date  DATE NOT NULL,
    event_time  VARCHAR(20),
    venue       VARCHAR(200),
    open_to     VARCHAR(20) DEFAULT 'all',
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concerns (
    id            SERIAL PRIMARY KEY,
    society_id    INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    flat_no       VARCHAR(20),
    concern_type  VARCHAR(50),
    description   TEXT,
    preferred_time VARCHAR(20),
    status        VARCHAR(20) DEFAULT 'open',
    assigned_to   VARCHAR(100),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS charges (
    id          SERIAL PRIMARY KEY,
    society_id  INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    charge_type VARCHAR(30),
    amount      NUMERIC(10,2),
    applies_to  VARCHAR(20) DEFAULT 'all',
    frequency   VARCHAR(20) DEFAULT 'monthly',
    due_day     INTEGER DEFAULT 15,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS society_settings (
    id         SERIAL PRIMARY KEY,
    society_id INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    key        VARCHAR(60) NOT NULL,
    value      TEXT,
    UNIQUE(society_id, key)
);

CREATE TABLE IF NOT EXISTS payments (
    id             SERIAL PRIMARY KEY,
    society_id     INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
    user_id        INTEGER REFERENCES users(id),
    apartment_id   INTEGER REFERENCES apartments(id),
    amount         NUMERIC(10,2) NOT NULL,
    payment_type   VARCHAR(50),
    payment_method VARCHAR(50),
    transaction_id VARCHAR(255),
    status         VARCHAR(20) DEFAULT 'pending',
    due_date       DATE,
    paid_at        TIMESTAMP,
    created_at     TIMESTAMP DEFAULT NOW()
);
```

---

## Environment Variables (.env)

```bash
# Flask
SECRET_KEY=your-very-secret-flask-key
FLASK_CONFIG=production

# NeonDB
PGHOST=ep-xxx.us-east-1.aws.neon.tech
PGDATABASE=societyos
PGUSER=societyos_owner
PGPASSWORD=your-neon-password
PGSSLMODE=require

# JWT
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ACCESS_TOKEN_EXPIRES=3600
JWT_REFRESH_TOKEN_EXPIRES=2592000

# VAPID Push
VAPID_PRIVATE_KEY=your-vapid-private-key
VAPID_PUBLIC_KEY=your-vapid-public-key
VAPID_CLAIM_EMAIL=admin@yourdomain.com
```

---

## ApexWeave Deployment

```bash
# 1. Push to Git
git add .
git commit -m "SocietyOS full stack"
git push origin main

# 2. ApexWeave → New App
#    Build command:  pip install -r requirements.txt
#    Start command:  gunicorn wsgi:server --workers 2 --threads 4 --timeout 120
#    Port:           8050

# 3. Set all .env vars in ApexWeave Environment panel

# 4. Run DB schema on NeonDB console
#    Paste dashestatehub.sql + extras above

# 5. Create master admin
INSERT INTO users (email, password_hash, role, login_method)
VALUES ('master@yourdomain.com', '<scrypt_hash>', 'admin', 'password');
```
