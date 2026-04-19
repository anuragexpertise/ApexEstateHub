#!/usr/bin/env python
"""Direct test society creation using psycopg2"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

load_dotenv()

def create_test_society_direct():
    """Direct database connection to create test society and admin"""
    
    print("=" * 60)
    print("CREATE TEST SOCIETY (DIRECT CONNECTION)")
    print("=" * 60)
    
    # Society details
    SOCIETY_NAME = "Green Valley Apartments"
    SOCIETY_EMAIL = "contact@greenvalley.com"
    SOCIETY_PHONE = "9876543210"
    SOCIETY_ADDRESS = "123 Main Street, Cityville"
    SECRETARY_NAME = "John Secretary"
    SECRETARY_PHONE = "9876543211"
    
    # Admin details
    ADMIN_EMAIL = "admin@greenvalley.com"
    ADMIN_PASSWORD = "Admin@123"
    ADMIN_PIN = "1234"
    
    # Get connection parameters
    pg_host = os.getenv('PGHOST', '').strip("'\"")
    pg_database = os.getenv('PGDATABASE', '').strip("'\"")
    pg_user = os.getenv('PGUSER', '').strip("'\"")
    pg_password = os.getenv('PGPASSWORD', '').strip("'\"")
    pg_sslmode = os.getenv('PGSSLMODE', 'require').strip("'\"")
    
    print(f"\nConnecting to: {pg_host}/{pg_database}")
    
    try:
        # Direct connection
        conn = psycopg2.connect(
            host=pg_host,
            database=pg_database,
            user=pg_user,
            password=pg_password,
            sslmode=pg_sslmode
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if society already exists
        print("\n1. Checking for existing society...")
        cur.execute("SELECT id, name FROM societies WHERE name = %s", (SOCIETY_NAME,))
        existing_society = cur.fetchone()
        
        if existing_society:
            society_id = existing_society[0]
            print(f"   Society already exists: ID={society_id}, Name={existing_society[1]}")
        else:
            print(f"   Creating new society: {SOCIETY_NAME}")
            
            # Insert society
            plan_validity = (datetime.now() + timedelta(days=365)).date()
            arrear_start_date = datetime.now().date()
            
            cur.execute("""
                INSERT INTO societies (
                    name, email, phone, address, 
                    secretary_name, secretary_phone, 
                    plan, plan_validity, arrear_start_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                SOCIETY_NAME, SOCIETY_EMAIL, SOCIETY_PHONE, SOCIETY_ADDRESS,
                SECRETARY_NAME, SECRETARY_PHONE,
                'Free', plan_validity, arrear_start_date
            ))
            
            result = cur.fetchone()
            if result:
                society_id = result[0]
                print(f"   ✅ Society created! ID: {society_id}")
            else:
                print("   ❌ Failed to create society")
                return False
        
        # Check if admin already exists
        print(f"\n2. Checking for existing admin: {ADMIN_EMAIL}")
        cur.execute("SELECT id, email, role FROM users WHERE email = %s", (ADMIN_EMAIL,))
        existing_admin = cur.fetchone()
        
        # Hash passwords
        print("\n3. Hashing passwords...")
        hashed_password = generate_password_hash(ADMIN_PASSWORD)
        hashed_pin = generate_password_hash(ADMIN_PIN)
        print(f"   Password hash created")
        print(f"   PIN hash created")
        
        if existing_admin:
            print(f"   Admin already exists: ID={existing_admin[0]}")
            print("\n4. Updating admin...")
            cur.execute("""
                UPDATE users 
                SET password_hash = %s, pin_hash = %s, society_id = %s
                WHERE email = %s
                RETURNING id
            """, (hashed_password, hashed_pin, society_id, ADMIN_EMAIL))
            result = cur.fetchone()
            if result:
                print(f"   ✅ Admin updated! ID: {result[0]}")
        else:
            print(f"   Creating new admin...")
            cur.execute("""
                INSERT INTO users (
                    society_id, email, password_hash, pin_hash, 
                    role, login_method
                ) VALUES (%s, %s, %s, %s, 'admin', 'password')
                RETURNING id
            """, (society_id, ADMIN_EMAIL, hashed_password, hashed_pin))
            result = cur.fetchone()
            if result:
                admin_id = result[0]
                print(f"   ✅ Admin created! ID: {admin_id}")
            else:
                print("   ❌ Failed to create admin")
                return False
        
        # Create a test apartment
        print("\n5. Creating test apartment...")
        cur.execute("""
            SELECT id FROM apartments WHERE society_id = %s AND flat_number = 'A-101'
        """, (society_id,))
        existing_apt = cur.fetchone()
        
        if not existing_apt:
            cur.execute("""
                INSERT INTO apartments (
                    society_id, flat_number, owner_name, mobile, apartment_size, active
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (society_id, 'A-101', 'Rajesh Sharma', '9876543212', 1200, True))
            apt_result = cur.fetchone()
            if apt_result:
                print(f"   ✅ Apartment created! ID: {apt_result[0]}")
            else:
                print("   ⚠️ Could not create apartment (table might not exist)")
        else:
            print(f"   Apartment already exists: ID={existing_apt[0]}")
        
        # Verify the setup
        print("\n6. Verifying setup...")
        cur.execute("""
            SELECT s.id, s.name, u.id, u.email, u.role 
            FROM societies s 
            JOIN users u ON u.society_id = s.id 
            WHERE s.id = %s AND u.email = %s
        """, (society_id, ADMIN_EMAIL))
        verify = cur.fetchone()
        
        if verify:
            print(f"   ✅ Verification PASSED!")
            print(f"   Society ID: {verify[0]}, Name: {verify[1]}")
            print(f"   Admin ID: {verify[2]}, Email: {verify[3]}, Role: {verify[4]}")
        else:
            print("   ⚠️ Verification could not confirm both records")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("TEST SOCIETY CREATED SUCCESSFULLY!")
        print("=" * 60)
        print("\nSOCIETY DETAILS:")
        print(f"  Name: {SOCIETY_NAME}")
        print(f"  ID: {society_id}")
        print(f"  Email: {SOCIETY_EMAIL}")
        print(f"  Phone: {SOCIETY_PHONE}")
        print(f"  Address: {SOCIETY_ADDRESS}")
        print("\nADMIN CREDENTIALS:")
        print(f"  Email: {ADMIN_EMAIL}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print(f"  PIN: {ADMIN_PIN}")
        print("\nLOGIN URL:")
        print(f"  http://127.0.0.1:8050/dashboard/")
        print("=" * 60)
        
        return True
        
    except psycopg2.errors.UndefinedTable as e:
        print(f"\n❌ Table error: {e}")
        print("\nYou may need to run migrations first:")
        print("  flask db upgrade")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_apartment_owner():
    """Create an apartment owner user"""
    
    print("\n" + "=" * 60)
    print("CREATE APARTMENT OWNER")
    print("=" * 60)
    
    OWNER_EMAIL = "rajesh@greenvalley.com"
    OWNER_PASSWORD = "Owner@123"
    OWNER_PIN = "5678"
    
    # Get society ID
    pg_host = os.getenv('PGHOST', '').strip("'\"")
    pg_database = os.getenv('PGDATABASE', '').strip("'\"")
    pg_user = os.getenv('PGUSER', '').strip("'\"")
    pg_password = os.getenv('PGPASSWORD', '').strip("'\"")
    pg_sslmode = os.getenv('PGSSLMODE', 'require').strip("'\"")
    
    try:
        conn = psycopg2.connect(
            host=pg_host,
            database=pg_database,
            user=pg_user,
            password=pg_password,
            sslmode=pg_sslmode
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Get society ID for Green Valley
        cur.execute("SELECT id FROM societies WHERE name = 'Green Valley Apartments'")
        society = cur.fetchone()
        
        if not society:
            print("   Society not found. Run create_test_society_direct.py first")
            return False
        
        society_id = society[0]
        
        # Get apartment ID
        cur.execute("SELECT id FROM apartments WHERE society_id = %s AND flat_number = 'A-101'", (society_id,))
        apartment = cur.fetchone()
        
        apartment_id = apartment[0] if apartment else None
        
        # Check if owner exists
        cur.execute("SELECT id FROM users WHERE email = %s", (OWNER_EMAIL,))
        existing = cur.fetchone()
        
        hashed_password = generate_password_hash(OWNER_PASSWORD)
        hashed_pin = generate_password_hash(OWNER_PIN)
        
        if existing:
            cur.execute("""
                UPDATE users 
                SET password_hash = %s, pin_hash = %s, society_id = %s, linked_id = %s
                WHERE email = %s
            """, (hashed_password, hashed_pin, society_id, apartment_id, OWNER_EMAIL))
            print(f"   ✅ Owner updated!")
        else:
            cur.execute("""
                INSERT INTO users (society_id, email, password_hash, pin_hash, role, linked_id, login_method)
                VALUES (%s, %s, %s, %s, 'apartment', %s, 'password')
                RETURNING id
            """, (society_id, OWNER_EMAIL, hashed_password, hashed_pin, apartment_id))
            result = cur.fetchone()
            if result:
                print(f"   ✅ Owner created! ID: {result[0]}")
        
        cur.close()
        conn.close()
        
        print("\nOWNER CREDENTIALS:")
        print(f"  Email: {OWNER_EMAIL}")
        print(f"  Password: {OWNER_PASSWORD}")
        print(f"  PIN: {OWNER_PIN}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    # Create society and admin
    if create_test_society_direct():
        print("\n" + "=" * 60)
        print("To test the login flow:")
        print("1. Go to http://127.0.0.1:8050/dashboard/")
        print("2. Select 'Green Valley Apartments' from dropdown")
        print("3. Login with admin@greenvalley.com / Admin@123")
        print("=" * 60)
        
        # Ask if user wants to create an apartment owner
        print("\nCreate apartment owner? (y/n)")
        response = input().strip().lower()
        if response == 'y':
            create_apartment_owner()