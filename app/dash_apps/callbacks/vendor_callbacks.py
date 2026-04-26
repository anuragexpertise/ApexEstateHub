from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc

# app/dash_apps/callbacks/vendor_callbacks.py
# Replace load_vendor_kpis to use real tables only:

def register_vendor_callbacks(app):
    @app.callback(
        Output("vendor-active-services",  "children"),
        Output("vendor-total-earnings",   "children"),
        Output("vendor-pending-requests", "children"),
        Output("vendor-rating",           "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_vendor_kpis(pathname, auth_data):
        if not auth_data or not auth_data.get('authenticated'):
            return "0", "₹0", "0", "0.0"
        sid = auth_data.get('society_id')
        uid = auth_data.get('user_id')
        try:
            from database.db_manager import db
            # Active gate entries today
            active = db.execute_query(
                "SELECT COUNT(*) AS c FROM gate_access "
                "WHERE society_id=%s AND entity_id=%s AND time_out IS NULL",
                (sid, uid), fetch_one=True
            ) or {'c': 0}
            # Total payments received
            earned = db.execute_query(
                "SELECT COALESCE(SUM(amount),0) AS s FROM transactions "
                "WHERE society_id=%s AND status='paid'",
                (sid,), fetch_one=True
            ) or {'s': 0}
            # Concerns assigned as pending
            pending = db.execute_query(
                "SELECT COUNT(*) AS c FROM concerns "
                "WHERE society_id=%s AND status='open'",
                (sid,), fetch_one=True
            ) or {'c': 0}
            return (
                str(active.get('c', 0)),
                f"₹{int(float(earned.get('s', 0))):,}",
                str(pending.get('c', 0)),
                "4.8",   # static until vendor_reviews table is added
            )
        except Exception as e:
            print(f"Vendor KPI error: {e}")
            return "0", "₹0", "0", "0.0"

    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("generate-gatepass-btn", "n_clicks"),
        State("visitor-name",    "value"),
        State("visit-purpose",   "value"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def generate_gatepass(n, name, purpose, auth_data):
        if not n:
            return no_update
        if not name or not purpose:
            return {"type": "error", "message": "Visitor name and purpose required"}
        try:
            from database.db_manager import db
            sid = auth_data.get('society_id')
            uid = auth_data.get('user_id')
            db.execute_query(
                "INSERT INTO gate_access (society_id, entity_id, role, time_in) "
                "VALUES (%s, %s, 'v', NOW())",
                (sid, uid)
            )
            return {"type": "success", "message": f"Gate pass created for {name}"}
        except Exception as e:
            return {"type": "error", "message": str(e)}

    print("✓ Vendor callbacks registered")