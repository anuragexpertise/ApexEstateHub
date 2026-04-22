# ================================================================
# INTEGRATION — 4 steps
# ================================================================
#
# STEP 1 — File placement
#   card_catalogue.py          → app/dash_apps/pages/card_catalogue.py
#   card_catalogue_callbacks.py → app/dash_apps/callbacks/card_catalogue_callbacks.py
#   customize.py (v2)          → app/dash_apps/pages/customize.py  (replace old)
#
# ================================================================
#
# STEP 2 — app/dash_apps/callbacks/__init__.py
#   Add one import + one call:
#
#   from .card_catalogue_callbacks import register_card_catalogue_callbacks
#
#   def register_callbacks(app):
#       register_auth_callbacks(app)
#       register_admin_callbacks(app)
#       register_owner_callbacks(app)
#       register_mobile_callbacks(app)
#       register_security_callbacks(app)
#       register_qr_callbacks(app)
#       register_customize_callbacks(app)
#       register_card_catalogue_callbacks(app)   # ← ADD
#       print("✓ All callbacks registered")
#
# ================================================================
#
# STEP 3 — admin_portal.py  (customize tab early return)
#   Replace:
#       elif active_tab == "customize":
#           content = html.Div([...html.P("coming soon")...])
#   With:
#       elif active_tab == "customize":
#           from app.dash_apps.pages.customize import customize_layout
#           return customize_layout()
#
# ================================================================
#
# STEP 4 — NeonDB: missing tables
#   Run once if not already created:
#
#   CREATE TABLE IF NOT EXISTS events (
#       id          SERIAL PRIMARY KEY,
#       society_id  INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
#       title       VARCHAR(200) NOT NULL,
#       description TEXT,
#       event_date  DATE NOT NULL,
#       event_time  VARCHAR(20),
#       venue       VARCHAR(200),
#       open_to     VARCHAR(20) DEFAULT 'all',
#       created_at  TIMESTAMP DEFAULT NOW()
#   );
#
#   CREATE TABLE IF NOT EXISTS concerns (
#       id           SERIAL PRIMARY KEY,
#       society_id   INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
#       flat_no      VARCHAR(20),
#       concern_type VARCHAR(50),
#       description  TEXT,
#       preferred_time VARCHAR(20),
#       status       VARCHAR(20) DEFAULT 'open',
#       assigned_to  VARCHAR(100),
#       created_at   TIMESTAMP DEFAULT NOW()
#   );
#
#   CREATE TABLE IF NOT EXISTS charges (
#       id          SERIAL PRIMARY KEY,
#       society_id  INTEGER NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
#       name        VARCHAR(100) NOT NULL,
#       charge_type VARCHAR(30),
#       amount      NUMERIC(10,2),
#       applies_to  VARCHAR(20) DEFAULT 'all',
#       frequency   VARCHAR(20) DEFAULT 'monthly',
#       due_day     INTEGER DEFAULT 15,
#       created_at  TIMESTAMP DEFAULT NOW()
#   );
#
# ================================================================
#
# CARD CATALOGUE SUMMARY (40 cards total)
# ─────────────────────────────────────────────────────────────────
# KPI (15):  Apartments ×3, Vendors ×3, Security ×3,
#            Events ×3, Cashbook ×3
#
# Form/List (25):
#   Society    — profile, create (with logo/sign/bg uploads), list
#   Entities   — profile, create (with avatar upload), list
#   Accounts   — profile, create, list
#   Payments   — profile, new transaction, list
#   Charges    — profile, create, list
#   Cashbook   — new receipt, new expense, cashbook list
#   Events     — profile, create, list
#   Gate Logs  — profile, create, list
#   Concerns   — profile, create, list
#   Security   — evaluate pass (camera + manual)
#   Settings   — rates & fines
#
# ================================================================
