"""
Callbacks for the "GST Accounts" tab: classify one income or fund account for the GST turnover worksheet.

Who: the CA (accountant login), the Treasurer, or the Secretary while no Treasurer is seated: the same people who may edit
TDS and GST rates. The service asks the policy engine (finance.taxrates.manage) and the committee on every write; this
callback never trusts a society or user from the browser.
"""
from dash import MATCH, Input, Output, State, ctx, no_update

from app.dash_apps.pages import gst_accounts_page as gp
from app.security.audit_context import get_current_society_id
from app.security.guards import require_session
from app.services import gst_classification as gc

P = gp.P


def register_gst_class_callbacks(app):

    @app.callback(
        Output({"type": f"{P}-row", "id": MATCH}, "children"),
        Input({"type": f"{P}-save", "id": MATCH}, "n_clicks"),
        State({"type": f"{P}-class", "id": MATCH}, "value"),
        State({"type": f"{P}-ref", "id": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def gsa_save(n, supply_class, ref):
        trig = ctx.triggered_id
        sid = get_current_society_id()
        if not n or not trig or not sid:
            return no_update
        sid, acc_id = int(sid), int(trig["id"])
        try:
            msg, ok = gc.classify(sid, acc_id, supply_class, ref), True
        except (ValueError, PermissionError) as exc:
            msg, ok = str(exc), False
        row = next((a for a in gc.accounts(sid) if a["id"] == acc_id), None)
        if row is None:
            return gp.row_cells({"id": acc_id, "name": "Account", "tab_name": "", "amount": 0, "supply_class": None}, False,
                                "That account does not belong to this society.", False)
        return gp.row_cells(row, gp.trs.may_edit_tax_rates(sid)[0], msg, ok)
