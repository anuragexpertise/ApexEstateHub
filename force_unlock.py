import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
dsn = os.getenv("DATABASE_URL")
conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT pid, query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();")
for pid, query in cur.fetchall():
    print(f"Terminating {pid} - {query[:30]}")
    try:
        cur.execute(f"SELECT pg_terminate_backend({pid});")
    except Exception as e:
        print(f"Failed to terminate {pid}: {e}")
print("Done.")
