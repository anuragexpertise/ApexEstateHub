# app/dash_apps/callbacks/__init__.py
"""
Master callback registrar.

Registration order is load-order significant in Dash:
  The FIRST file to declare an Output owns it.
  All subsequent files must use allow_duplicate=True for the same Output.

  shell_callbacks  → owns: society-dropdown, auth-store (initial), url,
                           login-modal, login-stage-*, toast-store, portal-content
  login_callbacks  → writes auth-store with allow_duplicate=True
  everything else  → must also use allow_duplicate=True for shared Outputs
"""


def register_all_callbacks(app):
    print("\n" + "=" * 60)
    print("🔄  REGISTERING CALLBACKS")
    print("=" * 60)

    # ── 1. Shell (owns auth-store, url, login-modal, society-dropdown) ────────
    from .shell_callbacks import register_shell_callbacks
    register_shell_callbacks(app)

    # ── 2. Login (writes auth-store with allow_duplicate) ─────────────────────
    from .login_callbacks import register_login_callbacks
    register_login_callbacks(app)

    # ── 3. Optional feature modules (all gracefully skipped if missing) ────────
    _optional = [
        ("qr_callbacks",             "register_qr_callbacks"),
        ("security_callbacks",       "register_security_callbacks"),
        ("owner_callbacks",          "register_owner_callbacks"),
        ("vendor_callbacks",         "register_vendor_callbacks"),
        ("admin_callbacks",          "register_admin_callbacks"),
        ("camera_callbacks",         "register_camera_callbacks"),
        # drilldown MUST come before card_catalogue
        ("drilldown_callbacks",      "register_drilldown_callbacks"),
        ("customize_callbacks",      "register_customize_callbacks"),
        ("customize_kpi_callbacks",  "register_customize_kpi_callbacks"),
        ("card_catalogue_callbacks", "register_card_catalogue_callbacks"),
        ("debug_callbacks",          "register_debug_callbacks"),
    ]

    for module_name, func_name in _optional:
        try:
            module = __import__(
                f"app.dash_apps.callbacks.{module_name}",
                fromlist=[func_name],
            )
            getattr(module, func_name)(app)
        except ImportError:
            print(f"⚠   {module_name} not found — skipping")
        except Exception as exc:
            print(f"⚠   {module_name} skipped: {exc}")

    print("=" * 60)
    print("✅  ALL CALLBACKS REGISTERED")
    print("=" * 60 + "\n")


# Alias kept for any legacy import
register_callbacks = register_all_callbacks
