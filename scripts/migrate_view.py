import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db_manager import db

sql = """
CREATE OR REPLACE VIEW vw_apartment_users AS
SELECT 
    id,
    society_id,
    email,
    user_type,
    created_at,
    linked_id AS apartment_id
FROM users
WHERE role = 'apartment';
"""
try:
    db._execute(sql)
    print("View vw_apartment_users created.")
except Exception as e:
    print(f"Error creating view: {e}")
