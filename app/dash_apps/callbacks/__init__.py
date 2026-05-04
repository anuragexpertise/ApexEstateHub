# app/dash_apps/callbacks/__init__.py
"""
Master callback registrar.
Import order matters — shell must be first (owns auth-store / url).
"""


def register_all_callbacks(app):
    """Register every callback module in safe dependency order."""

    # Shell first — owns auth-store, url, login-modal, router, toast
    from .shell_callbacks import register_shell_callbacks
    register_shell_callbacks(app)

    from .qr_callbacks import register_qr_callbacks
    register_qr_callbacks(app)

    from .security_callbacks import register_security_callbacks
    register_security_callbacks(app)

    from .owner_callbacks import register_owner_callbacks
    register_owner_callbacks(app)

    from .vendor_callbacks import register_vendor_callbacks
    register_vendor_callbacks(app)

    from .admin_callbacks import register_admin_callbacks
    register_admin_callbacks(app)

    # ── Camera + Evaluate Pass ────────────────────────────────────────────────
    try:
        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
    except Exception as e:
        print(f"⚠  camera_callbacks skipped: {e}")
        import traceback; traceback.print_exc()

    # ── Drill-down UX engine — MUST come before card_catalogue ────────────────
    try:
        from .drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
    except Exception as e:
        print(f"⚠  drilldown_callbacks skipped: {e}")
        import traceback; traceback.print_exc()

    # ── Drag-and-drop dashboard customisation ─────────────────────────────────
    try:
        from .customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
    except Exception as e:
        print(f"⚠  customize_callbacks skipped: {e}")

    # ── Card catalogue (KPI refresh + all form/list CRUD) ─────────────────────
    try:
        from .card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
    except Exception as e:
        print(f"⚠  card_catalogue_callbacks skipped: {e}")

    print("✓ ALL callbacks registered")


# Keep the old alias so any code that imports register_callbacks still works
register_callbacks = register_all_callbacks
