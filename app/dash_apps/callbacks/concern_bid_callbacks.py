# app/dash_apps/callbacks/concern_bid_callbacks.py
"""
Concern Bid Modal Callbacks
============================
Vendor/security's "Save Bid" action on a concern profile — the BID stage
of the unified concerns_assigns lifecycle (invited -> bid_submitted ->
assigned -> resolved -> closed). Small single-field modal (concern-bid-modal
/ concern-bid-store in app_shell.py) — writes concerns_assigns.bid_amount
and advances status for the CURRENT user's own 'invited' assignment row.

UI flow:
  1. Vendor/security clicks "Save Bid" on a concern profile -> modal opens
  2. They enter an amount -> Submit
  3. Writes concerns_assigns.bid_amount + status='bid_submitted' via
     loaders.submit_concern_bid() — only succeeds if their row is currently
     'invited'
  4. Push-notifies admin + the concern's creator apartment
  5. Modal closes, concern list/profile refreshes
"""

from __future__ import annotations

from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate
from database.db_manager import db
from app.dash_apps.drilldown import loaders
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
    get_current_linked_id,   # only if the file has an ownership check (apartment/vendor/security's own record)
)

# Maps auth-store "role" values to the role codes used in concerns_assigns.
# Vendor portal only, per the Concerns workflow spec
# (workflow_vendor_kpi_list_profile) — security does not bid.
BID_ROLE_CODE = {"vendor": "VND"}


def register_concern_bid_callbacks(app):
    """Register the Save-Bid modal callbacks."""

    # ── 1. Open modal from concern profile action ────────────────────────────
    @app.callback(
        Output("concern-bid-modal", "is_open", allow_duplicate=True),
        Output("concern-bid-store", "data", allow_duplicate=True),
        Output("concern-bid-amount-input", "value"),
        Output("concern-bid-error", "children"),
        Input("profile-action-trigger", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def open_bid_modal(trigger_data, auth):
        if not trigger_data or not isinstance(trigger_data, dict):
            raise PreventUpdate
        if trigger_data.get("action") != "open_bid_modal":
            raise PreventUpdate
        params = trigger_data.get("params") or {}
        concern_id = params.get("concern_id")
        if not concern_id:
            return False, no_update, no_update, no_update

        # Pre-fill with the caller's existing bid, if any.
        role_code = BID_ROLE_CODE.get(get_current_user_role())
        entity_id = get_current_linked_id()  # only if the file has an ownership check (apartment/vendor/security's own record)
        existing = None
        if role_code and entity_id:
            row = db._execute(
                "SELECT bid_amount FROM concerns_assigns "
                "WHERE concern_id=%s AND role=%s AND entity_id=%s",
                (int(concern_id), role_code, int(entity_id)), fetch_one=True,
            )
            existing = (row or {}).get("bid_amount")
        return True, {"concern_id": int(concern_id)}, existing, ""

    # ── 2. Close modal ────────────────────────────────────────────────────────
    @app.callback(
        Output("concern-bid-modal", "is_open", allow_duplicate=True),
        Input("close-concern-bid-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def close_bid_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Submit bid ─────────────────────────────────────────────────────────
    @app.callback(
        Output("concern-bid-modal", "is_open", allow_duplicate=True),
        Output("concern-bid-error", "children", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Input("concern-bid-submit-btn", "n_clicks"),
        State("concern-bid-store", "data"),
        State("concern-bid-amount-input", "value"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def submit_bid(n_clicks, store, bid_amount, auth, drill_store):
        if not n_clicks:
            raise PreventUpdate
        store = store or {}
        concern_id = store.get("concern_id")
        if not concern_id:
            return False, "", {"type": "warning", "message": "No concern selected."}, no_update, no_update, no_update

        society_id = get_current_society_id()
        role_code = BID_ROLE_CODE.get(get_current_user_role())
        entity_id = get_current_linked_id()  # only if the file has an ownership check (apartment/vendor/security's own record)
        if not society_id or not role_code or not entity_id:
            return False, "", {"type": "error", "message": "Only an invited vendor or security staff can bid."}, no_update, no_update, no_update

        ok, msg = loaders.submit_concern_bid(concern_id, society_id, role_code, entity_id, bid_amount)
        if not ok:
            return True, msg, no_update, no_update, no_update, no_update

        try:
            from app.services.push_service import notify_concern_bid_saved
            concern_row = db._execute(
                "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                (concern_id, society_id), fetch_one=True,
            )
            if role_code == "VND":
                e_row = db._execute(
                    "SELECT business_name, name FROM vendors WHERE id=%s AND society_id=%s",
                    (entity_id, society_id), fetch_one=True,
                )
                bidder_label = (e_row or {}).get("business_name") or (e_row or {}).get("name")
            else:
                e_row = db._execute(
                    "SELECT name FROM security_staff WHERE id=%s AND society_id=%s",
                    (entity_id, society_id), fetch_one=True,
                )
                bidder_label = (e_row or {}).get("name")
            if concern_row:
                notify_concern_bid_saved(
                    society_id, concern_row.get("apartment_id"), concern_row.get("concern_type"), bidder_label,
                )
            else:
                import logging
                logging.getLogger(__name__).warning(
                    "notify_concern_bid_saved skipped: concern %s not found in society %s (possibly deleted)",
                    concern_id, society_id,
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(
                "notify_concern_bid_saved failed (concern_id=%s): %s", concern_id, e,
            )

        from app.dash_apps.callbacks.drilldown_callbacks import _render_current
        content, breadcrumb, db_err = _render_current(drill_store or {}, auth or {})
        return (
            False, "",
            {"type": "success", "message": msg},
            no_update, content, breadcrumb,
        )

    print("  ✓ Concern-bid callbacks registered")
