# app/dash_apps/callbacks/vendor_pass_callbacks.py
"""
Vendor Pass Print / Save-as-PDF / Email — clientside callbacks.

Mirrors receipt_callbacks.py / noc_callbacks.py / event_ticket_callbacks.py,
but for the vendor pass document rendered in the vendor profile by
renderers.py's vendor_pass_section. The pass document uses the shared
letterhead (print_letterhead.py) so logo/watermark/signature/QR all appear.

BUGFIX (2026-08): the vendor-pass-print-data dcc.Store is passed as a proper
State(...) argument so the JS function receives the data directly, rather
than trying to read it out of the DOM.

Required addition to app_shell.py / the permanent layout:
    dcc.Store(id='vendor-pass-action-store', storage_type='memory'),
    dcc.Store(id='vendor-pass-action-store-print', storage_type='memory'),
    dcc.Store(id='vendor-pass-action-store-pdf', storage_type='memory'),
    dcc.Store(id='vendor-pass-action-store-email', storage_type='memory'),
"""
from dash import Output, Input, State, clientside_callback
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS, clientside_iife


def _vendor_pass_html_js() -> str:
    return """
    function vendorPassHtml(d) {
        return (
            '<h3 style="text-align:center;margin:10px 0 6px">' + (d.vendor_name || 'Vendor Pass') + '</h3>' +
            '<div style="text-align:center;font-size:11px;color:#999;margin-bottom:18px">' +
            'Service: ' + (d.service_type || '—') + '</div>' +
            '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
            row('Pass Type', d.pass_type) +
            row('Issued Date', d.issued_date) +
            row('Valid Until', d.valid_until) +
            row('Status', 'ACTIVE') +
            '</table>'
        );
        function row(label, val) {
            return (
                '<tr><td style="padding:6px 0;color:#777;width:35%">' + label + '</td>' +
                '<td style="padding:6px 0;font-weight:600">' + (val || '—') + '</td></tr>'
            );
        }
    }
    """


_VENDOR_PASS_PRINT_JS = clientside_iife(
    LETTERHEAD_JS + _vendor_pass_html_js() + r"""
function printVendorPass(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'Vendor Pass — ' + (d.vendor_name || ''),
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Vendor Pass</h3>' + vendorPassHtml(d),
        printWidth: '600px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);
    return window.dash_clientside.no_update;
}
""",
    "printVendorPass",
)

_VENDOR_PASS_PDF_JS = clientside_iife(
    LETTERHEAD_JS + _vendor_pass_html_js() + r"""
function downloadVendorPassPdf(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var html = buildLetterheadPdfDoc({
        title: 'Vendor Pass — ' + (d.vendor_name || ''),
        filename: 'VendorPass_' + (d.vendor_name || 'vendor'),
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: '<h3 style="text-align:center;margin:10px 0 20px">Vendor Pass</h3>' + vendorPassHtml(d),
        printWidth: '600px',
    });
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    w.document.write(html);
    w.document.close();
    return window.dash_clientside.no_update;
}
""",
    "downloadVendorPassPdf",
)

_VENDOR_PASS_EMAIL_JS = clientside_iife(r"""
function emailVendorPass(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var body = (
        'Vendor Pass — ' + (d.vendor_name || '') + '\n' +
        (d.service_type || '') + '\n\n' +
        'Pass Type: ' + (d.pass_type || '') + '\n' +
        'Issued Date: ' + (d.issued_date || '') + '\n' +
        'Valid Until: ' + (d.valid_until || '') + '\n' +
        'Status: ACTIVE\n' +
        'Verification code: ' + d.qr_payload
    );
    window.location.href = (
        'mailto:?subject=' + encodeURIComponent('Vendor Pass — ' + (d.vendor_name || '')) +
        '&body=' + encodeURIComponent(body)
    );
    return window.dash_clientside.no_update;
}
""",
    "emailVendorPass",
)


def register_vendor_pass_callbacks(app):
    clientside_callback(
        _VENDOR_PASS_PRINT_JS,
        Output('vendor-pass-action-store-print', 'data', allow_duplicate=True),
        Input('vendor-pass-btn-print', 'n_clicks'),
        State('vendor-pass-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _VENDOR_PASS_PDF_JS,
        Output('vendor-pass-action-store-pdf', 'data', allow_duplicate=True),
        Input('vendor-pass-btn-pdf', 'n_clicks'),
        State('vendor-pass-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _VENDOR_PASS_EMAIL_JS,
        Output('vendor-pass-action-store-email', 'data', allow_duplicate=True),
        Input('vendor-pass-btn-email', 'n_clicks'),
        State('vendor-pass-print-data', 'data'),
        prevent_initial_call=True,
    )

    print("  OK Vendor pass callbacks registered (Print / PDF / Email)")
