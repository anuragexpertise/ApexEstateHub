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

sql = """
CREATE OR REPLACE FUNCTION trg_payable_update_amount() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.role = 'security' THEN
        NEW.amount := (SELECT salary_per_shift FROM security_staff WHERE id = NEW.entity_id) * NEW.shift_fraction;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS payable_update_amount ON payables;
CREATE TRIGGER payable_update_amount BEFORE UPDATE ON payables
FOR EACH ROW EXECUTE FUNCTION trg_payable_update_amount();
"""
cur.execute(sql)
print("Trigger applied successfully.")
