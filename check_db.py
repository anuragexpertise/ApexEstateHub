import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
dsn = os.getenv("DATABASE_URL")
conn = psycopg2.connect(dsn)
cur = conn.cursor()
try:
    cur.execute("SELECT duty_hrs FROM societies LIMIT 1;")
    print("duty_hrs exists")
except Exception as e:
    print("Error:", e)
