from dash import Input, Output, State, html, no_update
import dash
import requests
from flask_login import logout_user
from app.services.auth_service import authenticate_user, authenticate_pin, authenticate_pattern
from app.services.society_service import get_societies, get_society_details
from app.dash_apps.pages.login import society_login_layout
from app.dash_apps.pages.society_select import society_select_layout
from app.dash_apps.pages.admin_portal import admin_portal_layout
from app.dash_apps.pages.owner_portal import owner_portal_layout
from app.dash_apps.pages.vendor_portal import vendor_portal_layout
from app.dash_apps.pages.security_portal import security_portal_layout
from app.dash_apps.pages.master_admin import layout as master_layout

def register_auth_callbacks(app):
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("society-select-btn", "n_clicks"),
        State("society-dropdown", "value"),
        State("remember-society-checkbox", "value"),
        prevent_initial_call=True
    )
    def select_society(n_clicks, society_id, remember_society):
        if not n_clicks or not society_id:
            return no_update, no_update, {"type": "error", "message": "Please select a society"}, no_update
        
        session_data = {"society_id": society_id, "authenticated": False}
        cookie_update = {"society_id": society_id} if remember_society else no_update
        
        return session_data, "/society-login", {"type": "success", "message": "Society selected"}, cookie_update
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("login-btn", "n_clicks"),
        State("login-email", "value"),
        State("login-password", "value"),
        State("auth-store", "data"),
        State("remember-me-checkbox", "value"),
        prevent_initial_call=True
    )
    def password_login(n_clicks, email, password, auth_data, remember):
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        
        society_id = auth_data.get("society_id") if auth_data else None
        user = authenticate_user(email, password, society_id)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid credentials"}, no_update
        
        user_dict = {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "society_id": user.society_id,
            "authenticated": True
        }
        
        cookie_data = no_update
        if remember:
            cookie_data = {"email": email, "society_id": society_id, "method": "password"}
        
        # Determine redirect
        if user.is_master_admin():
            redirect = "/master"
        elif user.role == "admin":
            redirect = "/admin-portal"
        elif user.role == "apartment":
            redirect = "/owner-portal"
        elif user.role == "vendor":
            redirect = "/vendor-portal"
        elif user.role == "security":
            redirect = "/pass-evaluation"
        else:
            redirect = "/"
        
        return user_dict, redirect, {"type": "success", "message": f"Welcome {email}"}, cookie_data
    
    @app.callback(
        Output("page-content", "children"),
        Output("navbar-container", "children"),
        Output("sidebar-container", "children"),
        Output("footer-container", "children"),
        Output("breadcrumb-container", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False
    )
    def router(pathname, auth_data):
        from app.dash_apps.components.header import create_header
        from app.dash_apps.components.sidebar import create_sidebar
        from app.dash_apps.components.footer import create_footer
        from app.dash_apps.components.breadcrumb import create_breadcrumb
        
        # Not authenticated
        if not auth_data or not auth_data.get("authenticated"):
            if pathname == "/society-login":
                return no_update, no_update, no_update, no_update, no_update
            
            try:
                societies = get_societies()
                if not societies:
                    return society_select_layout([], show_master_login=True), "", "", "", ""
                return society_select_layout(societies), "", "", "", ""
            except Exception as e:
                return html.Div([html.H2("Network Error"), html.P(str(e))]), "", "", "", ""
        
        # Authenticated
        role = auth_data.get("role")
        society_id = auth_data.get("society_id")
        email = auth_data.get("email")
        is_master = role == "admin" and society_id is None
        
        # Get society name
        society_name = "ApexEstateHub"
        if society_id:
            society = get_society_details(society_id)
            if society:
                society_name = society.get("name", "ApexEstateHub")
        
        # Create components
        header = create_header(society_name, role if not is_master else "master", email)
        sidebar = create_sidebar(role if not is_master else "admin", society_id)
        footer = create_footer()
        breadcrumb = create_breadcrumb(pathname)
        
        # Route to appropriate page
        if is_master:
            return master_layout(), header, sidebar, footer, breadcrumb
        elif role == "admin":
            # Extract active tab from pathname
            active_tab = pathname.split('/')[-1] if pathname != "/admin-portal" else "dashboard"
            return admin_portal_layout(active_tab), header, sidebar, footer, breadcrumb
        elif role == "apartment":
            active_tab = pathname.split('/')[-1] if pathname != "/owner-portal" else "dashboard"
            return owner_portal_layout(active_tab), header, sidebar, footer, breadcrumb
        elif role == "vendor":
            active_tab = pathname.split('/')[-1] if pathname != "/vendor-portal" else "dashboard"
            return vendor_portal_layout(active_tab), header, sidebar, footer, breadcrumb
        elif role == "security":
            active_tab = pathname.split('/')[-1] if pathname != "/pass-evaluation" else "pass_evaluation"
            return security_portal_layout(active_tab), header, sidebar, footer, breadcrumb
        
        return html.Div("Page not found"), header, sidebar, footer, breadcrumb
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("logout-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def logout(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update
        
        logout_user()
        return None, "/", {"type": "success", "message": "Logged out successfully"}