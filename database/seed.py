#!/usr/bin/env python3
# database/seed.py
"""
First-run seeder for ApexEstateHub.

 1. If NO users exist → create master admin
 2. If NO societies exist → prompt to create dummy data
    (one society + admin, owner, vendor, security users)

Can be run standalone:
    python3 database/seed.py

Or called by migrate.py automatically after schema creation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

from werkzeug.security import generate_password_hash


# ── DB helper (uses singleton) ────────────────────────────────────────────────
def _db():
    from database.db_manager import db
    return db


# ── 1. Master admin ───────────────────────────────────────────────────────────

MASTER_EMAIL    = 'master@estatehub.com'
MASTER_PASSWORD = 'Master@2024'


def ensure_master_admin() -> bool:
    """Create master admin if no users exist at all. Returns True if created."""
    db = _db()

    # Check connectivity first
    try:
        result = db.execute_query("SELECT COUNT(*) AS c FROM users", fetch_one=True)
    except Exception as e:
        print(f"❌  DB error checking users: {e}")
        return False

    if result and result['c'] > 0:
        print(f"✓ Users exist ({result['c']}) — skipping master admin creation.")
        return False

    # No users — create master admin (society_id = NULL = master)
    pw_hash = generate_password_hash(MASTER_PASSWORD)
    try:
        db.execute_query(
            """
            INSERT INTO users (email, password_hash, role, login_method)
            VALUES (%s, %s, 'admin', 'password')
            ON CONFLICT (email) DO NOTHING
            """,
            (MASTER_EMAIL, pw_hash)
        )
        print()
        print("  ┌─────────────────────────────────────────────┐")
        print("  │          Master Admin Created  ✓             │")
        print("  ├─────────────────────────────────────────────┤")
        print(f"  │  Email    : {MASTER_EMAIL:<33}│")
        print(f"  │  Password : {MASTER_PASSWORD:<33}│")
        print("  │  ⚠  Change this password after first login! │")
        print("  └─────────────────────────────────────────────┘")
        print()
        return True
    except Exception as e:
        print(f"❌  Failed to create master admin: {e}")
        return False


# ── 2. Dummy society + all roles ─────────────────────────────────────────────

DUMMY_SOCIETY = {
    'name':            'Sunrise Residency',
    'email':           'admin@sunriseresidency.com',
    'phone':           '9876543210',
    'address':         '12, MG Road, Sector 5, Meerut, UP - 250001',
    'secretary_name':  'Ramesh Kumar',
    'secretary_phone': '9876543211',
    'plan':            'Free',
    'plan_validity':   '2025-12-31',
    'arrear_start_date': '2024-04-01',
}

DUMMY_USERS = [
    {
        'role':        'admin',
        'email':       'admin@sunriseresidency.com',
        'password':    'Admin@2024',
        'flat':        None,
        'name':        'Society Admin',
        'description': 'Society Admin',
    },
    {
        'role':        'apartment',
        'email':       'owner@sunriseresidency.com',
        'password':    'Owner@2024',
        'flat':        'A-101',
        'area':        1200,
        'owner_name':  'Rajesh Sharma',
        'mobile':      '9811111111',
        'name':        'Rajesh Sharma',
        'description': 'Apartment Owner (Flat A-101)',
    },
    {
        'role':        'vendor',
        'email':       'vendor@sunriseresidency.com',
        'password':    'Vendor@2024',
        'flat':        None,
        'name':        'Plumbing Services',
        'description': 'Vendor (Plumbing)',
    },
    {
        'role':        'security',
        'email':       'security@sunriseresidency.com',
        'password':    'Security@2024',
        'flat':        None,
        'name':        'Guard Ramu',
        'description': 'Security Staff',
    },
]


def ensure_dummy_data():
    """If no societies exist, prompt user and optionally seed dummy data."""
    db = _db()

    try:
        result = db.execute_query("SELECT COUNT(*) AS c FROM societies", fetch_one=True)
    except Exception as e:
        print(f"❌  DB error checking societies: {e}")
        return

    if result and result['c'] > 0:
        print(f"✓ Societies exist ({result['c']}) — skipping dummy data.")
        return

    # No societies — ask user
    print()
    print("  ℹ  No societies found (first run).")
    print("  Would you like to create dummy data?")
    print("  This will create:")
    print("    • 1 society  : Sunrise Residency")
    print("    • 1 admin    : admin@sunriseresidency.com  / Admin@2024")
    print("    • 1 owner    : owner@sunriseresidency.com  / Owner@2024  (Flat A-101)")
    print("    • 1 vendor   : vendor@sunriseresidency.com / Vendor@2024")
    print("    • 1 security : security@sunriseresidency.com / Security@2024")
    print()

    try:
        answer = input("  Create dummy data? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = 'n'

    if answer != 'y':
        print("  Skipped. You can create a society by logging in as master admin.")
        return

    _seed_dummy(db)


def _seed_dummy(db):
    # ── Create society ────────────────────────────────────────────────────────
    try:
        soc = db.execute_query(
            """
            INSERT INTO societies
                (name, email, phone, address, secretary_name, secretary_phone,
                 plan, plan_validity, arrear_start_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (name) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """,
            (
                DUMMY_SOCIETY['name'], DUMMY_SOCIETY['email'],
                DUMMY_SOCIETY['phone'], DUMMY_SOCIETY['address'],
                DUMMY_SOCIETY['secretary_name'], DUMMY_SOCIETY['secretary_phone'],
                DUMMY_SOCIETY['plan'], DUMMY_SOCIETY['plan_validity'],
                DUMMY_SOCIETY['arrear_start_date'],
            ),
            fetch_one=True
        )
        society_id = soc['id']
        print(f"  ✓ Society created  (id={society_id}): {DUMMY_SOCIETY['name']}")
    except Exception as e:
        print(f"  ❌  Society creation failed: {e}")
        return

    # ── Create users ──────────────────────────────────────────────────────────
    for u in DUMMY_USERS:
        pw_hash = generate_password_hash(u['password'])
        try:
            user = db.execute_query(
                """
                INSERT INTO users (society_id, email, password_hash, role, login_method)
                VALUES (%s,%s,%s,%s,'password')
                ON CONFLICT (email) DO NOTHING
                RETURNING id
                """,
                (society_id, u['email'], pw_hash, u['role']),
                fetch_one=True
            )
            if not user:
                print(f"  ⚠  {u['description']} already exists — skipped.")
                continue

            user_id = user['id']

            # For apartment role → also create apartment record and link user
            if u['role'] == 'apartment' and u.get('flat'):
                apt = db.execute_query(
                    """
                    INSERT INTO apartments
                        (society_id, flat_number, owner_name, mobile, apartment_size, active)
                    VALUES (%s,%s,%s,%s,%s,TRUE)
                    ON CONFLICT (society_id, flat_number) DO NOTHING
                    RETURNING id
                    """,
                    (society_id, u['flat'], u.get('owner_name', u['name']),
                     u.get('mobile', ''), u.get('area', 1000)),
                    fetch_one=True
                )
                if apt:
                    db.execute_query(
                        "UPDATE users SET linked_id=%s WHERE id=%s",
                        (apt['id'], user_id)
                    )

            print(f"  ✓ {u['description']:<30} → {u['email']}  /  {u['password']}")

        except Exception as e:
            print(f"  ❌  {u['description']} failed: {e}")

    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │              Dummy Data Created  ✓                       │")
    print("  │  Login at http://127.0.0.1:8050                          │")
    print("  │  Master : master@estatehub.com     / Master@2024         │")
    print("  │  Admin  : admin@sunriseresidency.com / Admin@2024        │")
    print("  │  Owner  : owner@sunriseresidency.com / Owner@2024        │")
    print("  │  Vendor : vendor@sunriseresidency.com / Vendor@2024      │")
    print("  │  Sec    : security@sunriseresidency.com / Security@2024  │")
    print("  └─────────────────────────────────────────────────────────┘")


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    """Called by migrate.py or directly."""
    print()
    print("── Seed check ───────────────────────────────────────────────")
    ensure_master_admin()
    ensure_dummy_data()
    print("─────────────────────────────────────────────────────────────")


if __name__ == '__main__':
    run()
