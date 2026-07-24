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

    @app.callback(
        Output("subscribers-modal-container", "children"),
        Input({"type": "view-subscribers-btn", "channel_id": dash.ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def display_channel_subscribers(n_clicks_list, auth_data):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update
        try:
            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
            import json
            channel_id = json.loads(prop_id)["channel_id"]

            from app.services.alert_service import get_channel_subscribers_with_profile
            from app.dash_apps.drilldown.renderers import render_channel_subscriber_profiles
            from database.db_manager import db

            ch = db._execute("SELECT name FROM alert_channels WHERE id = %s", (channel_id,), fetch_one=True)
            ch_name = ch["name"] if ch else f"Channel #{channel_id}"

            subscribers = get_channel_subscribers_with_profile(channel_id)
            return render_channel_subscriber_profiles(ch_name, subscribers)
        except Exception as e:
            return html.Div(f"Error loading subscribers: {e}", className="alert alert-danger mt-2")