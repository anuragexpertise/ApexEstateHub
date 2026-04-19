#!/usr/bin/env python
"""Direct master admin setup using psycopg2"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

def setup_master_admin_direct():
    """Direct database connection for master admin setup"""
    
    print("=" * 60)
    print("MASTER ADMIN SETUP (DIRECT CONNECTION)")
    print("=" * 60)
    
    MASTER_EMAIL = "master@estatehub.com"
    MASTER_PASSWORD = "Master@2024"
    MASTER_PIN = "1234"
    
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
        
        # Hash password
        print("\n1. Hashing password...")
        hashed_password = generate_password_hash(MASTER_PASSWORD)
        hashed_pin = generate_password_hash(MASTER_PIN)
        print(f"   Password hash created")
        
        # Check if master admin exists
        print("\n2. Checking for existing master admin...")
        cur.execute("SELECT id, email FROM users WHERE email = %s", (MASTER_EMAIL,))
        existing = cur.fetchone()
        
        if existing:
            print(f"   Found existing: ID={existing[0]}")
            print("\n3. Updating master admin...")
            cur.execute("""
                UPDATE users 
                SET password_hash = %s, pin_hash = %s
                WHERE email = %s
                RETURNING id
            """, (hashed_password, hashed_pin, MASTER_EMAIL))
            result = cur.fetchone()
            if result:
                print(f"   ✅ Updated! ID: {result[0]}")
        else:
            print("   No existing master admin found")
            print("\n3. Creating master admin...")
            cur.execute("""
                INSERT INTO users (society_id, email, password_hash, pin_hash, role, login_method)
                VALUES (NULL, %s, %s, %s, 'admin', 'password')
                RETURNING id
            """, (MASTER_EMAIL, hashed_password, hashed_pin))
            result = cur.fetchone()
            if result:
                print(f"   ✅ Created! ID: {result[0]}")
        
        # Verify
        print("\n4. Verifying...")
        cur.execute("SELECT password_hash FROM users WHERE email = %s", (MASTER_EMAIL,))
        user = cur.fetchone()
        
        if user:
            from werkzeug.security import check_password_hash
            if check_password_hash(user[0], MASTER_PASSWORD):
                print("   ✅ Password verification PASSED!")
            else:
                print("   ❌ Password verification FAILED!")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("MASTER ADMIN READY!")
        print("=" * 60)
        print(f"Email: {MASTER_EMAIL}")
        print(f"Password: {MASTER_PASSWORD}")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    setup_master_admin_direct()