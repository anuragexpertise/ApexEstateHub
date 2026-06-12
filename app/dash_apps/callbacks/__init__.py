# callbacks/__init__.py

def register_callbacks(app):
    # Avoid registering callbacks multiple times (development reloader can import twice)
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

    try:
        from .qr_callbacks import register_qr_callbacks
        register_qr_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ qr_callbacks failed: {e}")

    try:
        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ camera_callbacks failed: {e}")

    # 7. Debug LAST (writes customize-kpi-metadata, kpi-audit-table)
    try:
        from .debug_callbacks import register_debug_callbacks
        register_debug_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ debug_callbacks failed: {e}")

    # KPI Inspector callbacks (Customize → KPI Inspector tab)
    try:
        from .customize_kpi_callbacks import register_customize_kpi_callbacks
        register_customize_kpi_callbacks(app)
    except Exception as e:
        print(f"  ⚠️ customize_kpi_callbacks failed: {e}")

    print("✅ All callbacks registered")