# app/dash_apps/callbacks/__init__.py
"""
Master callback registrar.
Import order matters — shell must be first (owns auth-store / url).
"""


def register_all_callbacks(app):
    """Register every callback module in safe dependency order."""
    
    print("\n" + "="*60)
    print("🔄 REGISTERING CALLBACKS")
    print("="*60)
    
    # Shell first — owns auth-store, url, login-modal, router, toast, society dropdown
    from .shell_callbacks import register_shell_callbacks
    register_shell_callbacks(app)
    
    # Login callbacks second — depends on auth-store from shell
    from .login_callbacks import register_login_callbacks
    register_login_callbacks(app)

    # QR callbacks
    try:
        from .qr_callbacks import register_qr_callbacks
        register_qr_callbacks(app)
    except ImportError:
        print("⚠  qr_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  qr_callbacks skipped: {e}")

    # Security callbacks
    try:
        from .security_callbacks import register_security_callbacks
        register_security_callbacks(app)
    except ImportError:
        print("⚠  security_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  security_callbacks skipped: {e}")

    # Owner callbacks
    try:
        from .owner_callbacks import register_owner_callbacks
        register_owner_callbacks(app)
    except ImportError:
        print("⚠  owner_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  owner_callbacks skipped: {e}")

    # Vendor callbacks
    try:
        from .vendor_callbacks import register_vendor_callbacks
        register_vendor_callbacks(app)
    except ImportError:
        print("⚠  vendor_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  vendor_callbacks skipped: {e}")

    # Admin callbacks
    try:
        from .admin_callbacks import register_admin_callbacks
        register_admin_callbacks(app)
    except ImportError:
        print("⚠  admin_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  admin_callbacks skipped: {e}")

    # ── Camera + Evaluate Pass ────────────────────────────────────────────────
    try:
        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
    except ImportError:
        print("⚠  camera_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  camera_callbacks skipped: {e}")

    # ── Drill-down UX engine — MUST come before card_catalogue ────────────────
    try:
        from .drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
    except ImportError:
        print("⚠  drilldown_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  drilldown_callbacks skipped: {e}")

    # ── Drag-and-drop dashboard customisation ─────────────────────────────────
    try:
        from .customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
    except ImportError:
        print("⚠  customize_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  customize_callbacks skipped: {e}")

    # ── Card catalogue (KPI refresh + all form/list CRUD) ─────────────────────
    try:
        from .card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
    except ImportError:
        print("⚠  card_catalogue_callbacks module not found - skipping")
    except Exception as e:
        print(f"⚠  card_catalogue_callbacks skipped: {e}")

    print("\n" + "="*60)
    print("✅ ALL CALLBACKS REGISTERED SUCCESSFULLY")
    print("="*60 + "\n")


# Keep the old alias so any code that imports register_callbacks still works
register_callbacks = register_all_callbacks
