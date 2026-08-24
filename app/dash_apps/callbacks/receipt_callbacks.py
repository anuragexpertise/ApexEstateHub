# app/dash_apps/callbacks/receipt_callbacks.py
"""
Receipt Print / Save-as-PDF / Email — clientside callbacks.

Same pattern as noc_callbacks.py, with one difference: NOC content is
free-text (a textarea the admin can edit before issuing), but a receipt is
a record of money already collected — it shouldn't be editable here. So
instead of reading a textarea's live DOM value, these read a hidden
dcc.Store (id="receipt-print-data", written by renderers.render_receipt_card)
holding the receipt's fields as JSON, and build the printable HTML from
that structured data.

receipts.last_printed_at / last_emailed_at already existed in estatehub.sql
(added for exactly this purpose, per the column comments) but were never
actually set anywhere — a second server-side callback here updates them
when Print/Email are used, alongside the clientside print/email action.

Branding (2026-08): Print/PDF now go through the shared letterhead
(print_letterhead.py) — society logo, watermark background, secretary
signature, and a verification QR (RPT role) are all resolved server-side
in render_receipt_card and shipped as part of receipt-print-data, so the
JS here only has to hand them to buildLetterheadDoc(). Email stays plain
text (mail clients strip most inline styling/images anyway, and a mailto:
link can't attach an image).

Required addition to app_shell.py / the permanent layout:
    dcc.Store(id='receipt-action-store', storage_type='memory'),
(same "dummy Output anchor" trick as noc-action-store, since this card is
rendered dynamically inside drill-content, not the permanent shell layout.)
"""
from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS


def _read_store_js(var_name: str) -> str:
    """Shared snippet: read the receipt-print-data dcc.Store's JSON payload
    out of the DOM (dcc.Store renders its value into the element's
    textContent, same trick used by noc-flat-store in noc_callbacks.py)."""
    return f"""
    var {var_name}Raw = document.getElementById('receipt-print-data');
    var {var_name} = null;
    if ({var_name}Raw) {{
        try {{ {var_name} = JSON.parse({var_name}Raw.textContent || {var_name}Raw.innerText || 'null'); }}
        catch(e) {{ {var_name} = null; }}
    }}
    if (!{var_name}) return window.dash_clientside.no_update;
    """


def _receipt_html_js() -> str:
    """Body-only table (society name/address/logo now come from the shared
    letterhead header — see print_letterhead.py — so this no longer repeats
    them itself)."""
    return """
    function receiptHtml(d) {
        return (
            '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
            row('Date', d.date) +
            row('Received From', d.payer + ' (' + d.role + ')') +
            row('Particulars', d.particulars) +
            row('Account', d.account) +
            row('Amount', '\\u20B9' + d.amount) +
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


_RECEIPT_PRINT_JS = LETTERHEAD_JS + _receipt_html_js() + r"""
function printReceipt(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;
""" + _read_store_js("d") + r"""
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'Receipt #' + d.receipt_no,
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Receipt #' + d.receipt_no + '</h3>' + receiptHtml(d),
        printWidth: '600px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);
    return window.dash_clientside.no_update;
}
"""

_RECEIPT_PDF_JS = LETTERHEAD_JS + _receipt_html_js() + r"""
function downloadReceiptHtml(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;
""" + _read_store_js("d") + r"""
    var html = buildLetterheadDoc({
        title: 'Receipt #' + d.receipt_no,
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Receipt #' + d.receipt_no + '</h3>' + receiptHtml(d),
        printWidth: '600px',
    });
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url  = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href     = url;
    a.download = 'Receipt_' + d.receipt_no + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return window.dash_clientside.no_update;
}
"""

_RECEIPT_EMAIL_JS = r"""
function emailReceipt(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;
""" + _read_store_js("d") + r"""
    var body = (
        'Receipt #' + d.receipt_no + '\n' +
        d.society_name + '\n\n' +
        'Date: ' + d.date + '\n' +
        'Received From: ' + d.payer + ' (' + d.role + ')\n' +
        'Particulars: ' + d.particulars + '\n' +
        'Account: ' + d.account + '\n' +
        'Amount: Rs. ' + d.amount + '\n' +
        'Mode: ' + d.mode + (d.ref ? (' - Ref: ' + d.ref) : '') + '\n' +
        'Status: ' + d.status
    );
    window.location.href = (
        'mailto:?subject=' + encodeURIComponent('Receipt #' + d.receipt_no) +
        '&body=' + encodeURIComponent(body)
    );
    return window.dash_clientside.no_update;
}
"""


def register_receipt_callbacks(app):
    """
    Register three clientside callbacks for the receipt card buttons, plus
    server-side timestamp tracking for last_printed_at/last_emailed_at
    (columns already existed in estatehub.sql for this purpose, never wired
    up until now).

    Output target for the clientside callbacks: 'receipt-action-store' (a
    dcc.Store in the permanent shell layout - same dummy-anchor pattern as
    noc-action-store). IMPORTANT: add
        dcc.Store(id='receipt-action-store', storage_type='memory')
    to app_shell.py alongside the other permanent stores.
    """

    clientside_callback(
        _RECEIPT_PRINT_JS,
        Output('receipt-action-store-print', 'data', allow_duplicate=True),
        Input('receipt-btn-print', 'n_clicks'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _RECEIPT_PDF_JS,
        Output('receipt-action-store-pdf', 'data', allow_duplicate=True),
        Input('receipt-btn-pdf', 'n_clicks'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _RECEIPT_EMAIL_JS,
        Output('receipt-action-store-email', 'data', allow_duplicate=True),
        Input('receipt-btn-email', 'n_clicks'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('receipt-action-store', 'data', allow_duplicate=True),
        Input('receipt-btn-print', 'n_clicks'),
        State('receipt-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_printed(n_clicks, print_data):
        receipt_id = (print_data or {}).get("receipt_no")
        if not n_clicks or not receipt_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE receipts SET last_printed_at = NOW() WHERE id = %s",
                (int(receipt_id),),
            )
        except Exception as e:
            print(f"receipt last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('receipt-action-store', 'data', allow_duplicate=True),
        Input('receipt-btn-email', 'n_clicks'),
        State('receipt-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_emailed(n_clicks, print_data):
        receipt_id = (print_data or {}).get("receipt_no")
        if not n_clicks or not receipt_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE receipts SET last_emailed_at = NOW() WHERE id = %s",
                (int(receipt_id),),
            )
        except Exception as e:
            print(f"receipt last_emailed_at stamp error: {e}")
        return no_update

    print("  OK Receipt callbacks registered (Print / PDF / Email)")
