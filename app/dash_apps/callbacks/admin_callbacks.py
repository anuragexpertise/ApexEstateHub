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

validate_qr_code_admin has been RETIRED (2026-07) — replaced by
qr_callbacks.py's validate_manual_qr_scoped, which is the same manual
paste-and-validate QR feature but modularized (render_manual_qr_card +
a single scope-pattern-matched callback) so it can render on more than one
page. The old version only ever showed a generic "Access Granted" card and
never actually opened anything for concern/receipt/expense/asset QR types;
the new one opens the real concern profile inline. It used ids
manual-qr-input / validate-qr-btn / qr-validation-result — those are now
{"type": "manual-qr-input"/"manual-qr-validate-btn"/"manual-qr-result",
"scope": <page>}, scoped per page (e.g. "pass_evaluation",
"vendor_concern_lookup") so multiple instances can coexist without
colliding.
"""

from dash import Input, Output, State, html, no_update
from datetime import datetime

from app.security.guards import require_session
from app.services.society_service import create_society


def register_admin_callbacks(app):
    # ── 0. CREATE SOCIETY (Master portal) ─────────────────────────────────────
    @app.callback(
        Output("master-create-result", "children"),
        Input("master-create-society-btn", "n_clicks"),
        State("new-society-name", "value"),
        State("new-society-address", "value"),
        State("new-society-pan", "value"),
        State("new-society-reg-num", "value"),
        State("new-society-email", "value"),
        State("new-society-password", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def handle_create_society(n_clicks, name, address, pan, reg_num, email, password):
        if not n_clicks or not name or not address or not pan or not reg_num or not email or not password:
            raise PreventUpdate
        if len(password) < 8:
            return html.Div([
                html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#e59620"}),
                "Password must be at least 8 characters.",
            ], className="alert alert-warning mt-2")
        try:
            sid = create_society({
                "name": name.strip(),
                "address": address.strip(),
                "pan": pan.strip(),
                "reg_num": reg_num.strip(),
                "admin_email": email.strip(),
                "admin_password": password,
            })
            if sid:
                return html.Div([
                    html.I(className="fas fa-check-circle me-2", style={"color": "#17976e"}),
                    f"Society '{name}' created successfully! (ID: {sid})",
                ], className="alert alert-success mt-2")
            return html.Div([
                html.I(className="fas fa-exclamation-circle me-2", style={"color": "#de5c52"}),
                "Failed to create society. Please try again.",
            ], className="alert alert-danger mt-2")
        except Exception as e:
            return html.Div([
                html.I(className="fas fa-exclamation-circle me-2", style={"color": "#de5c52"}),
                f"Error: {str(e)[:120]}",
            ], className="alert alert-danger mt-2")

    # ── 1. CLEAR CREATE-SOCIETY FORM ──────────────────────────────────────────
    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var fields = ['new-society-name','new-society-address','new-society-pan','new-society-reg-num','new-society-email','new-society-password'];
            fields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { el.value = ''; el.dispatchEvent(new Event('input',{bubbles:true})); }
            });
            return '';
        }
        """,
        Output("new-society-name", "value", allow_duplicate=True),
        Input("master-clear-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    print("  ✓ Admin callbacks registered (manual QR validate moved to qr_callbacks.py)")
