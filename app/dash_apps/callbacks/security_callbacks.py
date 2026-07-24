from dash import Input, Output, State, no_update, html, ctx
import dash_bootstrap_components as dbc
from datetime import datetime
from app.services.qr_service import validate_qr_code
from app.services.alert_service import (
    trigger_channel_alert,
    trigger_visitor_alert,
    create_walk_in_visitor,
    get_presumed_visitors,
    get_active_alerts,
)
from database.db_manager import db
import logging

logger = logging.getLogger(__name__)


# ── Renderers ────────────────────────────────────────────────────────────────

def render_gate_alerts_section(society_id=None):
    """
    Render the gate alerts section for the security portal:
    - Active channel alerts (School Bus, Taxi) with trigger/call buttons
    - Presumed visitors list with notify/call buttons
    - Walk-in visitor form
    """
    if not society_id:
        return no_update

    alerts = get_active_alerts(society_id)
    presumed = get_presumed_visitors(society_id)

    channel_alerts = [a for a in alerts if a.get("type") != "visitor"]
    visitor_alerts = [a for a in alerts if a.get("type") == "visitor"]

    # Channel alert cards
    channel_cards = []
    for alert in channel_alerts:
        ctype = alert.get("type", "")
        state = alert.get("state", "pending")
        ch_id = alert.get("id")
        alert_event_id = alert.get("alert_event_id")
        name = alert.get("title", "")
        identifier = alert.get("identifier", "")
        flat = alert.get("flat_number", "")
        owner_phone = alert.get("owner_phone", "")
        owner_name = alert.get("owner_name", "")

        if state == "resolved":
            badge = dbc.Badge("PASS / AUTO-RESOLVED", color="success", style={"fontSize": "11px"})
            action_btns = dbc.Button(
                [html.I(className="fas fa-bell me-1"), "Re-notify"],
                id={"type": "gate-alert-trigger-btn", "channel_id": ch_id},
                color="primary",
                size="sm",
                style={"borderRadius": "8px", "fontSize": "11px"},
            )
        elif state == "pending":
            badge = dbc.Badge("PENDING OWNER APPROVAL", color="warning", style={"fontSize": "11px"})
            action_btns = html.Div([
                dbc.Button(
                    [html.I(className="fas fa-phone-alt me-1"), f"Call Owner ({owner_phone or 'N/A'})"],
                    href=f"tel:{owner_phone}" if owner_phone else "#",
                    id={"type": "gate-alert-call-btn", "alert_event_id": alert_event_id},
                    color="danger",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px", "marginRight": "6px"},
                ) if owner_phone else html.Span("No owner phone", style={"fontSize": "11px", "color": "#999"}),
            ])
        elif state == "calling":
            badge = dbc.Badge("CALLING OWNER", color="danger", style={"fontSize": "11px"})
            action_btns = html.Div([
                dbc.Button(
                    [html.I(className="fas fa-phone-alt me-1"), f"Call Owner ({owner_phone or 'N/A'})"],
                    href=f"tel:{owner_phone}" if owner_phone else "#",
                    color="danger",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px", "marginRight": "6px"},
                ) if owner_phone else html.Span("No owner phone", style={"fontSize": "11px", "color": "#999"}),
            ])
        elif state == "denied":
            badge = dbc.Badge("DENIED", color="danger", style={"fontSize": "11px"})
            action_btns = dbc.Button(
                [html.I(className="fas fa-bell me-1"), "Re-trigger"],
                id={"type": "gate-alert-trigger-btn", "channel_id": ch_id},
                color="primary",
                size="sm",
                style={"borderRadius": "8px", "fontSize": "11px"},
            )
        else:
            badge = dbc.Badge(state.upper(), color="secondary", style={"fontSize": "11px"})
            action_btns = dbc.Button(
                [html.I(className="fas fa-bell me-1"), "Trigger Alert"],
                id={"type": "gate-alert-trigger-btn", "channel_id": ch_id},
                color="primary",
                size="sm",
                style={"borderRadius": "8px", "fontSize": "11px"},
            )

        channel_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(name, style={"fontWeight": "700", "fontSize": "13px"}),
                            badge,
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(f"Ref: {identifier or '—'} | Flat: {flat or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Owner: {owner_name or 'N/A'}", style={"fontSize": "11px", "color": "#64748b"}) if owner_name else None,
                        html.Div(action_btns, className="mt-2"),
                    ], style={"padding": "12px"})
                ], style={
                    "borderRadius": "10px",
                    "border": f"1px solid {'#eab308' if state == 'pending' else '#ef4444' if state == 'denied' else '#22c55e' if state == 'resolved' else '#f97316'}",
                })
            ], width=12, md=6, lg=4, className="mb-3")
        )

    # Presumed visitors list
    presumed_cards = []
    for v in presumed:
        visitor_id = v.get("visitor_id")
        name = v.get("name", "")
        mobile = v.get("mobile", "")
        purpose = v.get("purpose", "")
        flat = v.get("flat_number", "")
        owner_phone = v.get("owner_phone", "")
        owner_name = v.get("owner_name", "")

        presumed_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(f"👤 {name}", style={"fontWeight": "700", "fontSize": "13px"}),
                            dbc.Badge("PRESUMED", color="info", style={"fontSize": "10px"}),
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(f"Flat: {flat or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Purpose: {purpose or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Mobile: {mobile or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Owner: {owner_name or 'N/A'}", style={"fontSize": "11px", "color": "#64748b"}) if owner_name else None,
                        html.Div([
                            dbc.Button(
                                [html.I(className="fas fa-bell me-1"), "Notify Owner"],
                                id={"type": "presumed-visitor-notify-btn", "visitor_id": visitor_id},
                                color="primary",
                                size="sm",
                                style={"borderRadius": "8px", "fontSize": "11px", "marginRight": "6px"},
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-phone-alt me-1"), f"Call {owner_phone or 'Owner'}"],
                                href=f"tel:{owner_phone}" if owner_phone else "#",
                                id={"type": "presumed-visitor-call-btn", "visitor_id": visitor_id},
                                color="danger",
                                size="sm",
                                style={"borderRadius": "8px", "fontSize": "11px"},
                            ) if owner_phone else None,
                        ], className="mt-2"),
                    ], style={"padding": "12px"})
                ], style={"borderRadius": "10px", "border": "1px solid #1d74d8"})
            ], width=12, md=6, lg=4, className="mb-3")
        )

    # Walk-in visitor form
    walk_in_form = dbc.Card([
        dbc.CardHeader(html.H6("Walk-in Visitor Entry", style={"fontWeight": "700", "margin": 0})),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Visitor Name *", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-name", type="text", placeholder="Full name", style={"fontSize": "13px"}),
                ], width=6),
                dbc.Col([
                    dbc.Label("Mobile", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-mobile", type="text", placeholder="Mobile number", style={"fontSize": "13px"}),
                ], width=6),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Purpose of Visit *", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-purpose", type="text", placeholder="e.g. Delivery, Meeting", style={"fontSize": "13px"}),
                ], width=6),
                dbc.Col([
                    dbc.Label("Flat Number", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-flat", type="text", placeholder="e.g. A-101", style={"fontSize": "13px"}),
                ], width=6),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Vehicle Number", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-vehicle", type="text", placeholder="e.g. MH-02-1234", style={"fontSize": "13px"}),
                ], width=12),
            ], className="mb-3"),
            dbc.Button(
                [html.I(className="fas fa-camera me-1"), "Click Picture"],
                id="walk-in-visitor-photo-btn",
                color="info",
                size="sm",
                outline=True,
                style={"borderRadius": "8px", "fontSize": "12px", "marginBottom": "8px"},
            ),
            html.Div(id="walk-in-visitor-photo-preview", className="mb-2"),
            dbc.Button(
                [html.I(className="fas fa-paper-plane me-1"), "Create Visitor & Notify Owner"],
                id="walk-in-visitor-submit-btn",
                color="success",
                size="sm",
                style={"borderRadius": "8px", "fontWeight": "600"},
            ),
        ], style={"padding": "14px"})
    ], style={"borderRadius": "12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"})

    # Visitor alerts
    visitor_cards = []
    for alert in visitor_alerts:
        state = alert.get("state", "pending")
        alert_event_id = alert.get("alert_event_id")
        name = alert.get("title", "")
        purpose = alert.get("identifier", "")
        flat = alert.get("flat_number", "")
        owner_phone = alert.get("owner_phone", "")
        owner_name = alert.get("owner_name", "")

        if state == "resolved":
            badge = dbc.Badge("PASS / ENTERED", color="success", style={"fontSize": "11px"})
            action_btns = None
        elif state == "pending":
            badge = dbc.Badge("PENDING OWNER APPROVAL", color="warning", style={"fontSize": "11px"})
            action_btns = html.Div([
                dbc.Button(
                    [html.I(className="fas fa-phone-alt me-1"), f"Call Owner ({owner_phone or 'N/A'})"],
                    href=f"tel:{owner_phone}" if owner_phone else "#",
                    color="danger",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px", "marginRight": "6px"},
                ) if owner_phone else html.Span("No owner phone", style={"fontSize": "11px", "color": "#999"}),
            ])
        elif state == "calling":
            badge = dbc.Badge("CALLING OWNER", color="danger", style={"fontSize": "11px"})
            action_btns = html.Div([
                dbc.Button(
                    [html.I(className="fas fa-phone-alt me-1"), f"Call Owner ({owner_phone or 'N/A'})"],
                    href=f"tel:{owner_phone}" if owner_phone else "#",
                    color="danger",
                    size="sm",
                    style={"borderRadius": "8px", "fontSize": "11px", "marginRight": "6px"},
                ) if owner_phone else html.Span("No owner phone", style={"fontSize": "11px", "color": "#999"}),
            ])
        elif state == "denied":
            badge = dbc.Badge("DENIED", color="danger", style={"fontSize": "11px"})
            action_btns = None
        else:
            badge = dbc.Badge(state.upper(), color="secondary", style={"fontSize": "11px"})
            action_btns = None

        visitor_cards.append(
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(name, style={"fontWeight": "700", "fontSize": "13px"}),
                            badge,
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(f"Flat: {flat or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Purpose: {purpose or '—'}", style={"fontSize": "11px", "color": "#64748b"}),
                        html.Div(f"Owner: {owner_name or 'N/A'}", style={"fontSize": "11px", "color": "#64748b"}) if owner_name else None,
                        html.Div(action_btns, className="mt-2") if action_btns else None,
                    ], style={"padding": "12px"})
                ], style={
                    "borderRadius": "10px",
                    "border": f"1px solid {'#eab308' if state == 'pending' else '#ef4444' if state == 'denied' else '#22c55e' if state == 'resolved' else '#f97316'}",
                })
            ], width=12, md=6, lg=4, className="mb-3")
        )

    return html.Div([
        html.H5("Active Gate Alerts", style={"fontWeight": "700", "marginBottom": "12px", "marginTop": "16px"}),
        dbc.Row(channel_cards) if channel_cards else html.Div("No active channel alerts.", className="text-muted mb-3"),
        html.H5("Visitor Alerts", style={"fontWeight": "700", "marginBottom": "12px", "marginTop": "16px"}),
        dbc.Row(visitor_cards) if visitor_cards else html.Div("No active visitor alerts.", className="text-muted mb-3"),
        html.H5("Presumed Visitors (Pending)", style={"fontWeight": "700", "marginBottom": "12px", "marginTop": "16px"}),
        dbc.Row(presumed_cards) if presumed_cards else html.Div("No presumed visitors for today.", className="text-muted mb-3"),
        html.Hr(style={"margin": "20px 0"}),
        walk_in_form,
    ])


def render_walk_in_visitor_form():
    """Return empty walk-in form (clears after submission)."""
    return dbc.Card([
        dbc.CardHeader(html.H6("Walk-in Visitor Entry", style={"fontWeight": "700", "margin": 0})),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Visitor Name *", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-name", type="text", placeholder="Full name", style={"fontSize": "13px"}),
                ], width=6),
                dbc.Col([
                    dbc.Label("Mobile", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-mobile", type="text", placeholder="Mobile number", style={"fontSize": "13px"}),
                ], width=6),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Purpose of Visit *", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-purpose", type="text", placeholder="e.g. Delivery, Meeting", style={"fontSize": "13px"}),
                ], width=6),
                dbc.Col([
                    dbc.Label("Flat Number", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-flat", type="text", placeholder="e.g. A-101", style={"fontSize": "13px"}),
                ], width=6),
            ], className="mb-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Vehicle Number", style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="walk-in-visitor-vehicle", type="text", placeholder="e.g. MH-02-1234", style={"fontSize": "13px"}),
                ], width=12),
            ], className="mb-3"),
            dbc.Button(
                [html.I(className="fas fa-camera me-1"), "Click Picture"],
                id="walk-in-visitor-photo-btn",
                color="info",
                size="sm",
                outline=True,
                style={"borderRadius": "8px", "fontSize": "12px", "marginBottom": "8px"},
            ),
            html.Div(id="walk-in-visitor-photo-preview", className="mb-2"),
            dbc.Button(
                [html.I(className="fas fa-paper-plane me-1"), "Create Visitor & Notify Owner"],
                id="walk-in-visitor-submit-btn",
                color="success",
                size="sm",
                style={"borderRadius": "8px", "fontWeight": "600"},
            ),
        ], style={"padding": "14px"})
    ], style={"borderRadius": "12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.05)"})


# ── Callback Registration ────────────────────────────────────────────────────

def register_security_callbacks(app):

    # ── 1. Gate Alert Actions (School Bus, Taxi, Visitor) ───────────────────
    @app.callback(
        Output("gate-alert-toast", "data", allow_duplicate=True),
        Output("gate-alerts-refresh", "children", allow_duplicate=True),
        Input({"type": "gate-alert-trigger-btn", "channel_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def trigger_gate_alert(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        channel_id = triggered.get("channel_id")
        if not channel_id:
            return no_update, no_update

        auth = auth or {}
        user_id = auth.get("user_id")
        society_id = auth.get("society_id") or auth.get("linked_id")

        if not user_id or not society_id:
            return {"type": "error", "message": "Session expired"}, no_update

        try:
            ok, msg, data = trigger_channel_alert(channel_id, user_id)
            if ok:
                toast_type = "success"
                if data and data.get("state") == "resolved":
                    toast_type = "info"
                return {"type": toast_type, "message": msg}, render_gate_alerts_section(society_id)
            return {"type": "error", "message": msg}, no_update
        except Exception as e:
            logger.error(f"trigger_gate_alert error: {e}")
            return {"type": "error", "message": str(e)}, no_update

    # ── 2. Escalate to Call (second press while pending) ────────────────────
    @app.callback(
        Output("gate-alert-toast", "data", allow_duplicate=True),
        Output("gate-alerts-refresh", "children", allow_duplicate=True),
        Input({"type": "gate-alert-call-btn", "alert_event_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def escalate_to_call(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        alert_event_id = triggered.get("alert_event_id")
        if not alert_event_id:
            return no_update, no_update

        auth = auth or {}
        society_id = auth.get("society_id") or auth.get("linked_id")

        try:
            db._execute("""
                UPDATE alert_events SET state = 'calling' WHERE id = %s
            """, (alert_event_id,))
            return (
                {"type": "warning", "message": "Escalated: Calling owner for verbal confirmation"},
                render_gate_alerts_section(society_id),
            )
        except Exception as e:
            logger.error(f"escalate_to_call error: {e}")
            return {"type": "error", "message": str(e)}, no_update

    # ── 3. Trigger Presumed Visitor Alert ──────────────────────────────────
    @app.callback(
        Output("gate-alert-toast", "data", allow_duplicate=True),
        Output("gate-alerts-refresh", "children", allow_duplicate=True),
        Input({"type": "presumed-visitor-notify-btn", "visitor_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def notify_presumed_visitor(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        visitor_id = triggered.get("visitor_id")
        if not visitor_id:
            return no_update, no_update

        auth = auth or {}
        user_id = auth.get("user_id")
        society_id = auth.get("society_id") or auth.get("linked_id")

        try:
            ok, msg, data = trigger_visitor_alert(visitor_id, user_id)
            if ok:
                return {"type": "success", "message": msg}, render_gate_alerts_section(society_id)
            return {"type": "error", "message": msg}, no_update
        except Exception as e:
            logger.error(f"notify_presumed_visitor error: {e}")
            return {"type": "error", "message": str(e)}, no_update

    # ── 4. Escalate Presumed Visitor to Call ───────────────────────────────
    @app.callback(
        Output("gate-alert-toast", "data", allow_duplicate=True),
        Output("gate-alerts-refresh", "children", allow_duplicate=True),
        Input({"type": "presumed-visitor-call-btn", "visitor_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def call_presumed_visitor(n_clicks_list, auth):
        if not any(n for n in (n_clicks_list or []) if n):
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        visitor_id = triggered.get("visitor_id")
        if not visitor_id:
            return no_update, no_update

        auth = auth or {}
        society_id = auth.get("society_id") or auth.get("linked_id")

        try:
            db._execute("""
                UPDATE alert_events SET state = 'calling'
                 WHERE visitor_id = %s AND state = 'pending'
                   AND (expires_at IS NULL OR expires_at > NOW())
            """, (visitor_id,))
            return (
                {"type": "warning", "message": "Escalated: Calling owner for verbal confirmation"},
                render_gate_alerts_section(society_id),
            )
        except Exception as e:
            logger.error(f"call_presumed_visitor error: {e}")
            return {"type": "error", "message": str(e)}, no_update

    # ── 5. Create Walk-in Visitor ──────────────────────────────────────────
    @app.callback(
        Output("gate-alert-toast", "data", allow_duplicate=True),
        Output("walk-in-visitor-form-container", "children", allow_duplicate=True),
        Input("walk-in-visitor-submit-btn", "n_clicks"),
        State("walk-in-visitor-name", "value"),
        State("walk-in-visitor-mobile", "value"),
        State("walk-in-visitor-purpose", "value"),
        State("walk-in-visitor-flat", "value"),
        State("walk-in-visitor-vehicle", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def create_walk_in_visitor_handler(n_clicks, name, mobile, purpose, flat, vehicle, auth):
        if not n_clicks:
            return no_update, no_update

        auth = auth or {}
        user_id = auth.get("user_id")
        society_id = auth.get("society_id") or auth.get("linked_id")

        if not user_id or not society_id:
            return {"type": "error", "message": "Session expired"}, no_update

        if not name or not name.strip():
            return {"type": "warning", "message": "Visitor name is required"}, no_update

        if not purpose or not purpose.strip():
            return {"type": "warning", "message": "Purpose of visit is required"}, no_update

        # Resolve apartment_id from flat number
        apartment_id = None
        if flat and flat.strip():
            apt = db._execute("""
                SELECT id FROM apartments WHERE society_id=%s AND flat_number=%s AND active=TRUE
            """, (society_id, flat.strip()), fetch_one=True)
            if apt:
                apartment_id = apt["id"]

        try:
            visitor_id, msg = create_walk_in_visitor(
                society_id=society_id,
                name=name.strip(),
                mobile=mobile.strip() if mobile else "",
                purpose=purpose.strip(),
                apartment_id=apartment_id,
                vehicle_number=vehicle.strip() if vehicle else "",
                security_user_id=user_id,
            )
            if not visitor_id:
                return {"type": "error", "message": msg}, no_update

            # Auto-trigger alert to owner
            ok, alert_msg, data = trigger_visitor_alert(visitor_id, user_id)
            if ok:
                return (
                    {"type": "success", "message": f"Visitor created and owner notified: {alert_msg}"},
                    render_walk_in_visitor_form(),
                )
            return {"type": "error", "message": f"Visitor created but alert failed: {alert_msg}"}, no_update
        except Exception as e:
            logger.error(f"create_walk_in_visitor_handler error: {e}")
            return {"type": "error", "message": str(e)}, no_update

    # ── 6. QR Scan Result (shared with admin) ──────────────────────────────
    @app.callback(
        Output("security-scan-result", "children"),
        Output("security-scan-result", "style"),
        Input("security-validate-btn", "n_clicks"),
        State("security-qr-input", "value"),
        prevent_initial_call=True
    )
    def validate_qr(n_clicks, qr_data):
        if not n_clicks or not qr_data:
            return no_update, no_update

        result = validate_qr_code(qr_data, None)

        if result.get("status") == "PASS":
            return html.Div([
                html.I(className="fas fa-check-circle fa-3x mb-2", style={"color": "#2ecc71"}),
                html.H4("Access Granted", style={"color": "#2ecc71"}),
                html.P(f"Welcome {result.get('user', {}).get('name', 'Visitor')}!"),
                html.Hr(),
                html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            ]), {"backgroundColor": "#d4edda", "color": "#155724", "borderRadius": "10px"}
        else:
            return html.Div([
                html.I(className="fas fa-times-circle fa-3x mb-2", style={"color": "#e74c3c"}),
                html.H4("Access Denied", style={"color": "#e74c3c"}),
                html.P(result.get("reason", "Invalid QR code")),
                html.Hr(),
                html.Small("Please contact security administrator")
            ]), {"backgroundColor": "#f8d7da", "color": "#721c24", "borderRadius": "10px"}

    # ── 7. Attendance ──────────────────────────────────────────────────────
    @app.callback(
        Output("attendance-status", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("clock-in-btn", "n_clicks"),
        Input("clock-out-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True
    )
    def manage_attendance(clock_in_clicks, clock_out_clicks, auth_data):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        society_id = (auth_data or {}).get("society_id")
        user_id = (auth_data or {}).get("user_id")
        if not user_id or not society_id:
            return no_update, {"type": "error", "message": "Session expired — please log in again"}

        now_str = datetime.now().strftime("%I:%M %p")

        if button_id == "clock-in-btn":
            already_in = db._execute(
                """SELECT id FROM gate_access
                   WHERE society_id = %s AND entity_id = %s AND role = 's'
                     AND time_out IS NULL
                   ORDER BY time_in DESC LIMIT 1""",
                (society_id, user_id), fetch_one=True
            )
            if already_in:
                return no_update, {"type": "error", "message": "Already clocked in — clock out first"}

            db._execute(
                """INSERT INTO gate_access (society_id, role, entity_id, time_in, created_by)
                   VALUES (%s, 's', %s, NOW(), %s)""",
                (society_id, user_id, user_id)
            )
            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#2ecc71"}),
                html.H5("Clocked In"),
                html.Small(now_str)
            ]), {"type": "success", "message": "Clocked in successfully"}

        else:
            updated = db._execute(
                """UPDATE gate_access SET time_out = NOW(), updated_by = %s
                   WHERE id = (
                       SELECT id FROM gate_access
                       WHERE society_id = %s AND entity_id = %s AND role = 's'
                         AND time_out IS NULL
                       ORDER BY time_in DESC LIMIT 1
                   )
                   RETURNING id""",
                (user_id, society_id, user_id), fetch_one=True
            )
            if not updated:
                return no_update, {"type": "error", "message": "You're not clocked in"}

            return html.Div([
                html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#e74c3c"}),
                html.H5("Clocked Out"),
                html.Small(now_str)
            ]), {"type": "success", "message": "Clocked out successfully"}
