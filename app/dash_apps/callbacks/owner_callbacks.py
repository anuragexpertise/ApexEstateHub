from dash import Input, Output, State, no_update
import dash
import requests
import qrcode
import base64
from io import BytesIO

def register_owner_callbacks(app):
    
    @app.callback(
        Output("owner-qr-code", "src"),
        Input("show-qr-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def generate_owner_qr(n_clicks):
        if not n_clicks:
            return no_update
        
        # Get user info from session
        # This would come from auth-store in real implementation
        user_data = {"user_id": 1, "email": "owner@example.com", "role": "apartment"}
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(str(user_data))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("process-payment-btn", "n_clicks"),
        State("payment-amount", "value"),
        State("payment-method", "value"),
        prevent_initial_call=True
    )
    def process_payment(n_clicks, amount, method):
        if not n_clicks:
            return no_update
        
        if not amount:
            return {"type": "error", "message": "Please enter an amount"}
        
        # Process payment logic here
        return {"type": "success", "message": f"Payment of ₹{amount} processed successfully!"}