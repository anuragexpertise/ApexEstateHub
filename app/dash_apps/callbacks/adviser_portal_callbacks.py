# app/dash_apps/callbacks/adviser_portal_callbacks.py
"""The adviser's ledger download. The society and the user come from the SERVER session; adviser_access decides every time."""
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, no_update

from app.security import adviser_access as aa
from app.security.audit_context import get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import adviser_export as ae


def register_adviser_portal_callbacks(app):

    @app.callback(Output("adv-export-dl", "data"), Output("adv-export-msg", "children"),
                  Input("adv-export-btn", "n_clicks"), prevent_initial_call=True)
    @require_session
    def adviser_export(n):
        uid = get_current_user_id()
        if not n or not uid or get_current_user_role() != "adviser":
            return no_update, no_update
        try:
            name, data, rows = ae.ledger_csv(uid)
        except aa.AdviserRefused as exc:
            return no_update, dbc.Alert(str(exc), color="danger", className="py-2")
        return dcc.send_bytes(data, name), dbc.Alert(f"{rows} lines exported and logged.", color="success", className="py-2")

    print("  ✓ Adviser portal callbacks registered")
