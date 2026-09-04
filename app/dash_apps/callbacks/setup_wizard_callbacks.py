from dash import Input, Output, State, ALL, callback, no_update, html, ctx
import dash_bootstrap_components as dbc
import hashlib
import hmac
from utils.database import get_db_connection
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
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT qr_signing_secret_hash FROM societies WHERE id = %s", (society_id,))
                row = cur.fetchone()
                if row and row[0] is None:
                    # Trigger Wizard
                    return get_setup_wizard_layout()
        
        return html.Div() # Clear wizard

    @app.callback(
        Output("sw-current-step", "data"),
        Output("sw-category-title", "children"),
        Output("sw-category-content", "children"),
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
        prevent_initial_call=True
    )
    def handle_wizard_navigation(n_prev, n_next, nav_clicks, current_step, s_name, s_addr, s_pan, s_reg, qr_sec):
        triggered_id = ctx.triggered_id
        
        # Validation for Step 0 and 7
        error_msg = ""
        new_step = current_step
        
        if triggered_id == "sw-btn-next":
            if current_step == 0:
                if not all([s_name, s_addr, s_pan, s_reg]):
                    error_msg = "Please fill all mandatory fields (Name, Address, PAN, Registration)."
                    return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, error_msg
            if current_step < len(CATEGORIES) - 1:
                new_step = current_step + 1
        elif triggered_id == "sw-btn-prev":
            if current_step > 0:
                new_step = current_step - 1
        elif isinstance(triggered_id, dict) and triggered_id["type"] == "sw-nav-item":
            clicked_step = triggered_id["index"]
            if current_step == 0 and clicked_step != 0:
                 if not all([s_name, s_addr, s_pan, s_reg]):
                    error_msg = "Please fill all mandatory fields (Name, Address, PAN, Registration)."
                    return no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, error_msg
            new_step = clicked_step

        cat_name = CATEGORIES[new_step]
        content = render_category_content(cat_name)
        
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

        return new_step, cat_name, content, banner_text, banner_link, link_style, nav_active, prev_disabled, next_style, submit_style, error_msg


    @app.callback(
        Output("setup-wizard-modal", "is_open"),
        Input("sw-btn-submit", "n_clicks"),
        State("sw-qr-secret", "value"),
        State("sw-society-name", "value"),
        State("sw-society-address", "value"),
        State("sw-society-pan", "value"),
        State("sw-society-reg", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def submit_setup_wizard(n_submit, qr_secret, s_name, s_addr, s_pan, s_reg, auth):
        if not n_submit:
            return no_update
        
        if not qr_secret:
            return True # Keep open if missing mandatory field
            
        society_id = auth.get("society_id")
        
        # Hash the QR secret (HMAC based on society id or generic key)
        # Using a generic key or society_id string as the message
        # But wait, usually HMAC takes a key and a msg. If QR_SIGNING_SECRET *is* the secret, 
        # we can just hash it with sha256 to store it, or store HMAC of something.
        # The prompt says: "Put HMAC(QR_SIGNING_SECRET) in table 'societies'".
        # I'll create a simple hash of it.
        secret_hash = hmac.new(qr_secret.encode('utf-8'), b"EstateHub", hashlib.sha256).hexdigest()
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Update society
                cur.execute("""
                    UPDATE societies 
                    SET name = %s, address = %s, PAN_number = %s, registration_number = %s, qr_signing_secret_hash = %s
                    WHERE id = %s
                """, (s_name, s_addr, s_pan, s_reg, secret_hash, society_id))
            conn.commit()
            
        return False # Close modal
