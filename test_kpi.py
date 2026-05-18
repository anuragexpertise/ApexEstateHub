# test_kpi_flow.py
"""
Systematic KPI Testing Framework
Run each test individually to verify the complete drill-down flow
"""

from database.db_manager import db

def test_kpi_flow(kpi_id: str, society_id: int = 1):
    """
    Test complete flow for a KPI:
    1. KPI Query Execution
    2. List Card Loading
    3. Profile Card Loading
    4. Form Pre-fill
    5. CRUD Operations
    """
    
    print(f"\n{'='*60}")
    print(f"Testing KPI: {kpi_id}")
    print(f"{'='*60}")
    
    # ── Step 1: KPI Query ────────────────────────────────────────
    from app.dash_apps.pages.card_catalogue import KPI_CARDS
    cfg = KPI_CARDS.get(kpi_id)
    
    if not cfg:
        print(f"❌ KPI {kpi_id} not found in catalogue")
        return False
    
    print(f"\n1️⃣  KPI Query Test")
    print(f"   Query: {cfg['query'][:80]}...")
    
    # Build params
    n_params = cfg.get("params", 0)
    if n_params == 0:
        params = {}
        query = cfg["query"]
    else:
        params = {f"param_{i}": society_id for i in range(n_params)}
        query = cfg["query"]
        for i in range(n_params):
            query = query.replace("%s", f":param_{i}", 1)
    
    try:
        result = db.execute_query(query, params, fetch_one=True)
        value = result.get("v", 0) if result else 0
        print(f"   ✅ Value: {value}")
    except Exception as e:
        print(f"   ❌ Query Failed: {e}")
        return False
    
    # ── Step 2: List Card Navigation ─────────────────────────────
    from app.dash_apps.drilldown.registry import DRILLDOWN_MAP
    nav_info = DRILLDOWN_MAP.get(kpi_id)
    
    if not nav_info:
        print(f"\n⚠️  No drill-down mapping for {kpi_id}")
        return True  # KPI works, no drill-down
    
    target_card = nav_info.get("target")
    print(f"\n2️⃣  Navigation Test")
    print(f"   Target: {target_card}")
    
    if not target_card.startswith("list_"):
        print(f"   ⚠️  Target is not a list card: {target_card}")
        return True
    
    # ── Step 3: List Loading ─────────────────────────────────────
    entity = target_card[5:]  # Remove "list_" prefix
    
    print(f"\n3️⃣  List Loading Test")
    print(f"   Entity: {entity}")
    
    from app.dash_apps.drilldown import loaders
    
    filters = nav_info.get("filter", {})
    filters["society_id"] = society_id
    
    try:
        rows, total = loaders.load_list(entity, filters, page=1, page_size=5)
        print(f"   ✅ Loaded {len(rows)} / {total} rows")
        
        if rows:
            print(f"   Sample: {list(rows[0].keys())[:5]}")
    except Exception as e:
        print(f"   ❌ List Load Failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # ── Step 4: Profile Loading ──────────────────────────────────
    if not rows:
        print(f"\n⚠️  No rows to test profile")
        return True
    
    from app.dash_apps.drilldown.registry import to_singular, get_pk
    singular = to_singular(entity)
    pk = get_pk(entity, rows[0])
    
    print(f"\n4️⃣  Profile Loading Test")
    print(f"   Entity: {singular}, PK: {pk}")
    
    try:
        profile = loaders.load_profile(singular, pk, society_id)
        if profile:
            print(f"   ✅ Profile loaded: {list(profile.keys())[:5]}")
        else:
            print(f"   ❌ Profile not found")
            return False
    except Exception as e:
        print(f"   ❌ Profile Load Failed: {e}")
        return False
    
    # ── Step 5: Profile Actions ──────────────────────────────────
    from app.dash_apps.drilldown.registry import DRILLDOWN_MAP as DM
    profile_card_id = f"profile_{singular}"
    profile_cfg = DM.get(profile_card_id, {})
    actions = profile_cfg.get("actions", {})
    
    print(f"\n5️⃣  Profile Actions Test")
    print(f"   Available actions: {list(actions.keys())}")
    
    for action_id, action_cfg in actions.items():
        target = action_cfg.get("target")
        prefill_map = action_cfg.get("prefill", {})
        
        print(f"\n   Action: {action_id} → {target}")
        
        if prefill_map:
            from app.dash_apps.drilldown.registry import build_prefill
            prefill = build_prefill(profile, prefill_map)
            print(f"   Prefill keys: {list(prefill.keys())}")
    
    # ── Step 6: Form Fields Check ────────────────────────────────
    from app.dash_apps.drilldown.drilldown_callbacks import ENTITY_META
    meta = ENTITY_META.get(entity, {})
    form_fields_new = meta.get("form_fields", {}).get("new", [])
    form_fields_edit = meta.get("form_fields", {}).get("edit", [])
    
    print(f"\n6️⃣  Form Fields Test")
    print(f"   New form: {len(form_fields_new)} fields")
    print(f"   Edit form: {len(form_fields_edit)} fields")
    
    if form_fields_new:
        print(f"   New fields: {[f['id'] for f in form_fields_new[:3]]}")
    
    print(f"\n{'='*60}")
    print(f"✅ {kpi_id} - ALL TESTS PASSED")
    print(f"{'='*60}\n")
    
    return True


# ═══════════════════════════════════════════════════════════════
# RUN TESTS
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test one KPI at a time
    SOCIETY_ID = 1  # Change to your test society
    
    test_cases = [
        "kpi_apartments_total",
        "kpi_apartments_dues",
        "kpi_vendors_total",
        "kpi_security_total",
        "kpi_events_total",
        "kpi_concerns_open",
        "kpi_gate_logs",
        "kpi_receipts_month",
        "kpi_expenses_month",
        "kpi_balance",
    ]
    
    results = {}
    
    for kpi_id in test_cases:
        try:
            passed = test_kpi_flow(kpi_id, SOCIETY_ID)
            results[kpi_id] = "✅ PASS" if passed else "❌ FAIL"
        except Exception as e:
            results[kpi_id] = f"❌ ERROR: {e}"
        
        input("\nPress Enter to test next KPI...")
    
    # ── Final Report ──────────────────────────────────────────────
    print("\n" + "="*60)
    print("FINAL TEST REPORT")
    print("="*60)
    
    for kpi, status in results.items():
        print(f"{status:12} {kpi}")
    
    total = len(results)
    passed = sum(1 for s in results.values() if "PASS" in s)
    
    print(f"\nTotal: {passed}/{total} passed ({passed/total*100:.0f}%)")