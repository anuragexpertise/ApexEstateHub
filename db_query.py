#!/usr/bin/env python3
"""
PostgreSQL Query Runner - Execute SQL without Aiven console
===========================================================

Usage:
  python3 db_query.py                      # Interactive mode
  python3 db_query.py --file queries.sql   # Run SQL file
  python3 db_query.py --command "SELECT..." # Run single query
  python3 db_query.py --test              # Test connection

Features:
  - Load credentials from .env
  - Interactive SQL shell with history
  - Execute SQL files
  - Pretty-print results
  - Export to CSV/JSON
  - Connection pooling
"""

import os
import sys
import argparse
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
import json
import csv
from typing import List, Tuple, Optional, Dict, Any
from io import StringIO
# import readline  # Enables command history

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

# Load .env file
ENV_FILE = Path.cwd() / ".env"
if not ENV_FILE.exists():
    # Try parent directory
    print("ENV_FILE exists")
    ENV_FILE = Path.cwd().parent / ".env"

load_dotenv(ENV_FILE)

# Database configuration from .env
DB_HOST = os.getenv("DATABASE_HOST") or os.getenv("PGHOST") or "localhost"
DB_PORT = int(os.getenv("DATABASE_PORT") or os.getenv("PGPORT") or "5432")
DB_NAME = os.getenv("DATABASE_NAME") or os.getenv("PGDATABASE") or "neondb"
DB_USER = os.getenv("DATABASE_USER") or os.getenv("PGUSER") or "neondb_owner"
DB_PASSWORD = os.getenv("DATABASE_PASSWORD") or os.getenv("PGPASSWORD") or ""

# SSL for Aiven (recommended)
DB_SSL_MODE = os.getenv("DATABASE_SSL_MODE") or "require"
DB_SSL_CERT = os.getenv("DATABASE_SSL_CERT")  # Path to ca.pem for Aiven
DB_SSL_KEY = os.getenv("DATABASE_SSL_KEY")
DB_SSL_ROOT = os.getenv("DATABASE_SSL_ROOT_CERT")

# Output configuration
OUTPUT_FORMAT = "table"  # table, json, csv
MAX_ROWS_DISPLAY = 100
HISTORY_FILE = Path.home() / ".db_query_history"

# ════════════════════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ════════════════════════════════════════════════════════════════════════════

class DatabaseConnection:
    """Manages PostgreSQL connection with Aiven SSL support."""
    
    def __init__(self, host, port, database, user, password, ssl_mode="require", 
                 ssl_cert=None, ssl_key=None, ssl_root=None):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.ssl_mode = ssl_mode
        self.ssl_cert = ssl_cert
        self.ssl_key = ssl_key
        self.ssl_root = ssl_root
        self.connection = None
        self.cursor = None
    
    def connect(self) -> bool:
        """Establish database connection."""
        try:
            conn_params = {
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "user": self.user,
                "password": self.password,
                "sslmode": self.ssl_mode,
            }
            
            # Add SSL certificates if provided (for Aiven)
            if self.ssl_root:
                conn_params["sslrootcert"] = self.ssl_root
            if self.ssl_cert:
                conn_params["sslcert"] = self.ssl_cert
            if self.ssl_key:
                conn_params["sslkey"] = self.ssl_key
            
            self.connection = psycopg2.connect(**conn_params)
            self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            print(f"✅ Connected to {self.user}@{self.host}:{self.port}/{self.database}")
            return True
            
        except psycopg2.Error as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        print("✅ Disconnected")
    
    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            self.cursor.execute("SELECT 1")
            print("✅ Connection test passed")
            return True
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False
    
    def execute(self, query: str) -> Tuple[List[Dict], int]:
        """Execute query and return results."""
        try:
            self.cursor.execute(query)
            
            # Check if query returns results (SELECT)
            if self.cursor.description:
                rows = self.cursor.fetchall()
                return [dict(row) for row in rows], len(rows)
            else:
                # INSERT/UPDATE/DELETE
                self.connection.commit()
                return [], self.cursor.rowcount
                
        except psycopg2.Error as e:
            self.connection.rollback()
            raise Exception(f"SQL Error: {e}")
    
    def execute_many(self, queries: List[str]) -> List[Tuple]:
        """Execute multiple queries."""
        results = []
        for query in queries:
            try:
                rows, count = self.execute(query)
                results.append((query, rows, count, None))
            except Exception as e:
                results.append((query, [], 0, str(e)))
        return results


# ════════════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTING
# ════════════════════════════════════════════════════════════════════════════

class OutputFormatter:
    """Format query results for display."""
    
    @staticmethod
    def format_table(rows: List[Dict], max_rows: int = 100) -> str:
        """Format as ASCII table."""
        if not rows:
            return "No rows returned"
        
        # Limit rows for display
        display_rows = rows[:max_rows]
        if len(rows) > max_rows:
            display_rows.append({"...": f"({len(rows) - max_rows} more rows)"})
        
        # Get column widths
        keys = list(display_rows[0].keys())
        widths = {k: max(len(str(k)), max(len(str(r.get(k, ""))) for r in display_rows)) for k in keys}
        
        # Build table
        lines = []
        
        # Header
        header = " | ".join(f"{k:^{widths[k]}}" for k in keys)
        lines.append(header)
        lines.append("─" * len(header))
        
        # Rows
        for row in display_rows:
            line = " | ".join(f"{str(row.get(k, '')):^{widths[k]}}" for k in keys)
            lines.append(line)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_json(rows: List[Dict]) -> str:
        """Format as JSON."""
        return json.dumps(rows, indent=2, default=str)
    
    @staticmethod
    def format_csv(rows: List[Dict]) -> str:
        """Format as CSV."""
        if not rows:
            return ""
        
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
    
    @staticmethod
    def format(rows: List[Dict], format_type: str = "table") -> str:
        """Format results based on type."""
        if format_type == "json":
            return OutputFormatter.format_json(rows)
        elif format_type == "csv":
            return OutputFormatter.format_csv(rows)
        else:  # table
            return OutputFormatter.format_table(rows)


# ════════════════════════════════════════════════════════════════════════════
# INTERACTIVE SHELL
# ════════════════════════════════════════════════════════════════════════════

class DatabaseShell:
    """Interactive SQL shell."""
    
    def __init__(self, db: DatabaseConnection, output_format: str = "table"):
        self.db = db
        self.output_format = output_format
        self.formatter = OutputFormatter()
#         self.load_history()
#
#     def load_history(self):
#         """Load command history from file."""
#         if HISTORY_FILE.exists():
#             with open(HISTORY_FILE, "r") as f:
#                 for line in f:
#                     readline.add_history(line.strip())
#
    def save_history(self, command: str):
        """Save command to history."""
        with open(HISTORY_FILE, "a") as f:
            f.write(f"{command}\n")
    
    def run(self):
        """Start interactive shell."""
        print("\n" + "="*70)
        print("PostgreSQL Query Shell")
        print("="*70)
        print(f"Host: {self.db.host}:{self.db.port}")
        print(f"Database: {self.db.database}")
        print(f"Output format: {self.output_format}")
        print("\nCommands:")
        print("  .help          - Show help")
        print("  .format json   - Switch to JSON output")
        print("  .format csv    - Switch to CSV output")
        print("  .format table  - Switch to table output")
        print("  .export FILE   - Export last results to file")
        print("  .tables        - List all tables")
        print("  .quit          - Exit shell")
        print("="*70 + "\n")
        
        last_results = []
        
        while True:
            try:
                query = input("sql> ").strip()
                
                if not query:
                    continue
                
                # Handle special commands
                if query.startswith("."):
                    self._handle_command(query)
                    continue
                
                # Handle multi-line queries (ending with ;)
                if not query.endswith(";"):
                    query += ";"
                
                # Execute query
                print("\n⏳ Executing...")
                rows, count = self.db.execute(query)
                last_results = rows
                
                # Display results
                if rows:
                    print(f"\n✅ {count} rows returned\n")
                    output = self.formatter.format(rows, self.output_format)
                    print(output)
                else:
                    print(f"\n✅ Query executed ({count} rows affected)")
                
                print()
                self.save_history(query)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted. Type .quit to exit.")
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    def _handle_command(self, cmd: str):
        """Handle special commands."""
        parts = cmd.split()
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        if command == ".help":
            print("""
Commands:
  .help              - Show this help
  .tables            - List all tables in database
  .format [type]     - Switch output format (table/json/csv)
  .export [file]     - Export last results to file
  .quit              - Exit shell
            """)
        
        elif command == ".tables":
            try:
                rows, _ = self.db.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                if rows:
                    print("\nTables in database:")
                    for row in rows:
                        print(f"  - {row['table_name']}")
                else:
                    print("No tables found")
            except Exception as e:
                print(f"Error: {e}")
        
        elif command == ".format" and args:
            self.output_format = args[0].lower()
            print(f"Output format set to: {self.output_format}")
        
        elif command == ".export" and args:
            # Would implement file export here
            print("Export feature coming soon")
        
        elif command == ".quit":
            print("Goodbye!")
            sys.exit(0)
        
        else:
            print(f"Unknown command: {command}. Type .help for help.")


# ════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════════════════════

def print_config():
    """Print current database configuration."""
    print("\n" + "="*70)
    print("Database Configuration")
    print("="*70)
    print(f"Host: {DB_HOST}")
    print(f"Port: {DB_PORT}")
    print(f"Database: {DB_NAME}")
    print(f"User: {DB_USER}")
    print(f"SSL Mode: {DB_SSL_MODE}")
    if DB_SSL_ROOT:
        print(f"SSL CA: {DB_SSL_ROOT}")
    print(f".env file: {ENV_FILE}")
    print("="*70 + "\n")


def run_sql_file(db: DatabaseConnection, filepath: str):
    """Execute SQL from file."""
    try:
        with open(filepath, "r") as f:
            queries = f.read().split(";")
        
        print(f"\n📄 Running {len(queries)} queries from {filepath}\n")
        
        results = db.execute_many([q.strip() for q in queries if q.strip()])
        
        for i, (query, rows, count, error) in enumerate(results, 1):
            if error:
                print(f"❌ Query {i}: {error}")
                print(f"   {query[:80]}...")
            else:
                print(f"✅ Query {i}: {count} rows")
                if rows:
                    print(f"   {OutputFormatter.format_table(rows, max_rows=3)[:100]}...")
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")


def run_single_command(db: DatabaseConnection, command: str, output_format: str = "table"):
    """Execute single SQL command."""
    try:
        if not command.endswith(";"):
            command += ";"
        
        print(f"\n⏳ Executing...\n")
        rows, count = db.execute(command)
        
        if rows:
            print(f"✅ {count} rows returned\n")
            formatter = OutputFormatter()
            output = formatter.format(rows, output_format)
            print(output)
        else:
            print(f"✅ Query executed ({count} rows affected)")
        
    except Exception as e:
        print(f"❌ Error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="PostgreSQL Query Runner - Execute SQL without Aiven console"
    )
    parser.add_argument(
        "--command", "-c",
        help="Execute single SQL command"
    )
    parser.add_argument(
        "--file", "-f",
        help="Execute SQL file"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test database connection"
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)"
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show database configuration"
    )
    
    args = parser.parse_args()
    
    # Create database connection
    db = DatabaseConnection(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        ssl_mode=DB_SSL_MODE,
        ssl_cert=DB_SSL_CERT,
        ssl_key=DB_SSL_KEY,
        ssl_root=DB_SSL_ROOT
    )
    
    # Show config if requested
    if args.config:
        print_config()
    
    # Connect to database
    if not db.connect():
        sys.exit(1)
    
    try:
        # Test connection
        if args.test:
            db.test_connection()
            return
        
        # Run single command
        if args.command:
            run_single_command(db, args.command, args.format)
            return
        
        # Run SQL file
        if args.file:
            run_sql_file(db, args.file)
            return
        
        # Interactive shell
        shell = DatabaseShell(db, args.format)
        shell.run()
    
    finally:
        db.disconnect()


if __name__ == "__main__":
    main()
