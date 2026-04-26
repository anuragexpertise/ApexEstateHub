#!/usr/bin/env python
"""Test database connection with individual NeonDB parameters"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("TESTING NEONDB CONNECTION")
print("=" * 60)

# Check environment variables
print("\nChecking environment variables:")
pg_host = os.getenv('PGHOST', '').strip("'\"")
pg_db = os.getenv('PGDATABASE', '').strip("'\"")
pg_user = os.getenv('PGUSER', '').strip("'\"")
pg_pass = os.getenv('PGPASSWORD', '').strip("'\"")
pg_ssl = os.getenv('PGSSLMODE', 'require').strip("'\"")
pg_binding = os.getenv('PGCHANNELBINDING', 'require').strip("'\"")

print(f"PGHOST: {pg_host}")
print(f"PGDATABASE: {pg_db}")
print(f"PGUSER: {pg_user}")
print(f"PGPASSWORD: {'***' if pg_pass else 'NOT SET'}")
print(f"PGSSLMODE: {pg_ssl}")
print(f"PGCHANNELBINDING: {pg_binding}")

if not all([pg_host, pg_db, pg_user, pg_pass]):
    print("\n❌ Missing required environment variables!")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    print("\nAttempting to connect to NeonDB...")
    
    conn = psycopg2.connect(
        host=pg_host,
        database=pg_db,
        user=pg_user,
        password=pg_pass,
        sslmode=pg_ssl,
        connect_timeout=30
    )
    
    print("✅ Connection successful!")
    
    # Test query
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT current_database() as db_name, version() as version")
        result = cur.fetchone()
        print(f"\nDatabase: {result.get('db_name')}")
        print(f"Version: {result.get('version')[:80]}...")
    
    

    #test query
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, email , password_hash FROM users")
        result = cur.fetchall()
        print(f"\nUsers table query result: {result}")

    conn.close()
    print("\n✅ Database is working properly!")
    
except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    sys.exit(1)