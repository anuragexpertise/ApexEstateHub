from dash import Input, Output, State, no_update, clientside_callback
import dash


def register_mobile_callbacks(app):
    """Register all mobile / sidebar-toggle callbacks."""

    # ──────────────────────────────────────────────────────────────
    # 1. TOGGLE SIDEBAR  (hamburger button click)
    #    Updates: sidebar class, overlay class, main-content style,
    #             sidebar-open-store (shared state)
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output('main-sidebar',       'className'),
        Output('sidebar-overlay',    'className'),
        Output('main-content',       'style'),
        Output('sidebar-open-store', 'data'),
        Input('sidebar-toggle',  'n_clicks'),
        Input('sidebar-overlay', 'n_clicks'),
        State('sidebar-open-store', 'data'),
        prevent_initial_call=True
    )
    def toggle_sidebar(hamburger_clicks, overlay_clicks, is_open):
        """Open / close the sidebar by toggling CSS classes."""
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # Overlay click always closes
        if trigger_id == 'sidebar-overlay':
            new_open = False
        else:
            new_open = not bool(is_open)

        sidebar_class = 'glass-sidebar sidebar-open' if new_open else 'glass-sidebar'
        overlay_class = 'sidebar-overlay active'      if new_open else 'sidebar-overlay'

        # On desktop the margin is always 250 px; on mobile when open we
        # keep content in place (overlay covers it). We use CSS media
        # queries for the actual responsive margin — just return the base.
        content_style = {'marginLeft': '250px', 'transition': 'all 0.3s ease'}

        return sidebar_class, overlay_class, content_style, new_open

    # ──────────────────────────────────────────────────────────────
    # 2. AUTO-CLOSE SIDEBAR ON NAVIGATION (URL change)
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output('main-sidebar',       'className', allow_duplicate=True),
        Output('sidebar-overlay',    'className', allow_duplicate=True),
        Output('sidebar-open-store', 'data',      allow_duplicate=True),
        Input('url', 'pathname'),
        prevent_initial_call=True
    )
    def close_sidebar_on_navigate(_pathname):
        return 'glass-sidebar', 'sidebar-overlay', False

    # ──────────────────────────────────────────────────────────────
    # 3. CLIENTSIDE — smooth hamburger icon swap (≈0 ms, no round-trip)
    # ──────────────────────────────────────────────────────────────
    clientside_callback(
        """
        function(isOpen) {
            var btn = document.getElementById('sidebar-toggle');
            if (!btn) return window.dash_clientside.no_update;
            var icon = btn.querySelector('i');
            if (icon) {
                icon.className = isOpen ? 'fas fa-times' : 'fas fa-bars';
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output('sidebar-toggle', 'className'),   # dummy output (className unchanged)
        Input('sidebar-open-store', 'data'),
        prevent_initial_call=False
    )
