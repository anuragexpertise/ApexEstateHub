from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc

def register_vendor_callbacks(app):
    
    @app.callback(
        Output("vendor-active-services", "children"),
        Output("vendor-total-earnings", "children"),
        Output("vendor-pending-requests", "children"),
        Output("vendor-rating", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_vendor_kpis(pathname, auth_data):
        if not auth_data or not auth_data.get('authenticated'):
            return "0", "₹0", "0", "0.0"
        
        society_id = auth_data.get('society_id')
        user_id = auth_data.get('user_id')
        
        try:
            from database.db_manager import db
            
            # Active services count
            active = db.execute_query(
                "SELECT COUNT(*) FROM service_requests "
                "WHERE vendor_id = %s AND status = 'in_progress'",
                (user_id,), fetch_one=True
            ) or {"count": 0}
            
            # Total earnings
            earnings = db.execute_query(
                "SELECT COALESCE(SUM(amount), 0) FROM payments "
                "WHERE vendor_id = %s AND status = 'verified'",
                (user_id,), fetch_one=True
            ) or {"sum": 0}
            
            # Pending requests
            pending = db.execute_query(
                "SELECT COUNT(*) FROM service_requests "
                "WHERE vendor_id = %s AND status = 'pending'",
                (user_id,), fetch_one=True
            ) or {"count": 0}
            
            # Rating
            rating = db.execute_query(
                "SELECT COALESCE(AVG(rating), 0) FROM vendor_reviews "
                "WHERE vendor_id = %s",
                (user_id,), fetch_one=True
            ) or {"avg": 0}
            
            return (
                str(active.get('count', 0)),
                f"₹{int(earnings.get('sum', 0)):,}",
                str(pending.get('count', 0)),
                f"{float(rating.get('avg', 0)):.1f}"
            )
        except Exception as e:
            print(f"Vendor KPI error: {e}")
            return "0", "₹0", "0", "0.0"
    
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("generate-gatepass-btn", "n_clicks"),
        State("visitor-name", "value"),
        State("visitor-phone", "value"),
        State("visit-purpose", "value"),
        State("gatepass-validity", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def generate_gatepass(n_clicks, name, phone, purpose, valid_date, auth_data):
        if not n_clicks:
            return no_update
        
        if not name or not purpose:
            return {"type": "error", "message": "Visitor name and purpose required"}
        
        try:
            from database.db_manager import db
            society_id = auth_data.get('society_id')
            user_id = auth_data.get('user_id')
            
            db.execute_query(
                """INSERT INTO gate_access 
                   (society_id, entity_id, role, time_in, time_out, visitor_name, purpose)
                   VALUES (%s, %s, 'v', NOW(), NULL, %s, %s)""",
                (society_id, user_id, name, purpose)
            )
            return {"type": "success", "message": f"Gate pass generated for {name}"}
        except Exception as e:
            return {"type": "error", "message": str(e)}
    
    print("✓ Vendor callbacks registered")