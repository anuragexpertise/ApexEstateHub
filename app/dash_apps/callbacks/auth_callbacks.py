from dash import Input, Output, State, html, no_update
import dash
from flask_login import login_user, logout_user, current_user
from app.services.auth_service import authenticate_user
from app.services.society_service import get_societies, get_society_details
from app.dash_apps.pages.society_select import society_select_layout
from app.dash_apps.pages.login import society_login_layout
from app.dash_apps.pages.master_admin import layout as master_layout
from app.dash_apps.pages.admin_portal import admin_portal_layout
from app.dash_apps.pages.owner_portal import owner_portal_layout
from app.dash_apps.pages.vendor_portal import vendor_portal_layout
from app.dash_apps.pages.security_portal import security_portal_layout

def register_auth_callbacks(app):
    
    @app.callback(
        Output("page-content", "children"),
        Output("sidebar-container", "children"),
        Output("navbar-container", "children"),
        Output("footer-container", "children"),
        Output("society-login-container", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False
    )
    def router(pathname, auth_data):
        """Main routing logic"""
        print(f"\n=== ROUTER CALLED ===")
        print(f"Pathname: {pathname}")
        print(f"Auth data: {auth_data}")
        
        # Check if user is authenticated
        is_authenticated = auth_data and auth_data.get('authenticated', False)
        
        # Society login page (secondary login)
        if pathname == "/society-login":
            society_id = auth_data.get('society_id') if auth_data else None
            if society_id:
                society = get_society_details(society_id)
                society_name = society.get('name', 'EstateHub') if society else 'EstateHub'
            else:
                society_name = "EstateHub"
            
            login_page = society_login_layout(society_name)
            return login_page, "", "", "", ""
        
        # Not authenticated - show society selection
        if not is_authenticated:
            try:
                societies = get_societies()
                if not societies or len(societies) == 0:
                    return society_select_layout([], show_master_login=True), "", "", "", ""
                return society_select_layout(societies), "", "", "", ""
            except Exception as e:
                return html.Div([
                    html.H2("Error Loading Societies", style={"color": "red"}),
                    html.P(str(e))
                ]), "", "", "", ""
        
        # Authenticated user
        role = auth_data.get('role')
        society_id = auth_data.get('society_id')
        
        # Master Admin
        if role == 'admin' and society_id is None:
            return master_layout(), "", "", "", ""
        
        # Role-based dashboards
        if role == 'admin':
            return admin_portal_layout("dashboard"), "", "", "", ""
        elif role == 'apartment':
            return owner_portal_layout("dashboard"), "", "", "", ""
        elif role == 'vendor':
            return vendor_portal_layout("dashboard"), "", "", "", ""
        elif role == 'security':
            return security_portal_layout("pass_evaluation"), "", "", "", ""
        
        # Default
        return html.Div("Unknown role"), "", "", "", ""
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("society-select-btn", "n_clicks"),
        State("society-dropdown", "value"),
        prevent_initial_call=True
    )
    def select_society(n_clicks, society_id):
        """Handle society selection"""
        if not n_clicks or not society_id:
            return no_update, no_update, {"type": "error", "message": "Please select a society"}
        
        auth_data = {
            "society_id": society_id,
            "authenticated": False
        }
        
        return auth_data, "/society-login", {"type": "success", "message": "Society selected"}
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("login-btn", "n_clicks"),
        State("login-email", "value"),
        State("login-password", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def handle_login(n_clicks, email, password, auth_data):
        """Handle login"""
        if not n_clicks:
            return no_update, no_update, no_update
        
        if not email or not password:
            return no_update, no_update, {"type": "error", "message": "Please enter email and password"}
        
        society_id = auth_data.get("society_id") if auth_data else None
        user = authenticate_user(email, password, society_id)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid credentials"}
        
        # Convert user to dict for storage
        user_dict = {
            "user_id": user['user_id'] if isinstance(user, dict) else user.id,
            "email": user['email'] if isinstance(user, dict) else user.email,
            "role": user['role'] if isinstance(user, dict) else user.role,
            "society_id": user['society_id'] if isinstance(user, dict) else user.society_id,
            "authenticated": True
        }
        
        # Determine redirect
        role = user_dict['role']
        user_society_id = user_dict['society_id']
        
        if role == 'admin' and user_society_id is None:
            redirect = "/master"
        elif role == 'admin':
            redirect = "/admin-portal"
        elif role == 'apartment':
            redirect = "/owner-portal"
        elif role == 'vendor':
            redirect = "/vendor-portal"
        elif role == 'security':
            redirect = "/pass-evaluation"
        else:
            redirect = "/"
        
        return user_dict, redirect, {"type": "success", "message": f"Welcome {email}"}
    
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("logout-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def logout(n_clicks):
        """Handle logout"""
        if not n_clicks:
            return no_update, no_update, no_update
        
        return None, "/", {"type": "success", "message": "Logged out successfully"}