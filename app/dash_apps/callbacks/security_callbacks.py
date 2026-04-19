from dash import Input, Output, State, no_update, html
import dash
from app.services.qr_service import validate_qr_code

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
        
        # Validate QR code (mock for now)
        result = {"status": "PASS", "message": "Access granted", "user": {"name": "John Doe"}}
        
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
        prevent_initial_call=True
    )
    def manage_attendance(clock_in_clicks, clock_out_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if button_id == "clock-in-btn":
            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#2ecc71"}),
                html.H5("Clocked In"),
                html.Small(__import__('datetime').datetime.now().strftime("%I:%M %p"))
            ]), {"type": "success", "message": "Clocked in successfully"}
        else:
            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#e74c3c"}),
                html.H5("Clocked Out"),
                html.Small(__import__('datetime').datetime.now().strftime("%I:%M %p"))
            ]), {"type": "success", "message": "Clocked out successfully"}