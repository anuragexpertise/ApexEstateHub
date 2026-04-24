# app/dash_apps/callbacks/__init__.py
"""
Master callback registrar.
Import order matters: shell_callbacks last so it can see all other outputs.
"""


def register_all_callbacks(app):
    """Register every callback module."""

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

    from .mobile_callbacks import register_mobile_callbacks
    register_mobile_callbacks(app)

    try:
        from .customize_callbacks import register_customize_callbacks
        register_customize_callbacks(app)
    except Exception as e:
        print(f"⚠ customize_callbacks skipped: {e}")

    try:
        from .card_catalogue_callbacks import register_card_catalogue_callbacks
        register_card_catalogue_callbacks(app)
    except Exception as e:
        print(f"⚠ card_catalogue_callbacks skipped: {e}")

    print("✓ ALL callbacks registered")
