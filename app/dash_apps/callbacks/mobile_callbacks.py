from dash import Input, Output, State, no_update, clientside_callback, ClientsideFunction
import dash

def register_mobile_callbacks(app):
    
    # Toggle sidebar on mobile
    @app.callback(
        Output("main-sidebar", "className"),
        Input("mobile-menu-toggle", "n_clicks"),
        State("main-sidebar", "className"),
        prevent_initial_call=True
    )
    def toggle_sidebar(n_clicks, current_class):
        if n_clicks:
            if "sidebar-open" in (current_class or ""):
                return "glass-sidebar"
            else:
                return "glass-sidebar sidebar-open"
        return no_update
    
    # Close sidebar when clicking a link (mobile)
    @app.callback(
        Output("main-sidebar", "className", allow_duplicate=True),
        Input("sidebar-link-dashboard", "n_clicks"),
        prevent_initial_call=True
    )
    def close_sidebar_on_click(*args):
        # Close sidebar on mobile after navigation
        return "glass-sidebar"
    
    # Add overlay when sidebar is open
    @app.callback(
        Output("sidebar-overlay", "className"),
        Input("main-sidebar", "className"),
        prevent_initial_call=False
    )
    def toggle_overlay(sidebar_class):
        if sidebar_class and "sidebar-open" in sidebar_class:
            return "sidebar-overlay active"
        return "sidebar-overlay"
    
    # Close sidebar when clicking overlay
    @app.callback(
        Output("main-sidebar", "className", allow_duplicate=True),
        Input("sidebar-overlay", "n_clicks"),
        prevent_initial_call=True
    )
    def close_sidebar_overlay(n_clicks):
        if n_clicks:
            return "glass-sidebar"
        return no_update
    
    # Clientside callback for better performance
    clientside_callback(
        ClientsideFunction(
            namespace="clientside",
            function_name="handleMobileMenu"
        ),
        Output("main-sidebar", "style"),
        Input("mobile-menu-toggle", "n_clicks"),
        State("main-sidebar", "style")
    )