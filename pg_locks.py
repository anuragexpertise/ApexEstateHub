import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
dsn = os.getenv("DATABASE_URL")
if not dsn:
    dsn = f"dbname={os.getenv('PGDATABASE', 'estatehub')} user={os.getenv('PGUSER', 'postgres')} password={os.getenv('PGPASSWORD', '')} host={os.getenv('PGHOST', 'localhost')} port={os.getenv('PGPORT', '5432')}"
conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT pid, pg_blocking_pids(pid) as blocked_by, state, query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();")
rows = cur.fetchall()
for r in rows:
    print(r)
