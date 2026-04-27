# SocietyOS — ApexEstateHub
## Complete Project Structure & Integration Guide
> Stack: Flask + Plotly Dash · Aiven (PostgreSQL) · JWT + Push · ApexWeave

---



## 2-Stage Login Flow

```
Browser hits /dashboard/
        │
        ▼
[ Stage 1 — society_select.py ]
  • if no connection to database -> 'Network Error'. Retry button
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



---

## Environment Variables (.env)

```bash
# Flask
SECRET_KEY=your-very-secret-flask-key
FLASK_CONFIG=production

# Aiven Parameters


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
