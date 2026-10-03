# app/dash_apps/callbacks/up_compliance_callbacks.py
"""
Callbacks for the admin-only "UP AOA Compliance" card. Thin wrappers: they authenticate,
resolve the society from the session (never from the browser), call the handler in
app.services.up_aoa_actions, then refresh the card body on success.
"""
import dash_bootstrap_components as dbc
from dash import Input, Output, State, dcc, html, no_update
from dash.exceptions import PreventUpdate

from app.dash_apps.pages.up_compliance_card import render_up_compliance_body
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.services import up_aoa_actions as act

_TOAST = Output("upc-toast", "children", allow_duplicate=True)
_BODY = Output("upc-body", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _ctx():
    """(society_id, user_id) for an authenticated admin, else (None, error alert)."""
    if get_current_user_role() != "admin":
        return None, _alert("Admin only.", "danger")
    sid = get_current_society_id()
    if not sid:
        return None, _alert("Society not resolved.", "danger")
    return (sid, get_current_user_id()), None


def _run(fn):
    """Run fn(society_id, user_id) -> (ok, msg); refresh the card body only on success."""
    ctx, err = _ctx()
    if err:
        return err, no_update
    sid, uid = ctx
    try:
        ok, msg = fn(sid, uid)
    except Exception as exc:                                    # surface DB rule violations to the admin, never a blank page
        return _alert(f"Could not save: {exc}", "danger"), no_update
    body = render_up_compliance_body(act.load_card_data(sid)) if ok else no_update
    return _alert(msg, "success" if ok else "danger"), body


def register_up_compliance_callbacks(app):

    @app.callback(_TOAST, _BODY, Input("upc-fil-save", "n_clicks"),
                  State("upc-fil-fy", "value"), State("upc-fil-pub", "date"), State("upc-fil-auth", "date"),
                  State("upc-fil-sum", "date"), State("upc-fil-auditor", "value"), State("upc-fil-attach", "value"),
                  prevent_initial_call=True)
    def save_filing(n, fy, pub, auth, summ, auditor, attach):
        if not n:
            raise PreventUpdate
        attach = attach or []
        return _run(lambda sid, uid: act.save_filing(sid, uid, fy, pub, auth, summ, auditor, "owners" in attach, "loanees" in attach))

    @app.callback(Output("upc-export-dl", "data"), Input("upc-export-btn", "n_clicks"), prevent_initial_call=True)
    def export_annexures(n):
        if not n:
            raise PreventUpdate
        ctx, err = _ctx()
        if err:
            raise PreventUpdate
        return dcc.send_bytes(act.annexure_workbook_bytes(ctx[0]), "UP_AOA_Annexures_Owners_and_Loanees.xlsx")

    @app.callback(_TOAST, _BODY, Input("upc-ui-fill", "n_clicks"), prevent_initial_call=True)
    def fill_ui(n):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.fill_undivided_interest(sid))

    @app.callback(_TOAST, _BODY, Input("upc-basis-save", "n_clicks"),
                  State("upc-basis", "value"), State("upc-budget", "value"), prevent_initial_call=True)
    def save_basis(n, basis, budget):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.set_billing_basis(sid, basis, budget))

    @app.callback(_TOAST, _BODY, Input("upc-tr-save", "n_clicks"),
                  State("upc-tr-flat", "value"), State("upc-tr-date", "date"), State("upc-tr-value", "value"),
                  State("upc-tr-from", "value"), State("upc-tr-to", "value"), prevent_initial_call=True)
    def save_transfer(n, flat, d, value, seller, buyer):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.record_transfer(sid, uid, flat, d, value, seller, buyer))

    @app.callback(_TOAST, _BODY, Input("upc-nd-save", "n_clicks"),
                  State("upc-nd-transfer", "value"), State("upc-nd-action", "value"), State("upc-nd-date", "date"),
                  prevent_initial_call=True)
    def save_nodues(n, transfer, action, d):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.set_nodues(sid, transfer, action, d))

    @app.callback(Output("upc-b7-result", "children"), Input("upc-b7-run", "n_clicks"),
                  State("upc-b7-date", "date"), State("upc-b7-basis", "value"), prevent_initial_call=True)
    def run_bye_law7(n, d, basis):
        if not n:
            raise PreventUpdate
        ctx, err = _ctx()
        if err:
            return err
        rows, problem = act.bye_law7(ctx[0], d, basis)
        if problem:
            return _alert(problem, "warning")
        blocked = [r for r in rows if not r["eligible"]]
        cutoff = rows[0]["cutoff_date"].strftime("%d %b %Y") if rows else "-"
        head = html.Div(f"Arrears are counted as at {cutoff}. {len(blocked)} of {len(rows)} flats cannot vote or stand.",
                        style={"fontSize": "12px", "fontWeight": "700", "marginBottom": "6px"})
        if not blocked:
            return html.Div([head, html.Div("Every owner is eligible.", style={"fontSize": "12px", "color": "#17976e"})])
        return html.Div([head, dbc.Table([html.Thead(html.Tr([html.Th(h) for h in ("Flat", "Owner", "Overdue (\u20b9)", "Oldest due", "Days overdue")])),
                                          html.Tbody([html.Tr([html.Td(r["flat_number"]), html.Td(r["owner_name"]), html.Td(f"{float(r['overdue_amount']):,.2f}"),
                                                               html.Td(r["oldest_due_date"].strftime("%d %b %Y") if r["oldest_due_date"] else "-"),
                                                               html.Td(r["days_overdue"])]) for r in blocked])],
                                         size="sm", style={"fontSize": "12px"})])

    @app.callback(_TOAST, _BODY, Input("upc-s22-start", "n_clicks"),
                  State("upc-s22-flat", "value"), State("upc-s22-service", "value"), State("upc-s22-since", "date"),
                  State("upc-s22-notes", "value"), prevent_initial_call=True)
    def start_s22(n, flat, service, since, notes):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.start_cutoff(sid, uid, flat, service, since, notes))

    @app.callback(_TOAST, _BODY, Input("upc-s22-record", "n_clicks"),
                  State("upc-s22-proc", "value"), State("upc-s22-step", "value"), State("upc-s22-date", "date"),
                  prevent_initial_call=True)
    def record_s22(n, proc, step, d):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.set_cutoff_step(sid, proc, step, d))

    @app.callback(_TOAST, _BODY, Input("upc-ln-save", "n_clicks"),
                  State("upc-ln-flat", "value"), State("upc-ln-date", "date"), State("upc-ln-principal", "value"),
                  State("upc-ln-rate", "value"), State("upc-ln-mode", "value"), State("upc-ln-purpose", "value"),
                  State("upc-ln-ref", "value"), State("upc-ln-due", "date"), prevent_initial_call=True)
    def save_loan(n, flat, d, principal, rate, mode, purpose, ref, due):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.disburse_loan(sid, uid, flat, d, principal, rate, mode, purpose, ref, due))

    @app.callback(_TOAST, _BODY, Input("upc-ld-save", "n_clicks"),
                  State("upc-ld-loan", "value"), State("upc-ld-date", "date"), prevent_initial_call=True)
    def save_loan_due(n, loan, due):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.set_loan_due_date(sid, loan, due))

    @app.callback(_TOAST, _BODY, Input("upc-rp-save", "n_clicks"),
                  State("upc-rp-loan", "value"), State("upc-rp-date", "date"), State("upc-rp-principal", "value"),
                  State("upc-rp-interest", "value"), State("upc-rp-mode", "value"), prevent_initial_call=True)
    def save_repayment(n, loan, d, principal, interest, mode):
        if not n:
            raise PreventUpdate
        return _run(lambda sid, uid: act.repay_loan(sid, uid, loan, d, principal, interest, mode))
