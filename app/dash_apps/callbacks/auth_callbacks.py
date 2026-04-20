from dash import Input, Output, State, html, no_update
import dash
from flask_login import logout_user
from app.services.auth_service import authenticate_user, authenticate_pin, authenticate_pattern
from app.services.society_service import get_societies, get_society_details
from app.dash_apps.pages.login import society_login_layout
from app.dash_apps.pages.login import society_login_layout
from app.dash_apps.pages.society_select import society_select_layout
from app.dash_apps.pages.admin_portal import admin_portal_layout
from app.dash_apps.pages.owner_portal import owner_portal_layout
from app.dash_apps.pages.vendor_portal import vendor_portal_layout
from app.dash_apps.pages.security_portal import security_portal_layout
from app.dash_apps.pages.master_admin import layout as master_layout

def register_auth_callbacks(app):
    
    # ============================================
    # MAIN ROUTER - Handles all page navigation
    # ============================================
    @app.callback(
        Output("page-content", "children"),
        Output("navbar-container", "children"),
        Output("sidebar-container", "children"),
        Output("footer-container", "children"),
        Output("breadcrumb-container", "children"),
        Output("society-login-container", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False
    )
    def router(pathname, auth_data):
        """Main routing logic with all navbar components"""
        
        print(f"\n=== ROUTER CALLED ===")
        print(f"Pathname: {pathname}")
        print(f"Auth data: {auth_data}")
        
        # ============================================
        # CASE 1: NOT AUTHENTICATED
        # ============================================
        if not auth_data or not auth_data.get('authenticated'):
            print("User not authenticated")
            
            # Society login page (secondary login)
            if pathname == "/society-login":
                society_id = auth_data.get('society_id') if auth_data else None
                if society_id:
                    society = get_society_details(society_id)
                    society_name = society.get('name', 'EstateHub') if society else 'EstateHub'
                else:
                    society_name = "EstateHub"
                
                login_page = society_login_layout(society_name)
                return login_page, "", "", "", "", ""
            
            # Society selection page (primary login)
            try:
                societies = get_societies()
                if not societies or len(societies) == 0:
                    return society_select_layout([], show_master_login=True), "", "", "", "", ""
                return society_select_layout(societies), "", "", "", "", ""
            except Exception as e:
                print(f"Error loading societies: {e}")
                error_page = html.Div([
                    html.H2("Network Error", style={"color": "red", "textAlign": "center"}),
                    html.P(str(e), style={"textAlign": "center"}),
                    html.Button("Retry Connection", id="retry-connection-btn", 
                               style={"display": "block", "margin": "20px auto", "padding": "10px 20px"})
                ], style={"padding": "40px"})
                return error_page, "", "", "", "", ""
        
        # ============================================
        # CASE 2: AUTHENTICATED
        # ============================================
        print("User authenticated - loading dashboard")
        
        # Get navbar components
        from app.dash_apps.components.navbar import get_navbar_components
        header, sidebar, breadcrumb, footer = get_navbar_components(auth_data, pathname)
        
        role = auth_data.get('role')
        society_id = auth_data.get('society_id')
        is_master = (role == 'admin' and society_id is None)
        
        print(f"Role: {role}, Is Master: {is_master}")
        
        # ============================================
        # MASTER ADMIN ROUTES
        # ============================================
        if is_master:
            return master_layout(), header, sidebar, footer, breadcrumb, ""
        
        # ============================================
        # ADMIN ROUTES
        # ============================================
        if role == 'admin':
            # Extract active tab from pathname
            if pathname in ["/admin-portal", "/dashboard/admin-portal", "/admin-portal/"]:
                active_tab = "dashboard"
            elif "/cashbook" in pathname:
                active_tab = "cashbook"
            elif "/receipts" in pathname:
                active_tab = "receipts"
            elif "/expenses" in pathname:
                active_tab = "expenses"
            elif "/enroll" in pathname:
                active_tab = "enroll"
            elif "/users" in pathname:
                active_tab = "users"
            elif "/events" in pathname:
                active_tab = "events"
            elif "/evaluate-pass" in pathname:
                active_tab = "evaluate_pass"
            elif "/customize" in pathname:
                active_tab = "customize"
            elif "/settings" in pathname:
                active_tab = "settings"
            else:
                active_tab = "dashboard"
            
            return admin_portal_layout(active_tab), header, sidebar, footer, breadcrumb, ""
        
        # ============================================
        # OWNER/APARTMENT ROUTES
        # ============================================
        if role == 'apartment':
            if pathname in ["/owner-portal", "/dashboard/owner-portal"]:
                active_tab = "dashboard"
            elif "/owner-cashbook" in pathname or "/cashbook" in pathname:
                active_tab = "cashbook"
            elif "/payments" in pathname:
                active_tab = "payments"
            elif "/charges" in pathname:
                active_tab = "charges"
            elif "/owner-events" in pathname or "/events" in pathname:
                active_tab = "events"
            elif "/owner-settings" in pathname or "/settings" in pathname:
                active_tab = "settings"
            else:
                active_tab = "dashboard"
            
            return owner_portal_layout(active_tab), header, sidebar, footer, breadcrumb, ""
        
        # ============================================
        # VENDOR ROUTES
        # ============================================
        if role == 'vendor':
            if pathname in ["/vendor-portal", "/dashboard/vendor-portal"]:
                active_tab = "dashboard"
            elif "/vendor-cashbook" in pathname:
                active_tab = "vendor_cashbook"
            elif "/vendor-payments" in pathname:
                active_tab = "vendor_payments"
            elif "/vendor-charges" in pathname:
                active_tab = "vendor_charges"
            elif "/vendor-events" in pathname:
                active_tab = "vendor_events"
            elif "/vendor-settings" in pathname:
                active_tab = "vendor_settings"
            else:
                active_tab = "dashboard"
            
            return vendor_portal_layout(active_tab), header, sidebar, footer, breadcrumb, ""
        
        # ============================================
        # SECURITY ROUTES
        # ============================================
        if role == 'security':
            if pathname in ["/pass-evaluation", "/dashboard/pass-evaluation"]:
                active_tab = "pass_evaluation"
            elif "/attendance" in pathname:
                active_tab = "attendance"
            elif "/security-events" in pathname:
                active_tab = "security_events"
            elif "/security-receipt" in pathname:
                active_tab = "security_receipt"
            elif "/security-users" in pathname:
                active_tab = "security_users"
            elif "/security-settings" in pathname:
                active_tab = "security_settings"
            else:
                active_tab = "pass_evaluation"
            
            return security_portal_layout(active_tab), header, sidebar, footer, breadcrumb, ""
        
        # ============================================
        # FALLBACK
        # ============================================
        return html.Div("Page not found"), header, sidebar, footer, breadcrumb, ""
    
    # ============================================
    # SOCIETY SELECTION CALLBACK
    # ============================================
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
        """Handle society selection from primary login page"""
        if not n_clicks or not society_id:
            return no_update, no_update, {"type": "error", "message": "Please select a society"}, no_update
        
        auth_data = {
            "society_id": society_id,
            "authenticated": False
        }
        
        # Handle remember checkbox - it returns a list when checked
        cookie_update = no_update
        if remember_society and len(remember_society) > 0:
            cookie_update = {"society_id": society_id}
        
        return auth_data, "/society-login", {"type": "success", "message": "Society selected"}, cookie_update
    
    # ============================================
    # PASSWORD LOGIN CALLBACK
    # ============================================
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
        """Handle password-based login"""
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        
        if not email or not password:
            return no_update, no_update, {"type": "error", "message": "Please enter email and password"}, no_update
        
        society_id = auth_data.get("society_id") if auth_data else None
        user = authenticate_user(email, password, society_id)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid email or password"}, no_update
        
        # Convert user to dict for storage
        user_dict = {
            "user_id": user['user_id'] if isinstance(user, dict) else user.id,
            "email": user['email'] if isinstance(user, dict) else user.email,
            "role": user['role'] if isinstance(user, dict) else user.role,
            "society_id": user['society_id'] if isinstance(user, dict) else user.society_id,
            "authenticated": True
        }
        
        cookie_data = no_update
        if remember and len(remember) > 0:
            cookie_data = {"email": email, "society_id": society_id, "method": "password"}
        
        # Determine redirect based on role
        role = user_dict['role']
        user_society_id = user_dict['society_id']
        
        if role == 'admin' and user_society_id is None:
            redirect = "/dashboard/master"
        elif role == 'admin':
            redirect = "/dashboard/admin-portal"
        elif role == 'apartment':
            redirect = "/dashboard/owner-portal"
        elif role == 'vendor':
            redirect = "/dashboard/vendor-portal"
        elif role == 'security':
            redirect = "/dashboard/pass-evaluation"
        else:
            redirect = "/dashboard"
        
        return user_dict, redirect, {"type": "success", "message": f"Welcome {email}"}, cookie_data
    
    # ============================================
    # PIN LOGIN CALLBACK
    # ============================================
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("login-pin-btn", "n_clicks"),
        State("login-email-pin", "value"),
        State("login-pin", "value"),
        State("auth-store", "data"),
        State("remember-me-checkbox", "value"),
        prevent_initial_call=True
    )
    def pin_login(n_clicks, email, pin, auth_data, remember):
        """Handle PIN-based login"""
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        
        if not email or not pin:
            return no_update, no_update, {"type": "error", "message": "Please enter email and PIN"}, no_update
        
        society_id = auth_data.get("society_id") if auth_data else None
        user = authenticate_pin(email, pin, society_id)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid email or PIN"}, no_update
        
        user_dict = {
            "user_id": user['user_id'] if isinstance(user, dict) else user.id,
            "email": user['email'] if isinstance(user, dict) else user.email,
            "role": user['role'] if isinstance(user, dict) else user.role,
            "society_id": user['society_id'] if isinstance(user, dict) else user.society_id,
            "authenticated": True
        }
        
        cookie_data = no_update
        if remember and len(remember) > 0:
            cookie_data = {"email": email, "society_id": society_id, "method": "pin"}
        
        # Determine redirect based on role
        role = user_dict['role']
        user_society_id = user_dict['society_id']
        
        if role == 'admin' and user_society_id is None:
            redirect = "/dashboard/master"
        elif role == 'admin':
            redirect = "/dashboard/admin-portal"
        elif role == 'apartment':
            redirect = "/dashboard/owner-portal"
        elif role == 'vendor':
            redirect = "/dashboard/vendor-portal"
        elif role == 'security':
            redirect = "/dashboard/pass-evaluation"
        else:
            redirect = "/dashboard"
        
        return user_dict, redirect, {"type": "success", "message": f"Welcome {email}"}, cookie_data
    
    # ============================================
    # PATTERN LOGIN CALLBACK
    # ============================================
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("cookie-store", "data", allow_duplicate=True),
        Input("login-pattern-btn", "n_clicks"),
        State("login-email-pattern", "value"),
        State("login-pattern", "value"),
        State("auth-store", "data"),
        State("remember-me-checkbox", "value"),
        prevent_initial_call=True
    )
    def pattern_login(n_clicks, email, pattern, auth_data, remember):
        """Handle pattern-based login"""
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        
        if not email or not pattern:
            return no_update, no_update, {"type": "error", "message": "Please enter email and pattern"}, no_update
        
        society_id = auth_data.get("society_id") if auth_data else None
        user = authenticate_pattern(email, pattern, society_id)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid email or pattern"}, no_update
        
        user_dict = {
            "user_id": user['user_id'] if isinstance(user, dict) else user.id,
            "email": user['email'] if isinstance(user, dict) else user.email,
            "role": user['role'] if isinstance(user, dict) else user.role,
            "society_id": user['society_id'] if isinstance(user, dict) else user.society_id,
            "authenticated": True
        }
        
        cookie_data = no_update
        if remember and len(remember) > 0:
            cookie_data = {"email": email, "society_id": society_id, "method": "pattern"}
        
        # Determine redirect based on role
        role = user_dict['role']
        user_society_id = user_dict['society_id']
        
        if role == 'admin' and user_society_id is None:
            redirect = "/dashboard/master"
        elif role == 'admin':
            redirect = "/dashboard/admin-portal"
        elif role == 'apartment':
            redirect = "/dashboard/owner-portal"
        elif role == 'vendor':
            redirect = "/dashboard/vendor-portal"
        elif role == 'security':
            redirect = "/dashboard/pass-evaluation"
        else:
            redirect = "/dashboard"
        
        return user_dict, redirect, {"type": "success", "message": f"Welcome {email}"}, cookie_data
    
    # ============================================
    # MASTER ADMIN LOGIN CALLBACK
    # ============================================
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        State("master-admin-email", "value"),
        State("master-admin-password", "value"),
        prevent_initial_call=True
    )
    def master_admin_login(n_clicks, email, password):
        """Handle master admin login from society select page"""
        if not n_clicks:
            return no_update, no_update, no_update
        
        if not email or not password:
            return no_update, no_update, {"type": "error", "message": "Please enter email and password"}
        
        user = authenticate_user(email, password)
        
        if not user:
            return no_update, no_update, {"type": "error", "message": "Invalid master admin credentials"}
        
        # Check if user is actually master admin (society_id is None)
        user_role = user['role'] if isinstance(user, dict) else user.role
        user_society_id = user['society_id'] if isinstance(user, dict) else user.society_id
        
        if user_role != 'admin' or user_society_id is not None:
            return no_update, no_update, {"type": "error", "message": "Not authorized as master admin"}
        
        user_dict = {
            "user_id": user['user_id'] if isinstance(user, dict) else user.id,
            "email": user['email'] if isinstance(user, dict) else user.email,
            "role": "admin",
            "society_id": None,
            "authenticated": True
        }
        
        return user_dict, "/dashboard/master", {"type": "success", "message": "Welcome Master Admin"}
    
    # ============================================
    # LOGOUT CALLBACK
    # ============================================
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("logout-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def logout(n_clicks):
        """Handle user logout"""
        if not n_clicks:
            return no_update, no_update, no_update
        
        # Logout from Flask-Login
        logout_user()
        
        return None, "/dashboard", {"type": "success", "message": "Logged out successfully"}
    
    # ============================================
    # RETRY CONNECTION CALLBACK
    # ============================================
    @app.callback(
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("retry-connection-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def retry_connection(n_clicks):
        """Retry database connection"""
        if not n_clicks:
            return no_update, no_update
        
        try:
            societies = get_societies()
            if societies:
                return "/dashboard", {"type": "success", "message": f"Connected! Found {len(societies)} societies"}
            else:
                return "/dashboard", {"type": "warning", "message": "Connected but no societies found"}
        except Exception as e:
            return "/dashboard", {"type": "error", "message": f"Connection failed: {str(e)}"}