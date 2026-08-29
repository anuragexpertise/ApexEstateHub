# app/dash_apps/callbacks/expense_callbacks.py
"""
Expense Print / Save as PDF / Email — clientside callbacks.

Mirrors receipt_callbacks.py but for the expenses table. Uses the shared
letterhead (print_letterhead.py) for Print/PDF, and plain-text mailto for
Email (same rationale as receipts: mail clients strip inline styling).

expenses.last_printed_at / last_emailed_at already existed in estatehub.sql
(added for exactly this purpose, per the column comments) but were never
actually set anywhere — a server-side callback here updates them when
Print/Email are used, alongside the clientside print/email action.

Required addition to app_shell.py / the permanent layout:
    dcc.Store(id='expense-action-store', storage_type='memory'),
(same "dummy Output anchor" trick as receipt-action-store, since this card is
rendered dynamically inside drill-content, not the permanent shell layout.)
"""
from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS, clientside_iife


def _expense_html_js() -> str:
    """Body-only table (society name/address/logo now come from the shared
    letterhead header — see print_letterhead.py — so this no longer repeats
    them itself)."""
    return """
    function expenseHtml(d) {
        return (
            '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
            row('Date', d.date) +
            row('Paid To', d.payee + ' (' + d.role + ')') +
            row('Particulars', d.particulars) +
            row('Account', d.account) +
            row('Amount', '\\u20B9' + d.amount) +
            row('TDS %', d.tds_pct + '%') +
            row('Mode', d.mode + (d.ref ? (' \\u2014 Ref: ' + d.ref) : '')) +
            row('Status', d.status) +
            '</table>'
        );
        function row(label, val) {
            return (
                '<tr><td style="padding:6px 0;color:#777;width:35%">' + label + '</td>' +
                '<td style="padding:6px 0;font-weight:600">' + val + '</td></tr>'
            );
        }
    }
    """


_EXPENSE_PRINT_JS = clientside_iife(
    LETTERHEAD_JS + _expense_html_js() + r"""
function printExpense(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'Expense #' + d.expense_no,
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Expense #' + d.expense_no + '</h3>' +
                  (d.is_provisional ? '<div style="text-align:center;color:#dc3545;font-weight:bold;margin-bottom:15px;">Provisional - Subject to verification</div>' : '') +
                  expenseHtml(d),
        printWidth: '600px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);
    return window.dash_clientside.no_update;
}
""",
    "printExpense",
)

_EXPENSE_PDF_JS = clientside_iife(
    LETTERHEAD_JS + _expense_html_js() + r"""
function downloadExpensePdf(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var html = buildLetterheadPdfDoc({
        title: 'Expense #' + d.expense_no,
        filename: 'Expense_' + d.expense_no,
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Expense #' + d.expense_no + '</h3>' +
                  (d.is_provisional ? '<div style="text-align:center;color:#dc3545;font-weight:bold;margin-bottom:15px;">Provisional - Subject to verification</div>' : '') +
                  expenseHtml(d),
        printWidth: '600px',
    });
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    w.document.write(html);
    w.document.close();
    return window.dash_clientside.no_update;
}
""",
    "downloadExpensePdf",
)

_EXPENSE_EMAIL_JS = clientside_iife(r"""
function emailExpense(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var body = (
        'Expense #' + d.expense_no + '\n' +
        d.society_name + '\n\n' +
        'Date: ' + d.date + '\n' +
        'Paid To: ' + d.payee + ' (' + d.role + ')\n' +
        'Particulars: ' + d.particulars + '\n' +
        'Account: ' + d.account + '\n' +
        'Amount: Rs. ' + d.amount + '\n' +
        'TDS %: ' + d.tds_pct + '%\n' +
        'Mode: ' + d.mode + (d.ref ? (' - Ref: ' + d.ref) : '') + '\n' +
        'Status: ' + d.status + (d.is_provisional ? ' (Provisional - Subject to verification)' : '')
    );
    window.location.href = (
        'mailto:?subject=' + encodeURIComponent('Expense #' + d.expense_no) +
        '&body=' + encodeURIComponent(body)
    );
    return window.dash_clientside.no_update;
}
""",
    "emailExpense",
)


def register_expense_callbacks(app):
    """
    Register three clientside callbacks for the expense card buttons, plus
    server-side timestamp tracking for last_printed_at/last_emailed_at
    (columns already existed in estatehub.sql for this purpose, never wired
    up until now).

    Output target for the clientside callbacks: 'expense-action-store' (a
    dcc.Store in the permanent shell layout - same dummy-anchor pattern as
    receipt-action-store). IMPORTANT: add
        dcc.Store(id='expense-action-store', storage_type='memory')
    to app_shell.py alongside the other permanent stores.
    """

    clientside_callback(
        _EXPENSE_PRINT_JS,
        Output('expense-action-store-print', 'data', allow_duplicate=True),
        Input('expense-btn-print', 'n_clicks'),
        State('expense-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _EXPENSE_PDF_JS,
        Output('expense-action-store-pdf', 'data', allow_duplicate=True),
        Input('expense-btn-pdf', 'n_clicks'),
        State('expense-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _EXPENSE_EMAIL_JS,
        Output('expense-action-store-email', 'data', allow_duplicate=True),
        Input('expense-btn-email', 'n_clicks'),
        State('expense-print-data', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('expense-action-store', 'data', allow_duplicate=True),
        Input('expense-btn-print', 'n_clicks'),
        State('expense-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_printed(n_clicks, print_data):
        expense_no = (print_data or {}).get("expense_no")
        if not n_clicks or not expense_no:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE expenses SET last_printed_at = NOW() WHERE id = %s",
                (int(expense_no),),
            )
        except Exception as e:
            print(f"expense last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('expense-action-store', 'data', allow_duplicate=True),
        Input('expense-btn-email', 'n_clicks'),
        State('expense-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_emailed(n_clicks, print_data):
        expense_no = (print_data or {}).get("expense_no")
        if not n_clicks or not expense_no:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE expenses SET last_emailed_at = NOW() WHERE id = %s",
                (int(expense_no),),
            )
        except Exception as e:
            print(f"expense last_emailed_at stamp error: {e}")
        return no_update

    print("  OK Expense callbacks registered (Print / PDF / Email)")
