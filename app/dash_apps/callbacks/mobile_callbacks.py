# app/dash_apps/callbacks/mobile_callbacks.py
"""
Mobile sidebar callbacks.
shell_callbacks.py owns the main toggle; this module handles
the auto-close-on-navigate and the clientside icon swap.
"""
from dash import Input, Output, no_update, clientside_callback
import dash


def register_mobile_callbacks(app):

    # Auto-close sidebar when URL changes (mobile navigation)
    @app.callback(
        Output('app-sidebar',        'className',  allow_duplicate=True),
        Output('sidebar-open-store', 'data',       allow_duplicate=True),
        Input('url', 'pathname'),
        prevent_initial_call=True,
    )
    def close_on_navigate(_pathname):
        return 'app-sidebar', {'collapsed': False}

    # Clientside: swap hamburger icon without a Python round-trip
    clientside_callback(
        """
        function(state) {
            var btn = document.getElementById('hdr-hamburger-btn');
            if (!btn) return window.dash_clientside.no_update;
            var icon = btn.querySelector('i');
            if (icon) {
                var collapsed = state && state.collapsed;
                icon.className = collapsed ? 'fas fa-bars' : 'fas fa-bars';
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output('hdr-hamburger-btn', 'className'),   # dummy output
        Input('sidebar-open-store', 'data'),
        prevent_initial_call=False,
    )

    print('✓ Mobile callbacks registered')
