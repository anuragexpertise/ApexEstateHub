# app/dash_apps/callbacks/fund_management_callbacks.py
"""
Fund Management Callbacks — Admin-only Capital/Reserve/Sinking/Repair/Corpus
fund utilization. Mirrors expense_callbacks.py pattern.
"""
from dash import Output, Input, State, callback, no_update, ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from app.dash_apps.drilldown import loaders
from database.db_manager import db
from app.security.audit_context import get_current_user_role, get_current_user_id, get_current_society_id


# Fund accounts are resolved dynamically by name (see loaders.get_fund_balances'
# docstring) rather than by a hardcoded account-id list, since a different
# jurisdiction/legal regime can number the chart of accounts differently.
# This mirrors that by matching on the account NAME (ILIKE-style substring,
# checked in Python since the row is already fetched) instead of an id-keyed
# dict, so a fund keeps its correct approval/purpose labeling however its id
# is numbered for a given society.
FUND_TYPE_PATTERNS = [
    ("capital account", {"label": "Capital Account", "approval": "General Body", "purpose": "Capital expenditure, loan repayment", "icon": "fas fa-building"}),
    ("sinking",         {"label": "Sinking Fund", "approval": "General Body", "purpose": "Major structural repairs, lift/DG replacement, redevelopment", "icon": "fas fa-piggy-bank"}),
    ("repair",          {"label": "Repair & Maintenance Fund", "approval": "Managing Committee", "purpose": "Routine common area maintenance", "icon": "fas fa-tools"}),
    ("corpus",          {"label": "Corpus Fund", "approval": "General Body", "purpose": "ONLY INTEREST usable; principal inviolable (RERA)", "icon": "fas fa-vault"}),
    ("reserve",         {"label": "Reserve Fund", "approval": "General Body", "purpose": "Unforeseen expenses, structural repairs", "icon": "fas fa-shield-alt"}),
]


def resolve_fund_type_info(name: str) -> dict:
    """Match a fund's real account name (ILIKE-style substring) to its
    approval/purpose metadata. Falls back to the account's own name when no
    pattern matches, so an unrecognized fund (e.g. "Gifts Received") still
    displays sensibly instead of "Unknown Fund"."""
    n = (name or "").lower()
    for pattern, info in FUND_TYPE_PATTERNS:
        if pattern in n:
            return info
    return {"label": name or "Unknown Fund", "approval": "—", "purpose": "—", "icon": "fas fa-question"}


def register_fund_management_callbacks(app):
    """Register fund management callbacks."""

    @app.callback(
        Output("fund-mgmt-fund-select", "options"),
        Output("fund-mgmt-expense-select", "options"),
        Output("fund-mgmt-balances-table", "children", allow_duplicate=True),
        Output("fund-mgmt-log-table", "children", allow_duplicate=True),
        Output("fund-mgmt-toast", "children", allow_duplicate=True),
        Input("fund-mgmt-refresh-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def refresh_fund_management_data(refresh_clicks):
        """Reload fund balances and utilization log when refresh button is clicked."""
        if not refresh_clicks:
            raise PreventUpdate

        role = get_current_user_role()
        if role != "admin":
            return no_update, no_update, no_update, no_update, dbc.Alert("Admin only.", color="danger", style={"borderRadius": "8px"})

        # Resolved from the authenticated Flask-Login session, never a
        # hardcoded tenant id — this was previously `sid = 1`, which meant
        # Reload Data/Submit always operated on society 1's accounts
        # regardless of which society the logged-in admin actually belongs
        # to (the initial render got this right via the drilldown filters,
        # so the bug only showed up after the first refresh/submit click).
        sid = get_current_society_id()
        if not sid:
            return no_update, no_update, no_update, no_update, dbc.Alert("Society not resolved.", color="danger", style={"borderRadius": "8px"})

        try:
            # Get fund balances
            fund_balances = loaders.get_fund_balances(sid)

            # Get fund options for dropdown — label comes straight from the
            # account's real name (already fetched dynamically by name, see
            # loaders.get_fund_balances), no id-keyed lookup table needed.
            fund_options = []
            for fb in fund_balances:
                acc_id = fb.get("acc_id")
                balance = float(fb.get("balance") or 0)
                if balance > 0:
                    fund_options.append({
                        "label": f"{fb.get('name')} (₹{balance:,.2f})",
                        "value": str(acc_id)
                    })

            # Get expense/bank accounts (Dr accounts that can receive the credit)
            expense_accounts = loaders.get_expense_bank_accounts(sid)
            expense_options = [{"label": f"{a.get('name')} ({a.get('account_code')})", "value": str(a.get('id'))} for a in expense_accounts]

            # Build balances table
            balances_table = build_balances_table(fund_balances)

            # Get utilization log
            utilization_log = loaders.get_fund_utilization_log(sid, limit=20)
            log_table = build_log_table(utilization_log)

            return fund_options, expense_options, balances_table, log_table, no_update

        except Exception as e:
            return no_update, no_update, no_update, no_update, dbc.Alert(f"Error loading data: {e}", color="danger", style={"borderRadius": "8px"})

    @app.callback(
        Output("fund-mgmt-toast", "children", allow_duplicate=True),
        Output("fund-mgmt-fund-select", "value"),
        Output("fund-mgmt-expense-select", "value"),
        Output("fund-mgmt-amount-input", "value"),
        Output("fund-mgmt-cheque-input", "value"),
        Output("fund-mgmt-trx-input", "value"),
        Output("fund-mgmt-approval-ref", "value"),
        Output("fund-mgmt-approval-date", "date"),
        Output("fund-mgmt-particulars", "value"),
        Output("fund-mgmt-balances-table", "children", allow_duplicate=True),
        Output("fund-mgmt-log-table", "children", allow_duplicate=True),
        Input("fund-mgmt-btn-submit", "n_clicks"),
        State("fund-mgmt-fund-select", "value"),
        State("fund-mgmt-expense-select", "value"),
        State("fund-mgmt-amount-input", "value"),
        State("fund-mgmt-mode-select", "value"),
        State("fund-mgmt-cheque-input", "value"),
        State("fund-mgmt-trx-input", "value"),
        State("fund-mgmt-approval-ref", "value"),
        State("fund-mgmt-approval-date", "date"),
        State("fund-mgmt-particulars", "value"),
        prevent_initial_call=True,
    )
    def submit_fund_utilization(n_clicks, fund_acc_id, expense_acc_id, amount, mode, cheque_no, trx_id, approval_ref, approval_date, particulars):
        """Submit fund utilization request."""
        if not n_clicks:
            raise PreventUpdate

        role = get_current_user_role()
        if role != "admin":
            return dbc.Alert("Admin only.", color="danger", style={"borderRadius": "8px"}), no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        user_id = get_current_user_id()
        sid = get_current_society_id()  # never hardcode — see refresh callback's comment above
        if not sid:
            return dbc.Alert("Society not resolved.", color="danger", style={"borderRadius": "8px"}), no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        if not fund_acc_id or not expense_acc_id or not amount or not approval_ref or not approval_date or not particulars:
            return dbc.Alert("All required fields must be filled.", color="warning", style={"borderRadius": "8px"}), no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update

        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be > 0")

            # Call SQL function
            result = db._execute(
                """
                SELECT * FROM fn_process_fund_utilization(
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (sid, int(fund_acc_id), int(expense_acc_id), particulars, amount, mode, user_id, cheque_no, trx_id, approval_ref, approval_date),
                fetch_one=True
            )

            if result and result.get("status") == "confirmed":
                toast = dbc.Alert(f"Fund utilized successfully! Journal ID: {result.get('journal_id')}", color="success", style={"borderRadius": "8px"})
            elif result and result.get("status") == "pending":
                toast = dbc.Alert("Fund utilization request submitted for approval.", color="info", style={"borderRadius": "8px"})
            else:
                toast = dbc.Alert("Unexpected result.", color="warning", style={"borderRadius": "8px"})

            # Reload data — label comes straight from the account's real
            # name (see refresh callback's comment above), no id-keyed map.
            fund_balances = loaders.get_fund_balances(sid)
            fund_options = []
            for fb in fund_balances:
                acc_id = fb.get("acc_id")
                balance = float(fb.get("balance") or 0)
                if balance > 0:
                    fund_options.append({"label": f"{fb.get('name')} (₹{balance:,.2f})", "value": str(acc_id)})

            expense_accounts = loaders.get_expense_bank_accounts(sid)
            expense_options = [{"label": f"{a.get('name')} ({a.get('account_code')})", "value": str(a.get('id'))} for a in expense_accounts]

            balances_table = build_balances_table(fund_balances)
            utilization_log = loaders.get_fund_utilization_log(sid, limit=20)
            log_table = build_log_table(utilization_log)

            return (toast, None, None, None, None, None, None, None, None,
                    balances_table, log_table)

        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger", style={"borderRadius": "8px"}), no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update


def build_balances_table(fund_balances):
    """Build the fund balances table."""
    color = "#15304f"

    balance_rows = []
    for fb in fund_balances:
        info = resolve_fund_type_info(fb.get("name"))
        balance = float(fb.get("balance") or 0)
        balance_rows.append(html.Tr([
            html.Td(html.Div([
                html.I(className=info["icon"], style={"marginRight": "8px", "color": color}),
                html.Strong(info["label"])
            ]), style={"fontSize": "12px", "fontWeight": "600"}),
            html.Td(f"₹{balance:,.2f}", style={"fontSize": "13px", "fontWeight": "700", "color": "#1e7e34" if balance >= 0 else "#c0392b", "textAlign": "right"}),
            html.Td(info["approval"], style={"fontSize": "11px", "color": "#666", "textAlign": "center"}),
            html.Td(info["purpose"], style={"fontSize": "11px", "color": "#888"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Fund", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Available Balance", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "right"}),
            html.Th("Approval Required", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "center"}),
            html.Th("Permitted Purpose (per UP AOA / Bye-Laws)", style={"fontSize": "11px", "background": color, "color": "#fff"}),
        ])),
        html.Tbody(balance_rows),
    ], bordered=False, hover=True, responsive=True, size="sm", style={"marginTop": "4px"})


def build_log_table(utilization_log):
    """Build the utilization log table."""
    color = "#15304f"

    if not utilization_log:
        return dbc.Alert("No fund utilizations yet.", color="secondary", style={"borderRadius": "10px"})

    log_rows = []
    for u in utilization_log:
        status_color = {"confirmed": "#1e7e34", "pending": "#e67e22", "cancelled": "#c0392b"}.get(u.get("status", ""), "#666")
        log_rows.append(html.Tr([
            html.Td(u.get("created_at", "")[:10] if u.get("created_at") else "—", style={"fontSize": "11px"}),
            html.Td(u.get("fund_name") or f"Fund {u.get('fund_acc_id')}", style={"fontSize": "11px", "fontWeight": "600"}),
            html.Td(f"₹{float(u.get('amount') or 0):,.2f}", style={"fontSize": "11px", "textAlign": "right"}),
            html.Td(u.get("particulars", "")[:50], style={"fontSize": "11px", "color": "#555"}),
            html.Td(u.get("approval_ref", "—"), style={"fontSize": "11px", "color": "#666"}),
            html.Td(html.Span(u.get("status", "—").title(), style={"color": status_color, "fontWeight": "600", "fontSize": "11px"}), style={"textAlign": "center"}),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Date", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Fund", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Amount", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "right"}),
            html.Th("Particulars", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Approval Ref", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Status", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "center"}),
        ])),
        html.Tbody(log_rows),
    ], bordered=False, hover=True, responsive=True, size="sm", style={"marginTop": "4px"})


from dash import html