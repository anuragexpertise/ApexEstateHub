#!/usr/bin/env python
"""Create test society with admin user"""

import sys
import os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import db
from werkzeug.security import generate_password_hash

def create_test_society():
    """Create a test society"""
    
    print("=" * 60)
    print("CREATE TEST SOCIETY")
    print("=" * 60)
    
    try:
        # First, check if societies table exists
        check_table = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'societies')"
        table_exists = db.execute_query(check_table, fetch_one=True)
        
        if not table_exists or not table_exists.get('exists'):
            print("Creating societies table...")
            create_societies = """
                CREATE TABLE IF NOT EXISTS societies (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    logo VARCHAR(100),
                    address TEXT,
                    email VARCHAR(100),
                    phone VARCHAR(20),
                    secretary_name VARCHAR(100),
                    secretary_phone VARCHAR(20),
                    secretary_sign VARCHAR(100),
                    plan VARCHAR(4) CHECK (plan IN ('Free', 'Paid')) DEFAULT 'Free' NOT NULL,
                    plan_validity DATE NOT NULL,
                    arrear_start_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    login_background VARCHAR(100)
                )
            """
            db.execute_query(create_societies)
            print("✓ Societies table created")
        
        # Check if society already exists
        check_society = "SELECT id FROM societies WHERE name = %s"
        existing_society = db.execute_query(check_society, ("Green Valley Apartments",), fetch_one=True)
        
        # Set dates
        plan_validity = (datetime.now() + timedelta(days=365)).date()  # 1 year from now
        arrear_start_date = datetime.now().date()
        
        if existing_society:
            society_id = existing_society['id']
            print(f"\n✓ Society already exists with ID: {society_id}")
        else:
            # Insert test society with all required fields
            insert_society = """
                INSERT INTO societies (
                    name, email, phone, address, 
                    plan, plan_validity, arrear_start_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            
            result = db.execute_query(
                insert_society,
                (
                    "Green Valley Apartments", 
                    "contact@greenvalley.com", 
                    "9876543210", 
                    "123 Main Street, City",
                    "Free",
                    plan_validity,
                    arrear_start_date
                ),
                fetch_one=True
            )
            
            if result:
                society_id = result['id']
                print(f"\n✓ Society created with ID: {society_id}")
                print(f"  Name: Green Valley Apartments")
                print(f"  Email: contact@greenvalley.com")
                print(f"  Plan Validity: {plan_validity}")
            else:
                print("\n❌ Failed to create society")
                return
        
        # Create admin user for society
        hashed_password = generate_password_hash("Admin@123")
        
        # Check if admin already exists
        check_admin = "SELECT id FROM users WHERE email = %s"
        existing_admin = db.execute_query(check_admin, ("admin@greenvalley.com",), fetch_one=True)
        
        if existing_admin:
            print(f"\n⚠️ Admin already exists with ID: {existing_admin['id']}")
            print(f"  Email: admin@greenvalley.com")
        else:
            insert_admin = """
                INSERT INTO users (society_id, email, password_hash, role, login_method)
                VALUES (%s, %s, %s, 'admin', 'password')
                RETURNING id
            """
            admin_result = db.execute_query(insert_admin, (society_id, "admin@greenvalley.com", hashed_password), fetch_one=True)
            
            if admin_result:
                print(f"\n✅ Society admin created!")
                print(f"  ID: {admin_result['id']}")
                print(f"  Email: admin@greenvalley.com")
                print(f"  Password: Admin@123")
            else:
                print("\n❌ Failed to create admin")
        
        print("\n" + "=" * 60)
        print("LOGIN CREDENTIALS:")
        print(f"  Society Admin: admin@greenvalley.com / Admin@123")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_test_society()