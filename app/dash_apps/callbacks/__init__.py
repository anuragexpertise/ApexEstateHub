"""
Callback registration hub — called by create_dash_app().

Registration order matters:
  1. shell_callbacks   — owns auth-store, login-modal, society-dropdown
  2. login_callbacks   — owns password/PIN/pattern login
  3. drilldown_callbacks
  4. card_catalogue_callbacks
  5. navigation_callbacks
  6. debug_callbacks    — last
"""


def register_all_callbacks(app):
    """Register every callback module with the Dash app."""

    print("\n" + "="*60)
    print("📞 REGISTERING ALL CALLBACKS")
    print("="*60)

    errors = []

    # ── 1. Shell callbacks (MUST be first) ─────────────────────────────
    try:
        from app.dash_apps.callbacks.shell_callbacks import register_shell_callbacks
        register_shell_callbacks(app)
        print("  ✅ shell_callbacks registered (load_societies, router, sidebar)")
    except Exception as e:
        print(f"  ❌ shell_callbacks FAILED: {e}")
        import traceback; traceback.print_exc()
        errors.append(f"shell_callbacks: {e}")

    # ── 2. Login callbacks ──────────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.login_callbacks import register_login_callbacks
        register_login_callbacks(app)
        print("  ✅ login_callbacks registered")
    except Exception as e:
        print(f"  ❌ login_callbacks FAILED: {e}")
        import traceback; traceback.print_exc()
        errors.append(f"login_callbacks: {e}")

    # ── 3. Drilldown callbacks ──────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import register_drilldown_callbacks
        register_drilldown_callbacks(app)
        print("  ✅ drilldown_callbacks registered")
    except ImportError:
        print("  ⚠️  drilldown_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ drilldown_callbacks FAILED: {e}")
        errors.append(f"drilldown_callbacks: {e}")

    # ── 4. Card catalogue callbacks ────────────────────────────────────
    try:
        from app.dash_apps.callbacks.card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
        print("  ✅ card_catalogue_callbacks registered (KPI refresh, lists)")
    except ImportError:
        print("  ⚠️  card_catalogue_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ card_catalogue_callbacks FAILED: {e}")
        errors.append(f"card_catalogue_callbacks: {e}")

    # ── 6. Admin callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.admin_callbacks import register_admin_callbacks
        register_admin_callbacks(app)
        print("  ✅ admin_callbacks registered")
    except ImportError:
        print("  ⚠️  admin_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ admin_callbacks FAILED: {e}")
        errors.append(f"admin_callbacks: {e}")

    # ── 7. Owner callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.owner_callbacks import register_owner_callbacks
        register_owner_callbacks(app)
        print("  ✅ owner_callbacks registered")
    except ImportError:
        print("  ⚠️  owner_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ owner_callbacks FAILED: {e}")
        errors.append(f"owner_callbacks: {e}")

    # ── 8. Security callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.security_callbacks import register_security_callbacks
        register_security_callbacks(app)
        print("  ✅ security_callbacks registered")
    except ImportError:
        print("  ⚠️  security_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ security_callbacks FAILED: {e}")
        errors.append(f"security_callbacks: {e}")

    # ── 9. Customize callbacks ──────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
        print("  ✅ customize_callbacks registered")
    except ImportError:
        print("  ⚠️  customize_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ customize_callbacks FAILED: {e}")
        errors.append(f"customize_callbacks: {e}")

    # ── 10. KPI customize callbacks ──────────────────────────────────────
    try:
        from app.dash_apps.callbacks.customize_kpi_callbacks import register_customize_kpi_callbacks
        register_customize_kpi_callbacks(app)
        print("  ✅ customize_kpi_callbacks registered")
    except ImportError:
        print("  ⚠️  customize_kpi_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ customize_kpi_callbacks FAILED: {e}")
        errors.append(f"customize_kpi_callbacks: {e}")

    # ── 11. Camera / QR callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)
        print("  ✅ camera_callbacks registered (QR scanner)")
    except ImportError:
        print("  ⚠️  camera_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ camera_callbacks FAILED: {e}")
        errors.append(f"camera_callbacks: {e}")

    # ── 12. QR callbacks ────────────────────────────────────────
    try:
        from app.dash_apps.callbacks.qr_callbacks import register_qr_callbacks
        register_qr_callbacks(app)
        print("  ✅ qr_callbacks registered (QR scanner)")
    except ImportError:
        print("  ⚠️  qr_callbacks not found — skipping")
    except Exception as e:
        print(f"  ❌ qr_callbacks FAILED: {e}")
        errors.append(f"qr_callbacks: {e}")
    

    # ── 13. Debug callbacks (last) ───────────────────────────────────────
    # try:
    #     from app.dash_apps.callbacks.debug_callbacks import register_debug_callbacks
    #     register_debug_callbacks(app)
    #     print("  ✅ debug_callbacks registered (error monitoring)")
    # except ImportError:
    #     print("  ⚠️  debug_callbacks not found — skipping")
    # except Exception as e:
    #     print(f"  ❌ debug_callbacks FAILED: {e}")
    #     errors.append(f"debug_callbacks: {e}")

    # ── Summary ─────────────────────────────────────────────────────────
    print("="*60)
    if errors:
        print(f"  ⚠️  {len(errors)} callback module(s) failed:")
        for err in errors:
            print(f"     • {err}")
    else:
        print("  ✅ ALL callbacks registered successfully")
    print("="*60 + "\n")


# Alias — app/__init__.py calls register_callbacks (singular)
register_callbacks = register_all_callbacks
