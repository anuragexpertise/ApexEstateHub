# app/dash_apps/callbacks/patrol_location_callbacks.py
"""
Patrol Locations — minimal admin create + list + reissue flow (2026-09).

Prior to this, patrol_locations had zero rows anywhere in the codebase and
no INSERT path at all — the table, its BEFORE INSERT qr_payload trigger,
and its (read-only) drilldown profile card existed, but nothing could
actually create a row. This adds the minimum needed to make the table
usable: an admin-only Add form, a list, and a QR view/reissue action.

Deliberately NOT wired into the schema-driven drilldown/DRILLDOWN_MAP
system — registry.py explicitly opts patrol_location OUT of that (see
_NO_AUTO_ACTIONS and profile_patrol_location's empty "actions" block,
with a comment saying so) as a read-only QR-scan profile. Forcing it into
that generic engine would fight an existing, deliberate architectural
line rather than just adding the one thing that was actually missing
(a way to create a row). This is a self-contained page section instead.

QR view/reissue for a patrol location reuses the EXISTING shared qr-modal
and profile-action-trigger mechanism (the same one an admin uses to pull
up an apartment/vendor/security profile's "Gate Pass" QR) rather than
building a second QR display — patrol_location was added to
qr_service._QR_VERSIONED_ROLES / _QR_SIGNABLE_ROLES, so
generate_static_qr_code/revoke_and_reissue already work for role=
'patrol_location' with no changes needed there. This module only needs to
write {'entity_id','role','society_id','name'} to profile-action-trigger,
same shape toggle_qr_modal (qr_callbacks.py) already consumes.
"""

from dash import Input, Output, State, dcc, html, no_update, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.security.guards import require_session
from app.security.audit_context import get_current_user_id, get_current_user_role, get_current_society_id
from database.db_manager import db


def render_patrol_locations_section(sid) -> html.Div:
    """Called directly from portal_pages.py (admin Settings tab), same as
    _kpi_row_dynamic — a synchronous render, not itself a callback. The
    list refreshes via patrol-locations-list-refresh (a dcc.Store bump)
    after add/reissue."""
    return html.Div(
        [
            html.Hr(),
            html.Div(
                [
                    html.Div(
                        [
                            html.I(className="fas fa-shield-halved me-2",
                                   style={"color": "#7d8ea3", "fontSize": "13px"}),
                            html.Span("Patrol Locations",
                                      style={"fontWeight": "700", "fontSize": "14px", "color": "#15304f"}),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Div(
                        [
                            dbc.Button([html.I(className="fas fa-file-excel me-2"), "Export QR Audit Log"],
                                       id="qr-audit-export-btn", n_clicks=0,
                                       color="secondary", outline=True, size="sm",
                                       style={"marginRight": "8px"}),
                            dbc.Button([html.I(className="fas fa-plus me-2"), "Add Location"],
                                       id="patrol-loc-add-toggle-btn", n_clicks=0,
                                       color="primary", size="sm"),
                        ],
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "justifyContent": "space-between",
                       "marginBottom": "14px"},
            ),
            dcc.Download(id="qr-audit-export-download"),
            dcc.Store(id="patrol-locations-list-refresh", storage_type="memory", data=0),
            dbc.Collapse(
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Row(
                                [
                                    dbc.Col(dbc.Input(id="patrol-loc-name-input", placeholder="Location name (e.g. Block A Gate)"), md=4),
                                    dbc.Col(dbc.Input(id="patrol-loc-desc-input", placeholder="Description (optional)"), md=4),
                                    dbc.Col(dbc.Input(id="patrol-loc-interval-input", type="number", placeholder="Scan interval (min)", value=120), md=4),
                                ],
                                className="g-2",
                            ),
                            dbc.Row(
                                [
                                    dbc.Col(dbc.Input(id="patrol-loc-start-input", type="time", placeholder="Schedule start"), md=4),
                                    dbc.Col(dbc.Input(id="patrol-loc-end-input", type="time", placeholder="Schedule end"), md=4),
                                    dbc.Col(
                                        dbc.Button("Save Location", id="patrol-loc-save-btn", n_clicks=0,
                                                    color="success", style={"width": "100%"}),
                                        md=4,
                                    ),
                                ],
                                className="g-2 mt-1",
                            ),
                        ]
                    ),
                    style={"marginBottom": "14px"},
                ),
                id="patrol-loc-add-collapse", is_open=False,
            ),
            html.Div(id="patrol-locations-list"),
        ],
        id="patrol-locations-section",
    )


def _render_patrol_locations_list(sid) -> html.Div:
    rows = db._execute(
        """SELECT id, location_name, description, active, qr_version,
                  schedule_start, schedule_end, scan_interval
             FROM patrol_locations
            WHERE society_id = %s
            ORDER BY location_name""",
        (sid,), fetch_all=True,
    ) or []

    if not rows:
        return html.Div("No patrol locations yet — add one above.",
                         style={"color": "#9aa5b1", "fontSize": "12px", "padding": "10px 0"})

    items = []
    for r in rows:
        items.append(
            dbc.Row(
                [
                    dbc.Col(html.Div([
                        html.Span(r["location_name"], style={"fontWeight": "600", "fontSize": "13px"}),
                        html.Span(" (inactive)", style={"color": "#c0392b", "fontSize": "11px"}) if not r["active"] else None,
                    ]), md=4),
                    dbc.Col(html.Span(r.get("description") or "—", style={"fontSize": "12px", "color": "#6b7a8f"}), md=4),
                    dbc.Col(html.Span(f"Every {r.get('scan_interval') or 120} min",
                                       style={"fontSize": "12px", "color": "#6b7a8f"}), md=2),
                    dbc.Col(
                        dbc.Button([html.I(className="fas fa-qrcode me-1"), "QR"],
                                   id={"type": "patrol-loc-qr-btn", "id": r["id"], "name": r["location_name"]},
                                   n_clicks=0, color="info", size="sm", outline=True,
                                   style={"width": "100%"}),
                        md=2,
                    ),
                ],
                className="g-2 align-items-center",
                style={"padding": "8px 4px", "borderBottom": "1px solid #eef1f5"},
            )
        )
    return html.Div(items)


def register_patrol_location_callbacks(app):

    # ── Toggle add-location form ────────────────────────────────────
    @app.callback(
        Output("patrol-loc-add-collapse", "is_open"),
        Input("patrol-loc-add-toggle-btn", "n_clicks"),
        State("patrol-loc-add-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_add_patrol_location(n_clicks, is_open):
        if not n_clicks:
            raise PreventUpdate
        return not is_open

    # ── Render / refresh the list ───────────────────────────────────
    @app.callback(
        Output("patrol-locations-list", "children"),
        Input("patrol-locations-list-refresh", "data"),
        prevent_initial_call=False,
    )
    @require_session
    def render_list(_):
        sid = get_current_society_id()
        if not sid:
            raise PreventUpdate
        return _render_patrol_locations_list(sid)

    # ── Save a new patrol location ──────────────────────────────────
    @app.callback(
        Output("patrol-locations-list-refresh", "data", allow_duplicate=True),
        Output("patrol-loc-add-collapse", "is_open", allow_duplicate=True),
        Output("patrol-loc-name-input", "value"),
        Output("patrol-loc-desc-input", "value"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("patrol-loc-save-btn", "n_clicks"),
        State("patrol-loc-name-input", "value"),
        State("patrol-loc-desc-input", "value"),
        State("patrol-loc-interval-input", "value"),
        State("patrol-loc-start-input", "value"),
        State("patrol-loc-end-input", "value"),
        State("patrol-locations-list-refresh", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def save_patrol_location(n_clicks, name, desc, interval, start, end, refresh_count):
        if not n_clicks:
            raise PreventUpdate

        role = get_current_user_role() or ""
        if role != "admin":
            return no_update, no_update, no_update, no_update, {
                "type": "error", "message": "Only an admin can add a patrol location."
            }

        if not name or not name.strip():
            return no_update, no_update, no_update, no_update, {
                "type": "warning", "message": "Location name is required."
            }

        sid = get_current_society_id()
        uid = get_current_user_id()

        # qr_payload deliberately omitted — fn_trg_patrol_locations_qr
        # (BEFORE INSERT) fills in the canonical "<society_id>-PTL-<id>"
        # format, same as concerns/receipts/expenses/assets/events already
        # rely on. qr_version is left to its column DEFAULT (a random
        # 4-digit value), not set explicitly here.
        db._execute(
            """INSERT INTO patrol_locations
                   (society_id, location_name, description, schedule_start,
                    schedule_end, scan_interval, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (sid, name.strip(), (desc or "").strip() or None,
             start or None, end or None, interval or 120, uid),
        )

        return (refresh_count or 0) + 1, False, "", "", {
            "type": "success", "message": f'Patrol location "{name.strip()}" added.'
        }

    # ── "QR" button on a row -> reuse the existing shared qr-modal ──
    @app.callback(
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input({"type": "patrol-loc-qr-btn", "id": ALL, "name": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def open_patrol_location_qr(n_clicks_list):
        from dash import ctx
        if not ctx.triggered_id or not any(n_clicks_list):
            raise PreventUpdate

        role = get_current_user_role() or ""
        if role != "admin":
            # toggle_qr_modal's profile-action-trigger branch already
            # re-checks admin/master, but fail fast here too rather than
            # write a store update that'll just get rejected downstream.
            raise PreventUpdate

        sid = get_current_society_id()
        return {
            "action": "open_gate_pass",
            "entity_id": ctx.triggered_id["id"],
            "role": "patrol_location",
            "society_id": sid,
            "name": ctx.triggered_id["name"],
        }

    # ── Export QR reissue audit log as xlsx ─────────────────────────
    @app.callback(
        Output("qr-audit-export-download", "data"),
        Input("qr-audit-export-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def export_qr_audit_log(n_clicks):
        if not n_clicks:
            raise PreventUpdate

        role = get_current_user_role() or ""
        if role != "admin":
            raise PreventUpdate

        sid = get_current_society_id()
        from database.qr_reissue_export import generate_qr_reissue_log_excel
        data = generate_qr_reissue_log_excel(None, sid)
        filename = f"QR_Reissue_Log_Society{sid}.xlsx"
        return dcc.send_bytes(lambda buf: buf.write(data), filename=filename)
