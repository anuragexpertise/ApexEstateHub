import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db_manager import db

try:
    db._execute("ALTER TABLE users ADD COLUMN user_type VARCHAR(20) DEFAULT 'owner' CHECK (user_type IN ('owner', 'family', 'tenant', 'visitor'))")
    print("Column added.")
except Exception as e:
    print(f"Error adding column: {e}")

try:
    db._execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_user_type_check")
    db._execute("ALTER TABLE users ADD CONSTRAINT users_user_type_check CHECK (user_type IN ('owner', 'family', 'tenant', 'visitor'))")
    print("Constraint updated.")
except Exception as e:
    print(f"Error updating constraint: {e}")
