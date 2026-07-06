# app/dash_apps/callbacks/admin_callbacks.py
"""
Admin-portal callbacks.

PRUNED from the original file: update_society_count, update_recent_societies,
and enroll_member were removed. All three targeted component IDs
(total-societies, recent-societies-list, enroll-name/email/phone/role/flat/
area/password/confirm/enroll-submit-btn) that don't exist anywhere in the
current portal_pages.py layout — the master portal already surfaces society
counts through the generic KPI system (kpi_societies_total), and the admin
Enroll tab now uses the schema-driven "New" button flow
(drilldown_callbacks.py's _save_user_entity / _save_apartment) instead of a
dedicated enroll form. Keeping them registered would just be inert dead code
duplicating logic that already exists elsewhere.

validate_qr_code_admin is kept — it's a genuinely distinct feature (manual
paste-and-validate QR entry) rather than a duplicate of the camera-based
entry/exit scanner in qr_callbacks.py. It reads from "manual-qr-input"
rather than "qr-scan-input" deliberately: qr-scan-input is a hidden element
already owned by the camera pipeline in qr_callbacks.py/portal_pages.py's
_evaluate_pass_page(), and that page is shared by both the admin and
security portals — reusing its id for a second, visible field would create
a duplicate-component-ID error. The manual-entry panel (added to
_evaluate_pass_page(), so it renders on both portals) uses manual-qr-input /
validate-qr-btn / qr-validation-result, all distinct from the camera
pipeline's ids.
"""

from dash import Input, Output, State, html, no_update
from datetime import datetime


def register_admin_callbacks(app):

    @app.callback(
        Output("qr-validation-result", "children"),
        Input("validate-qr-btn", "n_clicks"),
        State("manual-qr-input", "value"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def validate_qr_code_admin(n_clicks, qr_data, auth_data):
        if not n_clicks or not qr_data:
            return no_update
        try:
            from app.services.qr_service import validate_qr_code
            # Pass the current society_id (was hardcoded None before) so the
            # manual path enforces the same cross-society check the camera
            # pipeline already does in qr_callbacks.py.
            society_id = (auth_data or {}).get("society_id")
            result = validate_qr_code(qr_data, society_id)
            if result.get("status") == "PASS":
                return html.Div([
                    html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                    html.H4("Access Granted", style={"color": "#2ecc71", "marginTop": "10px"}),
                    html.P(f"Welcome {result.get('user', {}).get('name', 'Visitor')}!"),
                    html.Hr(),
                    html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
                ], className="text-center p-3",
                   style={"backgroundColor": "#d4edda", "borderRadius": "10px"})
            return html.Div([
                html.I(className="fas fa-times-circle fa-2x", style={"color": "#e74c3c"}),
                html.H4("Access Denied", style={"color": "#e74c3c", "marginTop": "10px"}),
                html.P(result.get("reason", "Invalid QR code")),
                html.Hr(),
                html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            ], className="text-center p-3",
               style={"backgroundColor": "#f8d7da", "borderRadius": "10px"})
        except Exception as e:
            return html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x", style={"color": "#f39c12"}),
                html.H4("Error", style={"color": "#f39c12", "marginTop": "10px"}),
                html.P(str(e)),
            ], className="text-center p-3",
               style={"backgroundColor": "#fff3cd", "borderRadius": "10px"})

    print("  ✓ Admin callbacks registered (manual QR validate)")
