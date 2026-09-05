import json
from dash import Input, Output, State, ALL, callback, no_update, html, ctx
import dash_bootstrap_components as dbc
from werkzeug.security import generate_password_hash
from database.db_manager import db
from database.seed import TDS_SECTION_RATE_SEED
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
        State("sw-society-id", "data"),
        prevent_initial_call=True
    )
    def handle_wizard_navigation(n_prev, n_next, nav_clicks, current_step, society_id):
        # (society_id kept as a State for parity with the layout's dcc.Store,
        # though this callback doesn't currently need it beyond triggering
        # re-registration; the four sw-society-* / sw-qr-secret States that
        # used to sit here were unused dead params — removed 2026-09.)
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
        Output("sw-error-msg", "children", allow_duplicate=True),
        Input("sw-btn-submit", "n_clicks"),
        Input("sw-close-btn", "n_clicks"),
        State("sw-qr-secret", "value"),
        State("sw-qr-secret-confirm", "value"),
        State({"type": "sw-tds-rate", "index": ALL}, "value"),
        State("sw-cgst", "value"),
        State("sw-sgst", "value"),
        State("sw-apt-maint-amt", "value"),
        State("sw-apt-maint-rate", "value"),
        State("sw-apt-due-day", "value"),
        State("sw-apt-sinking", "value"),
        State("sw-apt-repair", "value"),
        State("sw-ven-1day", "value"),
        State("sw-ven-7day", "value"),
        State("sw-ven-1mth", "value"),
        State("sw-bf-fy", "value"),
        State("sw-bf-acc-id", "value"),
        State("sw-bf-drcr", "value"),
        State("sw-bf-amount", "value"),
        State("sw-bf-remarks", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def submit_setup_wizard(n_submit, n_close, qr_secret, qr_confirm, tds_rates, cgst, sgst,
                             apt_amt, apt_rate, apt_due_day, apt_sinking, apt_repair,
                             ven_1day, ven_7day, ven_1mth,
                             bf_fy, bf_acc_id, bf_drcr, bf_amount, bf_remarks, auth):
        triggered = ctx.triggered_id
        _noop = (no_update, no_update, no_update, no_update, no_update, no_update)

        if triggered == "sw-close-btn":
            if not n_close:
                return _noop
            try:
                from flask_login import logout_user
                logout_user()
            except Exception:
                pass
            return False, None, "/dashboard/", {"type": "info", "message": "Setup cancelled. You have been logged out."}, True, ""

        if triggered == "sw-btn-submit":
            if not n_submit:
                return _noop

            # auth-store must never be overwritten with anything but a real
            # auth dict or None (logout) — every other callback in the app
            # does auth.get(...) on it. Validation failures below only ever
            # touch is_open / sw-error-msg.
            if not auth or not auth.get("society_id"):
                return True, no_update, no_update, no_update, no_update, "Session error — please log in again."

            if not qr_secret:
                return True, no_update, no_update, no_update, no_update, "Setup Confirmation Password is required."

            if qr_secret != qr_confirm:
                return True, no_update, no_update, no_update, no_update, "Passwords do not match."

            import re
            if len(qr_secret) < 8 or not re.search(r'[A-Z]', qr_secret) or not re.search(r'[a-z]', qr_secret) or not re.search(r'[^a-zA-Z0-9]', qr_secret):
                return True, no_update, no_update, no_update, no_update, "Password must be >= 8 chars, 1 uppercase, 1 lowercase, 1 special char."

            society_id = auth.get("society_id")

            # werkzeug's salted hash (consistent with every other password/
            # PIN/pattern in this codebase) — replaces the old hmac-sha256
            # with a key hardcoded in this open-source file, which offered
            # no real protection against offline brute force.
            secret_hash = generate_password_hash(qr_secret)

            # Zip edited rates back onto their seed sections. See the note
            # on fn_complete_society_setup: TDS_SECTION_RATE_SEED has two
            # rows sharing section '194C' — the later one in this list wins
            # once persisted, a pre-existing schema/seed mismatch, not
            # something this fix resolves.
            tds_pairs = [
                {"section": item[0], "rate": float(tds_rates[idx])}
                for idx, item in enumerate(TDS_SECTION_RATE_SEED)
                if idx < len(tds_rates) and tds_rates[idx] not in (None, "")
            ]

            try:
                result = db._execute(
                    """SELECT fn_complete_society_setup(
                        :sid, :qr_hash, :tds_json::jsonb, :cgst, :sgst,
                        :apt_amt, :apt_rate, :apt_due, :apt_sink, :apt_repair,
                        :ven_1, :ven_7, :ven_30,
                        :bf_fy, :bf_acc, :bf_drcr, :bf_amt, :bf_remarks, :created_by
                    ) AS result""",
                    {
                        "sid": society_id,
                        "qr_hash": secret_hash,
                        "tds_json": json.dumps(tds_pairs),
                        "cgst": cgst, "sgst": sgst,
                        "apt_amt": apt_amt, "apt_rate": apt_rate, "apt_due": apt_due_day,
                        "apt_sink": apt_sinking, "apt_repair": apt_repair,
                        "ven_1": ven_1day, "ven_7": ven_7day, "ven_30": ven_1mth,
                        "bf_fy": bf_fy, "bf_acc": bf_acc_id, "bf_drcr": bf_drcr,
                        "bf_amt": bf_amount, "bf_remarks": bf_remarks,
                        "created_by": auth.get("user_id"),
                    },
                    fetch_one=True,
                )
            except Exception as e:
                return True, no_update, no_update, no_update, no_update, f"Error saving setup: {str(e)[:150]}"

            outcome = (result or {}).get("result") or ""
            if outcome != "OK":
                return True, no_update, no_update, no_update, no_update, outcome or "Setup could not be saved — please try again."

            return (
                False, no_update, no_update,
                {"type": "success", "message": "Setup completed successfully!"},
                no_update, ""
            )  # Close modal

        return _noop
