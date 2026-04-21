from dash import Input, Output, State, no_update, clientside_callback, ClientsideFunction
import dash

def register_mobile_callbacks(app):
    
    # Toggle sidebar on mobile
    @app.callback(
        Output("main-sidebar", "className"),
        Output("sidebar-overlay", "style"),
        Input("mobile-menu-toggle", "n_clicks"),
        State("main-sidebar", "className"),
        prevent_initial_call=True
    )
    def toggle_sidebar(n_clicks, current_class):
        if n_clicks:
            if current_class and "sidebar-open" in current_class:
                return "glass-sidebar", {"display": "none"}
            else:
                return "glass-sidebar sidebar-open", {
                    "position": "fixed",
                    "top": "0",
                    "left": "0",
                    "right": "0",
                    "bottom": "0",
                    "backgroundColor": "rgba(0,0,0,0.5)",
                    "zIndex": "1002",
                    "display": "block"
                }
        return no_update, no_update
    
    # Close sidebar when clicking overlay
    @app.callback(
        Output("main-sidebar", "className", allow_duplicate=True),
        Output("sidebar-overlay", "style", allow_duplicate=True),
        Input("sidebar-overlay", "n_clicks"),
        prevent_initial_call=True
    )
    def close_sidebar_overlay(n_clicks):
        if n_clicks:
            return "glass-sidebar", {"display": "none"}
        return no_update, no_update
    
    # Close sidebar when clicking any sidebar link (for mobile)
    # This catches all sidebar links
    @app.callback(
        Output("main-sidebar", "className", allow_duplicate=True),
        Output("sidebar-overlay", "style", allow_duplicate=True),
        Input("sidebar-link-dashboard", "n_clicks"),
        Input("sidebar-link-cashbook", "n_clicks"),
        Input("sidebar-link-receipts", "n_clicks"),
        Input("sidebar-link-expenses", "n_clicks"),
        Input("sidebar-link-enroll", "n_clicks"),
        Input("sidebar-link-users", "n_clicks"),
        Input("sidebar-link-events", "n_clicks"),
        Input("sidebar-link-evaluate-pass", "n_clicks"),
        Input("sidebar-link-customize", "n_clicks"),
        Input("sidebar-link-settings", "n_clicks"),
        Input("sidebar-link-owner-portal", "n_clicks"),
        Input("sidebar-link-owner-cashbook", "n_clicks"),
        Input("sidebar-link-payments", "n_clicks"),
        Input("sidebar-link-charges", "n_clicks"),
        Input("sidebar-link-owner-events", "n_clicks"),
        Input("sidebar-link-owner-settings", "n_clicks"),
        Input("sidebar-link-vendor-portal", "n_clicks"),
        Input("sidebar-link-vendor-cashbook", "n_clicks"),
        Input("sidebar-link-vendor-payments", "n_clicks"),
        Input("sidebar-link-vendor-charges", "n_clicks"),
        Input("sidebar-link-vendor-events", "n_clicks"),
        Input("sidebar-link-vendor-settings", "n_clicks"),
        Input("sidebar-link-pass-evaluation", "n_clicks"),
        Input("sidebar-link-attendance", "n_clicks"),
        Input("sidebar-link-security-events", "n_clicks"),
        Input("sidebar-link-security-receipt", "n_clicks"),
        Input("sidebar-link-security-users", "n_clicks"),
        Input("sidebar-link-security-settings", "n_clicks"),
        prevent_initial_call=True
    )
    def close_sidebar_on_link_click(*args):
        """Close sidebar on mobile when any link is clicked"""
        # Check if any click occurred
        for arg in args:
            if arg:
                return "glass-sidebar", {"display": "none"}
        return no_update, no_update