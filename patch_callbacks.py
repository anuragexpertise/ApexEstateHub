import re

with open("app/dash_apps/callbacks/setup_wizard_callbacks.py", "r") as f:
    content = f.read()

# Chunk 1: Save image function
c1_target = "def register_setup_wizard_callbacks(app):\n\n    @app.callback("
c1_replacement = """def register_setup_wizard_callbacks(app):

    def save_uploaded_image(contents, prefix):
        if not contents:
            return None
        try:
            import base64
            import uuid
            import os
            
            header, encoded = contents.split(',', 1)
            ext = header.split('/')[1].split(';')[0]
            if ext == 'jpeg': ext = 'jpg'
            
            filename = f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"
            upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../static/uploads"))
            os.makedirs(upload_dir, exist_ok=True)
            
            filepath = os.path.join(upload_dir, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(encoded))
                
            return f"/static/uploads/{filename}"
        except Exception as e:
            print("Error saving image:", e)
            return None

    @app.callback("""
content = content.replace(c1_target, c1_replacement)

# Chunk 2: States
c2_target = """        State("sw-qr-secret", "value"),
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
        State({"type": "sw-bf-amt", "acc_id": ALL}, "id"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def submit_setup_wizard(n_submit, n_close, qr_secret, qr_confirm, tds_rates, cgst, sgst,
                             apt_amt, apt_rate, apt_due_day, apt_sinking, apt_repair,
                             ven_1day, ven_7day, ven_1mth,
                             bf_fy, bf_ids, bf_amts, bf_remarks, auth):"""

c2_replacement = """        State("sw-logo-upload", "contents"),
        State("sw-society-address", "value"),
        State("sw-society-phone", "value"),
        State("sw-bg-upload", "contents"),
        State("sw-society-tan", "value"),
        State("sw-society-gstin", "value"),
        State("sw-payment-qr", "contents"),
        State("sw-calc-start-date", "date"),
        State("sw-sec-name", "value"),
        State("sw-sec-phone", "value"),
        State("sw-sec-sign", "contents"),
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
                            sec_name, sec_phone, sec_sign_data, 
                            qr_secret, qr_confirm, i_agree, admin_pass, qr_confirm_final,
                            tds_rates, cgst, sgst,
                            apt_amt, apt_rate, apt_due_day, apt_sinking, apt_repair,
                            ven_1day, ven_7day, ven_1mth,
                            bf_fy, bf_ids, bf_amts, bf_remarks, auth):"""
content = content.replace(c2_target, c2_replacement)


# Chunk 3: Validations
c3_target = """            if not qr_secret:
                return True, no_update, no_update, no_update, no_update, "Setup Confirmation Password is required."

            if qr_secret != qr_confirm:
                return True, no_update, no_update, no_update, no_update, "Passwords do not match."

            import re
            if len(qr_secret) < 8 or not re.search(r'[A-Z]', qr_secret) or not re.search(r'[a-z]', qr_secret) or not re.search(r'[^a-zA-Z0-9]', qr_secret):
                return True, no_update, no_update, no_update, no_update, "Password must be >= 8 chars, 1 uppercase, 1 lowercase, 1 special char.""""

c3_replacement = """            if i_agree != 'I AGREE':
                return True, no_update, no_update, no_update, no_update, "You must type 'I AGREE' to proceed."

            if not admin_pass:
                return True, no_update, no_update, no_update, no_update, "Admin Password is required."

            from werkzeug.security import check_password_hash
            user_row = db._execute("SELECT password_hash FROM users WHERE id = :uid", {"uid": auth.get("user_id")}, fetch_one=True)
            if not user_row or not check_password_hash(user_row["password_hash"], admin_pass):
                return True, no_update, no_update, no_update, no_update, "Invalid Admin Password."

            if not qr_secret:
                return True, no_update, no_update, no_update, no_update, "Setup Confirmation Password is required."

            if qr_secret != qr_confirm or qr_secret != qr_confirm_final:
                return True, no_update, no_update, no_update, no_update, "Passwords do not match."

            import re
            if len(qr_secret) < 8 or not re.search(r'[A-Z]', qr_secret) or not re.search(r'[a-z]', qr_secret) or not re.search(r'[^a-zA-Z0-9]', qr_secret):
                return True, no_update, no_update, no_update, no_update, "Password must be >= 8 chars, 1 uppercase, 1 lowercase, 1 special char.""""
content = content.replace(c3_target, c3_replacement)

# Chunk 4: DB logic
c4_target = """            try:
                result = db._execute(
                    \"\"\"SELECT fn_complete_society_setup(
                        :sid, :qr_hash, :tds_json::jsonb, :cgst, :sgst,
                        :apt_amt, :apt_rate, :apt_due, :apt_sink, :apt_repair,
                        :ven_1, :ven_7, :ven_30,
                        :bf_fy, :bf_json::jsonb, :created_by
                    ) AS result\"\"\",
                    {
                        "sid": society_id,
                        "qr_hash": secret_hash,
                        "tds_json": json.dumps(tds_pairs),
                        "cgst": cgst, "sgst": sgst,
                        "apt_amt": apt_amt, "apt_rate": apt_rate, "apt_due": apt_due_day,
                        "apt_sink": apt_sinking, "apt_repair": apt_repair,
                        "ven_1": ven_1day, "ven_7": ven_7day, "ven_30": ven_1mth,
                        "bf_fy": bf_fy, "bf_json": json.dumps(bf_json),
                        "created_by": auth.get("user_id"),
                    },
                    fetch_one=True,
                )"""

c4_replacement = """            logo_path = save_uploaded_image(logo_data, "logo")
            bg_path = save_uploaded_image(bg_data, "bg")
            qr_path = save_uploaded_image(pay_qr_data, "qr")
            sign_path = save_uploaded_image(sec_sign_data, "sign")

            try:
                result = db._execute(
                    \"\"\"SELECT fn_complete_society_setup(
                        :sid, :qr_hash, :logo, :addr, :phone, :bg, :tan, :gstin, :pay_qr, :calc_start, :sec_name, :sec_phone, :sec_sign,
                        :tds_json::jsonb, :cgst, :sgst,
                        :apt_amt, :apt_rate, :apt_due, :apt_sink, :apt_repair,
                        :ven_1, :ven_7, :ven_30,
                        :bf_fy, :bf_json::jsonb, :created_by
                    ) AS result\"\"\",
                    {
                        "sid": society_id,
                        "qr_hash": secret_hash,
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
                )"""
content = content.replace(c4_target, c4_replacement)

with open("app/dash_apps/callbacks/setup_wizard_callbacks.py", "w") as f:
    f.write(content)

print("Callbacks patched successfully.")
