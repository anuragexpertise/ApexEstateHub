# app/dash_apps/callbacks/financial_statements_callbacks.py
"""
4 Statements Financial Report Print / Save as PDF / Email — clientside callbacks.

Mirrors receipt_callbacks.py / noc_callbacks.py pattern. The 4 Statements card
(body built from dep/ie/cap/bs tables) ships its letterhead + body HTML in
dcc.Store(id="fin-stmt-letterhead-data") — the JS here only hands it to
buildLetterheadDoc()/buildLetterheadPdfDoc().

Required additions to app_shell.py / the permanent layout:
    dcc.Store(id='fin-stmt-action-store', storage_type='memory'),
    dcc.Store(id='fin-stmt-action-store-print', storage_type='memory'),
    dcc.Store(id='fin-stmt-action-store-pdf', storage_type='memory'),
    dcc.Store(id='fin-stmt-action-store-email', storage_type='memory'),
"""
from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS, clientside_iife


# ──────────────────────────────────────────────────────────────────────────────
# JS: build body HTML from the data stored in fin-stmt-letterhead-data
# The bodyHtml is pre-rendered in Python (render_financial_statements_card)
# and stored as part of the letterhead data object.
# ──────────────────────────────────────────────────────────────────────────────

# ── Print ────────────────────────────────────────────────────────────────────
_FIN_STMT_PRINT_JS = clientside_iife(
    LETTERHEAD_JS + r"""
function printFinStmt(n_clicks, lh, password) {
    if (!n_clicks) return window.dash_clientside.no_update;

    lh = lh || {};
    if (!lh.bodyHtml) return window.dash_clientside.no_update;

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }

    var doc = buildLetterheadDoc({
        title: '4 Statements — FY ' + (lh.fy || ''),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: lh.bodyHtml,
        printWidth: '750px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);

    return window.dash_clientside.no_update;
}
""",
    "printFinStmt",
)

# ── Save as PDF ──────────────────────────────────────────────────────────────
_FIN_STMT_PDF_JS = clientside_iife(
    LETTERHEAD_JS + r"""
function downloadFinStmtPdf(n_clicks, lh, password) {
    if (!n_clicks) return window.dash_clientside.no_update;

    lh = lh || {};
    if (!lh.bodyHtml) return window.dash_clientside.no_update;

    var html = buildLetterheadPdfDoc({
        title: '4 Statements — FY ' + (lh.fy || ''),
        filename: '4Statements_FY' + (lh.fy || ''),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: lh.bodyHtml,
        printWidth: '750px',
        password: password,
    });

    var blob = new Blob([html], {type: 'text/html'});
    var w = window.open(URL.createObjectURL(blob), '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }

    return window.dash_clientside.no_update;
}
""",
    "downloadFinStmtPdf",
)

# ── Email ────────────────────────────────────────────────────────────────────
_FIN_STMT_EMAIL_JS = clientside_iife(r"""
function emailFinStmt(n_clicks, lh) {
    if (!n_clicks) return window.dash_clientside.no_update;

    lh = lh || {};
    var body = (
        '4 Statements Financial Report — FY ' + (lh.fy || '') + '\n' +
        lh.society_name + '\n' +
        (lh.society_address ? lh.society_address + '\n' : '') +
        '\n' +
        'See attached PDF or log in to Apex Estate Hub for the full report.'
    );

    var _a = document.createElement('a');
    _a.href = (
        'mailto:?subject=' + encodeURIComponent('4 Statements — FY ' + (lh.fy || '')) +
        '&body=' + encodeURIComponent(body)
    );
    _a.click();

    return window.dash_clientside.no_update;
}
""",
    "emailFinStmt",
)


def register_financial_statements_callbacks(app):
    """
    Register three clientside callbacks for the 4 Statements card buttons.
    Output targets are dummy dcc.Store anchors in the permanent shell layout.
    """

    clientside_callback(
        _FIN_STMT_PRINT_JS,
        Output('fin-stmt-action-store-print', 'data', allow_duplicate=True),
        Input('fin-stmt-btn-print', 'n_clicks'),
        State('fin-stmt-letterhead-data', 'data'),
        State('fin-stmt-password', 'value'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _FIN_STMT_PDF_JS,
        Output('fin-stmt-action-store-pdf', 'data', allow_duplicate=True),
        Input('fin-stmt-btn-pdf', 'n_clicks'),
        State('fin-stmt-letterhead-data', 'data'),
        State('fin-stmt-password', 'value'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _FIN_STMT_EMAIL_JS,
        Output('fin-stmt-action-store-email', 'data', allow_duplicate=True),
        Input('fin-stmt-btn-email', 'n_clicks'),
        State('fin-stmt-letterhead-data', 'data'),
        prevent_initial_call=True,
    )

    print("  OK Financial Statements callbacks registered (Print / PDF / Email)")