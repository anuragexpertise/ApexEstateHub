#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db_manager import db
from werkzeug.security import generate_password_hash

def add_user(society_id, apartment_id, email, password, user_type):
    valid_types = {"owner", "family", "tenant", "visitor"}
    if user_type not in valid_types:
        print(f"Error: user_type must be one of {valid_types}")
        return

    try:
        db._execute(
            "INSERT INTO users(society_id, email, password_hash, role, login_method, linked_id, user_type) "
            "VALUES(%s, %s, %s, 'apartment', 'password', %s, %s)",
            (society_id, email, generate_password_hash(password), apartment_id, user_type)
        )
        print(f"Successfully added {user_type} '{email}' to apartment {apartment_id}.")
    except Exception as e:
        print(f"Error adding user: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python manage_apartment_users.py <society_id> <apartment_id> <email> <password> <user_type>")
        sys.exit(1)
    
    add_user(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
