# app/dash_apps/callbacks/__init__.py
"""
Register all Dash callbacks in dependency order.

shell_callbacks must come first — it owns the primary outputs
(auth-store, url, login-modal). Login callbacks use allow_duplicate=True.
"""

import logging

log = logging.getLogger(__name__)


def register_callbacks(app):
    from .shell_callbacks import register_shell_callbacks
    from .login_callbacks import register_login_callbacks

    from .navigation_callbacks import register_navigation_callbacks
    from .card_catalogue_callbacks import register_card_catalogue_callbacks
    from .drilldown_callbacks import register_drilldown_callbacks
    from .qr_callbacks import register_qr_callbacks
    from .camera_callbacks  import register_camera_callbacks
    from .customize_callbacks   import register_customize_callbacks
    from .customize_kpi_callbacks  import register_customize_kpi_callbacks  

    from .admin_callbacks   import register_admin_callbacks
    from .owner_callbacks   import register_owner_callbacks
    from .security_callbacks  import register_security_callbacks
    from .debug_callbacks   import register_debug_callbacks

    register_shell_callbacks(app)
    register_login_callbacks(app)
    register_navigation_callbacks(app)
    register_card_catalogue_callbacks(app)
    register_drilldown_callbacks(app)
    register_qr_callbacks(app)
    register_camera_callbacks(app)
    register_customize_callbacks(app)
    register_customize_kpi_callbacks(app)
    register_admin_callbacks(app)
    register_owner_callbacks(app)
    register_security_callbacks(app)
    register_debug_callbacks(app)


    log.info("All callbacks registered ✓")
