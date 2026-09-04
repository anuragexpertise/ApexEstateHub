import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app.security.audit_context
from app.dash_apps.callbacks.drilldown_callbacks import _render_current
from app.dash_apps.drilldown.registry import DRILLDOWN_MAP, ENTITY_MAP
from app.dash_apps.drilldown import state as nav_state
from app.dash_apps.pages.card_catalogue import DEFAULT_LAYOUTS
from database.db_manager import db

def test_workflows_for_role(role_name, layout_key):
    print(f"\n--- Phase: Simulating {role_name.capitalize()} Portal Workflows ---")
    
    # Setup mock user based on role
    society_id = 1 if role_name != "master" else None
    linked_id = 1 if role_name in ("apartment", "vendor", "security") else None
    
    app.security.audit_context.get_current_user_id = lambda: 1
    app.security.audit_context.get_current_user_role = lambda: role_name
    app.security.audit_context.get_current_society_id = lambda: society_id
    app.security.audit_context.get_current_linked_id = lambda: linked_id

    auth_store = {
        "user_id": 1,
        "role": role_name,
        "society_id": society_id,
        "linked_id": linked_id
    }

    layouts = DEFAULT_LAYOUTS.get(layout_key, {})
    all_kpis = []
    for tab, kpis in layouts.items():
        all_kpis.extend(kpis)
    all_kpis = list(set(all_kpis))

    total_tested = 0
    errors = []

    for kpi in all_kpis:
        nav_info = DRILLDOWN_MAP.get(kpi)
        if not nav_info:
            continue
            
        target_list = nav_info.get("target")
        if not target_list:
            continue
            
        print(f"\nTesting Workflow ({role_name}): {kpi} -> {target_list}")
        
        # 1. Simulate List View
        store = nav_state.initial_state(role_name, society_id)
        store = nav_state.navigate_to(store, target_list, nav_info.get("label", ""), filters=nav_info.get("filter", {}))
        
        try:
            content, bc, db_err = _render_current(store, auth_store)
            if db_err:
                msg = f"DB Error rendering {target_list} for {kpi}: {db_err}"
                print(f"  [X] {msg}")
                errors.append(msg)
                continue
            print(f"  [OK] List view rendered: {target_list}")
        except Exception as e:
            msg = f"Crash rendering {target_list} for {kpi}: {e}"
            print(f"  [X] {msg}")
            errors.append(msg)
            continue
            
        entity = target_list.replace("list_", "")
        singular = ENTITY_MAP.get(entity)
        if not singular:
            continue
            
        target_profile = f"profile_{singular}"
        target_form = f"form_{singular}_edit"
        
        try:
            if entity == "societies":
                q = "SELECT id FROM societies LIMIT 1"
            elif entity == "accounts":
                q = f"SELECT id FROM accounts WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "cashbook":
                q = f"SELECT id FROM transactions WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "receivables":
                q = f"SELECT id FROM receivables WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "payables":
                q = f"SELECT id FROM payables WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "ledger":
                q = f"SELECT row_date FROM ledger_view WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "apt_charges":
                q = f"SELECT id FROM apt_charges_fines_basis WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "ven_charges":
                q = f"SELECT id FROM ven_charges_fines_basis WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "security":
                q = f"SELECT id FROM security_staff WHERE society_id={society_id or 1} LIMIT 1"
            elif entity == "gate_logs":
                q = f"SELECT id FROM gate_pass_logs WHERE society_id={society_id or 1} LIMIT 1"
            else:
                q = f"SELECT id FROM {entity} WHERE society_id={society_id or 1} LIMIT 1"
                
            res = db._execute(q, fetch_one=True)
            if not res:
                print(f"  [-] Skipped profile/form (no data found in DB for {entity})")
                continue
                
            pk = res.get("id") or res.get("row_date")
            
            # 2. Simulate Profile View
            store = nav_state.navigate_to(store, target_profile, "Profile", entity_pk=pk)
            try:
                content, bc, db_err = _render_current(store, auth_store)
                if db_err:
                    msg = f"DB Error rendering {target_profile} (pk={pk}): {db_err}"
                    print(f"  [X] {msg}")
                    errors.append(msg)
                else:
                    print(f"  [OK] Profile view rendered: {target_profile} (pk={pk})")
            except Exception as e:
                msg = f"Crash rendering {target_profile} (pk={pk}): {e}"
                print(f"  [X] {msg}")
                errors.append(msg)
                
            # 3. Simulate Form View
            store = nav_state.navigate_to(store, target_form, "Edit", entity_pk=pk)
            try:
                content, bc, db_err = _render_current(store, auth_store)
                if db_err:
                    msg = f"DB Error rendering {target_form} (pk={pk}): {db_err}"
                    print(f"  [X] {msg}")
                    errors.append(msg)
                else:
                    print(f"  [OK] Form view rendered: {target_form} (pk={pk})")
            except Exception as e:
                msg = f"Crash rendering {target_form} (pk={pk}): {e}"
                print(f"  [X] {msg}")
                errors.append(msg)

        except Exception as e:
            print(f"  [-] Could not query table for {entity}: {e}")
            
        total_tested += 1

    return errors, total_tested

if __name__ == "__main__":
    roles = [
        ("apartment", "owner"),
        ("vendor", "vendor"),
        ("security", "security"),
        ("master", "master")
    ]
    
    total_errors = []
    total_tested = 0
    
    for role_name, layout_key in roles:
        errs, tested = test_workflows_for_role(role_name, layout_key)
        total_errors.extend(errs)
        total_tested += tested
        
    print("\n\n=== FINAL SUMMARY ===")
    if total_errors:
        print(f"Found {len(total_errors)} errors across {total_tested} workflows:")
        for err in total_errors:
            print(f"  - {err}")
    else:
        print(f"All remaining roles tested successfully! ({total_tested} workflows) Zero errors.")

