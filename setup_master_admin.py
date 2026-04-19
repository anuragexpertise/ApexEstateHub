#!/usr/bin/env python
"""Setup master admin user"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.db_manager import db
from werkzeug.security import generate_password_hash

def setup_master_admin():
    MASTER_EMAIL = "master@estatehub.com"
    MASTER_PASSWORD = "Master@2024"
    MASTER_PIN = "1234"
    
    try:
        # Hash passwords
        hashed_password = generate_password_hash(MASTER_PASSWORD, method='scrypt')
        hashed_pin = generate_password_hash(MASTER_PIN, method='scrypt')
        
        # Check if exists
        check_query = "SELECT id FROM users WHERE email = %s"
        existing = db.execute_query(check_query, (MASTER_EMAIL,), fetch_one=True)
        
        if existing:
            update_query = "UPDATE users SET password_hash = %s, pin_hash = %s WHERE email = %s"
            db.execute_query(update_query, (hashed_password, hashed_pin, MASTER_EMAIL))
            print("✓ Master admin updated!")
        else:
            insert_query = """
                INSERT INTO users (society_id, email, password_hash, pin_hash, role, login_method)
                VALUES (NULL, %s, %s, %s, 'admin', 'password')
            """
            db.execute_query(insert_query, (MASTER_EMAIL, hashed_password, hashed_pin))
            print("✓ Master admin created!")
        
        print("\n" + "=" * 60)
        print("MASTER ADMIN CREDENTIALS:")
        print(f"  Email: {MASTER_EMAIL}")
        print(f"  Password: {MASTER_PASSWORD}")
        print(f"  PIN: {MASTER_PIN}")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup_master_admin()
