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

cur.execute("SELECT id, society_id, salary_per_shift FROM security_staff LIMIT 1")
row = cur.fetchone()
if not row:
    print("No security staff found in DB!")
    exit(0)
staff_id, society_id, salary = row

cur.execute("SELECT id FROM users WHERE linked_id = %s AND role = 'security'", (staff_id,))
user_row = cur.fetchone()
if not user_row:
    print("No user linked to security staff found!")
    exit(0)
user_id = user_row[0]

print(f"Adding roster for Security Staff #{staff_id} for TODAY...")
cur.execute("""
    INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, attendance_status) 
    VALUES (%s, %s, CURRENT_DATE, 'morning', 'scheduled') 
    ON CONFLICT (society_id, security_id, roster_date) DO NOTHING
    RETURNING id
""", (society_id, staff_id))
res = cur.fetchone()
if res:
    roster_id = res[0]
else:
    cur.execute("SELECT id FROM security_roster WHERE society_id=%s AND security_id=%s AND roster_date=CURRENT_DATE", (society_id, staff_id))
    roster_id = cur.fetchone()[0]

print("Simulating a short 2-hour shift (time_in = 8 AM, time_out = 10 AM)...")
cur.execute("""
    INSERT INTO gate_access (society_id, entity_id, role, time_in, time_out) 
    VALUES (%s, %s, 'SEC', CURRENT_DATE + INTERVAL '8 hours', CURRENT_DATE + INTERVAL '10 hours')
""", (society_id, user_id))

print("Running fn_auto_generate_payables()...")
cur.execute("SELECT fn_auto_generate_payables(%s)", (society_id,))

cur.execute("SELECT amount, shift_fraction, description, status FROM payables WHERE roster_id = %s", (roster_id,))
payable = cur.fetchone()
if payable:
    print("\n✅ Successfully Generated Payable!")
    print(f"Amount: {payable[0]}")
    print(f"Shift Fraction: {payable[1]}")
    print(f"Description: {payable[2]}")
    print(f"Status: {payable[3]}")
else:
    print("\n❌ Failed to generate payable. Something went wrong.")
