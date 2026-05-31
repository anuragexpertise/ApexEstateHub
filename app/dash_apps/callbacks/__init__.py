# app/dash_apps/callbacks/__init__.py
"""
Register all Dash callbacks in dependency order.

shell_callbacks must come first — it owns the primary outputs
(auth-store, url, login-modal). Login callbacks use allow_duplicate=True.
"""

import logging

log = logging.getLogger(__name__)


def register_callbacks(app):
    from app.dash_apps.callbacks.shell_callbacks import register_shell_callbacks
    from app.dash_apps.callbacks.login_callbacks import register_login_callbacks

    register_shell_callbacks(app)
    register_login_callbacks(app)

    log.info("All callbacks registered ✓")
