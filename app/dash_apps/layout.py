# app/dash_apps/layout.py
"""
Exposes serve_layout() — the single function imported by
app/__init__.py  create_dash_app()  and by  app/dash_apps/__init__.py.

All it does is delegate to app_shell.shell_layout() so that both
import paths resolve to the same HTML tree.
"""

from app.dash_apps.app_shell import shell_layout


def serve_layout():
    """Return the top-level Dash layout component tree."""
    return shell_layout()