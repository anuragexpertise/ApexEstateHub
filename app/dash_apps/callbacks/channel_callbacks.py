# ============================================================
# app/dash_apps/callbacks/channel_callbacks.py
# ============================================================
# Callbacks for the Channels tab:
#   1. Admin: Create Channel (channel-create-btn)
#   2. Owner: Subscribe / Unsubscribe (alert-sub-btn pattern match)
#   3. Admin/Owner: View Subscriber Profiles (view-subscribers-btn)
# ============================================================

import json
import logging
from dash import Input, Output, State, ALL, ctx, html, no_update
import dash_bootstrap_components as dbc

logger = logging.getLogger(__name__)


def register_channel_callbacks(app):

    # ── 1. Admin: Create Channel ─────────────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input("channel-create-btn", "n_clicks"),
        State("channel-type-input", "value"),
        State("channel-name-input", "value"),
        State("channel-identifier-input", "value"),
        State("channel-recurring-switch", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def create_channel(n_clicks, ch_type, ch_name, identifier, is_recurring, auth):
        if not n_clicks:
            return no_update, no_update

        auth = auth or {}
        society_id = auth.get("society_id") or auth.get("linked_id")
        role = auth.get("role", "")

        if role not in ("admin", "master_admin"):
            return {"message": "Only admins can create channels.", "color": "danger"}, no_update

        if not ch_name or not ch_name.strip():
            return {"message": "Channel name is required.", "color": "warning"}, no_update

        if not ch_type:
            return {"message": "Channel type is required.", "color": "warning"}, no_update

        try:
            from app.services.alert_service import create_alert_channel
            ok, msg = create_alert_channel(
                society_id=society_id,
                channel_type=ch_type,
                name=ch_name.strip(),
                identifier=(identifier or "").strip() or None,
                is_recurring=bool(is_recurring),
            )
            if ok:
                return (
                    {"message": f"Channel '{ch_name}' created successfully.", "color": "success"},
                    f"/dashboard/channels",
                )
            return {"message": msg or "Failed to create channel.", "color": "danger"}, no_update
        except Exception as e:
            logger.error(f"create_channel callback error: {e}")
            return {"message": str(e), "color": "danger"}, no_update

    # ── 2. Owner: Subscribe / Unsubscribe ────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input({"type": "alert-sub-btn", "channel_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_subscription(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        channel_id = triggered.get("channel_id")
        if not channel_id:
            return no_update, no_update

        auth = auth or {}
        apartment_id = auth.get("apartment_id")
        society_id = auth.get("society_id") or auth.get("linked_id")

        if not apartment_id:
            return {"message": "Apartment not found. Please log in again.", "color": "danger"}, no_update

        try:
            from app.services.alert_service import subscribe_channel, unsubscribe_channel, list_channels

            # Determine current state
            channels = list_channels(society_id, apartment_id=apartment_id, is_admin=False)
            ch = next((c for c in channels if c["id"] == channel_id), None)
            currently_subscribed = ch.get("is_subscribed", False) if ch else False

            if currently_subscribed:
                ok, msg = unsubscribe_channel(channel_id=channel_id, apartment_id=apartment_id)
                action_word = "Unsubscribed"
            else:
                ok, msg = subscribe_channel(channel_id=channel_id, apartment_id=apartment_id)
                action_word = "Subscribed"

            if ok:
                return (
                    {"message": f"{action_word} successfully.", "color": "success"},
                    f"/dashboard/channels",
                )
            return {"message": msg or "Action failed.", "color": "danger"}, no_update
        except Exception as e:
            logger.error(f"toggle_subscription callback error: {e}")
            return {"message": str(e), "color": "danger"}, no_update

    # ── 3. View Subscriber Profiles ──────────────────────────────────────────
    @app.callback(
        Output("subscribers-modal-container", "children"),
        Input({"type": "view-subscribers-btn", "channel_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def view_subscribers(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update

        channel_id = triggered.get("channel_id")
        if not channel_id:
            return no_update

        auth = auth or {}
        society_id = auth.get("society_id") or auth.get("linked_id")

        try:
            from app.services.alert_service import get_channel_subscribers
            from app.dash_apps.drilldown.renderers import render_channel_subscriber_profiles

            result = get_channel_subscribers(channel_id=channel_id, society_id=society_id)
            channel_name = result.get("channel_name", "Channel")
            subscribers = result.get("subscribers", [])
            return render_channel_subscriber_profiles(channel_name, subscribers)
        except Exception as e:
            logger.error(f"view_subscribers callback error: {e}")
            return html.Div(f"Error loading subscribers: {e}", className="text-danger mt-2")
