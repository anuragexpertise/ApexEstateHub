#!/usr/bin/env python3
# database/migrate.py
"""
ApexEstateHub Database Migration Script
Handles: Schema creation, auth patches, master admin, society setup, dummy data, accounts

Usage:
    python3 database/migrate.py                    # Interactive mode
    python3 database/migrate.py --force            # Force re-run schema
    python3 database/migrate.py --master-only      # Only create master admin
    python3 database/migrate.py --society          # Create society interactively
    python3 database/migrate.py --dummy            # Create dummy data
    python3 database/migrate.py --accounts         # Seed chart of accounts
    python3 database/migrate.py --all              # Create everything
    python3 database/migrate.py --skip-seed        # Skip all seeding
"""
import os, sys, re, argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(override=False)


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_conn():
    """Get psycopg2 connection for raw SQL execution."""
    import psycopg2, psycopg2.extras

    raw = os.getenv('DATABASE_URL', '').strip()
    if raw:
        dsn = raw.replace('postgres://', 'postgresql://', 1)
    else:
        host   = os.getenv('PGHOST',     '').strip().strip("'\"")
        port   = os.getenv('PGPORT',     '5432').strip().strip("'\"") or '5432'
        dbname = os.getenv('PGDATABASE', '').strip().strip("'\"")
        user   = os.getenv('PGUSER',     '').strip().strip("'\"")
        pw     = os.getenv('PGPASSWORD', '').strip().strip("'\"")
        ssl    = os.getenv('PGSSLMODE',  'require').strip().strip("'\"")

        if not all([host, dbname, user, pw]):
            print("❌  Missing: PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD")
            sys.exit(1)
        try:
            port = str(int(port))
        except ValueError:
            port = '5432'

        dsn = f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"

    try:
        conn = psycopg2.connect(dsn,
                                cursor_factory=psycopg2.extras.RealDictCursor,
                                connect_timeout=15)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌  Cannot connect to database: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# SQL PARSER
# ══════════════════════════════════════════════════════════════════════════════

def _strip_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments."""
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    sql = re.sub(r'--[^\n]*', '', sql)
    return sql


def split_statements(raw_sql: str) -> list:
    """Split SQL on semicolons, skip empty/comment-only statements."""
    stmts = []
    for raw in raw_sql.split(';'):
        cleaned = _strip_comments(raw).strip()
        if cleaned:
            stmts.append(raw.strip())
    return stmts


# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def already_migrated(conn) -> bool:
    """Check if tables exist."""
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'societies'
        )
    """)
    exists = cur.fetchone()['exists']
    cur.close()
    return exists


def run_migration(conn, sql_path: str, verbose: bool = True) -> tuple:
    """Execute SQL file against database."""
    raw_sql  = open(sql_path, encoding='utf-8').read()
    stmts    = split_statements(raw_sql)
    ok = err = 0

    cur = conn.cursor()
    for stmt in stmts:
        try:
            cur.execute(stmt)
            conn.commit()
            ok += 1
        except Exception as e:
            conn.rollback()
            if verbose:
                snippet = _strip_comments(stmt)[:80].replace('\n', ' ').strip()
                print(f"  ⚠  Skipped ({e.__class__.__name__}): {snippet}…")
            err += 1
    cur.close()
    return ok, err


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Ask yes/no question with default."""
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix}: ").strip().lower()
        if not answer:
            return default
        return answer in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def ask_input(prompt: str, default: str = "") -> str:
    """Ask for text input with default."""
    try:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
            return result if result else default
        else:
            return input(f"{prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default


# ══════════════════════════════════════════════════════════════════════════════
# SEEDING FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def create_master_admin(conn) -> bool:
    """Create master admin if not exists."""
    from werkzeug.security import generate_password_hash
    
    MASTER_EMAIL = 'master@estatehub.com'
    MASTER_PASSWORD = 'Master@2024'
    
    cur = conn.cursor()
    
    # Check if any users exist
    cur.execute("SELECT COUNT(*) as c FROM users")
    count = cur.fetchone()['c']
    
    if count > 0:
        print(f"  ✓ Users exist ({count}) — skipping master admin creation")
        cur.close()
        return False
    
    # Create master admin
    pw_hash = generate_password_hash(MASTER_PASSWORD)
    
    try:
        cur.execute(
            """
            INSERT INTO users (email, password_hash, role, login_method, is_master_admin)
            VALUES (%s, %s, 'admin', 'password', TRUE)
            ON CONFLICT (email) DO UPDATE SET is_master_admin = TRUE
            """,
            (MASTER_EMAIL, pw_hash)
        )
        conn.commit()
        cur.close()
        
        print()
        print("  ┌─────────────────────────────────────────────┐")
        print("  │       ✓ Master Admin Created                │")
        print("  ├─────────────────────────────────────────────┤")
        print(f"  │  Email    : {MASTER_EMAIL:<29}│")
        print(f"  │  Password : {MASTER_PASSWORD:<29}│")
        print("  │  ⚠  Change this password after login!       │")
        print("  └─────────────────────────────────────────────┘")
        print()
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"  ❌ Failed to create master admin: {e}")
        cur.close()
        return False


def create_society_interactive(conn) -> int:
    """Create society interactively. Returns society_id or 0."""
    print()
    print("=" * 60)
    print("  CREATE NEW SOCIETY")
    print("=" * 60)
    print()
    
    name = ask_input("Society Name", "Sunrise Residency")
    if not name:
        print("  ❌ Society name is required")
        return 0
    
    email = ask_input("Email", f"admin@{name.lower().replace(' ', '')}.com")
    phone = ask_input("Phone", "9876543210")
    address = ask_input("Address", "12, MG Road, Sector 5, Agra, UP - 250001")
    secretary_name = ask_input("Secretary Name", "Ramesh Kumar")
    secretary_phone = ask_input("Secretary Phone", "9876543211")
    
    plan = "Free"
    plan_validity = str(date(2025, 12, 31))
    arrear_start_date = str(date(2024, 4, 1))
    
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            INSERT INTO societies 
                (name, email, phone, address, secretary_name, secretary_phone,
                 plan, plan_validity, arrear_start_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, email, phone, address, secretary_name, secretary_phone,
             plan, plan_validity, arrear_start_date)
        )
        result = cur.fetchone()
        conn.commit()
        society_id = result['id']
        cur.close()
        
        print()
        print(f"  ✓ Society created (ID: {society_id}): {name}")
        print()
        return society_id
        
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"  ❌ Failed to create society: {e}")
        return 0


def create_society_users(conn, society_id: int) -> bool:
    """Create admin, owner, vendor, security users for society."""
    from werkzeug.security import generate_password_hash
    
    # Get society details
    cur = conn.cursor()
    cur.execute("SELECT name, email FROM societies WHERE id = %s", (society_id,))
    society = cur.fetchone()
    
    if not society:
        cur.close()
        return False
    
    society_name = society['name']
    society_email = society['email']
    base_domain = society_email.split('@')[1] if '@' in society_email else 'example.com'
    
    users = [
        {
            'role': 'admin',
            'email': society_email,
            'password': 'Admin@2024',
            'name': 'Society Admin',
            'flat': None,
        },
        {
            'role': 'apartment',
            'email': f'owner@{base_domain}',
            'password': 'Owner@2024',
            'name': 'Rajesh Sharma',
            'flat': 'A-101',
            'area': 1200,
            'mobile': '9811111111',
        },
        {
            'role': 'vendor',
            'email': f'vendor@{base_domain}',
            'password': 'Vendor@2024',
            'name': 'Plumbing Services',
            'flat': None,
        },
        {
            'role': 'security',
            'email': f'security@{base_domain}',
            'password': 'Security@2024',
            'name': 'Guard Ramu',
            'flat': None,
        },
    ]
    
    print(f"  Creating users for {society_name}...")
    
    for u in users:
        pw_hash = generate_password_hash(u['password'])
        
        try:
            # Create user
            cur.execute(
                """
                INSERT INTO users (society_id, email, password_hash, role, login_method)
                VALUES (%s, %s, %s, %s, 'password')
                ON CONFLICT (email) DO NOTHING
                RETURNING id
                """,
                (society_id, u['email'], pw_hash, u['role'])
            )
            
            user_result = cur.fetchone()
            if not user_result:
                print(f"    ⚠  {u['role']:<10} already exists: {u['email']}")
                continue
            
            user_id = user_result['id']
            
            # Create apartment for owner
            if u['role'] == 'apartment' and u.get('flat'):
                cur.execute(
                    """
                    INSERT INTO apartments
                        (society_id, flat_number, owner_name, mobile, apartment_size, active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (society_id, flat_number) DO NOTHING
                    RETURNING id
                    """,
                    (society_id, u['flat'], u['name'], u.get('mobile', ''), u.get('area', 1000))
                )
                apt_result = cur.fetchone()
                if apt_result:
                    cur.execute(
                        "UPDATE users SET linked_id = %s WHERE id = %s",
                        (apt_result['id'], user_id)
                    )
            
            conn.commit()
            print(f"    ✓ {u['role']:<10} → {u['email']:<30} / {u['password']}")
            
        except Exception as e:
            conn.rollback()
            print(f"    ❌ {u['role']} failed: {e}")
    
    cur.close()
    
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print(f"  │  Society Users Created for: {society_name[:28]:<28} │")
    print("  ├─────────────────────────────────────────────────────────┤")
    print(f"  │  Admin  : {society_email:<45} │")
    print(f"  │  Owner  : owner@{base_domain:<42} │")
    print(f"  │  Vendor : vendor@{base_domain:<41} │")
    print(f"  │  Guard  : security@{base_domain:<39} │")
    print("  │  All passwords: <Role>@2024                             │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()
    
    return True


def seed_chart_of_accounts(conn, society_id: int) -> bool:
    """Seed standard chart of accounts for society."""
    
    print(f"  Seeding chart of accounts for society {society_id}...")
    
    # Check if accounts already exist
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM accounts WHERE society_id = %s", (society_id,))
    count = cur.fetchone()['c']
    
    if count > 0:
        print(f"    ✓ Accounts already exist ({count}) — skipping")
        cur.close()
        return True
    
    # Standard chart of accounts
    accounts = [
        # Root account
        (1, 'Root', None, 'Balance Sheet', 1, 'Dr', False, 'Dr', 0, 0),
        
        # Assets (Dr)
        (1000, 'Cash in Hand', 'Assets', 'Current Assets', 1, 'Dr', True, 'Dr', 50000, 0),
        (1001, 'Bank Account - SBI', 'Assets', 'Current Assets', 1, 'Dr', True, 'Dr', 100000, 0),
        (1002, 'Bank Account - HDFC', 'Assets', 'Current Assets', 1, 'Dr', True, 'Dr', 75000, 0),
        (1100, 'Maintenance Receivable', 'Assets', 'Current Assets', 1, 'Dr', False, 'Dr', 0, 0),
        (1200, 'Fixed Deposits', 'Assets', 'Investments', 1, 'Dr', False, 'Dr', 0, 0),
        (1300, 'Furniture & Fixtures', 'Assets', 'Fixed Assets', 1, 'Dr', False, 'Dr', 0, 10),
        (1301, 'Office Equipment', 'Assets', 'Fixed Assets', 1, 'Dr', False, 'Dr', 0, 15),
        (1302, 'Security Systems', 'Assets', 'Fixed Assets', 1, 'Dr', False, 'Dr', 0, 20),
        
        # Liabilities (Cr)
        (2000, 'Maintenance Advance', 'Liab', 'Current Liabilities', 1, 'Cr', False, 'Cr', 0, 0),
        (2001, 'Security Deposits', 'Liab', 'Current Liabilities', 1, 'Cr', False, 'Cr', 0, 0),
        (2100, 'Vendor Payables', 'Liab', 'Current Liabilities', 1, 'Cr', False, 'Cr', 0, 0),
        (2200, 'Staff Salary Payable', 'Liab', 'Current Liabilities', 1, 'Cr', False, 'Cr', 0, 0),
        
        # Income (Cr)
        (3000, 'Maintenance Charges', 'Income', 'Operating Income', 1, 'Cr', False, 'Cr', 0, 0),
        (3001, 'Parking Charges', 'Income', 'Operating Income', 1, 'Cr', False, 'Cr', 0, 0),
        (3002, 'Late Payment Fines', 'Income', 'Other Income', 1, 'Cr', False, 'Cr', 0, 0),
        (3003, 'Vendor Pass Fees', 'Income', 'Other Income', 1, 'Cr', False, 'Cr', 0, 0),
        (3100, 'Interest Income', 'Income', 'Other Income', 1, 'Cr', False, 'Cr', 0, 0),
        (3200, 'Event Sponsorship', 'Income', 'Other Income', 1, 'Cr', False, 'Cr', 0, 0),
        
        # Expenses (Dr)
        (4000, 'Electricity Charges', 'Expense', 'Utilities', 1, 'Dr', False, 'Dr', 0, 0),
        (4001, 'Water Charges', 'Expense', 'Utilities', 1, 'Dr', False, 'Dr', 0, 0),
        (4002, 'Internet & Cable', 'Expense', 'Utilities', 1, 'Dr', False, 'Dr', 0, 0),
        (4100, 'Security Staff Salary', 'Expense', 'Staff Costs', 1, 'Dr', False, 'Dr', 0, 0),
        (4101, 'Housekeeping Salary', 'Expense', 'Staff Costs', 1, 'Dr', False, 'Dr', 0, 0),
        (4102, 'Staff Welfare', 'Expense', 'Staff Costs', 1, 'Dr', False, 'Dr', 0, 0),
        (4200, 'Lift Maintenance', 'Expense', 'Maintenance', 1, 'Dr', False, 'Dr', 0, 0),
        (4201, 'Generator Maintenance', 'Expense', 'Maintenance', 1, 'Dr', False, 'Dr', 0, 0),
        (4202, 'Plumbing & Repairs', 'Expense', 'Maintenance', 1, 'Dr', False, 'Dr', 0, 0),
        (4203, 'Electrical Repairs', 'Expense', 'Maintenance', 1, 'Dr', False, 'Dr', 0, 0),
        (4204, 'Painting & Whitewash', 'Expense', 'Maintenance', 1, 'Dr', False, 'Dr', 0, 0),
        (4300, 'Cleaning Supplies', 'Expense', 'Consumables', 1, 'Dr', False, 'Dr', 0, 0),
        (4301, 'Garden & Landscaping', 'Expense', 'Consumables', 1, 'Dr', False, 'Dr', 0, 0),
        (4400, 'Insurance Premium', 'Expense', 'Administrative', 1, 'Dr', False, 'Dr', 0, 0),
        (4401, 'Legal & Professional', 'Expense', 'Administrative', 1, 'Dr', False, 'Dr', 0, 0),
        (4402, 'Audit Fees', 'Expense', 'Administrative', 1, 'Dr', False, 'Dr', 0, 0),
        (4403, 'Office Supplies', 'Expense', 'Administrative', 1, 'Dr', False, 'Dr', 0, 0),
        (4500, 'Event Expenses', 'Expense', 'Events', 1, 'Dr', False, 'Dr', 0, 0),
        (4600, 'Bank Charges', 'Expense', 'Financial', 1, 'Dr', False, 'Dr', 0, 0),
        (4601, 'Payment Gateway Fees', 'Expense', 'Financial', 1, 'Dr', False, 'Dr', 0, 0),
        (4700, 'Depreciation', 'Expense', 'Non-Cash', 1, 'Dr', False, 'Dr', 0, 0),
    ]
    
    created = 0
    for acc in accounts:
        try:
            cur.execute(
                """
                INSERT INTO accounts 
                    (society_id, name, tab_name, header, hierarchy,
                     drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (society_id, id) DO NOTHING
                """,
                (society_id,) + acc
            )
            conn.commit()
            created += 1
        except Exception as e:
            conn.rollback()
            print(f"    ⚠  Failed to create account {acc[0]}: {e}")
    
    cur.close()
    print(f"    ✓ Created {created} accounts")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='ApexEstateHub Database Migration & Seeding',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--force', action='store_true',
                        help='Force re-run schema even if tables exist')
    parser.add_argument('--sql', default=None,
                        help='Custom SQL file path')
    parser.add_argument('--master-only', action='store_true',
                        help='Only create master admin')
    parser.add_argument('--society', action='store_true',
                        help='Create society interactively')
    parser.add_argument('--dummy', action='store_true',
                        help='Create dummy society + users')
    parser.add_argument('--accounts', action='store_true',
                        help='Seed chart of accounts')
    parser.add_argument('--all', action='store_true',
                        help='Create master admin + dummy society + users + accounts')
    parser.add_argument('--skip-seed', action='store_true',
                        help='Skip all seeding (schema only)')
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_path = args.sql or os.path.join(project_root, 'dashestatehub.sql')

    if not os.path.isfile(sql_path):
        print(f"❌  SQL file not found: {sql_path}")
        sys.exit(1)

    print()
    print("=" * 70)
    print("  ApexEstateHub — Database Migration & Seeding")
    print("=" * 70)
    print(f"  SQL file : {sql_path}")
    print(f"  Host     : {os.getenv('PGHOST','?')}:{os.getenv('PGPORT','?')}")
    print(f"  Database : {os.getenv('PGDATABASE','?')}")
    print("=" * 70)
    print()

    conn = get_conn()
    print("✓ Connected to PostgreSQL")
    print()

    # ──────────────────────────────────────────────────────────────────────────
    # PHASE 1: Schema Migration
    # ──────────────────────────────────────────────────────────────────────────
    
    tables_exist = already_migrated(conn)
    
    if tables_exist and not args.force:
        print("✓ Tables already exist — running additive patches only")
        print("  (Use --force to re-run full schema)")
        ok, err = run_migration(conn, sql_path, verbose=False)
        print(f"  ✓ {ok} statements OK", end="")
        if err:
            print(f"  ({err} skipped)")
        else:
            print()
    else:
        if args.force:
            print("⚠  FORCE MODE: Re-running full schema")
        print("  Parsing and running SQL statements...")
        ok, err = run_migration(conn, sql_path)
        print(f"  ✓ {ok} statements OK")
        if err:
            print(f"  ⚠  {err} skipped (usually safe)")
    
    print()
    
    # ──────────────────────────────────────────────────────────────────────────
    # PHASE 2: Seeding (if not skipped)
    # ──────────────────────────────────────────────────────────────────────────
    
    if args.skip_seed:
        print("✓ Seeding skipped (--skip-seed)")
        conn.close()
        sys.exit(0)
    
    print("=" * 70)
    print("  SEEDING PHASE")
    print("=" * 70)
    print()
    
    # Check what exists
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    user_count = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM societies")
    society_count = cur.fetchone()['c']
    cur.close()
    
    # Determine what to create
    create_master = False
    create_society_flag = False
    create_dummy_flag = False
    create_accounts_flag = False
    
    if args.all:
        # Create everything
        create_master = True
        create_dummy_flag = True
        create_accounts_flag = True
        
    elif args.master_only:
        create_master = True
        
    elif args.society:
        create_society_flag = True
        
    elif args.dummy:
        create_dummy_flag = True
        
    elif args.accounts:
        create_accounts_flag = True
        
    else:
        # Interactive mode
        print("  Current Status:")
        print(f"    Users      : {user_count}")
        print(f"    Societies  : {society_count}")
        print()
        
        if user_count == 0:
            create_master = ask_yes_no("  Create master admin?", True)
        
        if society_count == 0:
            create_dummy_flag = ask_yes_no("  Create demo society with dummy data?", True)
            if not create_dummy_flag:
                create_society_flag = ask_yes_no("  Create custom society?", False)
        
        if create_society_flag or create_dummy_flag:
            create_accounts_flag = ask_yes_no("  Seed chart of accounts?", True)
    
    print()
    
    # ──────────────────────────────────────────────────────────────────────────
    # Execute seeding
    # ──────────────────────────────────────────────────────────────────────────
    
    society_id = None
    
    # 1. Master Admin
    if create_master:
        print("─" * 70)
        print("  CREATING MASTER ADMIN")
        print("─" * 70)
        create_master_admin(conn)
    
    # 2. Society
    if create_dummy_flag:
        print("─" * 70)
        print("  CREATING DUMMY SOCIETY")
        print("─" * 70)
        
        # Use predefined dummy data
        from werkzeug.security import generate_password_hash
        
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO societies 
                    (name, email, phone, address, secretary_name, secretary_phone,
                     plan, plan_validity, arrear_start_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                ('Sunrise Residency', 'admin@sunriseresidency.com', '9876543210',
                 '12, MG Road, Sector 5, Agra, UP - 250001', 'Ramesh Kumar', '9876543211',
                 'Free', '2025-12-31', '2024-04-01')
            )
            result = cur.fetchone()
            conn.commit()
            society_id = result['id']
            print(f"  ✓ Dummy society created (ID: {society_id}): Sunrise Residency")
            print()
            
            # Create users
            create_society_users(conn, society_id)
            
        except Exception as e:
            conn.rollback()
            print(f"  ❌ Failed to create dummy society: {e}")
        
        cur.close()
    
    elif create_society_flag:
        society_id = create_society_interactive(conn)
        if society_id:
            if ask_yes_no("  Create users for this society?", True):
                create_society_users(conn, society_id)
    
    # 3. Chart of Accounts
    if create_accounts_flag:
        print("─" * 70)
        print("  SEEDING CHART OF ACCOUNTS")
        print("─" * 70)
        
        if not society_id:
            # Find first society
            cur = conn.cursor()
            cur.execute("SELECT id, name FROM societies ORDER BY id LIMIT 1")
            result = cur.fetchone()
            cur.close()
            
            if result:
                society_id = result['id']
                print(f"  Using society: {result['name']} (ID: {society_id})")
            else:
                print("  ⚠  No society found. Create a society first.")
                society_id = None
        
        if society_id:
            seed_chart_of_accounts(conn, society_id)
        print()
    
    # ──────────────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────────────
    
    print()
    print("=" * 70)
    print("  MIGRATION COMPLETE")
    print("=" * 70)
    
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    final_users = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM societies")
    final_societies = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM accounts")
    final_accounts = cur.fetchone()['c']
    cur.close()
    
    print(f"  Final Counts:")
    print(f"    Users      : {final_users}")
    print(f"    Societies  : {final_societies}")
    print(f"    Accounts   : {final_accounts}")
    print()
    
    if final_users > 0:
        print("  ✓ You can now login to the application")
        print("  ✓ URL: http://127.0.0.1:8050")
        if user_count == 0 and create_master:
            print("  ✓ Master Admin: master@estatehub.com / Master@2024")
    
    print("=" * 70)
    print()
    
    conn.close()


if __name__ == '__main__':
    main()
