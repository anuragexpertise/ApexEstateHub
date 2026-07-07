# ============================================================
# app/dash_apps/callbacks/__init__.py
# ============================================================
# Changes vs previous version:
#   - Added registration of noc_callbacks (NOC Print/PDF/Email)
#     as step 10, before debug callbacks.
#   - Added registration of admin_callbacks (pruned to just
#     validate_qr_code_admin — see admin_callbacks.py header)
#     as step 11.
# ============================================================

def register_callbacks(app):
    if getattr(app, "_callbacks_registered", False):
        print("📋 Callbacks already registered — skipping")
        return
    app._callbacks_registered = True

    print("📋 Registering callbacks...")

    # 1. Shell FIRST (owns society-dropdown, guard_modal, route_page)
    from .shell_callbacks import register_shell_callbacks
    register_shell_callbacks(app)

    # 2. Login (writes auth-store with allow_duplicate=True)
    from .login_callbacks import register_login_callbacks
    register_login_callbacks(app)

    # 3. Drilldown — needs profile-action-trigger Store in app_shell
    try:
        from .drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ drilldown_callbacks failed: {e}")
        import traceback; traceback.print_exc()

    # 4. Card catalogue (KPI refresh + list loaders)
    try:
        from .card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ card_catalogue_callbacks failed: {e}")

    # 5. Customize (DnD layout editor)
    try:
        from .customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ customize_callbacks failed: {e}")

    # 6. QR gate pass callbacks
    try:
        from .qr_callbacks import register_qr_callbacks
        register_qr_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ qr_callbacks failed: {e}")

    # 7. Camera capture (clientside JS injection)
    try:
        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ camera_callbacks failed: {e}")

    # 8. KPI Inspector callbacks (Customize → KPI Inspector tab)
    try:
        from .customize_kpi_callbacks import register_customize_kpi_callbacks
        register_customize_kpi_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ customize_kpi_callbacks failed: {e}")

    # 9. Debug LAST (writes customize-kpi-metadata, kpi-audit-table)
    try:
        from .debug_callbacks import register_debug_callbacks
        register_debug_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ debug_callbacks failed: {e}")

    # 10. NOC card buttons (Print / PDF / Email — clientside JS)
    #     Requires dcc.Store(id='noc-action-store') in app_shell.py layout.
    try:
        from .noc_callbacks import register_noc_callbacks
        register_noc_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ noc_callbacks failed: {e}")

    # 11. Admin callbacks — pruned to just validate_qr_code_admin (manual
    #     paste-and-validate QR entry). update_society_count,
    #     update_recent_societies, and enroll_member were removed from
    #     admin_callbacks.py: their target component IDs don't exist
    #     anywhere in portal_pages.py — society counts already come from
    #     the generic KPI system, and enrollment already goes through the
    #     schema-driven "New" button flow. Registering the removed ones
    #     would just be inert duplicate logic. See admin_callbacks.py's
    #     module docstring for the full rationale.
    #     NOTE: validate_qr_code_admin's own target IDs (qr-scan-input,
    #     validate-qr-btn, qr-validation-result) also aren't in the layout
    #     yet — this registers cleanly but stays inert until a manual-entry
    #     panel is added somewhere (e.g. admin's Evaluate Pass tab).
    try:
        from .admin_callbacks import register_admin_callbacks
        register_admin_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ admin_callbacks failed: {e}")

    # 12. Form autofill — particulars auto-suggestion for Receipts/Expenses
    #     forms (implements the previously-unwired PARTICULARS_TEMPLATES
    #     intent noted in estatehub.sql's schema comments).
    try:
        from .form_autofill_callbacks import register_form_autofill_callbacks
        register_form_autofill_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ form_autofill_callbacks failed: {e}")

    # NOTE: security_callbacks.py and owner_callbacks.py are intentionally
    # NOT registered — they reference component IDs that don't exist in any
    # portal layout and caused NonExistentIdException at startup.
    # Gate scanning is covered by qr_callbacks.py; payment processing by
    # the drilldown form system.

    print("✅ All callbacks registered")
