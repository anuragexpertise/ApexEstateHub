# ApexEstateHub — Full Bug Report & Fix Map
# Generated from repo inspection + in-context code review

## FILES INCLUDED IN THIS PACKAGE

| Output file | Action | Destination in repo |
|-------------|--------|---------------------|
| root/run.py | REPLACE (was empty 0 bytes) | run.py |
| root/requirements.txt | REPLACE (missing 4 packages) | requirements.txt |
| root/wsgi.py | REPLACE (wrong server export) | wsgi.py |
| database/db_manager.py | CREATE (content unconfirmed) | database/db_manager.py |
| app/dash_apps/app_shell.py | REPLACE (had copy of __init__.py) | app/dash_apps/app_shell.py |
| app/dash_apps/layout.py | CREATE (missing entirely) | app/dash_apps/layout.py |
| app/dash_apps/callbacks/__init__.py | REPLACE (alias fix) | app/dash_apps/callbacks/__init__.py |
| app/dash_apps/callbacks/mobile_callbacks.py | REPLACE (ID mismatches) | app/dash_apps/callbacks/mobile_callbacks.py |
| app/routes/auth.py | REPLACE (login_user dict bug) | app/routes/auth.py |
| *_snippet.py files | READ & apply manually | see each file |


## BUG DETAILS

### 🔴 CRITICAL — app won't boot at all

**1. run.py is 0 bytes**
GitHub shows "0 lines (0 loc) · 0 Bytes". File is completely empty.
→ Replace with root/run.py

**2. wsgi.py exports wrong server object**
```python
# WRONG — current code:
server = flask_app

# FIX:
server = dash_app.server
```
gunicorn targets `wsgi:server`. flask_app is a bare Flask WSGI app
that has no knowledge of Dash routes. dash_app.server IS the same
Flask object but with Dash's blueprint mounted. Without this, all
/dashboard/ routes return 404.
→ Replace with root/wsgi.py

**3. requirements.txt missing critical packages**
Missing: flask-sqlalchemy, flask-migrate, pywebpush, werkzeug (pinned)
qrcode needs [pil] extra or PNG generation crashes on some hosts.
→ Replace with root/requirements.txt

**4. app_shell.py has completely wrong content**
Current file is a verbatim copy of app/__init__.py (Flask factory code).
shell_callbacks.py imports ROLE_CONFIG from app_shell — which doesn't
exist there — causing an ImportError that crashes Dash startup.
→ Replace with app/dash_apps/app_shell.py

**5. layout.py is missing**
app/__init__.py line: `from app.dash_apps.layout import serve_layout`
This file does not exist → ImportError on startup → fallback layout shown.
→ Create app/dash_apps/layout.py

**6. database/db_manager.py — verify it's committed**
Every service file does `from database.db_manager import db`.
The database/ folder shows in the repo tree but file content was
inaccessible. If it's empty or missing → ImportError on startup.
→ Create database/db_manager.py (included as full file)


### 🟠 HIGH — runtime errors once app boots

**7. ROLE_CONFIG tab iteration mismatch**
shell_callbacks.py _make_nav_items():
```python
# WRONG — unpacks as tuple:
for label, href, icon in cfg['tabs']:

# FIX — tabs are dicts:
for tab in cfg['tabs']:
    label, href, icon = tab['label'], tab['href'], tab['icon']
```
→ Apply shell_callbacks_snippet.py

**8. login_user() called with a dict, not UserMixin**
```python
# WRONG — routes/auth.py:
user = authenticate_user(email, password)  # returns dict
login_user(user, ...)  # TypeError: dict has no is_authenticated

# FIX:
user_dict = authenticate_user(email, password)
user_obj  = User(user_id=user_dict['user_id'], ...)
login_user(user_obj, ...)
```
→ Replace with app/routes/auth.py

**9. callbacks/__init__.py name mismatch**
app/__init__.py calls: register_callbacks(dash_app)
but __init__.py only defines: register_all_callbacks()
→ Replace with app/dash_apps/callbacks/__init__.py (exports both names)

**10. Mobile sidebar ID mismatches**
mobile_callbacks.py targeted 'mobile-menu-toggle' (non-existent).
shell_layout uses 'hdr-hamburger-btn' and 'sb-overlay'.
sidebar.py toggle used 'sidebar-toggle', custom.js uses 'sidebar-toggle'.
→ Replace with app/dash_apps/callbacks/mobile_callbacks.py

**11. Wrong QR import in admin_callbacks.py**
```python
# WRONG:
from services.qr_service import validate_qr_code
# FIX:
from app.services.qr_service import validate_qr_code
```
→ Apply admin_callbacks_snippet.py


### 🟡 MEDIUM — functional gaps

**12. VAPID keys not guarded in push_service.py**
If env vars missing, webpush() is called with None → cryptography crash.
→ Apply push_service_snippet.py

**13. logo.png may 404 inside Dash pages**
src="/static/assets/logo.png" works for Flask templates.
Inside Dash SPA, reference as src="/dashboard/assets/logo.png"
OR copy logo.png to app/assets/ and use that path.

**14. app/models/__init__.py is empty**
SQLAlchemy won't register relationships unless models are imported
before db.create_all(). Add explicit imports:
```python
# app/models/__init__.py
from app.models.user import User
from app.models.society import Society
from app.models.apartment import Apartment
from app.models.payment import Payment
from app.models.transaction import Transaction, Account
from app.models.gate_access import GateAccess
```


### 🟢 LOW — cleanup / housekeeping

**15.** Root /static/ folder is orphaned — nothing references it.
       Merge useful files into app/static/ or delete.

**16.** prompt.txt committed to repo — exposes AI prompting strategy.
       Add to .gitignore.

**17.** dashestatehub.sql committed — if it has real data, remove from
       git history: git filter-branch or git-filter-repo.

**18.** Multiple test_*.py at root — move to tests/ folder.

**19.** Procfile looks correct:
       `web: gunicorn wsgi:server --workers 2 --threads 4 --timeout 120`
       No changes needed once wsgi.py is fixed.


## DEPLOYMENT CHECKLIST (ApexWeave / NeonDB)

1. Set env vars on ApexWeave:
   DATABASE_URL=postgresql://...   (from NeonDB dashboard)
   SECRET_KEY=<random 32 chars>
   JWT_SECRET_KEY=<random 32 chars>
   VAPID_PRIVATE_KEY=<from web-push-codelab or npx web-push generate-vapid-keys>
   VAPID_PUBLIC_KEY=<same>
   VAPID_CLAIM_EMAIL=admin@yourdomain.com
   FLASK_CONFIG=production

2. Copy app/assets/style.css  (from previous fix delivery)

3. Copy logo.png to BOTH:
   app/static/assets/logo.png   (for login.html Flask template)
   app/assets/logo.png          (for Dash pages)

4. git push → ApexWeave redeploy
