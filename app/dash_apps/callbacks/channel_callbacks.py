# ============================================================
# app/dash_apps/callbacks/channel_callbacks.py
# ============================================================
# Callbacks for the Channels module (drilldown-aligned):
#   1. Toggle Target Apartment field on New Channel form
#   2. Open/close Channel Subscribers modal
#   3. Approve pending alert from channel profile alert events table
# ============================================================

import logging
from dash import Input, Output, State, ALL, ctx, html, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
    get_current_linked_id,
)

logger = logging.getLogger(__name__)


def render_channels_page(society_id: int, auth: dict) -> html.Div:
    """
    Re-render the owner channels page after an approve/deny action.
    DEPRECATED: inline rendering removed from portal_pages.py; kept
    as a utility in case external callers still reference it.
    """
    from app.services.alert_service import list_channels, get_active_alerts
    from app.dash_apps.drilldown.renderers import render_subscribable_alert_manager

    apartment_id = get_current_linked_id()
    channels = list_channels(society_id or 1, apartment_id=apartment_id, is_admin=False)
    alerts = get_active_alerts(society_id or 1)
    return render_subscribable_alert_manager(channels, alerts, is_admin=False, apartment_id=apartment_id)


def register_channel_callbacks(app):

    # ── 0. Show the "Target Apartment" picker only for Taxi / Visitor ───────
    @app.callback(
        Output({"type": "form-field", "entity": "channel", "field": "apartment_id"}, "style"),
        Input({"type": "form-field", "entity": "channel", "field": "channel_type"}, "value"),
        prevent_initial_call=False,
    )
    @require_session
    def toggle_apartment_field(ch_type):
        if ch_type in ("taxi", "visitor"):
            return {"display": "block"}
        return {"display": "none"}

    # ── 1. Open Channel Subscribers modal ────────────────────────────────────
    @app.callback(
        Output("channel-subscribers-modal", "is_open", allow_duplicate=True),
        Output("channel-subscribers-modal-body", "children", allow_duplicate=True),
        Input("profile-action-trigger", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def open_subscribers_modal(trigger_data, auth):
        if not trigger_data or not isinstance(trigger_data, dict):
            raise PreventUpdate
        action = trigger_data.get("action")
        if action != "open_subscribers_modal":
            raise PreventUpdate
        params = trigger_data.get("params") or {}
        channel_id = params.get("channel_id")
        if not channel_id:
            return False, no_update
        role = get_current_user_role() or ""
        if role not in ("admin", "master", "apartment", "security"):
            return False, html.Div("Not authorized.", style={"color": "#de5c52"})
        society_id = get_current_society_id()
        try:
            from app.services.alert_service import get_channel_subscribers
            from app.dash_apps.drilldown.renderers import render_channel_subscriber_profiles
            result = get_channel_subscribers(channel_id=channel_id, society_id=society_id)
            channel_name = result.get("channel_name", "Channel")
            subscribers = result.get("subscribers", [])
            return True, render_channel_subscriber_profiles(channel_name, subscribers)
        except Exception as e:
            logger.error(f"open_subscribers_modal error: {e}")
            return False, html.Div(f"Error loading subscribers: {e}", style={"color": "#de5c52"})

    # ── 2. Close Channel Subscribers modal ───────────────────────────────────
    @app.callback(
        Output("channel-subscribers-modal", "is_open", allow_duplicate=True),
        Input("close-channel-subscribers-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_subscribers_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Approve pending alert from channel profile alert events table ─────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Input({"type": "channel-approve-alert-btn", "alert_event_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def approve_channel_alert(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not triggered:
            raise PreventUpdate
        alert_event_id = triggered.get("alert_event_id")
        if not alert_event_id:
            raise PreventUpdate
        role = get_current_user_role() or ""
        if role != "apartment":
            return {"type": "error", "message": "Only apartment owners can approve alerts."}, no_update
        user_id = get_current_user_id()
        society_id = get_current_society_id()
        if not society_id:
            return {"type": "error", "message": "Session expired"}, no_update
        try:
            from app.services.alert_service import respond_to_alert
            ok, msg = respond_to_alert(int(alert_event_id), user_id, "approve")
            store = {"refresh": True}
            toast = {"type": "success" if ok else "error", "message": msg or "Action failed"}
            return toast, store
        except Exception as e:
            logger.error(f"approve_channel_alert error: {e}")
            return {"type": "error", "message": str(e)}, no_update
