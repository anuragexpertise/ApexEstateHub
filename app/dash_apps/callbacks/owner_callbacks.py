from dash import Input, Output, State, no_update
import dash
import requests
import qrcode
import base64
from io import BytesIO

def register_owner_callbacks(app):
    
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