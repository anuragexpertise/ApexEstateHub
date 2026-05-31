#!/usr/bin/env python3
"""
Callback Diagnostic Script
==========================
Tests all database queries and callback registrations to identify issues.

Usage:
    python diagnostic_callbacks.py
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import db
from app.dash_apps.pages.card_catalogue import KPI_CARDS, FORM_CARDS


def test_database_connection():
    """Test database connectivity."""
    print("\n" + "="*60)
    print("1. DATABASE CONNECTION TEST")
    print("="*60)
    
    try:
        result = db._execute("SELECT 1 AS test", fetch_one=True)
        if result and result.get("test") == 1:
            print("✅ Database connection: SUCCESS")
            return True
        else:
            print("❌ Database connection: FAILED (invalid response)")
            return False
    except Exception as e:
        print(f"❌ Database connection: FAILED - {e}")
        return False


def test_societies_exist():
    """Check if any societies exist."""
    print("\n" + "="*60)
    print("2. SOCIETIES TABLE TEST")
    print("="*60)
    
    try:
        result = db._execute(
            "SELECT COUNT(*) as cnt FROM societies",
            fetch_one=True
        )
        count = result.get("cnt", 0) if result else 0
        print(f"   Found {count} societies in database")
        
        if count > 0:
            # Get sample society
            sample = db._execute(
                "SELECT id, name FROM societies LIMIT 1",
                fetch_one=True
            )
            print(f"   Sample society: ID={sample.get('id')}, Name={sample.get('name')}")
            print("✅ Societies table: OK")
            return sample.get('id')
        else:
            print("⚠️  No societies found - create one first!")
            return None
            
    except Exception as e:
        print(f"❌ Societies table error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_kpi_queries(society_id):
    """Test all KPI queries."""
    print("\n" + "="*60)
    print("3. KPI QUERIES TEST")
    print("="*60)
    
    if not society_id:
        print("⚠️  Skipping - no society_id")
        return
    
    passed = 0
    failed = 0
    
    for card_id, cfg in KPI_CARDS.items():
        query = cfg.get("query", "")
        n_params = cfg.get("params", 0)
        
        # Build params dict
        if n_params == 0:
            params = {}
        elif n_params == 1:
            params = {"param_0": society_id}
        else:
            params = {f"param_{i}": society_id for i in range(n_params)}
        
        # Convert %s to :param_N
        converted_query = query
        for i in range(n_params):
            converted_query = converted_query.replace("%s", f":param_{i}", 1)
        
        try:
            result = db._execute(converted_query, params, fetch_one=True)
            value = result.get("v", 0) if result else 0
            
            print(f"   ✓ {card_id:30s} → {value}")
            passed += 1
            
        except Exception as e:
            print(f"   ✗ {card_id:30s} → ERROR: {str(e)[:50]}")
            failed += 1
    
    print(f"\n   Summary: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("❌ KPI queries: SOME FAILED")
    else:
        print("✅ KPI queries: ALL PASSED")


def test_list_queries(society_id):
    """Test all list table queries."""
    print("\n" + "="*60)
    print("4. LIST QUERIES TEST")
    print("="*60)
    
    if not society_id:
        print("⚠️  Skipping - no society_id")
        return
    
    queries = {
        "entities": """
            SELECT 
                u.id, 
                a.flat_number, 
                a.owner_name, 
                u.role, 
                u.email,
                COALESCE(a.active, true) AS active
            FROM users u 
            LEFT JOIN apartments a ON u.linked_id = a.id 
            WHERE u.society_id = :sid 
            ORDER BY u.created_at DESC 
            LIMIT 10
        """,
        "payments": """
            SELECT 
                p.id, 
                p.paid_at, 
                a.flat_number, 
                p.payment_type,
                p.amount, 
                p.payment_method, 
                p.status 
            FROM payments p 
            LEFT JOIN apartments a ON p.entity_id = a.id 
            WHERE p.society_id = :sid 
            ORDER BY p.paid_at DESC NULLS LAST 
            LIMIT 10
        """,
        "events": """
            SELECT id, event_date, title, venue, open_to 
            FROM events 
            WHERE society_id = :sid 
            ORDER BY event_date DESC 
            LIMIT 10
        """,
        "gate_logs": """
            SELECT 
                g.id, 
                g.time_in, 
                g.time_out, 
                g.role, 
                g.entity_id
            FROM gate_access g 
            WHERE g.society_id = :sid 
            ORDER BY g.time_in DESC 
            LIMIT 10
        """,
        "fn_apartments_list": """
            SELECT *
            FROM fn_apartment_list(1, NULL, NULL))
            
        """
    }
    
    passed = 0
    failed = 0
    
    for name, query in queries.items():
        try:
            result = db._execute(query, {"sid": society_id}, fetch_all=True)
            count = len(result) if result else 0
            
            print(f"   ✓ {name:20s} → {count} rows")
            passed += 1
            
        except Exception as e:
            print(f"   ✗ {name:20s} → ERROR: {str(e)[:50]}")
            failed += 1
    
    print(f"\n   Summary: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("❌ List queries: SOME FAILED")
    else:
        print("✅ List queries: ALL PASSED")


def test_callback_registration():
    """Test that all callbacks are registered."""
    print("\n" + "="*60)
    print("5. CALLBACK REGISTRATION TEST")
    print("="*60)
    
    callback_modules = [
        "shell_callbacks",
        "login_callbacks",
        "card_catalogue_callbacks",
        "qr_callbacks",
        "security_callbacks",
        "owner_callbacks",
        "vendor_callbacks",
        "admin_callbacks",
        "camera_callbacks",
        "drilldown_callbacks",
        "customize_callbacks",
    ]
    
    for module_name in callback_modules:
        try:
            module = __import__(
                f"app.dash_apps.callbacks.{module_name}",
                fromlist=[""]
            )
            
            # Check if register function exists
            register_func = getattr(module, f"register_{module_name}", None)
            
            if register_func:
                print(f"   ✓ {module_name:30s} → OK")
            else:
                print(f"   ⚠️  {module_name:30s} → No register function")
                
        except ImportError:
            print(f"   ✗ {module_name:30s} → NOT FOUND")
        except Exception as e:
            print(f"   ✗ {module_name:30s} → ERROR: {str(e)[:40]}")
    
    print("\n✅ Callback registration check: COMPLETE")


def main():
    """Run all diagnostic tests."""
    print("\n" + "="*60)
    print("APEX ESTATE HUB - CALLBACK DIAGNOSTICS")
    print("="*60)
    
    # Test 1: Database connection
    if not test_database_connection():
        print("\n❌ Cannot proceed - database connection failed")
        return
    
    # Test 2: Check societies
    society_id = test_societies_exist()
    
    # Test 3: KPI queries
    test_kpi_queries(society_id)
    
    # Test 4: List queries
    test_list_queries(society_id)
    
    # Test 5: Callback registration
    test_callback_registration()
    
    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)
    print("""
Next Steps:
-----------
1. If database connection failed:
   → Check your .env file and DATABASE_URL
   → Verify Neon DB credentials
   
2. If no societies found:
   → Login as master admin
   → Create a test society
   
3. If KPI/List queries failed:
   → Check table schemas match expected structure
   → Run database migrations
   
4. If callbacks not registered:
   → Check import paths in __init__.py
   → Verify callback module files exist
    """)


if __name__ == "__main__":
    main()
