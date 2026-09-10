import os
import re
from database.db_manager import db

with open('database/estatehub.sql', 'r') as f:
    sql = f.read()

# Extract the fn_complete_society_setup definition
start = sql.find("CREATE OR REPLACE FUNCTION fn_complete_society_setup")
end = sql.find("$$;", start) + 3
func_sql = sql[start:end]

try:
    with db._conn() as conn:
        with conn.cursor() as cur:
            cur.execute(func_sql)
            conn.commit()
    print("Function updated successfully")
except Exception as e:
    print(f"Error: {e}")
