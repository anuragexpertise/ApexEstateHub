# app/dash_apps/pages/society_select.py
"""
DEPRECATED: This file is now redundant.
All society selection logic is in login_system.py
Keep only for backwards compatibility, but it's not used.
"""

from dash import html
from app.dash_apps.pages.login_systemOLD import society_select_layout, LOGIN_STYLES

# This function is no longer called - login_system.py handles everything
# Keeping it here only for reference or backwards compatibility

def society_select_layout_old(societies_list=None, error_message=None, show_master_login=False):
    """
    DEPRECATED: Use login_system.py instead.
    This was the old standalone society selection page.
    Now replaced by two-stage modal system.
    """
    pass  # Not implemented - use login_system.py