from dash import Input, Output, State, ALL, callback, no_update, html, ctx
import dash_bootstrap_components as dbc
import hashlib
import hmac
from database.db_manager import db
from app.dash_apps.pages.setup_wizard import get_setup_wizard_layout, CATEGORIES, CONVERSATION_DATA, render_category_content

def register_setup_wizard_callbacks(app):

    @app.callback(
        Output("setup-wizard-container", "children"),
        Input("auth-store", "data")
    )
    def trigger_setup_wizard(auth):
        if not auth or not auth.get("authenticated"):
            return no_update
        if auth.get("role") != "admin":
            return no_update
            
        society_id = auth.get("society_id")
        if not society_id:
            return no_update
            
        # Check if qr_signing_secret_hash is NULL
        row = db._execute("SELECT qr_signing_secret_hash FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
        if row and row.get("qr_signing_secret_hash") is None:
            # Trigger Wizard
            return get_setup_wizard_layout(society_id)
        
        return html.Div() # Clear wizard

    @app.callback(
        Output("sw-current-step", "data"),
        Output("sw-category-title", "children"),
        Output({"type": "sw-step-container", "index": ALL}, "style"),
        Output("sw-banner-text", "children"),
        Output("sw-banner-link", "href"),
        Output("sw-banner-link", "style"),
        Output({"type": "sw-nav-item", "index": ALL}, "active"),
        Output("sw-btn-prev", "disabled"),
        Output("sw-btn-next", "style"),
        Output("sw-btn-submit", "style"),
        Output("sw-error-msg", "children"),
        Input("sw-btn-prev", "n_clicks"),
        Input("sw-btn-next", "n_clicks"),
        Input({"type": "sw-nav-item", "index": ALL}, "n_clicks"),
        State("sw-current-step", "data"),
        State("sw-society-name", "value"),
        State("sw-society-address", "value"),
        State("sw-society-pan", "value"),
        State("sw-society-reg", "value"),
        State("sw-qr-secret", "value"),
        State("sw-society-id", "data"),
        prevent_initial_call=True
    )
    def handle_wizard_navigation(n_prev, n_next, nav_clicks, current_step, s_name, s_addr, s_pan, s_reg, qr_sec, society_id):
        triggered_id = ctx.triggered_id
        
        # Validation for Step 0 and 7
        error_msg = ""
        new_step = current_step
        
        if triggered_id == "sw-btn-next" and n_next:
            if current_step < len(CATEGORIES) - 1:
                new_step = current_step + 1
        elif triggered_id == "sw-btn-prev" and n_prev:
            if current_step > 0:
                new_step = current_step - 1
        elif isinstance(triggered_id, dict) and triggered_id["type"] == "sw-nav-item" and any(nav_clicks):
            clicked_step = triggered_id["index"]
            new_step = clicked_step

        cat_name = CATEGORIES[new_step]
        step_styles = [{"display": "block"} if i == new_step else {"display": "none"} for i in range(len(CATEGORIES))]
        
        # Banner Data
        banner_text = "No additional regulations found."
        banner_link = "#"
        link_style = {"display": "none"}
        for row in CONVERSATION_DATA:
            if row.get("Category") == cat_name:
                banner_text = row.get("Act Summary text", banner_text)
                banner_link = row.get("website link", "#")
                link_style = {"display": "inline-block"}
                break

        nav_active = [i == new_step for i in range(len(CATEGORIES))]
        prev_disabled = (new_step == 0)
        
        next_style = {"display": "inline-block"} if new_step < len(CATEGORIES) - 1 else {"display": "none"}
        submit_style = {"display": "inline-block"} if new_step == len(CATEGORIES) - 1 else {"display": "none"}

        return new_step, cat_name, step_styles, banner_text, banner_link, link_style, nav_active, prev_disabled, next_style, submit_style, error_msg


    @app.callback(
        Output("setup-wizard-modal", "is_open"),
        Output("auth-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("sw-btn-submit", "n_clicks"),
        Input("sw-close-btn", "n_clicks"),
        State("sw-qr-secret", "value"),
        State("sw-qr-secret-confirm", "value"),
        State("sw-society-name", "value"),
        State("sw-society-address", "value"),
        State("sw-society-pan", "value"),
        State("sw-society-reg", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def submit_setup_wizard(n_submit, n_close, qr_secret, qr_confirm, s_name, s_addr, s_pan, s_reg, auth):
        triggered = ctx.triggered_id
        
        if triggered == "sw-close-btn":
            if not n_close:
                return no_update, no_update, no_update, no_update, no_update
            try:
                from flask_login import logout_user
                logout_user()
            except Exception:
                pass
            return False, None, "/dashboard/", {"type": "info", "message": "Setup cancelled. You have been logged out."}, True
            
        if triggered == "sw-btn-submit":
            if not n_submit:
                return no_update, no_update, no_update, no_update, no_update
            if not qr_secret:
                return True, "QR Secret is required.", no_update, no_update, no_update 
            
            if qr_secret != qr_confirm:
                return True, "Passwords do not match.", no_update, no_update, no_update
                
            import re
            if len(qr_secret) < 8 or not re.search(r'[A-Z]', qr_secret) or not re.search(r'[a-z]', qr_secret) or not re.search(r'[^a-zA-Z0-9]', qr_secret):
                return True, "Password must be >= 8 chars, 1 uppercase, 1 lowercase, 1 special char.", no_update, no_update, no_update
                
            society_id = auth.get("society_id")
            
            # Hash the QR secret (HMAC based on society id or generic key)
            secret_hash = hmac.new(qr_secret.encode('utf-8'), b"EstateHub", hashlib.sha256).hexdigest()
            
            # Update society
            db._execute("""
                UPDATE societies 
                SET name = :name, address = :addr, PAN_number = :pan, registration_number = :reg, qr_signing_secret_hash = :hash
                WHERE id = :id
            """, {
                "name": s_name, 
                "addr": s_addr, 
                "pan": s_pan, 
                "reg": s_reg, 
                "hash": secret_hash, 
                "id": society_id
            })
                
            return False, no_update, no_update, no_update, no_update # Close modal
            
        return no_update, no_update, no_update, no_update, no_update
