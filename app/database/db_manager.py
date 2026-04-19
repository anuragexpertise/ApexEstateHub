import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import traceback

load_dotenv()

class DatabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connection = None
        return cls._instance
    
    def get_connection_params(self):
        """Get database connection parameters from environment"""
        print("\n=== DATABASE PARAMETERS ===")
        
        pg_host = os.getenv('PGHOST', '').strip("'\"")
        pg_database = os.getenv('PGDATABASE', '').strip("'\"")
        pg_user = os.getenv('PGUSER', '').strip("'\"")
        pg_password = os.getenv('PGPASSWORD', '').strip("'\"")
        pg_sslmode = os.getenv('PGSSLMODE', 'require').strip("'\"")
        
        print(f"PGHOST: {pg_host}")
        print(f"PGDATABASE: {pg_database}")
        print(f"PGUSER: {pg_user}")
        print(f"PGPASSWORD: {'***' if pg_password else 'Not set'}")
        print(f"PGSSLMODE: {pg_sslmode}")
        
        if not all([pg_host, pg_database, pg_user, pg_password]):
            missing = []
            if not pg_host: missing.append("PGHOST")
            if not pg_database: missing.append("PGDATABASE")
            if not pg_user: missing.append("PGUSER")
            if not pg_password: missing.append("PGPASSWORD")
            raise Exception(f"Missing required environment variables: {', '.join(missing)}")
        
        return {
            'host': pg_host,
            'database': pg_database,
            'user': pg_user,
            'password': pg_password,
            'sslmode': pg_sslmode
        }
    
    def get_connection(self):
        """Get database connection using individual parameters"""
        try:
            if self.connection is None or self.connection.closed:
                params = self.get_connection_params()
                
                print(f"\nConnecting to NeonDB...")
                print(f"Host: {params['host']}")
                print(f"Database: {params['database']}")
                print(f"User: {params['user']}")
                
                self.connection = psycopg2.connect(
                    host=params['host'],
                    database=params['database'],
                    user=params['user'],
                    password=params['password'],
                    sslmode=params['sslmode'],
                    cursor_factory=RealDictCursor,
                    connect_timeout=30
                )
                print("✅ Database connection established successfully!")
            
            return self.connection
            
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            raise e
    
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False):
        """Execute a query and return results"""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                if fetch_one:
                    return cur.fetchone()
                if fetch_all:
                    return cur.fetchall()
                conn.commit()
                return cur.rowcount
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ Query error: {e}")
            raise e
    
    def test_connection(self):
        """Test database connection"""
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() as db_name, version() as version")
                result = cur.fetchone()
                print(f"✅ Connected to: {result.get('db_name') if result else 'Unknown'}")
                return True
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False

db = DatabaseManager()