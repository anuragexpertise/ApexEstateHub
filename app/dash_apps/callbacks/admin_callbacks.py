from dash import Input, Output, State, html, no_update
import dash
import dash_bootstrap_components as dbc
import json
from datetime import datetime

def register_admin_callbacks(app):
    
    @app.callback(
        Output("total-societies", "children"),
        Input("url", "pathname"),
        prevent_initial_call=False
    )
    def update_society_count(pathname):
        """Update total societies count"""
        try:
            from database.db_manager import db
            result = db.execute_query("SELECT COUNT(*) as count FROM societies", fetch_one=True)
            return str(result['count']) if result else "0"
        except Exception as e:
            print(f"Error updating society count: {e}")
            return "0"
    
    @app.callback(
        Output("recent-societies-list", "children"),
        Input("url", "pathname"),
        prevent_initial_call=False
    )
    def update_recent_societies(pathname):
        """Update recent societies list"""
        try:
            from database.db_manager import db
            societies = db.execute_query(
                "SELECT id, name, email, created_at FROM societies ORDER BY created_at DESC LIMIT 5",
                fetch_all=True
            )
            
            if not societies:
                return html.P("No societies added yet", className="text-muted text-center")
            
            items = []
            for society in societies:
                items.append(
                    dbc.ListGroupItem([
                        html.Div([
                            html.Strong(society.get('name', 'Unknown')),
                            html.Small(f" - {society.get('email', 'No email')}", className="text-muted ms-2"),
                            html.Br(),
                            html.Small(f"Added: {str(society.get('created_at', 'Unknown'))[:10]}", className="text-muted")
                        ])
                    ], className="mb-2")
                )
            return dbc.ListGroup(items)
        except Exception as e:
            print(f"Error loading societies: {e}")
            import traceback
            traceback.print_exc()
            return html.P(f"Error loading societies: {str(e)}", className="text-danger text-center")
    
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("enroll-submit-btn", "n_clicks"),
        State("enroll-name", "value"),
        State("enroll-email", "value"),
        State("enroll-phone", "value"),
        State("enroll-role", "value"),
        State("enroll-flat", "value"),
        State("enroll-area", "value"),
        State("enroll-password", "value"),
        State("enroll-confirm", "value"),
        prevent_initial_call=True
    )
    def enroll_member(n_clicks, name, email, phone, role, flat, area, password, confirm):
        """Enroll a new member"""
        if not n_clicks:
            return no_update
        
        if not name or not email or not role:
            return {"type": "error", "message": "Please fill all required fields"}
        
        if password != confirm:
            return {"type": "error", "message": "Passwords do not match"}
        
        if not password:
            return {"type": "error", "message": "Please enter a password"}
        
        try:
            from database.db_manager import db
            from werkzeug.security import generate_password_hash
            
            hashed_password = generate_password_hash(password)
            
            # Check if user already exists
            check_query = "SELECT id FROM users WHERE email = %s"
            existing = db.execute_query(check_query, (email,), fetch_one=True)
            
            if existing:
                return {"type": "error", "message": f"User with email {email} already exists"}
            
            # Get society_id from session (you'll need to pass this)
            # For now, get the first society
            society_result = db.execute_query("SELECT id FROM societies LIMIT 1", fetch_one=True)
            society_id = society_result['id'] if society_result else None
            
            if not society_id:
                return {"type": "error", "message": "No society found. Please create a society first."}
            
            insert_query = """
                INSERT INTO users (society_id, email, password_hash, role, login_method)
                VALUES (%s, %s, %s, %s, 'password')
                RETURNING id
            """
            result = db.execute_query(insert_query, (society_id, email, hashed_password, role), fetch_one=True)
            
            if result:
                # If role is apartment, also create apartment record
                if role == 'apartment' and flat:
                    apt_query = """
                        INSERT INTO apartments (society_id, flat_number, owner_name, apartment_size, active)
                        VALUES (%s, %s, %s, %s, TRUE)
                        RETURNING id
                    """
                    apt_result = db.execute_query(apt_query, (society_id, flat, name, area or 0), fetch_one=True)
                    if apt_result:
                        # Link user to apartment
                        update_user = "UPDATE users SET linked_id = %s WHERE id = %s"
                        db.execute_query(update_user, (apt_result['id'], result['id']))
                
                return {"type": "success", "message": f"Member {name} enrolled successfully!"}
            else:
                return {"type": "error", "message": "Failed to enroll member"}
        except Exception as e:
            print(f"Enrollment error: {e}")
            import traceback
            traceback.print_exc()
            return {"type": "error", "message": f"Error: {str(e)}"}
    
    @app.callback(
        Output("qr-validation-result", "children"),
        Input("validate-qr-btn", "n_clicks"),
        State("qr-scan-input", "value"),
        prevent_initial_call=True
    )
    def validate_qr_code(n_clicks, qr_data):
        """Validate QR code for gate access"""
        if not n_clicks or not qr_data:
            return no_update
        
        try:
            from database.db_manager import db
            from app.services.qr_service import validate_qr_code
            
            # Validate the QR code
            result = validate_qr_code(qr_data, None)  # society_id will be determined from session
            
            if result.get('status') == 'PASS':
                return html.Div([
                    html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                    html.H4("Access Granted", style={"color": "#2ecc71", "marginTop": "10px"}),
                    html.P(f"Welcome {result.get('user', {}).get('name', 'Visitor')}!"),
                    html.Hr(),
                    html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                ], className="text-center p-3", style={"backgroundColor": "#d4edda", "borderRadius": "10px"})
            else:
                return html.Div([
                    html.I(className="fas fa-times-circle fa-2x", style={"color": "#e74c3c"}),
                    html.H4("Access Denied", style={"color": "#e74c3c", "marginTop": "10px"}),
                    html.P(result.get('reason', 'Invalid QR code')),
                    html.Hr(),
                    html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                ], className="text-center p-3", style={"backgroundColor": "#f8d7da", "borderRadius": "10px"})
        except Exception as e:
            return html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x", style={"color": "#f39c12"}),
                html.H4("Error", style={"color": "#f39c12", "marginTop": "10px"}),
                html.P(str(e))
            ], className="text-center p-3", style={"backgroundColor": "#fff3cd", "borderRadius": "10px"})
        
    @app.callback(
        Output("total-users",    "children"),
        Output("total-revenue",  "children"),
        Output("pending-dues",   "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def update_admin_kpis(pathname, auth_data):
        sid = (auth_data or {}).get('society_id')
        try:
            from database.db_manager import db
            users = db.execute_query(
                "SELECT COUNT(*) AS c FROM users WHERE society_id=%s", (sid,), fetch_one=True
            ) or {'c': 0}
            revenue = db.execute_query(
                "SELECT COALESCE(SUM(amount),0) AS s FROM transactions "
                "WHERE society_id=%s AND status='paid' "
                "AND trx_date >= date_trunc('month', CURRENT_DATE)",
                (sid,), fetch_one=True
            ) or {'s': 0}
            dues = db.execute_query(
                "SELECT COALESCE(SUM(amount),0) AS s FROM payments "
                "WHERE society_id=%s AND status='pending'",
                (sid,), fetch_one=True
            ) or {'s': 0}
            return (
                str(users.get('c', 0)),
                f"₹{int(float(revenue.get('s', 0))):,}",
                f"₹{int(float(dues.get('s', 0))):,}",
            )
        except Exception as e:
            print(f"Admin KPI error: {e}")
            return "0", "₹0", "₹0"