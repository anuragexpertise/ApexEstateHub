#!/usr/bin/env python3
"""
COMPREHENSIVE DEBUG SCRIPT - Societies Dropdown Not Working
============================================================

Run this from your project root:
    python3 debug_societies_dropdown_FULL.py

This script will:
1. Test database connectivity
2. Verify societies exist with correct plan values
3. Test the exact load_societies SQL query
4. Check callback registration
5. Verify HTML component structure
6. Check for Python syntax errors
7. Provide detailed remediation steps

Author: Claude
Date: 2026-05-31
"""

import os
import sys
from pathlib import Path
from datetime import date

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent
DEBUG_MODE = True

# ════════════════════════════════════════════════════════════════════════════
# COLORS FOR OUTPUT
# ════════════════════════════════════════════════════════════════════════════

class Colors:
    OK = '\033[92m'      # Green
    ERROR = '\033[91m'   # Red
    WARNING = '\033[93m' # Yellow
    INFO = '\033[94m'    # Blue
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title):
    print(f"\n{Colors.BOLD}{Colors.INFO}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.INFO}{title:^80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.INFO}{'='*80}{Colors.RESET}\n")


def print_section(title):
    print(f"\n{Colors.BOLD}[{title}]{Colors.RESET}")
    print("-" * 80)


def print_ok(msg):
    print(f"{Colors.OK}✅ {msg}{Colors.RESET}")


def print_error(msg):
    print(f"{Colors.ERROR}❌ {msg}{Colors.RESET}")


def print_warning(msg):
    print(f"{Colors.WARNING}⚠️  {msg}{Colors.RESET}")


def print_info(msg):
    print(f"{Colors.INFO}ℹ️  {msg}{Colors.RESET}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN DIAGNOSTIC
# ════════════════════════════════════════════════════════════════════════════

def main():
    print_header("SOCIETIES DROPDOWN DEBUG - COMPREHENSIVE DIAGNOSTIC")
    
    # Add project root to path
    sys.path.insert(0, str(PROJECT_ROOT))
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
    
    print_info(f"Project root: {PROJECT_ROOT}")
    print_info(f"Python version: {sys.version.split()[0]}")
    
    # ════════════════════════════════════════════════════════════════════════
    # 1. DATABASE CONNECTION
    # ════════════════════════════════════════════════════════════════════════
    
    print_section("1. DATABASE CONNECTION TEST")
    
    try:
        from database.db_manager import db
        
        test_result = db._execute(
            "SELECT NOW() AS current_time, version() AS version",
            fetch_one=True
        )
        
        if test_result:
            print_ok("Database connection successful")
            print(f"   Server time: {test_result.get('current_time')}")
            version = test_result.get('version', 'unknown')
            print(f"   PostgreSQL: {version.split(',')[0]}")
        else:
            print_error("Database connection test returned no result")
            return False
            
    except Exception as e:
        print_error(f"Cannot connect to database: {e}")
        import traceback
        traceback.print_exc()
        print()
        print_info("Troubleshooting:")
        print("   1. Check .env file has DATABASE_URL or PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD")
        print("   2. Verify Aiven PostgreSQL is accessible from your network")
        print("   3. Check firewall rules")
        print("   4. Verify .env DATABASE_SSL_MODE is 'require'")
        return False
    
    # ════════════════════════════════════════════════════════════════════════
    # 2. SOCIETIES TABLE
    # ════════════════════════════════════════════════════════════════════════
    
    print_section("2. SOCIETIES TABLE INSPECTION")
    
    try:
        # Check table exists
        table_check = db._execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'societies'
            ) AS exists
            """,
            fetch_one=True
        )
        
        if not table_check or not table_check.get('exists'):
            print_error("SOCIETIES TABLE DOES NOT EXIST!")
            print()
            print("Fix:")
            print("   python3 database/migrate.py --force")
            return False
        
        print_ok("Societies table exists")
        
        # Count rows
        count = db._execute(
            "SELECT COUNT(*) AS c FROM societies",
            fetch_one=True
        )
        
        rows_count = count.get('c', 0) if count else 0
        print_ok(f"Total societies in database: {rows_count}")
        
        if rows_count == 0:
            print_error("NO SOCIETIES FOUND IN DATABASE!")
            print()
            print("Fix:")
            print("   python3 database/seed.py")
            return False
        
        # Show all societies
        all_societies = db._execute(
            "SELECT id, name, plan, plan_validity FROM societies ORDER BY name",
            fetch_all=True
        )
        
        print("\n   Societies in database:")
        for s in all_societies:
            print(f"   • {s['name']:<35} plan={s['plan']:<15} expires={s['plan_validity']}")
        
        return all_societies  # Return for later use
        
    except Exception as e:
        print_error(f"Error checking societies: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query(all_societies):
    """Test the exact load_societies query"""
    
    print_section("3. LOAD_SOCIETIES QUERY TEST")
    
    try:
        from database.db_manager import db
        
        query = """
        SELECT id, name, plan, plan_validity 
        FROM societies 
        WHERE 
            plan = 'Free' 
            OR (plan IN ('9Apts', '99Apts', '999Apts', 'Unlimited') 
                AND plan_validity >= CURRENT_DATE)
        ORDER BY name ASC
        """
        
        filtered = db._execute(query, fetch_all=True)
        
        print_ok("Query executed successfully")
        print(f"   Societies matching dropdown filter: {len(filtered)}")
        
        if not filtered:
            print_error("NO SOCIETIES MATCH THE FILTER!")
            print()
            print("   Expected criteria:")
            print("   • plan = 'Free'")
            print("   • OR plan IN ('9Apts', '99Apts', '999Apts', 'Unlimited')")
            print("      AND plan_validity >= TODAY")
            print(f"\n   Today's date: {date.today()}")
            print("\n   Analysis of each society:")
            
            for s in all_societies:
                plan_match = s['plan'] == 'Free'
                plan_str = s['plan']
                valid_date = s['plan_validity']
                
                if isinstance(valid_date, date):
                    date_ok = valid_date >= date.today()
                else:
                    date_ok = str(valid_date) >= str(date.today())
                
                paid_plan = plan_str in ['9Apts', '99Apts', '999Apts', 'Unlimited']
                
                if plan_match:
                    print_ok(f"   {s['name']:<35} - matches Free plan")
                elif paid_plan and date_ok:
                    print_ok(f"   {s['name']:<35} - matches paid plan + valid date")
                else:
                    reasons = []
                    if not plan_match and plan_str != 'Free':
                        reasons.append(f"plan='{plan_str}' (not 'Free' or 9Apts|99Apts|999Apts|Unlimited)")
                    if paid_plan and not date_ok:
                        reasons.append(f"plan expired ({valid_date})")
                    print_warning(f"   {s['name']:<35} - {', '.join(reasons)}")
        else:
            print_ok("Societies found matching filter:")
            for s in filtered:
                print(f"   ✓ {s['name']:<35} (plan={s['plan']})")
        
        return len(filtered) > 0
        
    except Exception as e:
        print_error(f"Query execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_callbacks():
    """Check if callbacks are registered"""
    
    print_section("4. CALLBACK REGISTRATION")
    
    issues = []
    
    try:
        # Test shell_callbacks import
        try:
            from app.dash_apps.callbacks import shell_callbacks
            print_ok("shell_callbacks module imported successfully")
        except ImportError as e:
            print_error(f"Cannot import shell_callbacks: {e}")
            issues.append("shell_callbacks import failed")
            return issues
        
        # Check load_societies function
        if hasattr(shell_callbacks, 'load_societies'):
            print_ok("load_societies() callback function exists")
        else:
            print_error("load_societies() function NOT FOUND")
            issues.append("load_societies function missing")
        
        # Check register function
        if hasattr(shell_callbacks, 'register_shell_callbacks'):
            print_ok("register_shell_callbacks() function exists")
        else:
            print_error("register_shell_callbacks() function NOT FOUND")
            issues.append("register_shell_callbacks function missing")
        
        # List all functions
        functions = [name for name in dir(shell_callbacks) 
                    if callable(getattr(shell_callbacks, name)) and not name.startswith('_')]
        print(f"\n   Total functions in shell_callbacks: {len(functions)}")
        print("   First 15 functions:")
        for func in sorted(functions)[:15]:
            print(f"   • {func}")
        
    except Exception as e:
        print_error(f"Error checking callbacks: {e}")
        import traceback
        traceback.print_exc()
        issues.append(f"Callback check failed: {e}")
    
    return issues


def check_html_structure():
    """Check HTML component IDs"""
    
    print_section("5. HTML COMPONENT STRUCTURE")
    
    issues = []
    
    try:
        from app.dash_apps.pages.login_systemOLD import society_select_layout
        
        layout = society_select_layout()
        layout_str = str(layout)
        
        print_ok("society_select_layout() renders successfully")
        
        required_ids = {
            'society-dropdown': 'The dropdown selector',
            'society-select-btn': 'The "Continue to Login" button',
            'remember-society-checkbox': 'The "Remember society" checkbox',
            'login-db-error': 'The database error message container'
        }
        
        print("\n   Required component IDs:")
        for id_str, description in required_ids.items():
            found = (f'"{id_str}"' in layout_str or 
                    f"'{id_str}'" in layout_str or 
                    f'id="{id_str}"' in layout_str)
            
            if found:
                print_ok(f"   {id_str:<35} - {description}")
            else:
                print_error(f"   {id_str:<35} - MISSING!")
                issues.append(f"HTML ID missing: {id_str}")
        
    except Exception as e:
        print_error(f"Error checking HTML: {e}")
        import traceback
        traceback.print_exc()
        issues.append(f"HTML check failed: {e}")
    
    return issues


def check_syntax():
    """Check Python syntax of key files"""
    
    print_section("6. PYTHON SYNTAX CHECK")
    
    issues = []
    files_to_check = [
        'app/dash_apps/app_shell.py',
        'app/dash_apps/callbacks/shell_callbacks.py',
        'app/dash_apps/pages/login_system.py',
        'app/dash_apps/pages/portal_pages.py',
    ]
    
    for filepath in files_to_check:
        full_path = PROJECT_ROOT / filepath
        
        if not full_path.exists():
            print_warning(f"{filepath} - FILE NOT FOUND")
            issues.append(f"Missing file: {filepath}")
            continue
        
        try:
            with open(full_path) as f:
                compile(f.read(), str(full_path), 'exec')
            print_ok(f"{filepath}")
        except SyntaxError as e:
            print_error(f"{filepath} - SYNTAX ERROR")
            print(f"   Line {e.lineno}: {e.msg}")
            issues.append(f"Syntax error in {filepath}:{e.lineno}")
        except Exception as e:
            print_error(f"{filepath} - ERROR: {e}")
            issues.append(f"Error in {filepath}: {e}")
    
    return issues


def main_diagnostic():
    """Run all diagnostics"""
    
    print_header("SOCIETIES DROPDOWN DEBUG - COMPREHENSIVE DIAGNOSTIC")
    
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
    
    # Run diagnostics in order
    all_issues = []
    
    # 1. Database
    all_societies = main()
    if not all_societies:
        print_header("DIAGNOSTIC FAILED")
        print_error("Cannot proceed - database connection or societies table issue")
        return False
    
    # 2. Query test
    query_ok = test_query(all_societies)
    if not query_ok:
        all_issues.append("Load societies query returns no results")
    
    # 3. Callbacks
    callback_issues = check_callbacks()
    all_issues.extend(callback_issues)
    
    # 4. HTML
    html_issues = check_html_structure()
    all_issues.extend(html_issues)
    
    # 5. Syntax
    syntax_issues = check_syntax()
    all_issues.extend(syntax_issues)
    
    # ════════════════════════════════════════════════════════════════════════
    # SUMMARY & REMEDIATION
    # ════════════════════════════════════════════════════════════════════════
    
    print_section("SUMMARY & NEXT STEPS")
    
    if not all_issues:
        print_ok("All checks passed! ✅")
        print()
        print("Dropdown should be working. Try:")
        print("   1. Refresh browser (Ctrl+Shift+R)")
        print("   2. Clear browser cache")
        print("   3. Open DevTools (F12) → Console tab")
        print("   4. Check for JavaScript errors")
        print("   5. Check Network tab to see if callback fires")
        return True
    
    print_error(f"Found {len(all_issues)} issue(s):")
    print()
    
    for i, issue in enumerate(all_issues, 1):
        print(f"{i}. {issue}")
    
    print()
    print("=" * 80)
    print("REMEDIATION STEPS")
    print("=" * 80)
    print()
    
    if any('database' in i.lower() for i in all_issues):
        print("Step 1: Fix database issues")
        print("   python3 database/migrate.py --force")
        print("   python3 database/seed.py")
        print()
    
    if any('syntax' in i.lower() for i in all_issues):
        print("Step 2: Fix syntax errors")
        print("   Review the files mentioned above")
        print("   Check for missing imports, mismatched parentheses, etc.")
        print()
    
    if any('missing' in i.lower() or 'import' in i.lower() for i in all_issues):
        print("Step 3: Fix imports and structure")
        print("   Verify all files are in correct locations")
        print("   Check that __init__.py files exist in app/ and app/dash_apps/")
        print()
    
    if any('callback' in i.lower() for i in all_issues):
        print("Step 4: Fix callback registration")
        print("   Check app/__init__.py calls register_shell_callbacks()")
        print("   Verify shell_callbacks.py is in app/dash_apps/callbacks/")
        print()
    
    print("Step 5: Restart application")
    print("   python3 run.py")
    print()
    
    return False


if __name__ == '__main__':
    try:
        success = main_diagnostic()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
