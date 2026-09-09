# app/dash_apps/callbacks/qr_reissue_callbacks.py
"""
Re-issue QR — Settings tab, admin-only (2026-09).

Replaces the old in-modal "Revoke & Reissue" button that used to live
inside the Gate Pass QR viewer (qr-modal in app_shell.py). That button let
an admin revoke whatever entity's QR they happened to already have open —
this tool instead makes revoking a printed pass its own deliberate
Settings-tab action: the admin manually selects the entity (by role+id, or
by pasting/scanning the QR string itself) and must additionally type the
society's own SIGNING_SECRET to confirm, on top of already being logged in
as admin. Every action is still logged to qr_reissue_log (reason + actor +
timestamp), same as before — see render_qr_reissue_card for the log table
and loaders.get_qr_reissue_log for how it's read back.

Three callbacks:
  1. lookup_reissue_entity   — role+id "Look Up" button
  2. parse_reissue_qr        — "Parse QR" button (pasted QR string)
  3. confirm_reissue         — "Confirm Re-issue" button (does the actual
                                revoke_and_reissue call)

(1) and (2) both just resolve an entity and write the SAME
qr-reissue-resolved-store shape: {"role_code", "entity_id", "label"} or
{"error": ...} — (3) only reads that store, it doesn't care which path
produced it.
"""

from dash import Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.security.guards import require_session
from app.security.audit_context import get_current_user_role, get_current_user_id, get_current_society_id


def _resolved_ok_display(label: str, role_code: str, entity_id: int) -> html.Div:
    return html.Div([
        html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
        html.Span(f"{label} ", style={"fontWeight": "600"}),
        html.Span(f"({role_code} #{entity_id})", style={"color": "#7d8ea3", "fontSize": "12px"}),
    ])


def _resolved_error_display(message: str) -> html.Div:
    return html.Div([
        html.I(className="fas fa-times-circle me-2", style={"color": "#e74c3c"}),
        html.Span(message),
    ])


def register_qr_reissue_callbacks(app):

    # ── 1. Manual role+id lookup ────────────────────────────────────────
    # ── 1. Manual role+id+date-of-issue lookup ──────────────────────────
    # Requires all three to match a real record — role+id alone is
    # guessable (sequential ids), so the date of issue (visible on the
    # printed pass) is what proves the admin actually has that entity's
    # record in front of them rather than probing IDs one at a time.
    @app.callback(
        Output("qr-reissue-resolved-display", "children"),
        Output("qr-reissue-resolved-store", "data"),
        Input("qr-reissue-lookup-btn", "n_clicks"),
        State("qr-reissue-role-select", "value"),
        State("qr-reissue-entity-id-input", "value"),
        State("qr-reissue-issue-date", "date"),
        prevent_initial_call=True,
    )
    @require_session
    def lookup_reissue_entity(n_clicks, role_code, entity_id, issue_date):
        if not n_clicks:
            raise PreventUpdate
        if get_current_user_role() != "admin":
            raise PreventUpdate
        if not role_code or not entity_id or not issue_date:
            return _resolved_error_display(
                "Select a role, enter the entity ID, and pick its date of issue."
            ), None

        from app.services.qr_service import resolve_entity_for_reissue
        society_id = get_current_society_id()
        result = resolve_entity_for_reissue(role_code, int(entity_id), society_id, issue_date)
        if "error" in result:
            return _resolved_error_display(result["error"]), None

        data = {"role_code": role_code, "entity_id": int(entity_id), "label": result["label"]}
        return _resolved_ok_display(result["label"], role_code, int(entity_id)), data

    # ── 2. Scan/paste an existing, currently-valid QR ───────────────────
    # Strict by design: verify_scanned_qr requires a real signature that
    # matches the entity's CURRENT qr_version — this only recognizes a QR
    # that is genuinely, presently valid for this society, not just a
    # correctly-shaped string. That's the equivalent proof-of-legitimacy
    # for this path that the date-of-issue check is for the manual path.
    @app.callback(
        Output("qr-reissue-resolved-display", "children", allow_duplicate=True),
        Output("qr-reissue-resolved-store", "data", allow_duplicate=True),
        Input("qr-reissue-parse-btn", "n_clicks"),
        State("qr-reissue-qr-paste", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def parse_reissue_qr(n_clicks, qr_data):
        if not n_clicks:
            raise PreventUpdate
        if get_current_user_role() != "admin":
            raise PreventUpdate
        if not (qr_data or "").strip():
            return _resolved_error_display("Paste or scan a QR string first."), None

        from app.services.qr_service import verify_scanned_qr, resolve_entity_for_reissue
        society_id = get_current_society_id()
        verified = verify_scanned_qr(qr_data.strip(), society_id)
        if "error" in verified:
            return _resolved_error_display(verified["error"]), None

        role_code = verified["role_code"]
        entity_id = verified["entity_id"]
        # verify_scanned_qr already proved this QR is real, current, and
        # for this society — no date-of-issue needed on this path.
        result = resolve_entity_for_reissue(role_code, entity_id, society_id)
        if "error" in result:
            return _resolved_error_display(result["error"]), None

        data = {"role_code": role_code, "entity_id": entity_id, "label": result["label"]}
        return _resolved_ok_display(result["label"], role_code, entity_id), data

    # ── 3. Confirm — the only place this tool actually calls
    #      revoke_and_reissue. Requires: admin role (re-checked here, not
    #      just at the KPI-click/render gate), a resolved entity, a reason,
    #      AND the society's own SIGNING_SECRET typed correctly — being
    #      logged in as admin alone is not enough, since this immediately
    #      and irreversibly invalidates a real printed pass.
    @app.callback(
        Output("qr-reissue-result", "children"),
        Output("qr-reissue-log-tbody", "children"),
        Output("qr-reissue-secret-input", "value"),
        Input("qr-reissue-confirm-btn", "n_clicks"),
        State("qr-reissue-resolved-store", "data"),
        State("qr-reissue-reason", "value"),
        State("qr-reissue-secret-input", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def confirm_reissue(n_clicks, resolved, reason, typed_secret):
        if not n_clicks:
            raise PreventUpdate
        if get_current_user_role() != "admin":
            return dbc.Alert("Only an admin can re-issue a QR code.", color="danger"), no_update, ""

        if not resolved or not resolved.get("role_code") or not resolved.get("entity_id"):
            return dbc.Alert("Look up or parse an entity first.", color="warning"), no_update, no_update
        if not reason:
            return dbc.Alert("Select a reason.", color="warning"), no_update, no_update

        from app.services.qr_service import verify_signing_secret, revoke_and_reissue
        society_id = get_current_society_id()
        if not verify_signing_secret(society_id, typed_secret or ""):
            return dbc.Alert("Signing Secret did not match.", color="danger"), no_update, ""

        actor_user_id = get_current_user_id()
        try:
            src, payload, old_nonce, new_nonce = revoke_and_reissue(
                society_id, resolved["role_code"], resolved["entity_id"],
                reason, actor_user_id, resolved.get("label"),
            )
        except (ValueError, RuntimeError) as e:
            return dbc.Alert(str(e), color="danger"), no_update, ""

        if not src:
            return dbc.Alert(f"Re-issue failed: {payload}", color="danger"), no_update, ""

        from app.dash_apps.drilldown import loaders
        from app.dash_apps.drilldown.renderers import _qr_reissue_log_rows

        result_card = html.Div([
            dbc.Alert(
                f"{resolved.get('label')} — old code revoked (reason: {reason}). "
                f"New code generated below.",
                color="success",
            ),
            html.Img(src=src, style={"width": "160px", "height": "160px",
                                      "display": "block", "margin": "10px auto",
                                      "border": "2px solid #667eea", "borderRadius": "10px",
                                      "padding": "6px"}),
            dbc.Textarea(value=payload, readOnly=True,
                         style={"marginTop": "8px", "fontFamily": "monospace",
                                "fontSize": "13px", "textAlign": "center", "resize": "none"}),
        ])

        log_rows = loaders.get_qr_reissue_log(society_id)
        # Secret field is cleared on every outcome (success or failure) —
        # it's a one-shot confirmation, never left sitting in the input.
        return result_card, _qr_reissue_log_rows(log_rows), ""
