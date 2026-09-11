# ============================================================
# app/dash_apps/callbacks/__init__.py
# ============================================================
# Changes vs previous version:
#   - Added registration of noc_callbacks (NOC Print/PDF/Email)
#     as step 10, before debug callbacks.
#   - admin_callbacks (step 11) fully pruned — validate_qr_code_admin
#     moved to qr_callbacks.py's validate_manual_qr_scoped; remaining
#     callbacks (update_society_count, update_recent_societies,
#     enroll_member) had no matching layout IDs and were removed.
# ============================================================

def register_callbacks(app):
    if getattr(app, "_callbacks_registered", False):
        print("📋 Callbacks already registered — skipping")
        return
    app._callbacks_registered = True
    app._failed_callbacks = []

    print("📋 Registering callbacks...")

    import importlib
    import pathlib

    # Define the intended order of callback registrations
    CALLBACK_MODULES = [
        "shell_callbacks",            # 1. Shell FIRST
        "login_callbacks",            # 2. Login
        "drilldown_callbacks",        # 3. Drilldown
        "patrol_map_callbacks",       
        "card_catalogue_callbacks",   # 4. Card catalogue
        "customize_callbacks",        # 5. Customize
        "qr_callbacks",               # 6. QR gate pass
        "security_callbacks",         # 6b. Security gate-alert
        "camera_callbacks",           # 7. Camera capture
        "customize_kpi_callbacks",    # 8. KPI Inspector
        "list_inspector_callbacks",   # 8b. List Inspector
        "form_inspector_callbacks",   
        "setup_wizard_callbacks",     # 9. Setup Wizard
        "debug_callbacks",            # 10. Debug
        "noc_callbacks",              # 10. NOC card buttons
        "agreement_callbacks",        # 10b. Agreement card buttons
        "admin_callbacks",            # 11. Admin callbacks
        "form_autofill_callbacks",    # 12. Form autofill
        "receipt_callbacks",          # 13. Receipt buttons
        "event_ticket_callbacks",     # 13b. Event Ticket buttons
        "vendor_pass_callbacks",      # 13c. Vendor Pass buttons
        "expense_callbacks",          # 13d. Expense buttons
        "bulk_enroll_callbacks",      # 14. Bulk Enroll
        "bank_reconcile_callbacks",   # 14a2. Bank Reconcile
        "assign_to_callbacks",        # 14b. Assign-To
        "concern_bid_callbacks",      # 14c. Concern Bid
        "invite_to_callbacks",        # 14d. Invite-To
        "drillin_callbacks",          # 14e. Drill-In (and pay dues)
        "channel_callbacks",          # 15. Channel
        "poll_callbacks",             # 16. Poll
        "account_callbacks",          # 17. Account Settings
        "mode_conditional_callbacks", # 18. Mode-conditional
        "qty_stepper_callbacks",      # 19. Quantity stepper
        "qr_reissue_callbacks",       # 21. Re-issue QR
    ]

    for mod_name in CALLBACK_MODULES:
        full_mod_name = f"app.dash_apps.callbacks.{mod_name}"
        try:
            mod = importlib.import_module(full_mod_name)
            
            # Find and call any function starting with 'register_'
            registered_any = False
            for attr_name in dir(mod):
                if attr_name.startswith("register_") and callable(getattr(mod, attr_name)):
                    getattr(mod, attr_name)(app)
                    registered_any = True
            
            # Some modules (e.g. patrol_map_callbacks) only have module-level clientside_callbacks
            if not registered_any and "register_" not in "".join(dir(mod)):
                pass
                
        except Exception as e:
            err_msg = f"⚠️ {mod_name} failed: {e}"
            print(err_msg)
            import traceback; traceback.print_exc()
            app._failed_callbacks.append({"module": mod_name, "error": str(e)})

    # Startup-time check for unregistered callback modules
    try:
        callbacks_dir = pathlib.Path(__file__).parent
        all_callback_files = [f.stem for f in callbacks_dir.glob("*_callbacks.py")]
        unregistered = set(all_callback_files) - set(CALLBACK_MODULES)
        
        for unreg_mod in unregistered:
            content = (callbacks_dir / f"{unreg_mod}.py").read_text(encoding="utf-8")
            if "def register_" in content:
                print(f"⚠️  WARNING: Module {unreg_mod}.py contains a register_* function but is NOT listed in CALLBACK_MODULES in __init__.py!")
    except Exception as e:
        print(f"⚠️  WARNING: Could not perform dead-code startup check: {e}")

    print("✅ All callbacks registered")
