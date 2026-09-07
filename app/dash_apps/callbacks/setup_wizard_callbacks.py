import json
from dash import Input, Output, State, ALL, callback, no_update, html, ctx
import dash_bootstrap_components as dbc
from database.db_manager import db
from database.seed import TDS_SECTION_RATE_SEED
from app.dash_apps.pages.setup_wizard import get_setup_wizard_layout, CATEGORIES, CONVERSATION_DATA, render_category_content

def register_setup_wizard_callbacks(app):


    @app.callback(
        Output("setup-wizard-container", "children"),
        Input("auth-store", "data")
    )
    def trigger_setup_wizard(auth):
        if not auth or not isinstance(auth, dict) or not auth.get("authenticated"):
            return no_update
        if auth.get("role") != "admin":
            return no_update
            
        society_id = auth.get("society_id")
        if not society_id:
            return no_update
            
        # Check if signing_secret_enc is NULL (setup not completed yet)
        row = db._execute("SELECT signing_secret_enc FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True)
        if row and row.get("signing_secret_enc") is None:
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
        Output("agreement-modal", "is_open", allow_duplicate=True),
        Output("agreement-modal-body", "children", allow_duplicate=True),
        Input("sw-btn-submit", "n_clicks"),
        Input("sw-close-btn", "n_clicks"),
        State({"type": "form-field-hidden", "entity": "society", "field": "logo"}, "value"),
        State("sw-society-address", "value"),
        State("sw-society-phone", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "bg"}, "value"),
        State("sw-society-tan", "value"),
        State("sw-society-gstin", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "pay_qr"}, "value"),
        State("sw-calc-start-date", "date"),
        State("sw-sec-name", "value"),
        State("sw-sec-phone", "value"),
        State("sw-sec-email", "value"),
        State({"type": "form-field-hidden", "entity": "society", "field": "sec_sign"}, "value"),
        State("sw-qr-secret", "value"),
        State("sw-qr-secret-confirm", "value"),
        State("sw-i-agree", "value"),
        State("sw-admin-password", "value"),
        State("sw-qr-confirm-final", "value"),
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
        State({"type": "sw-bf-amt", "acc_id": ALL}, "id"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def submit_setup_wizard(n_submit, n_close, 
                            logo_data, address, phone, bg_data, 
                            tan, gstin, pay_qr_data, calc_start, 
                            sec_name, sec_phone, sec_email, sec_sign_data, 
                            qr_secret, qr_confirm, i_agree, admin_pass, qr_confirm_final,
                            tds_rates, cgst, sgst,
                            apt_amt, apt_rate, apt_due_day, apt_sinking, apt_repair,
                            ven_1day, ven_7day, ven_1mth,
                            bf_fy, bf_ids, bf_amts, bf_remarks, auth):
        triggered = ctx.triggered_id
        _noop = (no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update)

        if triggered == "sw-close-btn":
            if not n_close:
                return _noop
            try:
                from flask_login import logout_user
                logout_user()
            except Exception:
                pass
            return False, None, "/dashboard/", {"type": "info", "message": "Setup cancelled. You have been logged out."}, True, "", no_update, no_update

        if triggered == "sw-btn-submit":
            if not n_submit:
                return _noop

            # auth-store must never be overwritten with anything but a real
            # auth dict or None (logout) — every other callback in the app
            # does auth.get(...) on it. Validation failures below only ever
            # touch is_open / sw-error-msg.
            if not auth or not auth.get("society_id"):
                return True, no_update, no_update, no_update, no_update, "Session error — please log in again.", no_update, no_update

            if i_agree != 'I AGREE':
                return True, no_update, no_update, no_update, no_update, "You must type 'I AGREE' to proceed.", no_update, no_update

            if not admin_pass:
                return True, no_update, no_update, no_update, no_update, "Admin Password is required.", no_update, no_update

            from werkzeug.security import check_password_hash
            user_row = db._execute("SELECT password_hash FROM users WHERE id = :uid", {"uid": auth.get("user_id")}, fetch_one=True)
            if not user_row or not check_password_hash(user_row["password_hash"], admin_pass):
                return True, no_update, no_update, no_update, no_update, "Invalid Admin Password.", no_update, no_update

            if not qr_secret:
                return True, no_update, no_update, no_update, no_update, "SIGNING_SECRET is required.", no_update, no_update

            if qr_secret != qr_confirm or qr_secret != qr_confirm_final:
                return True, no_update, no_update, no_update, no_update, "SIGNING_SECRETs do not match.", no_update, no_update

            import re
            if len(qr_secret) < 8 or not re.search(r'[A-Z]', qr_secret) or not re.search(r'[a-z]', qr_secret) or not re.search(r'[^a-zA-Z0-9]', qr_secret):
                return True, no_update, no_update, no_update, no_update, "SIGNING_SECRET must be >= 8 chars, 1 uppercase, 1 lowercase, 1 special char.", no_update, no_update

            society_id = auth.get("society_id")

            # Reversible encryption (NOT a one-way hash like passwords/PINs
            # elsewhere in this codebase) — this is society_id's own real
            # QR HMAC key and must be decryptable at sign/verify time. See
            # app/services/secret_vault.py. Requires SECRET_VAULT_KEY to be
            # configured on the deployment; if it isn't, fail loudly here
            # rather than silently storing something unusable.
            try:
                from app.services.secret_vault import encrypt_secret
                secret_enc = encrypt_secret(qr_secret)
            except Exception as e:
                return True, no_update, no_update, no_update, no_update, f"Could not secure the SIGNING_SECRET: {str(e)[:150]}", no_update, no_update

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
            
            bf_json = []
            if bf_ids and bf_amts:
                for idx, acc_dict in enumerate(bf_ids):
                    amt = bf_amts[idx]
                    if amt is not None and float(amt) > 0:
                        bf_json.append({
                            "acc_id": acc_dict["acc_id"],
                            "bf_amount": float(amt),
                            "remarks": bf_remarks[idx] if idx < len(bf_remarks) else ""
                        })

            logo_path = logo_data
            bg_path = bg_data
            qr_path = pay_qr_data
            sign_path = sec_sign_data

            from app.dash_apps.callbacks.drilldown_callbacks import _move_temp_images
            form_data = {}
            if logo_path: form_data["logo"] = logo_path
            if bg_path: form_data["bg"] = bg_path
            if qr_path: form_data["pay_qr"] = qr_path
            if sign_path: form_data["sec_sign"] = sign_path

            if form_data:
                _move_temp_images("society", society_id, society_id, form_data)

            tan = str(tan)[:10] if tan else None
            gstin = str(gstin)[:15] if gstin else None
            phone = str(phone)[:20] if phone else None
            sec_phone = str(sec_phone)[:20] if sec_phone else None
            sec_name = str(sec_name)[:100] if sec_name else None
            sec_email = str(sec_email)[:100] if sec_email else None
            
            try:
                from database.seed import seed_accounts
                with db._conn() as conn:
                    with conn.cursor() as cur:
                        seed_accounts(cur, conn, society_id)
            except Exception as e:
                return True, no_update, no_update, no_update, no_update, f"Could not seed accounts: {str(e)[:150]}", no_update, no_update

            try:
                result = db._execute(
                    """SELECT fn_complete_society_setup(
                        :sid, :secret_enc, :logo, :addr, :phone, :bg, :tan, :gstin, :pay_qr, :calc_start, :sec_name, :sec_phone, :sec_email, :sec_sign,
                        CAST(:tds_json AS jsonb), :cgst, :sgst,
                        :apt_amt, :apt_rate, :apt_due, :apt_sink, :apt_repair,
                        :ven_1, :ven_7, :ven_30,
                        :bf_fy, CAST(:bf_json AS jsonb), :created_by
                    ) AS result""",
                    {
                        "sid": society_id,
                        "secret_enc": secret_enc,
                        "logo": logo_path,
                        "addr": address,
                        "phone": phone,
                        "bg": bg_path,
                        "tan": tan,
                        "gstin": gstin,
                        "pay_qr": qr_path,
                        "calc_start": calc_start,
                        "sec_name": sec_name,
                        "sec_phone": sec_phone,
                        "sec_email": sec_email,
                        "sec_sign": sign_path,
                        "tds_json": json.dumps(tds_pairs),
                        "cgst": cgst, "sgst": sgst,
                        "apt_amt": apt_amt, "apt_rate": apt_rate, "apt_due": apt_due_day,
                        "apt_sink": apt_sinking, "apt_repair": apt_repair,
                        "ven_1": ven_1day, "ven_7": ven_7day, "ven_30": ven_1mth,
                        "bf_fy": bf_fy, "bf_json": json.dumps(bf_json),
                        "created_by": auth.get("user_id"),
                    },
                    fetch_one=True,
                )
            except Exception as e:
                return True, no_update, no_update, no_update, no_update, f"Error saving setup: {str(e)[:150]}", no_update, no_update

            outcome = (result or {}).get("result") or ""
            if outcome != "OK":
                return True, no_update, no_update, no_update, no_update, outcome or "Setup could not be saved — please try again.", no_update, no_update

            # Auto-show the society's Agreement right after onboarding
            # completes, and persist it (society_agreements) so it can be
            # reprinted/audited later. A failure here must never block the
            # setup itself from completing — the wizard has already
            # succeeded at this point.
            agreement_body = no_update
            agreement_open = no_update
            try:
                from app.dash_apps.callbacks.drilldown_callbacks import _get_or_create_agreement
                from app.dash_apps.drilldown import renderers
                agreement_record = _get_or_create_agreement(db, society_id, auth.get("user_id"))
                society = db._execute("SELECT * FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True) or {}
                agreement_body = renderers.render_agreement_card(society=dict(society), agreement_record=agreement_record)
                agreement_open = True
            except Exception as e:
                print(f"⚠️  Agreement generation failed after setup: {e}")

            return (
                False, no_update, no_update,
                {"type": "success", "message": "Setup completed successfully!"},
                no_update, "",
                agreement_open, agreement_body,
            )  # Close wizard modal, open Agreement modal

        return _noop
