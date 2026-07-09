from dash import Input, Output, State, no_update, html
from datetime import datetime
import dash
from app.services.qr_service import validate_qr_code
from database.db_manager import db

def register_security_callbacks(app):
    
    @app.callback(
        Output("security-scan-result", "children"),
        Output("security-scan-result", "style"),
        Input("security-validate-btn", "n_clicks"),
        State("security-qr-input", "value"),
        prevent_initial_call=True
    )
    def validate_qr(n_clicks, qr_data):
        if not n_clicks or not qr_data:
            return no_update, no_update
        
        result = validate_qr_code(qr_data, None)
        
        if result.get("status") == "PASS":
            return html.Div([
                html.I(className="fas fa-check-circle fa-3x mb-2", style={"color": "#2ecc71"}),
                html.H4("Access Granted", style={"color": "#2ecc71"}),
                html.P(f"Welcome {result.get('user', {}).get('name', 'Visitor')}!"),
                html.Hr(),
                html.Small(f"Time: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            ]), {"backgroundColor": "#d4edda", "color": "#155724", "borderRadius": "10px"}
        else:
            return html.Div([
                html.I(className="fas fa-times-circle fa-3x mb-2", style={"color": "#e74c3c"}),
                html.H4("Access Denied", style={"color": "#e74c3c"}),
                html.P(result.get("reason", "Invalid QR code")),
                html.Hr(),
                html.Small("Please contact security administrator")
            ]), {"backgroundColor": "#f8d7da", "color": "#721c24", "borderRadius": "10px"}
    
    @app.callback(
        Output("attendance-status", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("clock-in-btn", "n_clicks"),
        Input("clock-out-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def manage_attendance(clock_in_clicks, clock_out_clicks, auth_data):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        society_id = (auth_data or {}).get("society_id")
        user_id = (auth_data or {}).get("user_id")
        if not user_id or not society_id:
            return no_update, {"type": "error", "message": "Session expired — please log in again"}

        now_str = datetime.now().strftime("%I:%M %p")

        # gate_access is the single source of truth for security shift
        # tracking (same table QR gate scans write to). role='s' is the
        # code used for security throughout gate_access/fn_evaluate_gate_pass.
        if button_id == "clock-in-btn":
            already_in = db._execute(
                """SELECT id FROM gate_access
                   WHERE society_id = %s AND entity_id = %s AND role = 's'
                     AND time_out IS NULL
                   ORDER BY time_in DESC LIMIT 1""",
                (society_id, user_id), fetch_one=True
            )
            if already_in:
                return no_update, {"type": "error", "message": "Already clocked in — clock out first"}

            db._execute(
                """INSERT INTO gate_access (society_id, role, entity_id, time_in)
                   VALUES (%s, 's', %s, NOW())""",
                (society_id, user_id)
            )
            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#2ecc71"}),
                html.H5("Clocked In"),
                html.Small(now_str)
            ]), {"type": "success", "message": "Clocked in successfully"}

        else:
            updated = db._execute(
                """UPDATE gate_access SET time_out = NOW()
                   WHERE id = (
                       SELECT id FROM gate_access
                       WHERE society_id = %s AND entity_id = %s AND role = 's'
                         AND time_out IS NULL
                       ORDER BY time_in DESC LIMIT 1
                   )
                   RETURNING id""",
                (society_id, user_id), fetch_one=True
            )
            if not updated:
                return no_update, {"type": "error", "message": "You're not clocked in"}

            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#e74c3c"}),
                html.H5("Clocked Out"),
                html.Small(now_str)
            ]), {"type": "success", "message": "Clocked out successfully"}