#!/usr/bin/env python
"""Check database schema and constraints"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import db

def check_schema():
    """Check existing tables and constraints"""
    
    print("=" * 60)
    print("DATABASE SCHEMA CHECK")
    print("=" * 60)
    
    # Check users table columns
    print("\n1. Users table columns:")
    query = """
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'users'
        ORDER BY ordinal_position
    """
    columns = db.execute_query(query, fetch_all=True)
    if columns:
        for col in columns:
            print(f"   - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    
    # Check constraints
    print("\n2. Users table constraints:")
    query = """
        SELECT constraint_name, constraint_type 
        FROM information_schema.table_constraints 
        WHERE table_name = 'users'
    """
    constraints = db.execute_query(query, fetch_all=True)
    if constraints:
        for con in constraints:
            print(f"   - {con['constraint_name']}: {con['constraint_type']}")
    
    # Check if master admin exists
    print("\n3. Existing master admin:")
    query = "SELECT id, email, role, society_id FROM users WHERE email = 'master@estatehub.com'"
    existing = db.execute_query(query, fetch_one=True)
    if existing:
        print(f"   Found: ID={existing['id']}, Email={existing['email']}, Role={existing['role']}")
    else:
        print("   No master admin found")

if __name__ == "__main__":
    check_schema()