from dash import Input, Output, State, no_update
import dash
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta

def register_qr_callbacks(app):
    
    @app.callback(
        Output("qr-modal", "is_open"),
        Output("qr-code-img", "src"),
        Output("qr-user-name", "children"),
        Output("qr-user-email", "children"),
        Output("qr-user-role", "children"),
        Output("qr-valid-until", "children"),
        Input("show-qr-btn", "n_clicks"),
        Input("close-qr-modal", "n_clicks"),
        State("qr-modal", "is_open"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def toggle_qr_modal(show_clicks, close_clicks, is_open, auth_data):
        """Show/hide QR modal and generate QR code"""
        
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update
        
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        # Close modal
        if button_id == "close-qr-modal":
            return False, "", "", "", "", ""
        
        # Open modal and generate QR
        if button_id == "show-qr-btn" and show_clicks:
            if not auth_data or not auth_data.get('authenticated'):
                return False, "", "", "", "", ""
            
            # Get user details
            user_id = auth_data.get('user_id')
            email = auth_data.get('email')
            role = auth_data.get('role')
            society_id = auth_data.get('society_id')
            
            # Get user name
            user_name = email.split('@')[0].title()
            
            # Create QR data
            qr_data = {
                'user_id': user_id,
                'email': email,
                'role': role,
                'society_id': society_id,
                'name': user_name,
                'timestamp': datetime.now().isoformat()
            }
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(str(qr_data))
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            qr_src = f"data:image/png;base64,{img_str}"
            
            # Calculate validity (7 days from now)
            valid_until = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            
            return True, qr_src, user_name, email, role, valid_until
        
        return no_update, no_update, no_update, no_update, no_update, no_update