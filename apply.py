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

cur.execute("ALTER TABLE payables ADD COLUMN IF NOT EXISTS shift_fraction NUMERIC(3, 2) DEFAULT 1.0;")
cur.execute("ALTER TABLE security_roster ADD COLUMN IF NOT EXISTS attendance_status VARCHAR(20) DEFAULT 'scheduled' CHECK (attendance_status IN ('scheduled', 'present', 'absent', 'leave_paid', 'leave_unpaid'));")
cur.execute(open("database/estatehub.sql").read())
print("Applied successfully.")
