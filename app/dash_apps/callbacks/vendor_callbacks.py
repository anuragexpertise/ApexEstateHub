from dash import Input, Output, State, no_update, html
import dash_bootstrap_components as dbc

# app/dash_apps/callbacks/vendor_callbacks.py
# Replace load_vendor_kpis to use real tables only:

def register_vendor_callbacks(app):

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
            db._execute(
                "INSERT INTO gate_access (society_id, entity_id, role, time_in) "
                "VALUES (%s, %s, 'v', NOW())",
                (sid, uid)
            )
            return {"type": "success", "message": f"Gate pass created for {name}"}
        except Exception as e:
            return {"type": "error", "message": str(e)}

    print("✓ Vendor callbacks registered")