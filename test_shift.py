import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
dsn = os.getenv("DATABASE_URL")
if not dsn:
    dsn = f"dbname={os.getenv('PGDATABASE', 'estatehub')} user={os.getenv('PGUSER', 'postgres')} password={os.getenv('PGPASSWORD', '')} host={os.getenv('PGHOST', 'localhost')} port={os.getenv('PGPORT', '5432')}"

conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()

# Get a security guard
cur.execute("SELECT id, society_id, salary_per_shift FROM security_staff LIMIT 1")
row = cur.fetchone()
staff_id, society_id, salary = row

# Insert a roster for yesterday
cur.execute("INSERT INTO security_roster (society_id, security_id, roster_date, shift_type) VALUES (%s, %s, CURRENT_DATE - INTERVAL '1 day', 'morning') RETURNING id", (society_id, staff_id))
roster_id = cur.fetchone()[0]

# Insert gate access for a 2 hour shift
cur.execute("SELECT id FROM users WHERE linked_id = %s AND role = 'security'", (staff_id,))
user_id = cur.fetchone()[0]
cur.execute("INSERT INTO gate_access (society_id, entity_id, role, time_in, time_out, status) VALUES (%s, %s, 'SEC', CURRENT_DATE - INTERVAL '1 day' + INTERVAL '8 hours', CURRENT_DATE - INTERVAL '1 day' + INTERVAL '10 hours', 'allowed')", (society_id, user_id))

# Run generator
cur.execute("SELECT fn_auto_generate_payables(%s)", (society_id,))

# Check payable
cur.execute("SELECT amount, shift_fraction, description FROM payables WHERE roster_id = %s", (roster_id,))
p = cur.fetchone()
print(f"Payable: amount={p[0]}, fraction={p[1]}, desc={p[2]}")

# Test trigger: modify fraction
cur.execute("UPDATE payables SET shift_fraction = 0.5 WHERE roster_id = %s", (roster_id,))
cur.execute("SELECT amount, shift_fraction FROM payables WHERE roster_id = %s", (roster_id,))
p2 = cur.fetchone()
print(f"After trigger: amount={p2[0]}, fraction={p2[1]}")
