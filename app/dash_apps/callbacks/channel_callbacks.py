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

from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id, get_current_user_role,
    get_current_society_id, get_current_linked_id,
)

logger = logging.getLogger(__name__)


def render_channels_page(society_id: int, auth: dict) -> html.Div:
    """
    Re-render the owner channels page after an approve/deny action.
    Returns the same content as portal_pages.py's owner-channels tab.

    `auth` here is expected to already be server-verified (see
    owner_respond_to_alert's verified_auth) — this function doesn't
    re-derive apartment_id itself so it stays a plain rendering helper,
    not a second place that has to remember to call get_current_linked_id().
    """
    from app.services.alert_service import list_channels, get_active_alerts
    from app.dash_apps.drilldown.renderers import render_subscribable_alert_manager

    apartment_id = (auth or {}).get("apartment_id")
    channels = list_channels(society_id or 1, apartment_id=apartment_id, is_admin=False)
    alerts = get_active_alerts(society_id or 1)
    return render_subscribable_alert_manager(channels, alerts, is_admin=False, apartment_id=apartment_id)


def register_channel_callbacks(app):

    # ── 0. Show the "Target Apartment" picker only for Taxi / Visitor ───────
    # School Bus is broadcast-to-subscribers and has no single owner, so the
    # field is irrelevant (and left blank/ignored) for that type.
    @app.callback(
        Output("channel-apartment-input-wrap", "style"),
        Input("channel-type-input", "value"),
        prevent_initial_call=False,
    )
    @require_session
    def toggle_channel_apartment_field(ch_type):
        if ch_type in ("taxi", "visitor"):
            return {"display": "block"}
        return {"display": "none"}

    # ── 1. Admin: Create Channel ─────────────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input("channel-create-btn", "n_clicks"),
        State("channel-type-input", "value"),
        State("channel-name-input", "value"),
        State("channel-identifier-input", "value"),
        State("channel-apartment-input", "value"),
        State("channel-recurring-switch", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def create_channel(n_clicks, ch_type, ch_name, identifier, apartment_id, is_recurring, auth):
        if not n_clicks:
            return no_update, no_update

        # Server session is authoritative for role/society_id — auth-store
        # (the `auth` param above) is client-editable localStorage and is
        # no longer trusted for this check. @require_session already
        # guarantees a session exists on this request; get_current_*()
        # below reads that same session rather than the request body.
        role = get_current_user_role() or ""
        society_id = get_current_society_id()

        if role not in ("admin", "master"):
            return {"message": "Only admins can create channels.", "color": "danger"}, no_update

        if not ch_name or not ch_name.strip():
            return {"message": "Channel name is required.", "color": "warning"}, no_update

        if not ch_type:
            return {"message": "Channel type is required.", "color": "warning"}, no_update

        # Taxi / Visitor channels are addressed to a single apartment: the
        # owner is who gets push-notified and who is authorized to
        # approve/deny (see alert_service.trigger_channel_alert /
        # respond_to_alert). Without apartment_id set at creation, those
        # channels silently orphan every alert they raise — no push goes
        # out and no one can ever respond to it. School Bus doesn't need
        # this since it broadcasts to all subscribers instead.
        if ch_type in ("taxi", "visitor") and not apartment_id:
            return {
                "message": "Please select the target apartment/flat for a Taxi or Visitor channel.",
                "color": "warning",
            }, no_update

        try:
            from app.services.alert_service import create_alert_channel
            ok, msg = create_alert_channel(
                society_id=society_id,
                channel_type=ch_type,
                name=ch_name.strip(),
                identifier=(identifier or "").strip() or None,
                apartment_id=apartment_id if ch_type in ("taxi", "visitor") else None,
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
    @require_session
    def toggle_subscription(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        channel_id = triggered.get("channel_id")
        if not channel_id:
            return no_update, no_update

        # Server-verified — apartment_id here is auth-store's client-
        # editable value previously, meaning any authenticated user could
        # (un)subscribe an apartment that wasn't theirs by supplying its
        # id. get_current_linked_id() only ever returns the ownership
        # linkage recorded in the DB for the actual logged-in user.
        role = get_current_user_role() or ""
        if role != "apartment":
            return {"message": "Only apartment owners can manage channel subscriptions.", "color": "danger"}, no_update

        apartment_id = get_current_linked_id()
        society_id = get_current_society_id()

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
                    f"/dashboard/owner-channels",
                )
            return {"message": msg or "Action failed.", "color": "danger"}, no_update
        except Exception as e:
            logger.error(f"toggle_subscription callback error: {e}")
            return {"message": str(e), "color": "danger"}, no_update

    # ── 4. Owner: Approve / Deny Pending Alert ────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("channels-page-refresh", "children", allow_duplicate=True),
        Input({"type": "owner-approve-alert-btn", "alert_event_id": ALL}, "n_clicks"),
        Input({"type": "owner-deny-alert-btn", "alert_event_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def owner_respond_to_alert(approve_clicks, deny_clicks, auth):
        role = get_current_user_role() or ""
        if role != "apartment":
            return {"message": "Only apartment owners can respond to alerts.", "color": "danger"}, no_update

        if not ctx.triggered:
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        alert_event_id = triggered.get("alert_event_id")
        action = "approve" if triggered.get("type") == "owner-approve-alert-btn" else "deny"

        if not alert_event_id:
            return no_update, no_update

        # respond_to_alert() itself checks this user_id against the
        # alert's linked apartment owner (see alert_service.py) — passing
        # the server-verified id is what makes that check meaningful
        # instead of trivially satisfiable by a matching client value.
        user_id = get_current_user_id()
        society_id = get_current_society_id()
        verified_auth = dict(auth or {})
        verified_auth["apartment_id"] = get_current_linked_id()
        verified_auth["society_id"] = society_id

        try:
            from app.services.alert_service import respond_to_alert
            ok, msg = respond_to_alert(alert_event_id, user_id, action)
            if ok:
                action_label = "Approved (PASS)" if action == "approve" else "Denied"
                return {"message": f"Alert {action_label}.", "color": "success"}, render_channels_page(society_id, verified_auth)
            return {"message": msg or "Action failed.", "color": "danger"}, no_update
        except Exception as e:
            logger.error(f"owner_respond_to_alert error: {e}")
            return {"message": str(e), "color": "danger"}, no_update

    # ── 5. View Subscriber Profiles ──────────────────────────────────────────
    @app.callback(
        Output("subscribers-modal-container", "children"),
        Input({"type": "view-subscribers-btn", "channel_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def view_subscribers(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update

        channel_id = triggered.get("channel_id")
        if not channel_id:
            return no_update

        role = get_current_user_role() or ""
        if role not in ("admin", "master", "apartment"):
            return html.Div("Not authorized to view subscribers.", className="text-danger mt-2")

        society_id = get_current_society_id()

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
