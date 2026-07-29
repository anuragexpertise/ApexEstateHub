# app/dash_apps/callbacks/concern_bid_callbacks.py
"""
Concern Bid Modal Callbacks
============================
Vendor's "Save Bid" action on a concern profile. Small single-field modal
(concern-bid-modal / concern-bid-store in app_shell.py) — writes
concerns_assigns.bid_amount for the CURRENT vendor's own assignment row.

UI flow:
  1. Vendor clicks "Save Bid" on a concern profile -> modal opens
  2. Vendor enters an amount -> Submit
  3. Writes concerns_assigns.bid_amount via loaders.save_concern_bid()
  4. Push-notifies admin + the concern's creator apartment
  5. Modal closes, concern list/profile refreshes
"""

from __future__ import annotations

from dash import Input, Output, State, no_update
from dash.exceptions import PreventUpdate
from dash.exceptions import PreventUpdate
from database.db_manager import db
from app.dash_apps.drilldown import loaders


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
    def open_bid_modal(trigger_data, auth):
        if not trigger_data or not isinstance(trigger_data, dict):
            raise PreventUpdate
        if trigger_data.get("action") != "open_bid_modal":
            raise PreventUpdate
        params = trigger_data.get("params") or {}
        concern_id = params.get("concern_id")
        if not concern_id:
            return False, no_update, no_update, no_update

        # Pre-fill with the vendor's existing bid, if any.
        vendor_entity_id = (auth or {}).get("linked_id")
        existing = None
        if vendor_entity_id:
            row = db._execute(
                "SELECT bid_amount FROM concerns_assigns "
                "WHERE concern_id=%s AND role='VND' AND entity_id=%s",
                (int(concern_id), int(vendor_entity_id)), fetch_one=True,
            )
            existing = (row or {}).get("bid_amount")
        return True, {"concern_id": int(concern_id)}, existing, ""

    # ── 2. Close modal ────────────────────────────────────────────────────────
    @app.callback(
        Output("concern-bid-modal", "is_open", allow_duplicate=True),
        Input("close-concern-bid-modal", "n_clicks"),
        prevent_initial_call=True,
    )
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
    def submit_bid(n_clicks, store, bid_amount, auth, drill_store):
        if not n_clicks:
            raise PreventUpdate
        store = store or {}
        concern_id = store.get("concern_id")
        if not concern_id:
            return False, "", {"type": "warning", "message": "No concern selected."}, no_update, no_update, no_update

        society_id = (auth or {}).get("society_id")
        vendor_entity_id = (auth or {}).get("linked_id")
        if not society_id or (auth or {}).get("role") != "vendor" or not vendor_entity_id:
            return False, "", {"type": "error", "message": "Only an assigned vendor can bid."}, no_update, no_update, no_update

        ok, msg = loaders.save_concern_bid(concern_id, society_id, vendor_entity_id, bid_amount)
        if not ok:
            return True, msg, no_update, no_update, no_update, no_update

        try:
            from app.services.push_service import notify_concern_bid_saved
            concern_row = db._execute(
                "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                (concern_id, society_id), fetch_one=True,
            )
            v_row = db._execute(
                "SELECT business_name, name FROM vendors WHERE id=%s AND society_id=%s",
                (vendor_entity_id, society_id), fetch_one=True,
            )
            vendor_label = (v_row or {}).get("business_name") or (v_row or {}).get("name")
            if concern_row:
                notify_concern_bid_saved(
                    society_id, concern_row.get("apartment_id"), concern_row.get("concern_type"), vendor_label,
                )
        except Exception as e:
            print(f"⚠️  notify_concern_bid_saved failed: {e}")

        from app.dash_apps.callbacks.drilldown_callbacks import _render_current
        content, breadcrumb, db_err = _render_current(drill_store or {}, auth or {})
        return (
            False, "",
            {"type": "success", "message": msg},
            no_update, content, breadcrumb,
        )

    print("  ✓ Concern-bid callbacks registered")
