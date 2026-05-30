# app/dash_apps/callbacks/debug_callbacks.py
"""
DEBUG CALLBACKS - Log all database errors and mismatches to toast notifications
Helps identify:
  1. Database connection issues
  2. SQL errors in loaders/KPI functions
  3. KPI vs List count mismatches
  4. Missing data or filters
"""

from dash import callback, Input, Output, State, ctx
import json
from datetime import datetime

def register_debug_callbacks(app):
    """Register debug callbacks that monitor and report errors."""
    
    print("  → Registering debug callbacks...")
    
    # ──────────────────────────────────────────────────────────────────────────
    # 1. MONITOR SOCIETY DROPDOWN LOAD (SQL errors)
    # ──────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("society-dropdown", "options"),
        prevent_initial_call=True,
    )
    def debug_society_dropdown_load(options):
        """Alert if society dropdown is empty (DB connection issue)."""
        if not options or len(options) == 0:
            print("\n❌ DEBUG: Society dropdown is EMPTY!")
            print("   → DB connection issue OR no valid societies in database")
            print("   → Check:")
            print("      1. Database connectivity")
            print("      2. Societies table has records")
            print("      3. Plan names match: 'Free', '9Apts', '99Apts', '999Apts', 'Unlimited'")
            print("      4. plan_validity >= TODAY for paid plans")
            
            return {
                "type": "error",
                "message": "❌ Cannot load societies - check database connection and ensure societies exist in DB"
            }
        
        print(f"\n✅ DEBUG: {len(options)} societies loaded")
        return None  # No error
    
    # ──────────────────────────────────────────────────────────────────────────
    # 2. KPI VALUE MONITOR (track KPI counts)
    # ──────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("debug-kpi-log", "data", allow_duplicate=True),
        Input({"type": "kpi-value", "card_id": "kpi_apartments_total"}, "children"),
        Input({"type": "kpi-value", "card_id": "kpi_vendors_total"}, "children"),
        Input({"type": "kpi-value", "card_id": "kpi_security_total"}, "children"),
        prevent_initial_call=True,
    )
    def debug_kpi_values(*kpi_values):
        """Log KPI values for comparison with list counts."""
        kpi_map = {
            0: "apartments_total",
            1: "vendors_total",
            2: "security_total"
        }
        
        log = {}
        for i, val in enumerate(kpi_values):
            if val and val != "—":
                log[kpi_map[i]] = val
        
        print(f"\n📊 DEBUG: KPI Values = {log}")
        return log
    
    # ──────────────────────────────────────────────────────────────────────────
    # 3. LIST LOAD MONITOR (track list counts and compare to KPI)
    # ──────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("debug-list-log", "data", allow_duplicate=True),
        Input("drilldown-store", "data"),
        State("debug-kpi-log", "data"),
        prevent_initial_call=True,
    )
    def debug_list_load_mismatch(store, kpi_log):
        """Compare list counts to KPI counts - identify mismatches."""
        if not store or not store.get("active_card", "").startswith("list_"):
            return None, {}
        
        active_card = store.get("active_card", "")
        entity_map = {
            "list_apartments": ("apartments", "apartments_total"),
            "list_vendors": ("vendors", "vendors_total"),
            "list_security": ("security", "security_total"),
        }
        
        if active_card not in entity_map:
            return None, {}
        
        entity, kpi_key = entity_map[active_card]
        
        # Extract list count from store (would be set by list render callback)
        # For now, just log the KPI value
        kpi_val = kpi_log.get(kpi_key, "?") if kpi_log else "?"
        
        print(f"\n📋 DEBUG: Viewing {active_card}")
        print(f"   → KPI says {kpi_key} = {kpi_val}")
        print(f"   → Waiting for list to load...")
        
        return None, {"entity": entity, "kpi_value": kpi_val, "active_card": active_card}
    
    # ──────────────────────────────────────────────────────────────────────────
    # 4. SQL ERROR MONITOR (catch and display DB errors)
    # ──────────────────────────────────────────────────────────────────────────
    @app.callback(
        Output("debug-sql-error", "data", allow_duplicate=True),
        Input("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def debug_sql_errors(store):
        """Monitor for SQL errors in drilldown operations."""
        # This would need to be enhanced with try-catch in loaders.py
        # For now, just track the store state
        return {"timestamp": datetime.now().isoformat(), "store_keys": list(store.keys()) if store else []}
    
    print("  ✓ Debug callbacks registered")


# ══════════════════════════════════════════════════════════════════════════════
# ENHANCED LOADERS WITH ERROR TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def load_list_with_debug(entity: str, filters: dict, page: int = 1, search: str = "", page_size: int = 15) -> tuple[list, int, dict]:
    """
    Load list with comprehensive error reporting.
    Returns: (rows, total, debug_info)
    """
    from app.dash_apps.drilldown import loaders
    
    debug = {
        "entity": entity,
        "filters": filters,
        "page": page,
        "search": search,
        "timestamp": datetime.now().isoformat(),
        "error": None,
        "rows_returned": 0,
        "total_count": 0,
        "society_id": filters.get("society_id"),
    }
    
    try:
        rows, total = loaders.load_list(entity, filters, page=page, search=search, page_size=page_size)
        debug["rows_returned"] = len(rows)
        debug["total_count"] = total
        
        # ✅ Compare to KPI
        if total == 0 and filters.get("society_id"):
            print(f"\n⚠️  WARNING: Empty list for {entity}")
            print(f"   Filters: {filters}")
            print(f"   Search: '{search}'")
            print(f"   Page: {page}")
        
        return rows, total, debug
        
    except Exception as e:
        print(f"\n❌ ERROR loading {entity}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        debug["error"] = str(e)
        return [], 0, debug


# ══════════════════════════════════════════════════════════════════════════════
# KPI LOAD DEBUG
# ══════════════════════════════════════════════════════════════════════════════

def load_kpi_with_debug(kpi_id: str, society_id: int) -> tuple[int, dict]:
    """
    Load KPI value with error tracking.
    Returns: (value, debug_info)
    """
    from database.db_manager import db
    
    debug = {
        "kpi_id": kpi_id,
        "society_id": society_id,
        "timestamp": datetime.now().isoformat(),
        "error": None,
        "value": 0,
        "sql_function": None,
    }
    
    # Map KPI to SQL function
    kpi_to_function = {
        "kpi_apartments_total": "fn_apartments_list",
        "kpi_vendors_total": "fn_vendors_list",
        "kpi_security_total": "fn_security_list",
        "kpi_events_total": "fn_events_list",
        "kpi_concerns_open": "fn_concerns_list",
    }
    
    func = kpi_to_function.get(kpi_id)
    if not func:
        debug["error"] = f"Unknown KPI: {kpi_id}"
        print(f"❌ Unknown KPI: {kpi_id}")
        return 0, debug
    
    debug["sql_function"] = func
    
    try:
        # For most KPIs, we count the rows from the SQL function
        rows = db._execute(
            f"SELECT * FROM {func}(%s, NULL) LIMIT 1000",
            (society_id,),
            fetch_all=True
        ) or []
        
        value = len(rows)
        debug["value"] = value
        
        print(f"\n✅ KPI {kpi_id} loaded: {value}")
        print(f"   Function: {func}({society_id})")
        
        return value, debug
        
    except Exception as e:
        print(f"\n❌ ERROR loading KPI {kpi_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        debug["error"] = str(e)
        debug["sql_function"] = func
        return 0, debug


# ══════════════════════════════════════════════════════════════════════════════
# MISMATCH DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

def check_kpi_list_mismatch(kpi_value: int, list_count: int, entity: str, society_id: int) -> dict:
    """
    Check if KPI and list counts match.
    If not, log detailed diagnostic info.
    """
    result = {
        "entity": entity,
        "society_id": society_id,
        "kpi_value": kpi_value,
        "list_count": list_count,
        "match": kpi_value == list_count,
        "difference": abs(kpi_value - list_count),
    }
    
    if not result["match"]:
        print(f"\n⚠️  MISMATCH DETECTED: {entity}")
        print(f"   KPI says: {kpi_value}")
        print(f"   List shows: {list_count}")
        print(f"   Difference: {result['difference']}")
        print(f"   Society ID: {society_id}")
        print(f"\n   Possible causes:")
        print(f"   1. Filters applied to list but not KPI")
        print(f"   2. Permission checks hiding records in list")
        print(f"   3. Different SQL functions used")
        print(f"   4. Search/status filters applied")
        print(f"   5. RBAC filtering out records")
    
    return result
