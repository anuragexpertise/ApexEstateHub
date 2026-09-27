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

# A law-protected principal is called out in warm amber rather than the
# green used for a spendable balance, so "nothing here is drawable" is
# legible before the admin types an amount.
_FUND_LOCK = "#b8860b"


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
            fund_options = build_fund_options(fund_balances)

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
            fund_options = build_fund_options(fund_balances)

            expense_accounts = loaders.get_expense_bank_accounts(sid)
            expense_options = [{"label": f"{a.get('name')} ({a.get('account_code')})", "value": str(a.get('id'))} for a in expense_accounts]

            balances_table = build_balances_table(fund_balances)
            utilization_log = loaders.get_fund_utilization_log(sid, limit=20)
            log_table = build_log_table(utilization_log)

            return (toast, None, None, None, None, None, None, None, None,
                    balances_table, log_table)

        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger", style={"borderRadius": "8px"}), no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update, no_update


def fund_drawable_amount(fb: dict) -> float:
    """
    How much of a fund's balance can actually be drawn.

    Single source of truth for the balances table, the fund dropdown and the
    button state, because the two surfaces once disagreed: the table derived
    `balance - locked` while the dropdown fell back to the gross balance, so a
    locked fund with no available_amount key would be advertised as fully
    drawable in the very dropdown used to pick it.

    Mirrors fn_process_fund_utilization:
        locked    = round(balance * lock_pct / 100, 2)
        available = max(balance - locked, 0)
    """
    balance = float(fb.get("balance") or 0)
    supplied = fb.get("available_amount")
    if supplied is not None:
        return float(supplied)
    locked = float(fb.get("locked_amount") or 0)
    if not locked and float(fb.get("statutory_lock_pct") or 0):
        locked = round(balance * float(fb["statutory_lock_pct"]) / 100, 2)
    return max(balance - locked, 0)


def build_fund_options(fund_balances):
    """
    Fund dropdown options, labelled with the amount that can actually be
    drawn rather than the gross balance.

    A fund with no drawable headroom is still listed — dropping it silently
    would leave an admin wondering where the Corpus Fund went — but it is
    marked locked and disabled, so the statutory principal cannot be
    targeted at all.
    """
    options = []
    for fb in fund_balances:
        acc_id = fb.get("acc_id")
        balance = float(fb.get("balance") or 0)
        if balance <= 0:
            continue
        lock_pct = float(fb.get("statutory_lock_pct") or 0)
        available = fund_drawable_amount(fb)
        name = fb.get("name")
        if lock_pct > 0:
            options.append({
                "label": f"🔒 {name} — ₹{available:,.2f} drawable "
                         f"(₹{balance:,.2f} held, {lock_pct:g}% statutory principal)",
                "value": str(acc_id),
                "disabled": available <= 0,
            })
        else:
            options.append({
                "label": f"{name} (₹{available:,.2f})",
                "value": str(acc_id),
                "disabled": available <= 0,
            })
    return options


def build_balances_table(fund_balances):
    """Build the fund balances table."""
    color = "#15304f"

    balance_rows = []
    any_locked = False
    for fb in fund_balances:
        info = resolve_fund_type_info(fb.get("name"))
        balance = float(fb.get("balance") or 0)
        lock_pct = float(fb.get("statutory_lock_pct") or 0)
        locked = float(fb.get("locked_amount") or 0)
        # Headroom, not the gross figure. The column used to be headed
        # "Available Balance" while showing the gross balance, which told an
        # admin the whole Corpus Fund was spendable right up until the
        # database refused the posting.
        available = fund_drawable_amount(fb)
        is_locked = lock_pct > 0
        any_locked = any_locked or is_locked

        if is_locked:
            # Gross balance stays visible (it is real money) but is no longer
            # presented as spendable; the drawable figure leads.
            amount_cell = html.Td([
                html.Div(f"₹{available:,.2f}", style={
                    "fontSize": "13px", "fontWeight": "700",
                    "color": _FUND_LOCK if available <= 0 else "#1e7e34",
                    "textAlign": "right",
                }),
                html.Div(f"of ₹{balance:,.2f} held", style={
                    "fontSize": "9.5px", "color": "#8a8f98", "textAlign": "right",
                    "marginTop": "1px",
                }),
            ])
            lock_cell = html.Td([
                html.Div([html.I(className="fas fa-lock me-1"), f"{lock_pct:g}%"],
                         style={"fontSize": "11px", "fontWeight": "700",
                                "color": _FUND_LOCK, "whiteSpace": "nowrap"}),
                html.Div(f"₹{locked:,.2f} protected", style={
                    "fontSize": "9.5px", "color": "#8a8f98", "marginTop": "1px",
                }),
            ], style={"textAlign": "center"})
        else:
            amount_cell = html.Td(
                f"₹{balance:,.2f}",
                style={"fontSize": "13px", "fontWeight": "700",
                       "color": "#1e7e34" if balance >= 0 else "#c0392b",
                       "textAlign": "right"})
            lock_cell = html.Td("—", style={"fontSize": "11px", "color": "#bbb",
                                            "textAlign": "center"})

        balance_rows.append(html.Tr([
            html.Td(html.Div([
                html.I(className=info["icon"], style={"marginRight": "8px", "color": color}),
                html.Strong(info["label"])
            ]), style={"fontSize": "12px", "fontWeight": "600"}),
            amount_cell,
            lock_cell,
            html.Td(info["approval"], style={"fontSize": "11px", "color": "#666", "textAlign": "center"}),
            html.Td(info["purpose"], style={"fontSize": "11px", "color": "#888"}),
        ], style={"background": "#fffaf5" if is_locked else None}))

    table = dbc.Table([
        html.Thead(html.Tr([
            html.Th("Fund", style={"fontSize": "11px", "background": color, "color": "#fff"}),
            html.Th("Available to Draw", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "right"}),
            html.Th("Statutory Lock", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "center"}),
            html.Th("Approval Required", style={"fontSize": "11px", "background": color, "color": "#fff", "textAlign": "center"}),
            html.Th("Permitted Purpose (per UP AOA / Bye-Laws)", style={"fontSize": "11px", "background": color, "color": "#fff"}),
        ])),
        html.Tbody(balance_rows),
    ], bordered=False, hover=True, responsive=True, size="sm", style={"marginTop": "4px"})

    if not any_locked:
        return table

    # Say out loud what the lock means, because "0.00 available" next to a
    # six-figure balance otherwise reads as a bug rather than the law.
    return html.Div([
        table,
        html.Div([
            html.I(className="fas fa-shield-halved me-2",
                   style={"color": _FUND_LOCK, "fontSize": "11px"}),
            html.Span([
                html.Strong("Statutory principal is protected."),
                " The locked share cannot be drawn down under RERA / the Model "
                "Bye-Laws, and the database refuses any request that would breach "
                "it. Interest earned on a locked fund is usable — it is credited "
                "to the Interest Income account rather than drawn from the fund.",
            ], style={"fontSize": "10.5px", "color": "#666"}),
        ], style={"marginTop": "10px", "padding": "9px 12px", "background": "#fffaf5",
                  "borderLeft": f"3px solid {_FUND_LOCK}", "borderRadius": "0 6px 6px 0",
                  "lineHeight": "1.5"}),
    ])


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